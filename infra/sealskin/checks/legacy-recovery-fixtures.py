#!/usr/bin/env python3
"""Stage and retire only R2B's source/recovered QA, retaining encrypted evidence."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import tempfile
from types import SimpleNamespace

import yaml


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


CHECKS = Path(__file__).resolve().parent
browser = module("r2b_browser", CHECKS / "check-legacy-browser-recovery.py")
backup = module("r2b_backup", CHECKS.parent / "lifecycle/secure-backup.py")
network, docker, require, WORK = browser.network, browser.docker, browser.require, browser.WORK
PROXY_SOCKET = Path("/tmp/browser-platform-network-qa-docker.sock")


def production():
    expected = json.loads((WORK / "production-before.json").read_text())
    values = json.loads(docker("inspect", *expected["containers"]).stdout)
    actual = {v["Name"]: {"id": v["Id"], "started_at": v["State"]["StartedAt"],
                          "image": v["Image"], "pid": v["State"]["Pid"]} for v in values}
    files = {p: backup.sha(CHECKS.parent / p) for p in expected["files"]}
    require(actual == expected["containers"] and files == expected["files"], "PRODUCTION_CHANGED")
    require(backup.sha(browser.PROJECT / ".git/index") == expected["index_sha256"], "INDEX_CHANGED")
    return {"four_containers_unchanged": True, "five_configs_unchanged": True, "index_unchanged": True}


def empty(root):
    browser.root_checked(root)
    d = browser.boot.Drill(root)
    require(d.control(browser.PROFILE)[1]["result"]["status"] == "stopped", "STOPPED_QA_BINDING_REQUIRED")
    require(all(not d.snapshot(browser.HOME)[k] for k in ("workers", "records", "resources")), "QA_HOME_OCCUPIED")
    sessions_status, sessions = d.checks.client.call("GET", "/api/sessions")
    require(sessions_status == 200 and not sessions, "QA_SESSIONS_REMAIN")
    scope = hashlib.sha256(str(root / "config/.config/sealskin/sessions.yml").encode()).hexdigest()
    require(not docker("ps", "-aq", "--filter", "label=io.browser-platform.scope=" + scope).stdout.strip()
            and not docker("network", "ls", "-q", "--filter", "label=io.browser-platform.scope=" + scope).stdout.strip(),
            "QA_GENERATION_REMAINS")
    for name in ("profile-launch-runtime", "profile-network-runtime"):
        require(not list((root / "config/.config/sealskin" / name).glob("*.json")), "UNFINISHED_QA_JOURNAL_REMAINS")


def stop_process(root, name):
    path = root / (name + "-pid.json")
    pid = json.loads(path.read_text())["pid"]
    def command():
        try:
            return Path("/proc", str(pid), "cmdline").read_bytes()
        except FileNotFoundError:
            return b""
    before = command()
    require(str(root).encode() in before and os.getpgid(pid) == pid, "QA_PROCESS_OWNERSHIP_MISMATCH")
    os.killpg(pid, signal.SIGTERM)
    network.wait(lambda: not command(), "retired QA " + name, seconds=20)
    path.rename(root / (name + "-stopped.json"))


def remove_socket(path):
    if os.path.lexists(path):
        info = path.lstat()
        require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid(), "QA_SOCKET_OWNER_MISMATCH")
        deadline = __import__("time").monotonic() + 10
        while True:
            with socket.socket(socket.AF_UNIX) as probe:
                code = probe.connect_ex(str(path))
            if code != 0:
                break
            require(__import__("time").monotonic() < deadline, "QA_SOCKET_STILL_ACTIVE")
            __import__("time").sleep(.1)
        path.unlink()


def retire(root, evidence):
    empty(root)
    stop_process(root, "adapter")
    container = json.loads(docker("inspect", network.SERVER).stdout)[0]
    network.write_json(evidence, container)
    volumes = [m["Name"] for m in container["Mounts"] if m["Type"] == "volume"]
    for name in volumes:
        require(docker("ps", "-aq", "--no-trunc", "--filter", "volume=" + name).stdout.split() == [container["Id"]],
                "QA_VOLUME_HAS_ANOTHER_OWNER")
    docker("stop", "-t", "10", container["Id"])
    docker("rm", "-v", container["Id"])
    stop_process(root, "proxy")
    for path in (PROXY_SOCKET, Path(network.SOCKET)):
        remove_socket(path)
    require(all(docker("volume", "inspect", name, check=False).returncode != 0 for name in volumes), "QA_VOLUME_REMAINS")
    return volumes


def process(root, name, command):
    with (root / (name + ".log")).open("ab") as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    network.write_json(root / (name + "-pid.json"), {"pid": child.pid})
    return child


def stage(age):
    source, target, bundle = WORK / "source/qa", WORK / "recovered/qa", WORK / "offline-bundle"
    require(not target.parent.exists(), "FRESH_RECOVERY_ROOT_REQUIRED")
    production()
    empty(source)
    receipt = json.loads((bundle / "recovery.json").read_text())
    require(receipt["offline_only"] and not receipt["ready_to_activate"]
            and (bundle / ".legacy-recovery-pending.json").is_file(), "OFFLINE_LEGACY_BUNDLE_REQUIRED")
    scratch = Path(tempfile.mkdtemp(prefix="browser-platform-r2b-rebind-", dir="/dev/shm"))
    args = SimpleNamespace(age=age, archive=WORK / "profile-legacy.age", identity=WORK / "age-identity.txt", scratch_root=scratch)
    try:
        with backup.decrypted(args) as (_, _, manifest):
            require(manifest["format"] == backup.LEGACY_FORMAT and receipt["archive_sha256"] == backup.sha(args.archive),
                    "LEGACY_ARCHIVE_IDENTITY_MISMATCH")
            entries, _, excluded = backup.snapshot({name: bundle / name for name in ("home", "adapter", "control", "runtime")})
            # restore creates the four staging roots even when the tar stream
            # did not need a separate root member; compare archived children.
            for name in ("adapter", "control", "runtime"):
                entries.pop(name, None)
            require(entries == manifest["entries"] and not excluded, "OFFLINE_BUNDLE_CHANGED")
    finally:
        require(not list(scratch.iterdir()), "QA_TMPFS_NOT_EMPTY")
        scratch.rmdir()
    recorded = json.loads((bundle / "runtime/snapshot.json").read_text())
    release = json.loads((source.parent / "build/release.json").read_text())
    image = docker("image", "inspect", release["image"], "--format", "{{.Id}}").stdout.strip()
    require(recorded["worker"]["image_id"] == browser.IMAGE and recorded["controller"]["image_id"] == image,
            "RESTORE_IMAGE_MISMATCH")
    target.mkdir(parents=True, mode=0o700)
    metadata = target / "config/.config/sealskin"
    shutil.copytree(bundle / "control", metadata, ignore=shutil.ignore_patterns("ssl", "admin.json"))
    shutil.copytree(bundle / "control/ssl", target / "config/ssl")
    for path in (target / "admin.json", target / "config/admin.json"):
        shutil.copy2(bundle / "control/admin.json", path)
    shutil.copytree(bundle / "home", target / "storage/network-qa" / browser.HOME, symlinks=True)
    for name in ("client-private.pem", "server-public.pem"):
        shutil.copy2(bundle / "adapter" / name, target / name)
    shutil.copy2(bundle / "adapter/state.json", target / "adapter-state.json")
    shutil.copytree(source / "bin", target / "bin")
    shutil.copytree(source.parent / "build", target.parent / "build")
    for name in ("allow.json", "images.json", "policy.json"):
        shutil.copy2(source / name, target / name)
    config = json.loads((bundle / "adapter/config.json").read_text())
    require(len(config["profiles"]) == 1 and config["profiles"][0]["id"] == browser.PROFILE
            and not config.get("access"), "SINGLE_LEGACY_PROFILE_REQUIRED")
    config.update(state_file="adapter-state.json", control_socket=network.SOCKET)
    config["sealskin"].update(client_private_key_file="client-private.pem", server_public_key_file="server-public.pem")
    network.write_json(target / "adapter-config.json", config)
    apps_path = metadata / "installed_apps.yml"
    apps = yaml.safe_load(apps_path.read_text())
    apps = [v for v in apps if v["id"] == browser.APP]
    require(len(apps) == 1, "RECOVERED_APP_MISSING")
    # Extra mock fixture Homes/apps are absent from this one-Home archive.
    # Retain the original registry in the offline bundle, stage only this app.
    apps_path.write_text(yaml.safe_dump(apps, sort_keys=False))
    network.write_json(metadata / "profile-network-policies.json", {"version": 1, "policies": {}})
    network.write_json(target.parent / "offline-review.json", {
        "archive_sha256": receipt["archive_sha256"], "home_from_archive_only": True,
        "excluded_other_fixture_apps": True, "unused_mock_policies_disabled": True,
        "old_journal_preserved": True, "pending_marker_kept_in_bundle": True,
        "production_activation": False, "controller_image": image, "worker_image": browser.IMAGE})
    removed = retire(source, WORK / "retired-source-controller-private.json")
    child = process(target, "proxy", ["sg", "docker", "-c", shlex.join(["python3",
        str(CHECKS.parent / "lifecycle/qa-network-docker-proxy.py"), "--root", str(target), "--socket", str(PROXY_SOCKET)])])
    network.wait(PROXY_SOCKET.exists, "recovered Docker proxy", seconds=15)
    require(child.poll() is None, "RECOVERY_PROXY_FAILED")
    docker("run", "-d", "--name", network.SERVER, "--label", "io.browser-platform.qa=network-20260913",
        "--network", "browser-platform-network-qa", "--memory", "512m", "--cpus", "1.5", "--pids-limit", "256",
        "-e", "PUID=1000", "-e", "PGID=1000", "-e", "TZ=Etc/UTC", "-e", "HOST_URL=network.invalid",
        "-v", str(target / "config") + ":/config", "-v", str(target / "storage") + ":/storage",
        "-v", str(PROXY_SOCKET) + ":/var/run/docker.sock", "-p", "127.0.0.1:28110:8000", image)
    network.wait(lambda: network.request("POST", "/api/handshake/initiate")[0] == 200, "restored API", seconds=60)
    d = browser.boot.Drill(target)
    require(d.admin_client().call("GET", "/api/admin/apps/installed")[0] == 200
            and d.checks.client.call("GET", "/api/homedirs")[0] == 200, "RESTORED_API_IDENTITY_FAILED")
    adapter = process(target, "adapter", [str(target / "bin/profile-adapter"), "-config", str(target / "adapter-config.json")])
    network.wait(lambda: network.request("GET", "/healthz", port=29110)[0] == 200,
                 "restored QA Adapter", seconds=30)
    require(adapter.poll() is None, "RECOVERY_ADAPTER_FAILED")
    return {"status": "pass", "stage": "new-private-root", "source_retired_first": True,
            "source_anonymous_volumes_removed": removed, "admin_and_user_api_identity_verified": True, **production()}


def cleanup():
    root = WORK / "recovered/qa"
    require(json.loads((WORK / "read-recovered-1.json").read_text())["three_stores_match"], "RECOVERY_EVIDENCE_REQUIRED")
    volumes = retire(root, WORK / "retired-recovered-controller-private.json")
    remaining = docker("ps", "-a", "--filter", "label=io.browser-platform.qa=network-20260913", "--format", "{{.Names}}").stdout.split()
    require(remaining == ["network-qa-upstream"], "UNKNOWN_QA_FIXTURE_REMAINS")
    upstream = json.loads(docker("inspect", "network-qa-upstream").stdout)[0]
    require(any(m.get("Source") == str(WORK / "source/qa/upstream") and m["Destination"] == "/qa"
                for m in upstream["Mounts"]), "UPSTREAM_OWNER_MISMATCH")
    network.write_json(WORK / "retired-upstream-private.json", upstream)
    owned = [m["Name"] for m in upstream["Mounts"] if m["Type"] == "volume"]
    for name in owned:
        require(docker("ps", "-aq", "--no-trunc", "--filter", "volume=" + name).stdout.split() == [upstream["Id"]],
                "UPSTREAM_VOLUME_HAS_ANOTHER_OWNER")
    docker("stop", "-t", "10", upstream["Id"])
    docker("rm", "-v", upstream["Id"])
    base = json.loads(docker("network", "inspect", "browser-platform-network-qa").stdout)[0]
    require(not base["Containers"] and base["Labels"].get("io.browser-platform.qa") == "network-20260913", "QA_NETWORK_NOT_EMPTY")
    docker("network", "rm", base["Id"])
    require(all(docker("volume", "inspect", v, check=False).returncode != 0 for v in owned), "QA_UPSTREAM_VOLUME_REMAINS")
    for port in (28110, 29110):
        with socket.socket() as probe:
            require(probe.connect_ex(("127.0.0.1", port)) != 0, "QA_PORT_REMAINS")
    return {"status": "pass", "qa_containers_network_and_listeners_removed": True,
            "anonymous_volumes_removed": volumes + owned, "private_evidence_retained": True, **production()}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "cleanup"))
    parser.add_argument("--age", type=Path)
    args = parser.parse_args()
    output = WORK / (args.action + "-fixtures.json")
    require(not output.exists(), "FRESH_FIXTURE_EVIDENCE_REQUIRED")
    result = stage(args.age.resolve()) if args.action == "stage" and args.age else cleanup() if args.action == "cleanup" else None
    require(result is not None, "AGE_REQUIRED_FOR_STAGE")
    network.write_json(output, result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
