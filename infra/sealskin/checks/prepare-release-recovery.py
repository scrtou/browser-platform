#!/usr/bin/env python3
"""Restore one stopped R5E Home from age into a fresh, private QA environment.

Uses archived Home/control/identity/assets as the recovery data source. Fixed
images and QA executables are separate, verified local deployment inputs.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import uuid

import yaml

CHECKS = Path(__file__).resolve().parent
PROJECT = CHECKS.parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


runner = module("release_recovery_runner", CHECKS / "run-release-combination.py")
network = runner.network
require = runner.require


def command(values, output, expected=0):
    result = subprocess.run([str(v) for v in values], capture_output=True, text=True, timeout=180)
    output.write_text(result.stdout + result.stderr)
    require(result.returncode == expected, "QA_RECOVERY_COMMAND_FAILED")
    return json.loads(result.stdout)


def process(qa, name, args, env=None):
    with (qa / (name + ".log")).open("ab") as log:
        child = subprocess.Popen([str(v) for v in args], stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True, env=env)
    network.write_json(qa / (name + "-pid.json"), {"pid": child.pid})
    return child


def prepare(args):
    qa, output, target = args.root.resolve(), args.output.resolve(), args.target.resolve()
    work = qa.parent.parent
    require(work.name == "r5e-release-combination-2026-09-15" and output.parent == target.parent == work
            and re.fullmatch(r"recovered-[1-9][0-9]*", target.name) and not target.exists() and not output.exists(),
            "NEW_R5E_RECOVERY_ROOT_REQUIRED")
    output.mkdir(mode=0o700)
    (output / "observations").mkdir(mode=0o700)
    source = runner.Coordinator(qa, output, "recovered")
    profile = "network-qa-entry-a"
    expected = json.loads(args.baseline.read_text())
    observed = source.snapshot(browser_storage=True)
    require(observed["storage"] == expected["storage"], "SOURCE_BROWSER_STORAGE_CHANGED")
    source.record("source-before", observed)
    for name in source.profiles:
        source.stop_profile(name)
    storage = module("release_recovery_store", source.candidate / "build/payload/app/secret_store.py")
    store = storage.FileSecretStore(source.metadata / "proxy-secret-store", source.key_directory / "master.key")
    credentials = json.loads((source.endpoint_bundle / "before/credentials.json").read_text())
    definition = source.profiles[profile]
    grant = {"owner": "network-qa", "profile": profile, "home": definition["home_name"], "app": definition["application_id"]}
    later_id = "r5e-post-backup-" + uuid.uuid4().hex[:12]
    store.put(later_id, 1, [grant], username=credentials["username"], password=credentials["password"])
    later_refs = storage.references(later_id, 1)
    identity, archive = output / "age-identity.txt", output / "profile.age"
    age = args.age.resolve()
    generated = subprocess.run([str(age.with_name("age-keygen")), "-o", str(identity)], capture_output=True)
    require(generated.returncode == 0, "QA_AGE_IDENTITY_CREATION_FAILED")
    recipient = subprocess.check_output([str(age.with_name("age-keygen")), "-y", str(identity)], text=True).strip()
    backup = CHECKS.parent / "lifecycle/secure-backup.py"
    create = [sys.executable, backup, "create", "--age", age, "--config", qa / "adapter-config.json", "--profile", profile,
              "--storage", qa / "storage", "--sealskin-config", source.metadata, "--artifact", source.active["artifact"],
              "--acceptance", source.active["acceptance"], "--master-key-file", source.key_directory / "master.key",
              "--admin-recovery-file", qa / "admin.json", "--recipient", recipient, "--output", archive]
    created = command(create, output / "create.json")
    require(created["encrypted"], "QA_BACKUP_NOT_ENCRYPTED")
    print(json.dumps({"stage": "encrypted-backup-created", "archive_sha256": created["archive_sha256"]}), flush=True)
    scratch = Path(tempfile.mkdtemp(prefix="browser-platform-r5e-restore-", dir="/dev/shm"))
    network.write_json(output / "scratch.json", {"directory": str(scratch)})
    bundle = output / "restored-bundle"
    try:
        common = ["--age", age, "--archive", archive, "--identity", identity, "--scratch-root", scratch]
        verified = command([sys.executable, backup, "verify", *common], output / "verify.json")
        require(verified["result"] == "BACKUP_VERIFIED", "QA_BACKUP_VERIFY_FAILED")
        restored = command([sys.executable, backup, "restore", *common, "--target", bundle], output / "restore.json")
        require(restored["access_review_required"] and not restored["ready_to_activate"] and not list(scratch.iterdir()),
                "QA_RESTORE_REVIEW_GATE_MISSING")
    finally:
        require(not list(scratch.iterdir()), "QA_RESTORE_SCRATCH_NOT_EMPTY")
        scratch.rmdir()
    recovered_store = storage.FileSecretStore(bundle / "control/proxy-secret-store", bundle / "key-material/secret-store.key")
    policy = json.loads((source.metadata / "profile-network-policies.json").read_text())["policies"][definition["network_policy_id"]]
    try:
        recovered_store.resolve(grant, policy["username_secret_ref"], policy["password_secret_ref"])
        raise RuntimeError("QA_RECOVERED_STORE_UNLOCKED_BEFORE_REVIEW")
    except storage.SecretError as error:
        require(error.code == "SECRET_RECOVERY_LOCKED", "QA_RECOVERY_WRONG_REFUSAL")
    rejected = command([sys.executable, backup, "activate", "--bundle", bundle, "--current-store", store.directory],
                       output / "missing-current-access.json", expected=1)
    require(rejected["code"] == "BACKUP_CURRENT_ACCESS_REQUIRED", "QA_CURRENT_ACCESS_NOT_REQUIRED")
    status, revoked = source.admin.call("POST", "/api/admin/profile-secrets/revoke", {
        "secret_ref": later_refs["password"], "operation_id": uuid.uuid4().hex})
    source.record("post-backup-revocation", {"status": status, "result": revoked})
    require(status == 200 and revoked["cleanup_complete"], "QA_POST_BACKUP_REVOCATION_FAILED")
    disable = subprocess.run([str(source.candidate / "bin/profile-accounts"), "disable", "--config", str(qa / "adapter-config.json"),
                              "--user", "bob"], capture_output=True)
    require(disable.returncode == 0, "QA_POST_BACKUP_ACCOUNT_DISABLE_FAILED")
    require(Path(source.config["access"]["users_file"]).read_bytes() != (bundle / "adapter/access-users.json").read_bytes(),
            "QA_ACCOUNT_CHANGE_NOT_AFTER_BACKUP")
    for name, executable in (("adapter", source.candidate / "bin/profile-adapter"), ("front-caddy", "caddy")):
        runner.entry.stage.stop_process(qa, name, executable)
        (qa / (name + "-pid.json")).rename(qa / (name + "-stopped.json"))
    for name in source.profiles:
        require(not any(source.inventory(name)[k] for k in ("records", "workers", "resources")), "SOURCE_QA_STILL_OCCUPIED")
    controller = source.controller()
    source.record("source-controller-before-removal", controller)
    network.docker("stop", "-t", "10", controller["Id"])
    network.docker("rm", "-v", controller["Id"])
    runner.entry.stage.stop_process(qa, "proxy", "qa-network-docker-proxy.py")
    proxy_socket = Path("/tmp/browser-platform-network-qa-docker.sock")
    require(proxy_socket.is_socket() and proxy_socket.stat().st_uid == os.geteuid(), "QA_PROXY_SOCKET_SCOPE_MISMATCH")
    proxy_socket.unlink()
    (qa / "proxy-pid.json").rename(qa / "proxy-stopped.json")
    activated = command([sys.executable, backup, "activate", "--bundle", bundle, "--current-store", store.directory,
                         "--current-access-users", source.config["access"]["users_file"]], output / "activate.json")
    require(activated["started_workers"] == 0, "QA_ACTIVATION_STARTED_A_WORKER")
    try:
        recovered_store.resolve(grant, later_refs["username"], later_refs["password"])
        raise RuntimeError("QA_POST_BACKUP_REVOCATION_LOST")
    except storage.SecretError as error:
        require(error.code == "SECRET_REVOKED", "QA_RESTORED_REVOCATION_WRONG_REFUSAL")
    require(json.loads((bundle / "adapter/access-users.json").read_bytes()) ==
            json.loads(Path(source.config["access"]["users_file"]).read_bytes()),
            "QA_CURRENT_ACCESS_REGISTRY_NOT_MERGED")
    values = recovered_store.resolve(grant, policy["username_secret_ref"], policy["password_secret_ref"])
    require(values == {k: credentials[k].encode() for k in ("username", "password")}, "QA_RECOVERED_CREDENTIAL_MISMATCH")
    stage_restored(args, source, created, observed, bundle)


def stage_restored(args, source, created, observed, bundle):
    """Rebind verified offline data; no fallback to the original Home."""
    qa, output, target = args.root.resolve(), args.output.resolve(), args.target.resolve()
    archive = output / "profile.age"
    profile = "network-qa-entry-a"
    definition = source.profiles[profile]
    proxy_socket = Path("/tmp/browser-platform-network-qa-docker.sock")
    target.mkdir(mode=0o700)
    newqa = target / "qa"
    newqa.mkdir(mode=0o700)
    display = Path("/dev/shm/browser-platform-r5e-" + target.name + "-display-20260915")
    secret_runtime = Path("/dev/shm/browser-platform-r5e-" + target.name + "-proxy-20260915")
    key_directory = target / "master-key"
    resources = {"candidate": str(target), "qa": str(newqa), "display": str(display), "credentials": str(secret_runtime),
                 "key_directory": str(key_directory), "source_candidate": str(source.candidate), "backup": str(archive)}
    network.write_json(target / "resources.json", resources)
    network.write_json(output / "resources.json", resources)
    for directory in (display, secret_runtime, key_directory):
        directory.mkdir(mode=0o700)
    metadata = newqa / "config/.config/sealskin"
    shutil.copytree(bundle / "control", metadata, ignore=shutil.ignore_patterns("ssl", "admin.json"))
    shutil.copytree(bundle / "control/ssl", newqa / "config/ssl")
    shutil.copy2(bundle / "control/admin.json", newqa / "config/admin.json")
    shutil.copy2(bundle / "control/admin.json", newqa / "admin.json")
    shutil.copytree(bundle / "home", newqa / "storage/network-qa" / definition["home_name"], symlinks=True)
    shutil.copy2(bundle / "key-material/secret-store.key", key_directory / "master.key")
    access = newqa / "access"
    access.mkdir(mode=0o700)
    for leaf in ("client-private.pem", "server-public.pem"):
        shutil.copy2(bundle / "adapter" / leaf, newqa / leaf)
    shutil.copy2(bundle / "adapter/state.json", newqa / "adapter-state.json")
    shutil.copy2(bundle / "adapter/access-users.json", access / "users.json")
    shutil.copy2(bundle / "adapter/session-ca.pem", access / "session-ca.pem")
    for leaf in ("images.json", "worker-build.json"):
        shutil.copy2(source.candidate / leaf, target / leaf)
    shutil.copytree(source.candidate / "bin", target / "bin")
    shutil.copytree(source.candidate / "build/payload", target / "build/payload")
    shutil.copytree(qa / "bin", newqa / "bin")
    shutil.copy2(qa / "images.json", newqa / "images.json")
    config = json.loads((bundle / "adapter/config.json").read_text())
    config.update(state_file="adapter-state.json", control_socket="/tmp/browser-platform-network-qa.sock")
    config["sealskin"].update(client_private_key_file="client-private.pem", server_public_key_file="server-public.pem")
    config["access"].update(users_file=str(access / "users.json"), session_ca_file=str(access / "session-ca.pem"))
    network.write_json(newqa / "adapter-config.json", config)
    apps_path = metadata / "installed_apps.yml"
    apps = yaml.safe_load(apps_path.read_text())
    asset_sources = []
    for app in apps:
        provider = app.get("overrides", {}).get("provider_config", {})
        for mount in provider.get("docker_overrides", {}).get("mounts", []):
            original = Path(mount["Source"])
            require(original.is_relative_to(source.metadata / "coherence-assets"), "RECOVERY_APP_MOUNT_OUTSIDE_ARCHIVED_ASSETS")
            restored_path = metadata / "coherence-assets" / original.relative_to(source.metadata / "coherence-assets")
            require(restored_path.is_file(), "RECOVERY_APP_ASSET_MISSING")
            mount["Source"] = str(restored_path)
            asset_sources.append(str(restored_path))
    apps_path.write_text(yaml.safe_dump(apps, sort_keys=False))
    apps_path.chmod(0o600)
    allow = json.loads((qa / "allow.json").read_text())
    allow.update(display_runtime_root=str(display), credential_runtime_root=str(secret_runtime), readonly_sources=sorted(set(asset_sources)))
    network.write_json(newqa / "allow.json", allow)
    network.write_json(newqa / "policy.json", {})
    active = copy.deepcopy(source.active)
    active.update(candidate=str(target), display_runtime_root=str(display), credential_runtime_root=str(secret_runtime),
                  key_directory=str(key_directory), artifact=str(metadata / "coherence-assets" / Path(source.active["artifact"]).name),
                  acceptance=str(metadata / "coherence-assets" / Path(source.active["acceptance"]).name))
    for app in active["applications"].values():
        for mount in app["provider_config"]["docker_overrides"]["mounts"]:
            mount["Source"] = str(metadata / "coherence-assets" / Path(mount["Source"]).name)
    accounts = json.loads((qa / "access/test-accounts.json").read_text())
    accounts["recovery_expected"] = {"storage": observed["storage"][profile], "original_identity": observed["profiles"][profile],
                                    "source_home": definition["home_name"], "disabled_user": "bob"}
    network.write_json(access / "test-accounts.json", accounts)
    proxy = process(newqa, "proxy", ["sg", "docker", "-c", shlex.join(["python3", str(CHECKS.parent / "lifecycle/qa-network-docker-proxy.py"),
                    "--root", str(newqa), "--socket", str(proxy_socket)])])
    network.wait(proxy_socket.exists, "recovered QA Docker proxy", seconds=15)
    require(proxy.poll() is None, "RECOVERED_QA_PROXY_EXITED")
    image = json.loads((target / "images.json").read_text())["runtime"]["image"]
    controller_id = network.docker("run", "-d", "--name", network.SERVER, "--label", "io.browser-platform.qa=network-20260913",
        "--network", "browser-platform-network-qa", "--memory", "512m", "--cpus", "1.5", "--pids-limit", "256",
        "-e", "PUID=1000", "-e", "PGID=1000", "-e", "TZ=Etc/UTC", "-e", "HOST_URL=network.invalid",
        "--mount", f"type=bind,src={newqa / 'config'},dst=/config", "--mount", f"type=bind,src={newqa / 'storage'},dst=/storage",
        "--mount", f"type=bind,src={proxy_socket},dst=/var/run/docker.sock",
        "--mount", f"type=bind,src={key_directory},dst=/run/browser-platform-key,readonly",
        "--mount", f"type=bind,src={secret_runtime},dst=/run/browser-platform-secrets",
        "--mount", f"type=bind,src={display},dst=/run/browser-platform-session-secrets",
        "--mount", "type=bind,src=/proc/1/net/fib_trie,dst=/run/browser-platform-host/ipv4-fib-trie,readonly",
        "-p", "127.0.0.1:28110:8000", "-p", "127.0.0.1:28443:8443", image).stdout.strip()
    active["controller"] = controller_id
    network.write_json(access / "active-candidate.json", active)
    network.wait(lambda: network.request("POST", "/api/handshake/initiate")[0] == 200, "restored controller identity", seconds=50)
    recovered_client = network.SecureClient(newqa)
    admin = json.loads((newqa / "admin.json").read_text())
    administrator = network.SecureClient(newqa, username=admin["username"], private=admin["private_key"].encode(),
                                         public=admin["server_public_key"].encode())
    require(administrator.call("GET", "/api/admin/apps/installed")[0] == 200, "RESTORED_ADMIN_IDENTITY_FAILED")
    # The archive contains one Home. Keep the other configured QA Profile
    # disabled with an explicit empty placeholder, never claim its data restored.
    other_home = source.profiles["network-qa-entry-b"]["home_name"]
    require(not (newqa / "storage/network-qa" / other_home).exists(), "UNEXPECTED_SECOND_RESTORED_HOME")
    require(recovered_client.call("POST", "/api/homedirs", {"home_name": other_home})[0] == 201, "QA_PLACEHOLDER_HOME_FAILED")
    log_check = module("recovery_front_identity", CHECKS / "check-entry-log-boundary.py")
    certificate, private_key = log_check.identity(access)
    template = (CHECKS.parent / "entry-auth/Caddyfile.example").read_text().replace("admin off", "admin off\n    auto_https off", 1)
    template = template.replace("mybrowser.example.com, mysession.example.com {", accounts["entry_origin"] + ", " + accounts["session_origin"] +
                                " {\n    bind 127.0.0.1\n    tls " + str(certificate) + " " + str(private_key))
    template = template.replace("127.0.0.1:8080", config["listen_address"])
    (access / "Caddyfile").write_text(template)
    env = dict(os.environ, XDG_CONFIG_HOME=str(access / "caddy-config"), XDG_DATA_HOME=str(access / "caddy-data"))
    validation = subprocess.run(["caddy", "adapt", "--config", str(access / "Caddyfile"), "--adapter", "caddyfile", "--validate"],
                                env=env, capture_output=True)
    (access / "caddy-validation.log").write_bytes(validation.stdout + validation.stderr)
    require(validation.returncode == 0, "RESTORED_FRONTEND_CONFIG_INVALID")
    runner.entry.stage.start_adapter(newqa, target / "bin/profile-adapter")
    process(newqa, "front-caddy", ["caddy", "run", "--config", access / "Caddyfile", "--adapter", "caddyfile"], env)
    assets = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (metadata / "coherence-assets").iterdir()}
    require(assets == {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (bundle / "control/coherence-assets").iterdir()},
            "RESTORED_COHERENCE_ASSETS_CHANGED")
    receipt = {"result": "PREPARED", "archive_sha256": created["archive_sha256"], "target": str(target), "controller": controller_id,
               "assets": assets, "server_and_admin_identity_verified": True, "post_backup_revocation_preserved": True,
               "current_account_registry_merged": True, "restored_home": definition["home_name"],
               "other_profile": "disabled; new empty QA placeholder", "frontend_certificate": "new QA identity",
               "browser_recovery": "NOT_RUN"}
    network.write_json(output / "result.json", receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key not in {"assets"}}), flush=True)


def resume_offline(args):
    """Continue only the recorded, activated bundle after its source retired.

    This is a QA checkpoint, not an option to skip product recovery validation.
    A partially staged target is deliberately refused for operator inspection.
    """
    qa, output, target = args.root.resolve(), args.output.resolve(), args.target.resolve()
    work = qa.parent.parent
    require(work.name == "r5e-release-combination-2026-09-15" and qa == work / "candidate-1/qa"
            and output.parent == target.parent == work
            and re.fullmatch(r"backup-restore-[1-9][0-9]*", output.name)
            and re.fullmatch(r"recovered-[1-9][0-9]*", target.name)
            and output.is_dir() and not target.exists(), "R5E_OFFLINE_CHECKPOINT_SCOPE_REQUIRED")
    runner.prepare.owned_directory(output)
    config = json.loads((qa / "adapter-config.json").read_text())
    active = json.loads((qa / "access/active-candidate.json").read_text())
    require(Path(active["candidate"]) == qa.parent and config["sealskin"]["username"] == "network-qa",
            "R5E_SOURCE_IDENTITY_MISMATCH")
    require(network.docker("inspect", active["controller"], check=False).returncode != 0,
            "SOURCE_CONTROLLER_NOT_RETIRED")
    for name in ("adapter", "front-caddy", "proxy"):
        require(not (qa / (name + "-pid.json")).exists(), "SOURCE_QA_PROCESS_NOT_RETIRED")
        pid = json.loads((qa / (name + "-stopped.json")).read_text())["pid"]
        command_path = Path("/proc", str(pid), "cmdline")
        require(not command_path.exists() or str(qa).encode() not in command_path.read_bytes(),
                "SOURCE_QA_PROCESS_REMAINS")
    scope = hashlib.sha256(str(qa / "config/.config/sealskin/sessions.yml").encode()).hexdigest()
    for inspect_command in (("ps", "-aq"), ("network", "ls", "-q")):
        require(not network.docker(*inspect_command, "--filter", "label=io.browser-platform.scope=" + scope).stdout.strip(),
                "SOURCE_QA_GENERATION_REMAINS")
    state = json.loads((qa / "adapter-state.json").read_text())
    require(all(value["status"] == "stopped" for value in state["bindings"].values()), "SOURCE_QA_NOT_STOPPED")
    bundle = output / "restored-bundle"
    created = json.loads((output / "create.json").read_text())
    receipt = json.loads((bundle / "recovery.json").read_text())
    require(created["encrypted"] and receipt["archive_sha256"] == created["archive_sha256"] ==
            hashlib.sha256((output / "profile.age").read_bytes()).hexdigest(), "RECOVERY_ARCHIVE_IDENTITY_CHANGED")
    backup = CHECKS.parent / "lifecycle/secure-backup.py"
    scratch = Path(tempfile.mkdtemp(prefix="browser-platform-r5e-resume-", dir="/dev/shm"))
    try:
        require(not (output / "resume-verify.json").exists() and not (output / "resume-activate.json").exists(),
                "RECOVERY_CHECKPOINT_ALREADY_ATTEMPTED")
        command([sys.executable, backup, "verify", "--age", args.age.resolve(), "--archive", output / "profile.age",
                 "--identity", output / "age-identity.txt", "--scratch-root", scratch], output / "resume-verify.json")
    finally:
        require(not list(scratch.iterdir()), "QA_RESTORE_SCRATCH_NOT_EMPTY")
        scratch.rmdir()
    command([sys.executable, backup, "activate", "--bundle", bundle, "--current-store",
             qa / "config/.config/sealskin/proxy-secret-store", "--current-access-users", config["access"]["users_file"]],
            output / "resume-activate.json")
    require(json.loads((bundle / "adapter/access-users.json").read_bytes()) ==
            json.loads(Path(config["access"]["users_file"]).read_bytes()), "QA_CURRENT_ACCESS_REGISTRY_NOT_MERGED")
    observed_paths = list(output.glob("[0-9][0-9][0-9]-source-before.json"))
    require(len(observed_paths) == 1, "RECOVERY_BASELINE_AMBIGUOUS")
    observed = json.loads(observed_paths[0].read_text())
    require(observed["storage"] == json.loads(args.baseline.read_text())["storage"], "RECOVERY_BASELINE_CHANGED")
    source = SimpleNamespace(qa=qa, candidate=qa.parent, metadata=qa / "config/.config/sealskin",
                             config=config, active=active, profiles={p["id"]: p for p in config["profiles"]})
    stage_restored(args, source, created, observed, bundle)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "output", "target", "baseline", "age"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--resume-offline", action="store_true", help="Continue a verified bundle after the exact source QA retired")
    args = parser.parse_args()
    (resume_offline if args.resume_offline else prepare)(args)


if __name__ == "__main__":
    main()
