#!/usr/bin/env python3
"""Run the real r7 /init with invalid display materials in disposable QA roots."""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
import uuid


spec = importlib.util.spec_from_file_location("entry_network", Path(__file__).parents[1] / "lifecycle/check-network-live.py")
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.exists()
    output.mkdir(mode=0o700)
    build = json.loads(args.build.read_text())
    app = json.loads(args.app.read_text())["provider_config"]
    assert app["image"] == build["imageId"]
    expected_targets = {"/run/browser-platform/environment.json", "/run/browser-platform/acceptance.json"}
    assert {m["Target"] for m in app["docker_overrides"]["mounts"]} == expected_targets
    image = json.loads(network.docker("image", "inspect", build["imageId"]).stdout)[0]
    assert image["Config"]["Labels"]["io.browser-platform.session-auth"] == "1"
    assert image["Config"]["Labels"]["io.browser-platform.session-auth-input-sha256"] == build["inputSHA256"]
    root = Path(tempfile.mkdtemp(prefix="bp-r5d-invalid-auth-", dir="/dev/shm"))
    resources, results = [], []
    network.write_json(output / "resources.json", {"tmpfs": str(root), "containers": resources})
    try:
        for case in ("missing-input", "wrong-session", "permissive-file", "symlink-file", "writable-input"):
            sid, user, password = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
            directory = root / case
            directory.mkdir(mode=0o700)
            binding = {"version": 1, "session_id": str(uuid.uuid4()) if case == "wrong-session" else sid, "uid": os.geteuid()}
            network.write_json(directory / "binding.json", binding)
            salt = os.urandom(16)
            verifier = user + ":{SSHA}" + base64.b64encode(hashlib.sha1(password.encode() + salt).digest() + salt).decode() + "\n"
            (directory / "basic.htpasswd").write_text(verifier)
            (directory / "master-token").write_text(base64.urlsafe_b64encode(os.urandom(24)).decode())
            if case == "permissive-file":
                (directory / "basic.htpasswd").chmod(0o644)
            if case == "symlink-file":
                (directory / "basic.htpasswd").unlink()
                (directory / "basic.htpasswd").symlink_to("binding.json")
            name = "bp-r5d-invalid-" + uuid.uuid4().hex[:12]
            resources.append(name)
            network.write_json(output / "resources.json", {"tmpfs": str(root), "containers": resources})
            command = ["run", "-d", "--name", name, "--label", "io.browser-platform.qa=r5d-auth-negative",
                "--network", "none", "--memory", "384m", "--cpus", "1", "--pids-limit", "256",
                "--tmpfs", "/config:rw,nosuid,nodev,uid=1000,gid=1000,size=32m",
                "--tmpfs", "/run/browser-platform-display:rw,nosuid,nodev,noexec,mode=0755,size=1m",
                "-e", "PUID=1000", "-e", "PGID=1000", "-e", "SUBFOLDER=/" + sid + "/"]
            for item in app["env"]:
                assert item["name"] not in {"PASSWORD", "CUSTOM_USER", "SELKIES_MASTER_TOKEN"}
                command += ["-e", item["name"] + "=" + item["value"]]
            for mount in app["docker_overrides"]["mounts"]:
                assert mount["ReadOnly"] is True and mount["Type"] == "bind"
                command += ["--mount", f"type=bind,src={mount['Source']},dst={mount['Target']},readonly"]
            if case != "missing-input":
                command += ["--mount", f"type=bind,src={directory},dst=/run/browser-platform-session-input" +
                            ("" if case == "writable-input" else ",readonly")]
            network.docker(*command, build["imageId"])
            deadline = time.monotonic() + 20
            marker = False
            while time.monotonic() < deadline:
                value = json.loads(network.docker("inspect", name).stdout)[0]
                log = network.docker("logs", name)
                raw = (log.stdout + log.stderr).encode()
                marker = b"SESSION_AUTH_INPUT_INVALID" in raw
                if marker or value["State"]["Status"] == "exited":
                    break
                time.sleep(.3)
            (output / (case + ".log")).write_bytes(raw)
            network.write_json(output / (case + "-inspect.json"), value)
            assert marker, "REAL_WORKER_AUTH_GATE_DID_NOT_REJECT"
            # Allow the actual s6 init failure to propagate; a still-running
            # service must never have opened nginx's display listener.
            time.sleep(1)
            value = json.loads(network.docker("inspect", name).stdout)[0]
            assert value["HostConfig"]["NetworkMode"] == "none" and not value["HostConfig"]["PortBindings"]
            if value["State"]["Status"] == "running":
                code = "import socket; s=socket.socket(); s.settimeout(.3); assert s.connect_ex(('127.0.0.1',3000))!=0"
                assert network.docker("exec", name, "python3", "-c", code, check=False).returncode == 0
            log = network.docker("logs", name)
            (output / (case + ".log")).write_text(log.stdout + log.stderr)
            network.write_json(output / (case + "-inspect.json"), value)
            results.append({"case": case, "status": "pass", "init_rejected": True, "no_display_listener": True})
            network.write_json(output / "checks.json", results)
            assert value["Config"]["Labels"]["io.browser-platform.qa"] == "r5d-auth-negative"
            network.docker("rm", "-f", "-v", name)
            print(json.dumps(results[-1]), flush=True)
    finally:
        for name in resources:
            inspected = network.docker("inspect", name, check=False)
            if inspected.returncode == 0:
                value = json.loads(inspected.stdout)[0]
                assert value["Config"]["Labels"]["io.browser-platform.qa"] == "r5d-auth-negative"
                network.docker("rm", "-f", "-v", name)
        info = root.lstat()
        assert root.parent == Path("/dev/shm") and stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
        shutil.rmtree(root)
        network.write_json(output / "cleanup.json", {"containers_removed": len(resources), "tmpfs_directory_removed": True})
    network.write_json(output / "result.json", {"status": "pass", "image": build["imageId"], "checks": results})


if __name__ == "__main__":
    main()
