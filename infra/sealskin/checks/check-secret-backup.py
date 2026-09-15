#!/usr/bin/env python3
"""Restore one encrypted QA backup into a fresh controller, Home and secret runtime.

The original QA controller is stopped only after the browser and all owned
resources have stopped. Production and source Homes are never modified.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

import yaml

spec = importlib.util.spec_from_file_location("secret_checks", Path(__file__).with_name("check-secret-store.py"))
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
network = checks.network
PROJECT = Path(__file__).resolve().parents[3]


def command(args, log, expected=0):
    result = subprocess.run([str(v) for v in args], capture_output=True, text=True, timeout=360)
    log.write_text(result.stdout + result.stderr)
    log.chmod(0o600)
    assert result.returncode == expected, "QA backup command failed; inspect private evidence"
    return json.loads(result.stdout)


def start_process(args, root, kind):
    with (root / (kind + ".log")).open("ab") as log:
        process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    network.write_json(root / (kind + "-pid.json"), {"pid": process.pid})
    return process


def stop_adapter(qa):
    info = qa / "adapter-pid.json"
    if not info.exists():
        return
    pid = json.loads(info.read_text())["pid"]
    assert Path(os.readlink(f"/proc/{pid}/exe")).resolve() == (qa / "bin/profile-adapter").resolve()
    os.kill(pid, signal.SIGTERM)
    network.wait(lambda: not Path(f"/proc/{pid}").exists() or ") Z " in Path(f"/proc/{pid}/stat").read_text(), "QA Adapter exit")
    info.rename(qa / "adapter-stopped.json")


def stop_proxy(qa):
    record = qa / "proxy-pid.json"
    pid = json.loads(record.read_text())["pid"]
    value = Path(f"/proc/{pid}/cmdline").read_bytes()
    assert b"qa-network-docker-proxy.py" in value and str(qa).encode() in value and os.getpgid(pid) == pid
    os.killpg(pid, signal.SIGTERM)
    time.sleep(.3)
    socket = Path("/tmp/browser-platform-network-qa-docker.sock")
    assert socket.is_socket() and socket.stat().st_uid == os.getuid()
    socket.unlink()
    record.rename(qa / "proxy-stopped.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    qa, output = args.root.resolve(), args.output.resolve()
    stop_adapter(qa)
    runner = checks.SecretChecks(qa, output)
    try:
        policy, generation = runner.launch("https", 7)
        runner.materials(generation, 7)
        original_worker = runner.info["instance_id"]
        marker = uuid.uuid4().hex
        expected = {"href": "https://entry.leak.qa.test/test", "cookie": marker, "localStorage": marker, "indexedDB": marker}
        assert runner.control.evaluate("(" + checks.STORAGE + ")(true," + json.dumps(marker) + ")") == expected
        runner.stop()
        runner.put(5)
        network.write_json(output / "expected-storage.json", expected)
        config = json.loads((qa / "adapter-config.json").read_text())
        config["profiles"] = [p for p in config["profiles"] if p["id"] != runner.info["profile"]]
        config["profiles"].append({"id": runner.info["profile"], "application_id": runner.app["id"], "home_name": runner.info["home"],
            "start_url": runner.request["url"], "language": "zh_TW.UTF-8", "timezone": "Asia/Taipei",
            "wayland_mode": False, "network_policy_id": runner.request["network_policy_id"],
            "network_policy_sha256": runner.request["network_policy_sha256"]})
        network.write_json(qa / "adapter-config.json", config)
        runner.checks.start_adapter()
        status, _, _ = network.request("POST", "/browser/" + runner.info["profile"] + "/start", "",
            {"Origin": "https://network.invalid", "Host": "network.invalid", "Content-Type": "application/x-www-form-urlencoded"}, port=29110)
        assert status == 303, "QA Adapter did not create its source binding"
        connection = network.UnixConnection("adapter", timeout=90)
        try:
            connection.request("POST", "/profiles/" + runner.info["profile"] + "/stop")
            response = connection.getresponse()
            stopped = json.loads(response.read())
            assert response.status == 200 and stopped["result"]["status"] == "stopped"
        finally:
            connection.close()
        assert (qa / "adapter-state.json").is_file()
        network.write_json(output / "source-adapter-cycle.json", {"result": "PASS", "startStatus": status,
                           "stopped": stopped, "journalSHA256": hashlib.sha256((qa / "adapter-state.json").read_bytes()).hexdigest()})
        age = qa.parent / "tools/age"
        identity = output / "recovery-identity.txt"
        subprocess.run([str(age.with_name("age-keygen")), "-o", str(identity)], capture_output=True, check=True)
        recipient = subprocess.check_output([str(age.with_name("age-keygen")), "-y", str(identity)], text=True).strip()
        backup = PROJECT / "infra/sealskin/lifecycle/secure-backup.py"
        artifact = PROJECT / "infra/camoufox/artifacts/env-tw-camoufox-r6.json"
        acceptance = PROJECT / "infra/camoufox/evidence/acceptance-r6-2026-09-14.json"
        archive = output / "qa-profile.age"
        create = [sys.executable, backup, "create", "--age", age, "--config", qa / "adapter-config.json", "--profile", runner.info["profile"],
            "--storage", qa / "storage", "--sealskin-config", qa / "config/.config/sealskin", "--artifact", artifact,
            "--acceptance", acceptance, "--master-key-file", runner.key, "--recipient", recipient, "--output", archive]
        created = command(create, output / "create.json")
        assert created["encrypted"]
        scratch = Path(tempfile.mkdtemp(prefix="browser-platform-r5b-backup-", dir="/dev/shm"))
        try:
            common = ["--age", age, "--archive", archive, "--identity", identity, "--scratch-root", scratch]
            verified = command([sys.executable, backup, "verify", *common], output / "verify.json")
            assert verified["result"] == "BACKUP_VERIFIED"
            wrong = output / "wrong-identity.txt"
            subprocess.run([str(age.with_name("age-keygen")), "-o", str(wrong)], capture_output=True, check=True)
            invalid = output / "must-not-exist"
            rejected = command([sys.executable, backup, "restore", "--age", age, "--archive", archive, "--identity", wrong,
                "--scratch-root", scratch, "--target", invalid], output / "wrong-key.json", expected=1)
            assert rejected["code"] == "BACKUP_AUTHENTICATION_FAILED" and not invalid.exists()
            damaged = output / "damaged.age"
            raw = bytearray(archive.read_bytes()); raw[-20] ^= 1; damaged.write_bytes(raw); damaged.chmod(0o600)
            rejected = command([sys.executable, backup, "restore", "--age", age, "--archive", damaged, "--identity", identity,
                "--scratch-root", scratch, "--target", invalid], output / "damaged-archive.json", expected=1)
            assert rejected["code"] == "BACKUP_AUTHENTICATION_FAILED" and not invalid.exists()
            bundle = output / "restored-bundle"
            restored = command([sys.executable, backup, "restore", *common, "--target", bundle], output / "restore.json")
            assert not restored["ready_to_activate"] and not list(scratch.iterdir())
        finally:
            scratch.rmdir()
        restored_store = runner.storage.FileSecretStore(bundle / "control/proxy-secret-store", bundle / "key-material/secret-store.key")
        refs = runner.storage.references("r5b-proxy", 7)
        try:
            restored_store.resolve(runner.principal, refs["username"], refs["password"])
            raise AssertionError("restored credentials activated before revocation merge")
        except runner.storage.SecretError as error:
            assert error.code == "SECRET_RECOVERY_LOCKED"
        runner.refresh()
        status, result = runner.admin.call("POST", "/api/admin/profile-secrets/revoke", {
            "secret_ref": "secret://r5b-proxy/password/5", "operation_id": uuid.uuid4().hex})
        assert status == 200 and result["cleanup_complete"]
        stop_adapter(qa)
        controller = json.loads(network.docker("inspect", "sealskin-network-qa").stdout)[0]
        assert any(v["Source"] == str(qa / "config") and v["Destination"] == "/config" for v in controller["Mounts"])
        assert runner.snapshot()["records"] == runner.snapshot()["workers"] == runner.snapshot()["resources"] == []
        network.docker("stop", "-t", "15", controller["Id"])
        network.docker("rm", controller["Id"])
        activated = command([sys.executable, backup, "activate", "--bundle", bundle, "--current-store", runner.store.directory], output / "activate.json")
        assert activated["started_workers"] == 0
        values = restored_store.resolve(runner.principal, refs["username"], refs["password"])
        assert values == {k:v.encode() for k,v in runner.inputs["7"].items()}
        revoked = runner.storage.references("r5b-proxy", 5)
        try:
            restored_store.resolve(runner.principal, revoked["username"], revoked["password"])
            raise AssertionError("post-backup revocation was lost")
        except runner.storage.SecretError as error:
            assert error.code == "SECRET_REVOKED"
        stop_proxy(qa)
        recovery = qa.parent / "recovered-environment"
        recovery.mkdir(mode=0o700)
        newqa = recovery / "qa"
        newqa.mkdir(mode=0o700)
        newconfig = newqa / "config"
        newmetadata = newconfig / ".config/sealskin"
        shutil.copytree(bundle / "control", newmetadata, ignore=shutil.ignore_patterns("ssl", "admin.json"))
        shutil.copytree(bundle / "control/ssl", newconfig / "ssl")
        shutil.copy2(bundle / "control/admin.json", newconfig / "admin.json")
        shutil.copytree(bundle / "home", newqa / "storage/network-qa" / runner.info["home"], symlinks=True)
        shutil.copytree(bundle / "environment", newqa / "environment")
        shutil.copytree(qa / "bin", newqa / "bin")
        (recovery / "master-key").mkdir(mode=0o700)
        shutil.copy2(bundle / "key-material/secret-store.key", recovery / "master-key/master.key")
        recovered_runtime = Path("/dev/shm/browser-platform-r5b-recovered-secrets")
        recovered_runtime.mkdir(mode=0o700)
        network.write_json(recovery / "secret-runtime.json", {"runtime_root": str(recovered_runtime)})
        for leaf in ("client-private.pem", "server-public.pem"):
            shutil.copy2(bundle / "adapter" / leaf, newqa / leaf)
        shutil.copy2(bundle / "adapter/config.json", newqa / "adapter-config.json")
        shutil.copy2(bundle / "adapter/state.json", newqa / "adapter-state.json")
        admin = json.loads((bundle / "control/admin.json").read_text())
        admin.update(server_endpoint="http://127.0.0.1:28110", api_port=28110)
        network.write_json(newqa / "admin.json", admin)
        apps = yaml.safe_load((newmetadata / "installed_apps.yml").read_text())
        app = next(v for v in apps if v["id"] == runner.app["id"])
        provider = app["overrides"]["provider_config"]
        for mount in provider["docker_overrides"]["mounts"]:
            if mount["Target"] == "/run/browser-platform/environment.json":
                mount["Source"] = str(newqa / "environment/artifact.json")
            if mount["Target"] == "/run/browser-platform/acceptance.json":
                mount["Source"] = str(newqa / "environment/acceptance.json")
        (newmetadata / "installed_apps.yml").write_text(yaml.safe_dump(apps, sort_keys=False))
        allow = json.loads((qa / "allow.json").read_text())
        allow.update(credential_runtime_root=str(recovered_runtime), readonly_sources=[m["Source"] for m in provider["docker_overrides"]["mounts"]])
        network.write_json(newqa / "allow.json", allow)
        network.write_json(newqa / "policy.json", {})
        network.write_json(newqa / "images.json", runner.images)
        proxy = start_process(["sg", "docker", "-c", shlex.join(["python3", str(PROJECT / "infra/sealskin/lifecycle/qa-network-docker-proxy.py"),
            "--root", str(newqa), "--socket", "/tmp/browser-platform-network-qa-docker.sock"])], newqa, "proxy")
        network.wait(lambda: Path("/tmp/browser-platform-network-qa-docker.sock").exists(), "recovery QA proxy")
        assert proxy.poll() is None
        identifier = network.docker("run", "-d", "--name", "sealskin-network-qa", "--label", "io.browser-platform.qa=network-20260913",
            "--network", "browser-platform-network-qa", "--memory", "512m", "--cpus", "1.5", "--pids-limit", "256",
            "-e", "PUID=1000", "-e", "PGID=1000", "-e", "TZ=Etc/UTC", "-e", "HOST_URL=network.invalid",
            "--add-host", "proxy.leak.qa.test:" + runner.images["upstream_host"],
            "-v", str(newconfig) + ":/config", "-v", str(newqa / "storage") + ":/storage",
            "-v", "/tmp/browser-platform-network-qa-docker.sock:/var/run/docker.sock", "-v", str(recovered_runtime) + ":/run/browser-platform-secrets",
            "-v", str(recovery / "master-key") + ":/run/browser-platform-key:ro", "-p", "127.0.0.1:28110:8000", runner.images["controller"]).stdout.strip()
        network.wait(lambda: network.request("POST", "/api/handshake/initiate")[0] == 200, "restored QA control")
        client = network.SecureClient(newqa)
        admin_client = network.SecureClient(newqa, username=admin["username"], private=admin["private_key"].encode(), public=admin["server_public_key"].encode())
        status, _ = admin_client.call("GET", "/api/admin/apps/installed")
        assert status == 200, "restored administrative identity failed"
        mapping = "from pathlib import Path; p=Path('/etc/hosts');p.write_text(p.read_text()+'\\n" + runner.images["upstream_host"] + " proxy.leak.qa.test\\n')"
        network.docker("exec", identifier, "python3", "-c", mapping)
        launch = dict(runner.request, operation_id=uuid.uuid4().hex)
        body = {k: launch[k] for k in ("application_id", "profile_id", "operation_id", "network_policy_id", "network_policy_sha256")}
        body["bootstrap_url"] = launch["url"]
        network.write_json(newqa / "browser-launch.json", launch)
        network.write_json(newqa / "browser-stop.json", body)
        status, result = client.call("POST", "/api/launch/url", launch)
        network.write_json(output / "restored-launch.json", {"status": status, "result": result})
        assert status == 200, "restored QA launch failed"
        body["session_id"] = result["session_id"]
        network.write_json(newqa / "browser-stop.json", body)
        status, inventory = client.call("GET", "/api/profile-runtime/" + runner.info["home"])
        assert status == 200 and len(inventory["workers"]) == 1
        worker = inventory["workers"][0]["instance_id"]
        info = dict(runner.info, instance_id=worker)
        network.write_json(newqa / "browser-worker.json", info)
        assert worker != original_worker
        desktop = checks.matrix.desktop.Desktop(worker)
        network.wait(lambda: desktop.available_title().startswith("Private browser network check"),
                     "restored launcher fixture navigation", seconds=60)
        desktop.navigate("https://entry.leak.qa.test/test")
        actual = desktop.evaluate("(" + checks.STORAGE + ")(false,null)")
        network.write_json(output / "restored-storage.json", actual)
        assert actual == expected and desktop.evaluate("fetchCheck('encrypted-restoration')")
        details = json.loads(network.docker("inspect", worker).stdout)[0]
        assert any(v["Source"] == str(newqa / "storage/network-qa" / runner.info["home"]) for v in details["Mounts"])
        assert any(v["Source"] == str(newqa / "environment/artifact.json") for v in details["Mounts"])
        runtime = network.Checks(newqa)
        runtime.start_adapter()
        status, _, _ = network.request("GET", "/readyz", port=29110)
        assert status == 200
        status, _ = client.call("POST", "/api/profile-runtime/" + runner.info["home"] + "/stop", body)
        assert status == 204 and not list(recovered_runtime.iterdir())
        network.write_json(output / "encrypted-recovery-results.json", {
            "result": "PASS", "archiveSHA256": created["archive_sha256"], "newController": identifier,
            "newEnvironmentDirectory": str(recovery), "authenticatedBeforeWrites": True, "wrongKeyAndTamperRefused": True,
            "recoveryLockedUntilRevocationMerge": True, "postBackupRevocationPreserved": True,
            "restoredAdapterAndServerIdentity": True, "restoredArtifactAndAcceptanceUsed": True,
            "restoredSecretAuthenticated": True, "cookieLocalStorageIndexedDBPreserved": True,
            "newWorkerSameBrowserImage": details["Image"], "stoppedAndMaterialsRemoved": True})
        print(json.dumps({"check": "encrypted-backup-fresh-environment", "result": "PASS", "browserDataAndCredentialRecovered": True}), flush=True)
    except BaseException as error:
        (output / "failure.txt").write_text(traceback.format_exc())
        print(json.dumps({"result": "FAIL", "type": type(error).__name__, "privateEvidenceRetained": True}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
