#!/usr/bin/env python3
"""Coordinate the real R5D client using only an explicitly staged QA scope.

The unprivileged client receives no Docker socket or controller credentials.
Its small action protocol selects fixed operations; all identities and paths
come from the host's validated QA configuration, never from client commands.
"""

import argparse
import base64
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import stat
import socket
import socketserver
import struct
import subprocess
import time
import threading
import tempfile
import traceback
from urllib.parse import urlsplit
import uuid

from cryptography import x509
from cryptography.hazmat.primitives import serialization

CHECKS = Path(__file__).resolve().parent
PROJECT = CHECKS.parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


stage = module("entry_stage", CHECKS / "stage-entry-auth.py")
desktop = module("entry_desktop", CHECKS / "qa-desktop.py")
network = stage.network


class PrivateForward(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def verify_request(self, request, address):
        _, uid, _ = struct.unpack("3i", request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        accepted = uid == os.geteuid()
        if not accepted:
            self.rejected_peers += 1
        return accepted


class ForwardRequest(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.create_connection(("127.0.0.1", 29443), timeout=5) as upstream:
            self.request.settimeout(5)
            peers = {self.request: upstream, upstream: self.request}
            try:
                while not self.server.stopping.is_set():
                    ready, _, _ = select.select(list(peers), [], [], .3)
                    for stream in ready:
                        data = stream.recv(65536)
                        if not data:
                            return
                        peers[stream].sendall(data)
            except OSError:
                return


def client_forward(output, image):
    directory = Path(tempfile.mkdtemp(prefix="bp-r5d-entry-client-"))
    path = directory / "entry.sock"
    server = PrivateForward(str(path), ForwardRequest)
    path.chmod(0o600)
    server.rejected_peers = 0
    server.stopping = threading.Event()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # This ephemeral probe has only the QA socket mounted. UID 0 can pass
    # pathname permissions but must still be rejected by peer credentials.
    probe = "import socket; s=socket.socket(socket.AF_UNIX); s.settimeout(3); s.connect('/forward/entry.sock'); assert s.recv(1)==b''"
    network.docker("run", "--rm", "--network", "none", "--user", "0:0", "--read-only", "--memory", "64m",
        "--pids-limit", "32", "--cap-drop", "ALL", "--cap-add", "DAC_OVERRIDE", "--entrypoint", "python3",
        "--mount", f"type=bind,src={directory},dst=/forward,readonly", image, "-c", probe)
    assert server.rejected_peers == 1
    network.write_json(output / "client-network.json", {"network": "none", "transport": "private Unix socket",
        "socket_directory": str(directory),
        "client_listener": "127.0.0.1:29443", "host_target": "127.0.0.1:29443", "peer_uid": os.geteuid(),
        "wrong_uid_rejected": True})
    return directory, server


class Coordinator:
    def __init__(self, qa, output):
        self.qa, self.output = qa, output
        self.config = json.loads((qa / "adapter-config.json").read_text())
        self.active = json.loads((qa / "access/active-candidate.json").read_text())
        self.candidate = Path(self.active["candidate"])
        self.accounts = json.loads((qa / "access/test-accounts.json").read_text())
        self.profiles = {p["id"]: p for p in self.config["profiles"]}
        self.display = Path(self.active["display_runtime_root"])
        self.state = (qa / self.config["state_file"]).resolve()
        assert qa.name == "qa" and self.candidate.parent == qa.parent.parent
        assert self.config["sealskin"]["username"] == "network-qa"
        assert self.config["listen_address"] == "127.0.0.1:29110"
        assert set(self.profiles) == {"network-qa-entry-a", "network-qa-entry-b"}
        assert {p["home_name"] for p in self.profiles.values()} == {"network-qa-home-entry-a", "network-qa-home-entry-b"}
        assert self.state == qa / "adapter-state.json"
        assert self.display == Path("/dev/shm/browser-platform-r5d-display-20260914")
        self.controller()
        self.client = network.SecureClient(qa)
        self.binding_faults = {}
        self.events = []
        self.sequence = 0
        self.original_config = copy.deepcopy(self.config)
        self.original_registry = Path(self.config["access"]["users_file"]).read_bytes()
        self.accounts["ticket_seconds"] = self.config["access"]["ticket_seconds"]

    def controller(self):
        value = json.loads(network.docker("inspect", network.SERVER).stdout)[0]
        assert value["Config"]["Labels"].get(network.PREFIX + "qa") == "network-20260913"
        assert value["Image"] == json.loads((self.candidate / "images.json").read_text())["runtime"]["id"]
        mounts = {m["Destination"]: m["Source"] for m in value["Mounts"] if m["Type"] == "bind"}
        assert mounts["/config"] == str(self.qa / "config") and mounts["/storage"] == str(self.qa / "storage")
        assert mounts[stage.DISPLAY_TARGET] == str(self.display)
        return value

    def inventory(self, profile):
        definition = self.profiles[profile]
        status, inventory = self.client.call("GET", "/api/profile-runtime/" + definition["home_name"])
        assert status == 200, "QA_INVENTORY_UNAVAILABLE"
        return inventory

    def journal(self):
        with Path(str(self.state) + ".lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            return json.loads(self.state.read_text()) if self.state.exists() else {"version": 1, "bindings": {}}

    def worker(self, profile):
        inventory = self.inventory(profile)
        assert len(inventory["records"]) == len(inventory["workers"]) == 1
        value = json.loads(network.docker("inspect", inventory["workers"][0]["instance_id"]).stdout)[0]
        labels = value["Config"]["Labels"]
        assert labels[network.PREFIX + "owner"] == "network-qa"
        assert labels[network.PREFIX + "home"] == self.profiles[profile]["home_name"]
        assert labels[network.PREFIX + "profile"] == profile
        assert labels[network.PREFIX + "session-auth"] == "1"
        binding = self.journal()["bindings"][profile]
        assert labels[network.PREFIX + "session"] == binding["session_id"]
        assert labels[network.PREFIX + "operation"] == binding["operation_id"]
        return value, binding, inventory

    def observe(self, worker, profile):
        control = desktop.Desktop(worker, fixture_origin=getattr(self, "website_origin", None))
        nonce = uuid.uuid4().hex
        control.navigate(getattr(self, "website_origin", "https://entry.leak.qa.test") + "/client?nonce=" + nonce)
        network.wait(lambda: control.available_title().startswith("Browser Platform Client QA Ready"),
                     "browser fixture storage initialization", seconds=35)
        deadline = time.monotonic() + 35
        next_key = 0
        while time.monotonic() < deadline:
            if time.monotonic() >= next_key:
                control.key("F9")
                next_key = time.monotonic() + 2
            result = network.docker("exec", "--user", "1000", "-e", "DISPLAY=:1", worker,
                                    "xclip", "-selection", "clipboard", "-o", check=False)
            if result.returncode == 0 and result.stdout.startswith("BP_CLIENT_REPORT:"):
                value = json.loads(result.stdout[len("BP_CLIENT_REPORT:"):])
                if value.get("qaNonce") != nonce:
                    time.sleep(.15)
                    continue
                storage = value["storage"]
                assert set(storage) == {"cookie", "localStorage", "indexedDB"}
                assert storage["cookie"] and len(set(storage.values())) == 1
                self.sequence += 1
                network.write_json(self.output / "observations" / f"{self.sequence:03}-{profile}.json", value)
                return {"cookie_localStorage_indexedDB_equal": True,
                        "value_sha256": hashlib.sha256(storage["cookie"].encode()).hexdigest()}
            time.sleep(.15)
        (self.output / (profile + "-clipboard-timeout.txt")).write_text(result.stdout)
        network.write_json(self.output / (profile + "-clipboard-timeout.json"), {"title": control.available_title(), "expected_nonce": nonce})
        raise RuntimeError("QA_BROWSER_STORAGE_REPORT_TIMEOUT")

    def snapshot(self, browser_storage=False):
        identities, storage = {}, {}
        for profile, definition in self.profiles.items():
            value, binding, _ = self.worker(profile)
            assert value["State"]["Status"] == "running"
            identities[profile] = {"worker": value["Id"], "started_at": value["State"]["StartedAt"],
                "image": value["Image"], "home": definition["home_name"], "application": definition["application_id"],
                "session": binding["session_id"], "operation": binding["operation_id"]}
            if browser_storage:
                storage[profile] = self.observe(value["Id"], profile)
        return {"profiles": identities, "storage": storage}

    def account(self, username, enabled):
        account = next(a for a in self.accounts["accounts"] if a["username"] == username)
        command = [str(self.candidate / "bin/profile-accounts"), "put" if enabled else "disable",
                   "--config", str(self.qa / "adapter-config.json"), "--user", username]
        if enabled:
            command += ["--replace", "--profiles", account["profile"]]
        result = subprocess.run(command, input=account["password"].encode() if enabled else None, capture_output=True)
        assert result.returncode == 0, "QA_ACCOUNT_UPDATE_REJECTED"
        return {"enabled": enabled}

    def lifetime(self, seconds):
        assert seconds in {15, 1800}
        stage.stop_process(self.qa, "adapter", self.candidate / "bin/profile-adapter")
        self.config["access"]["session_seconds"] = seconds
        network.write_json(self.qa / "adapter-config.json", self.config)
        stage.start_adapter(self.qa, self.candidate / "bin/profile-adapter")
        return {"seconds": seconds}

    def binding(self, profile, restore):
        assert profile in self.profiles
        with Path(str(self.state) + ".lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            value = json.loads(self.state.read_text())
            before = copy.deepcopy(value)
            current = value["bindings"][profile]
            if restore:
                saved, replacement = self.binding_faults[profile]
                assert current == replacement, "QA_BINDING_CHANGED_DURING_FAULT"
                value["bindings"][profile] = saved
            else:
                assert profile not in self.binding_faults
                saved = copy.deepcopy(current)
                current["session_id"] = str(uuid.uuid4())
                self.binding_faults[profile] = (saved, copy.deepcopy(current))
                network.write_json(self.output / (profile + "-binding-before.json"), before)
            expected = copy.deepcopy(before)
            expected["bindings"][profile]["session_id"] = value["bindings"][profile]["session_id"]
            assert expected == value
            network.write_json(self.state, value)
        if restore:
            del self.binding_faults[profile]
        return {"restored": restore, "only_session_id_changed": True}

    def controller_restart(self):
        before = self.snapshot()
        controller = self.controller()
        status, sessions = self.client.call("GET", "/api/sessions")
        assert status == 200
        # Container restart retains its network attachments. No Worker is
        # stopped, and startup must decrypt its persisted Session snapshot.
        network.docker("restart", "-t", "10", network.SERVER)
        network.wait(lambda: network.request("POST", "/api/handshake/initiate")[0] == 200,
                     "restarted QA controller", seconds=60)
        self.client = network.SecureClient(self.qa)
        network.wait(lambda: network.request("GET", "/readyz", headers={"Host": urlsplit(self.accounts["entry_origin"]).netloc},
                                            port=29110)[0] == 200, "private TLS after controller restart", seconds=40)
        status, after_sessions = self.client.call("GET", "/api/sessions")
        assert status == 200
        before_ids = {s["session_id"] for s in sessions}
        assert before_ids == {s["session_id"] for s in after_sessions}
        after = self.snapshot()
        assert before == after and self.controller()["Id"] == controller["Id"]
        network.write_json(self.output / "controller-restart.json", {"before": before, "after": after,
            "session_ids_preserved": True, "container_restarted": True})
        return {"sessions_preserved": True, "workers_preserved": True}

    def worker_resume(self, profile):
        assert profile in self.profiles
        before, binding, _ = self.worker(profile)
        directory = self.display / ("session-" + binding["session_id"])
        assert directory.parent == self.display and directory.resolve() == directory
        assert set(p.name for p in directory.iterdir()) == {"binding.json", "basic.htpasswd", "master-token"}
        network.docker("stop", "-t", "60", before["Id"])
        stopped = json.loads(network.docker("inspect", before["Id"]).stdout)[0]
        assert stopped["State"]["Status"] == "exited" and stopped["State"]["ExitCode"] == 0
        for path in directory.iterdir():
            info = path.lstat()
            assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
            assert stat.S_IMODE(info.st_mode) == 0o600
        # An explicit fault injection for this stopped QA Worker simulates
        # losing host tmpfs across reboot, while retaining its sealed Session.
        shutil.rmtree(directory)
        body = {key: binding[key] for key in ("profile_id", "application_id", "operation_id", "session_id",
                                             "bootstrap_url", "network_policy_id", "network_policy_sha256")}
        for attempt in range(4):
            if attempt:
                time.sleep(10.2)
            status, result = self.client.call("POST", "/api/profile-runtime/" + self.profiles[profile]["home_name"] + "/resume", body)
            network.write_json(self.output / ("worker-resume-response-" + str(attempt + 1) + ".json"), {"status": status, "result": result})
            if status == 200:
                break
            assert status == 503, "QA_WORKER_RESUME_NONRETRYABLE"
        network.write_json(self.output / "worker-resume-response.json", {"status": status, "result": result})
        assert status == 200 and result["resumed"] is True, "QA_WORKER_RESUME_REJECTED"
        after, after_binding, _ = self.worker(profile)
        assert before["Id"] == after["Id"] and before["Image"] == after["Image"]
        assert before["State"]["StartedAt"] != after["State"]["StartedAt"]
        assert binding["session_id"] == after_binding["session_id"] and binding["operation_id"] == after_binding["operation_id"]
        assert set(p.name for p in directory.iterdir()) == {"binding.json", "basic.htpasswd", "master-token"}
        return {"same_generation": True, "materials_recreated": True}

    def dispatch(self, request):
        action = request.get("action")
        schemas = {"inventory_empty": set(), "snapshot": {"browser_storage"}, "disable": {"username"},
            "enable": {"username"}, "lifetime": {"seconds"}, "binding_change": {"profile"},
            "binding_restore": {"profile"}, "controller_restart": set(), "worker_resume": {"profile"}}
        assert action in schemas and set(request) <= schemas[action] | {"action"}
        if action == "inventory_empty":
            return {"empty": all(not any(self.inventory(p)[k] for k in ("records", "workers", "resources")) for p in self.profiles)}
        if action == "snapshot":
            assert isinstance(request.get("browser_storage", False), bool)
            return self.snapshot(request.get("browser_storage", False))
        if action in {"disable", "enable"}:
            assert request["username"] in {"alice", "bob"}
            return self.account(request["username"], action == "enable")
        if action == "lifetime":
            return self.lifetime(request["seconds"])
        if action in {"binding_change", "binding_restore"}:
            return self.binding(request["profile"], action == "binding_restore")
        if action == "controller_restart":
            return self.controller_restart()
        if action == "worker_resume":
            return self.worker_resume(request["profile"])
        raise AssertionError("QA_ACTION_NOT_ALLOWED")

    def restore_faults(self):
        for profile in list(self.binding_faults):
            self.binding(profile, True)
        if self.config["access"]["session_seconds"] != self.original_config["access"]["session_seconds"]:
            self.lifetime(self.original_config["access"]["session_seconds"])
        # These are temporary QA accounts. Restore their exact original
        # registry after a failed run so retries do not inherit disabled users.
        path = Path(self.config["access"]["users_file"])
        if path.read_bytes() != self.original_registry:
            temporary = path.with_suffix(".restore")
            with temporary.open("wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(self.original_registry)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)


def run(qa, output, coordinator_class=Coordinator, client_script="entry-auth-client.py", *, scope="r5d", copy_fixture=True):
    assert scope in {"r5d", "r5e"} and client_script in {"entry-auth-client.py", "release-combination-client.py"}
    assert not output.exists() and qa.parent.parent in output.parents
    output.mkdir(mode=0o700)
    for name in ("requests", "responses", "observations"):
        (output / name).mkdir(mode=0o700)
    coordinator = coordinator_class(qa, output)
    if copy_fixture:
        shutil.copyfile(CHECKS / "client-fixture.html", qa.parent / "observer/client-fixture.html")
    network.write_json(output / "accounts.json", coordinator.accounts)
    cert = x509.load_pem_x509_certificate((qa / "access/cert.pem").read_bytes())
    public = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    pin = base64.b64encode(hashlib.sha256(public).digest()).decode()
    name = "bp-" + scope + "-client-" + uuid.uuid4().hex[:12]
    forward_dir, forward = client_forward(output, json.loads((coordinator.candidate / "images.json").read_text())["checks"]["image"])
    browsers = PROJECT / "infra/camoufox/.build/playwright-client-browsers"
    command = ["docker", "run", "--rm", "--name", name, "--label", "io.browser-platform.qa=" + scope + "-entry-client",
        "--network", "none", "--user", "1000:1000", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--read-only", "--memory", "1536m", "--cpus", "1.5", "--shm-size", "256m",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m", "--tmpfs", "/config:rw,nosuid,nodev,uid=1000,gid=1000,size=32m",
        "-e", "PLAYWRIGHT_BROWSERS_PATH=/client-browsers", "--mount", f"type=bind,src={browsers},dst=/client-browsers,readonly",
        "--mount", f"type=bind,src={CHECKS},dst=/checks,readonly", "--mount", f"type=bind,src={output},dst=/evidence",
        "--mount", f"type=bind,src={forward_dir},dst=/forward,readonly",
        "--entrypoint", "/opt/camoufox-python/bin/python", "browser-platform/camoufox:0.5.6-beta.30-r4",
        "/checks/" + client_script, "--config", "/evidence/accounts.json", "--output", "/evidence", "--certificate-spki", pin,
        "--forward-socket", "/forward/entry.sock"]
    network.write_json(output / "resources.json", {"client": name, "qa": str(qa), "candidate": str(coordinator.candidate)})
    processed, last_stage = set(), ""
    try:
        with (output / "client.log").open("w") as log:
            os.fchmod(log.fileno(), 0o600)
            process = subprocess.Popen(["sg", "docker", "-c", shlex.join(command)], stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 1200
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise RuntimeError("QA_CLIENT_BUDGET_EXCEEDED")
                for path in sorted((output / "requests").glob("*.json")):
                    if path.name in processed:
                        continue
                    assert re.fullmatch(r"[a-f0-9]{32}\.json", path.name)
                    info = path.lstat()
                    assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size < 4096
                    request = json.loads(path.read_text())
                    try:
                        result = coordinator.dispatch(request)
                        response = {"status": "ok", "result": result}
                    except Exception as exc:
                        with (output / "host-errors.log").open("a") as errors:
                            os.fchmod(errors.fileno(), 0o600)
                            traceback.print_exc(file=errors)
                        response = {"status": "error", "errorType": type(exc).__name__}
                    network.write_json(output / "responses" / path.name, response)
                    processed.add(path.name)
                    coordinator.events.append({"action": request["action"], "status": response["status"]})
                    network.write_json(output / "host-actions.json", coordinator.events)
                report_path = output / "client-result.json"
                if report_path.exists():
                    try:
                        report = json.loads(report_path.read_text())
                        if report["stage"] != last_stage:
                            last_stage = report["stage"]
                            print(json.dumps({"stage": last_stage, "status": report["status"]}), flush=True)
                    except json.JSONDecodeError:
                        pass
                time.sleep(.1)
            code = process.returncode
        report = json.loads((output / "client-result.json").read_text()) if (output / "client-result.json").exists() else {"status": "fail"}
        result = {"status": report["status"], "client_exit_code": code, "checks": report.get("checks", []),
            "candidate": str(coordinator.candidate), "finished_at": datetime.now(timezone.utc).isoformat()}
        network.write_json(output / "result.json", result)
        print(json.dumps(result), flush=True)
        return 0 if code == 0 and result["status"] == "pass" else 1
    finally:
        network.docker("rm", "-f", name, check=False)
        forward.stopping.set()
        forward.shutdown()
        forward.server_close()
        socket_path = forward_dir / "entry.sock"
        assert stat.S_ISSOCK(socket_path.lstat().st_mode) and socket_path.lstat().st_uid == os.geteuid()
        socket_path.unlink()
        forward_dir.rmdir()
        coordinator.restore_faults()
        network.write_json(output / "client-cleanup.json", {"removed": network.docker("inspect", name, check=False).returncode != 0,
            "private_network_namespace_removed": True, "forward_closed": True, "wrong_uid_rejected": forward.rejected_peers >= 1,
            "qa_faults_restored": True})


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return run(args.root.resolve(), args.output.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
