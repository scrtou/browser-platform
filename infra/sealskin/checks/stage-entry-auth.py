#!/usr/bin/env python3
"""Stage a fixed R5D build into an already prepared, empty private QA scope."""

import argparse
import copy
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
import sys
import time
from urllib.parse import urlsplit

PROJECT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("entry_network", PROJECT / "infra/sealskin/lifecycle/check-network-live.py")
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)
SOCKET = Path("/tmp/browser-platform-network-qa-docker.sock")
DISPLAY_TARGET = "/run/browser-platform-session-secrets"


def stop_process(qa, name, expected):
    path = qa / (name + "-pid.json")
    pid = json.loads(path.read_text())["pid"]
    command = Path("/proc", str(pid), "cmdline").read_bytes()
    if str(expected).encode() not in command or str(qa).encode() not in command or os.getpgid(pid) != pid:
        raise RuntimeError("QA_PROCESS_OWNERSHIP_UNPROVEN")
    os.killpg(pid, signal.SIGTERM)
    deadline = time.monotonic() + 8
    while Path("/proc", str(pid)).exists():
        if "State:\tZ" in Path("/proc", str(pid), "status").read_text():
            break
        if time.monotonic() > deadline:
            raise RuntimeError("QA_PROCESS_STOP_UNCONFIRMED")
        time.sleep(.1)


def start_adapter(qa, binary):
    with (qa / "adapter.log").open("ab") as log:
        process = subprocess.Popen([str(binary), "--config", str(qa / "adapter-config.json")],
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    network.write_json(qa / "adapter-pid.json", {"pid": process.pid})
    config = json.loads((qa / "adapter-config.json").read_text())
    host = urlsplit(config["public_base_url"]).netloc
    network.wait(lambda: network.request("GET", "/readyz", headers={"Host": host}, port=29110)[0] == 200,
                 "QA Adapter with verified private TLS", seconds=45)
    assert process.poll() is None
    return process


def register_accounts(qa, candidate, config, accounts):
    # A registry is validated against the current Profile set. Use a fresh QA
    # registry when replacing the old empty Homes; retain the old one intact.
    users = qa / "access/users-r7.json"
    assert not users.exists(), "new QA registry already exists; inspect partial staging"
    config["access"]["users_file"] = str(users)
    network.write_json(qa / "adapter-config.json", config)
    for account in accounts["accounts"]:
        command = [str(candidate / "bin/profile-accounts"), "put", "--config", str(qa / "adapter-config.json"),
                   "--user", account["username"], "--profiles", account["profile"]]
        result = subprocess.run(command, input=account["password"].encode(), capture_output=True)
        if result.returncode:
            raise RuntimeError("QA_ACCOUNT_REGISTRATION_REJECTED")


def replace_controller(qa, image, display_root=None, restart_proxy=False):
    old = json.loads(network.docker("inspect", network.SERVER).stdout)[0]
    assert old["Config"]["Labels"].get(network.PREFIX + "qa") == "network-20260913"
    assert old["HostConfig"]["NetworkMode"] == "browser-platform-network-qa"
    required = {"/config": str(qa / "config"), "/storage": str(qa / "storage"), "/var/run/docker.sock": str(SOCKET)}
    mounts = {}
    for value in old["Mounts"]:
        if value["Type"] != "bind":
            raise RuntimeError("QA_UNEXPECTED_CONTROLLER_VOLUME")
        target = value["Destination"]
        if target not in {*required, DISPLAY_TARGET}:
            raise RuntimeError("QA_UNEXPECTED_CONTROLLER_MOUNT")
        if target in required and value["Source"] != required[target]:
            raise RuntimeError("QA_CONTROLLER_MOUNT_MISMATCH")
        mounts[target] = value["Source"]
    assert all(mounts.get(k) == v for k, v in required.items())
    if display_root:
        info = display_root.lstat()
        assert display_root.parent == Path("/dev/shm") and display_root.resolve() == display_root
        assert info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700
        mounts[DISPLAY_TARGET] = str(display_root)
    ports = old["HostConfig"]["PortBindings"]
    assert ports == {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "28110"}],
                     "8443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "28443"}]}
    network.docker("stop", "-t", "10", network.SERVER)
    network.docker("rm", "-v", network.SERVER)
    if restart_proxy:
        stop_process(qa, "proxy", PROJECT / "infra/sealskin/lifecycle/qa-network-docker-proxy.py")
        check = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            check.settimeout(.5)
            check.connect(str(SOCKET))
            raise RuntimeError("QA_PROXY_STILL_LISTENING")
        except ConnectionRefusedError:
            pass
        finally:
            check.close()
        info = SOCKET.lstat()
        assert stat.S_ISSOCK(info.st_mode) and info.st_uid == os.geteuid()
        SOCKET.unlink()
        command = ["python3", str(PROJECT / "infra/sealskin/lifecycle/qa-network-docker-proxy.py"),
                   "--root", str(qa), "--socket", str(SOCKET)]
        with (qa / "proxy.log").open("ab") as log:
            process = subprocess.Popen(["sg", "docker", "-c", shlex.join(command)],
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        network.write_json(qa / "proxy-pid.json", {"pid": process.pid})
        network.wait(SOCKET.exists, "updated private Docker proxy", seconds=10)
    command = ["run", "-d", "--name", network.SERVER, "--label", network.PREFIX + "qa=network-20260913",
               "--network", "browser-platform-network-qa", "--memory", "512m", "--cpus", "1.5", "--pids-limit", "256"]
    for value in old["Config"]["Env"]:
        if value.split("=", 1)[0] in {"PUID", "PGID", "TZ", "HOST_URL"}:
            command += ["-e", value]
    for target, source in mounts.items():
        command += ["--mount", f"type=bind,src={source},dst={target}"]
    for target, bindings in ports.items():
        command += ["-p", "127.0.0.1:" + bindings[0]["HostPort"] + ":" + target]
    for value in old["HostConfig"].get("ExtraHosts") or []:
        command += ["--add-host", value]
    network.docker(*command, image)
    network.wait(lambda: network.request("POST", "/api/handshake/initiate")[0] == 200, "fixed QA controller", seconds=60)
    current = json.loads(network.docker("inspect", network.SERVER).stdout)[0]
    return {"old": old["Id"], "new": current["Id"], "image": current["Image"], "same_bind_mounts": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    args = parser.parse_args()
    qa, candidate = args.root.resolve(), args.candidate.resolve()
    assert qa.name == "qa" and candidate.parent == qa.parent.parent
    stage = candidate / "stage"
    stage.mkdir(mode=0o700)
    config = json.loads((qa / "adapter-config.json").read_text())
    assert config["sealskin"]["username"] == "network-qa" and config["listen_address"] == "127.0.0.1:29110"
    client = network.SecureClient(qa)
    for profile in config["profiles"]:
        status, value = client.call("GET", "/api/profile-runtime/" + profile["home_name"])
        assert status == 200 and not any(value[k] for k in ("records", "workers", "resources"))
    stop_process(qa, "adapter", "profile-adapter")
    for name in ("adapter-config.json", "access/test-accounts.json", "allow.json"):
        shutil.copy2(qa / name, stage / (Path(name).name + ".before"))
    display_root = Path("/dev/shm/browser-platform-r5d-display-20260914")
    display_root.mkdir(mode=0o700, exist_ok=False)
    network.write_json(stage / "resources.json", {"display_runtime_root": str(display_root), "qa_root": str(qa)})
    accounts = json.loads((qa / "access/test-accounts.json").read_text())
    policies_path = qa / "config/.config/sealskin/profile-network-policies.json"
    policies = json.loads(policies_path.read_text())
    base = policies["policies"][config["profiles"][0]["network_policy_id"]]
    admin = json.loads((qa / "admin.json").read_text())
    administrator = network.SecureClient(qa, username=admin["username"], private=admin["private_key"].encode(), public=admin["server_public_key"].encode())
    allow = json.loads((qa / "allow.json").read_text())
    allow["display_runtime_root"] = str(display_root)
    profiles = []
    for suffix, account in zip(("a", "b"), accounts["accounts"]):
        profile_id, home, app_id = "network-qa-entry-" + suffix, "network-qa-home-entry-" + suffix, "camoufox-r5d-" + suffix
        policy_id = "r5d-entry-" + suffix + "-r1"
        policy = copy.deepcopy(base)
        policy.update(profile_id=profile_id, home_name=home, application_id=app_id)
        revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        policies["policies"][policy_id] = policy
        network.write_json(policies_path, policies)
        status, _ = client.call("POST", "/api/homedirs", {"home_name": home})
        assert status == 201
        profile = qa / "storage/network-qa" / home / ".camoufox/profile"
        profile.mkdir(mode=0o700, parents=True)
        nss = qa.parent / "nss-tools/extracted/usr"
        command = ["/lib64/ld-linux-x86-64.so.2", "--library-path", str(nss / "lib/x86_64-linux-gnu"), str(nss / "bin/certutil")]
        for extra in (["-N", "--empty-password", "-d", "sql:" + str(profile)],
                      ["-A", "-d", "sql:" + str(profile), "-n", "Private Network QA CA", "-t", "C,,", "-i", str(qa.parent / "observer/ca.pem")]):
            assert subprocess.run(command + extra, capture_output=True).returncode == 0
        command = [sys.executable, str(PROJECT / "infra/camoufox/prepare-sealskin.py"), "--artifact", str(args.artifact.resolve()),
            "--acceptance", str(args.acceptance.resolve()), "--app-id", app_id, "--username", "network-qa", "--store", "QA",
            "--network-policy-id", policy_id, "--network-policy-sha256", revision,
            "--session-origin", accounts["session_origin"], "--output", str(stage / (app_id + ".json"))]
        prepared = subprocess.run(command, capture_output=True)
        (stage / (app_id + ".log")).write_bytes(prepared.stdout + prepared.stderr)
        assert prepared.returncode == 0, "QA app preparation rejected"
        app = json.loads((stage / (app_id + ".json")).read_text())
        status, _ = administrator.call("POST", "/api/admin/apps/installed", app)
        assert status == 201
        allow["images"] = sorted(set(allow["images"] + [app["provider_config"]["image"]]))
        allow["readonly_sources"] = sorted(set(allow["readonly_sources"] + [m["Source"] for m in app["provider_config"]["docker_overrides"]["mounts"]]))
        definition = copy.deepcopy(config["profiles"][0])
        definition.update(id=profile_id, home_name=home, application_id=app_id, network_policy_id=policy_id, network_policy_sha256=revision)
        profiles.append(definition)
        account.update(profile=profile_id, home=home)
    config["profiles"] = profiles
    config["access"]["ticket_seconds"] = 5
    network.write_json(qa / "adapter-config.json", config)
    network.write_json(qa / "access/test-accounts.json", accounts)
    network.write_json(qa / "allow.json", allow)
    register_accounts(qa, candidate, config, accounts)
    image = json.loads((candidate / "images.json").read_text())["runtime"]["image"]
    controller = replace_controller(qa, image, display_root, restart_proxy=True)
    start_adapter(qa, candidate / "bin/profile-adapter")
    network.write_json(qa / "access/active-candidate.json", {"candidate": str(candidate), "controller": controller,
        "display_runtime_root": str(display_root), "profiles": [p["id"] for p in profiles]})
    result = {"result": "STAGED", "controller": controller, "profiles": [p["id"] for p in profiles], "production_mutations": 0}
    network.write_json(stage / "result.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
