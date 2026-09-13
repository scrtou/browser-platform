#!/usr/bin/env python3
"""Exercise an explicitly prepared, isolated lifecycle QA deployment.

Requires the test venv (cryptography and PyJWT), qa-docker-proxy.py, a fresh
sealskin-lifecycle-qa server, and QA Adapter config/binary under --root.
Never supplies a production Home, account or container to a stop operation.
"""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import time

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROFILE = "lifecycle-qa"
HOME = "lifecycle-qa-home"
SERVER = "sealskin-lifecycle-qa"
NETWORK = "browser-platform-lifecycle-qa"
SOCKET = "/tmp/browser-platform-lifecycle-qa.sock"
IMAGE = "sha256:7e3dbebd9e730952648b8c902ce90fa72c0e2be3e786ab17026c38e0909b47f7"


def request(method, path, body=None, headers=None, port=28100):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=90)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET)


def control(action="inspect"):
    connection = UnixConnection("adapter", timeout=90)
    try:
        connection.request("GET" if action == "inspect" else "POST",
                           "/profiles/" + PROFILE + ("" if action == "inspect" else "/" + action))
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def docker(*args, check=True):
    result = subprocess.run(["sg", "docker", "-c", shlex.join(["docker", *args])],
                            text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError("QA Docker command failed: " + result.stderr[:300])
    return result.stdout


def wait_for(predicate, description, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (OSError, http.client.HTTPException, json.JSONDecodeError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Timed out waiting for " + description)


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(data, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class SecureClient:
    def __init__(self, root):
        self.private = (root / "client-private.pem").read_bytes()
        public = serialization.load_pem_public_key((root / "server-public.pem").read_bytes())
        status, _, raw = request("POST", "/api/handshake/initiate")
        assert status == 200, "QA handshake failed"
        start = json.loads(raw)
        public.verify(base64.b64decode(start["signature"]), base64.b64decode(start["nonce"]),
                      padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
        self.key = os.urandom(32)
        wrapped = public.encrypt(self.key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        status, _, raw = request("POST", "/api/handshake/exchange",
                                json.dumps({"encrypted_session_key": base64.b64encode(wrapped).decode()}),
                                {"Content-Type": "application/json"})
        assert status == 200, "QA handshake exchange failed"
        self.session = json.loads(raw)["session_id"]

    def call(self, method, path, value=None, key=None):
        now = int(time.time())
        headers = {"Authorization": "Bearer " + jwt.encode({"sub": PROFILE, "iat": now, "exp": now + 300}, self.private, algorithm="RS256"),
                   "X-Session-ID": self.session, "Content-Type": "application/json"}
        if key:
            headers["X-Idempotency-Key"] = key
        body = None
        if value is not None:
            iv = os.urandom(12)
            cipher = AESGCM(self.key).encrypt(iv, json.dumps(value).encode(), None)
            body = json.dumps({"iv": base64.b64encode(iv).decode(), "ciphertext": base64.b64encode(cipher).decode()})
        status, _, raw = request(method, path, body, headers)
        if not raw:
            return status, None
        envelope = json.loads(raw)
        if "iv" not in envelope or "ciphertext" not in envelope:
            # Upstream FastAPI HTTPException responses bypass EncryptedRoute;
            # the production Go client likewise accepts these error statuses.
            assert status >= 400, "QA success response was not encrypted"
            return status, envelope
        data = AESGCM(self.key).decrypt(base64.b64decode(envelope["iv"]), base64.b64decode(envelope["ciphertext"]), None)
        return status, json.loads(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--resume-initial", action="store_true", help="reuse only a running QA generation with no stop intent")
    args = parser.parse_args()
    root = args.root.resolve()
    assert root.name == "qa", "Explicit QA directory required"
    config = json.loads((root / "adapter-config.json").read_text())
    assert config["sealskin"]["username"] == PROFILE and config["profiles"][0]["home_name"] == HOME
    assert config["sealskin"]["api_base_url"] == "http://127.0.0.1:28100"
    if (root / "adapter-state.json").exists():
        existing = json.loads((root / "adapter-state.json").read_text())["bindings"]
        assert args.resume_initial and list(existing) == [PROFILE], "This check requires fresh QA state"
        assert existing[PROFILE]["status"] == "running" and not existing[PROFILE].get("stop_operation_id")
    server = json.loads(docker("inspect", SERVER))[0]
    assert server["Config"]["Labels"].get("io.browser-platform.qa") == "lifecycle-20260913"
    adapter = None
    results = []

    def passed(name, **details):
        entry = {"check": name, "result": "PASS", **details}
        results.append(entry)
        write_json(root / "live-results.json", results)
        print(json.dumps(entry), flush=True)

    def binding():
        return json.loads((root / "adapter-state.json").read_text())["bindings"][PROFILE]

    def start_adapter():
        log = (root / "adapter.log").open("ab")
        process = subprocess.Popen([str(root / "bin/profile-adapter"), "-config", str(root / "adapter-config.json")],
                                   stdout=log, stderr=subprocess.STDOUT)
        log.close()
        (root / "adapter-pid").write_text(str(process.pid))
        wait_for(lambda: request("GET", "/healthz", port=29100)[0] == 200, "QA Adapter")
        assert process.poll() is None, "QA Adapter exited during startup"
        return process

    def snapshot(client):
        status, data = client.call("GET", "/api/profile-runtime/" + HOME)
        assert status == 200, "QA runtime inspection failed"
        return data

    def start_browser():
        status, headers, _ = request("POST", "/browser/" + PROFILE + "/start", b"",
                                     {"Origin": "https://lifecycle.invalid"}, port=29100)
        return status, headers.get("Location")

    def policy(mode=None, instance=None):
        write_json(root / "policy.json", {"mode": mode, "instance": instance} if mode else {})

    def assert_reserved(client, instance, status="stopping"):
        current = snapshot(client)
        assert len(current["records"]) == 1 and len(current["workers"]) == 1
        assert current["workers"][0]["instance_id"] == instance and current["workers"][0]["status"] == "running"
        assert current["records"][0]["phase"] == status
        assert start_browser()[0] == 409, "An unconfirmed stop allowed another start"
        assert binding()["status"] == status

    try:
        adapter = start_adapter()
        client = SecureClient(root)
        with ThreadPoolExecutor(max_workers=20) as pool:
            starts = list(pool.map(lambda _: start_browser(), range(20)))
        assert all(status == 303 for status, _ in starts), "Concurrent QA starts failed"
        assert len({location for _, location in starts}) == 1, "Concurrent starts returned multiple sessions"
        initial = snapshot(client)
        assert len(initial["records"]) == len(initial["workers"]) == 1
        first = initial["workers"][0]["instance_id"]
        first_binding = binding()
        assert initial["workers"][0]["owned"] and initial["workers"][0]["managed"]
        home = root / "storage" / PROFILE / HOME
        sentinel = home / "lifecycle-sentinel.txt"
        sentinel.write_text("Lifecycle QA persistent Home — 中文\n")
        sentinel_hash = hashlib.sha256(sentinel.read_bytes()).hexdigest()
        passed("20 concurrent starts reuse one labeled real Worker", workers=1)

        duplicate = subprocess.run([str(root / "bin/profile-adapter"), "-config", str(root / "adapter-config.json")],
                                   capture_output=True, timeout=10)
        assert duplicate.returncode != 0 and b"another adapter owns this state file" in duplicate.stdout, "Second Adapter process was not refused"
        passed("service lifetime lock refuses a second Adapter")

        policy("false-ack", first)
        code, response = control("stop")
        assert code == 503 and response["result"]["status"] == "stopping"
        assert_reserved(client, first)
        stopped_intent = binding()
        passed("Docker false stop acknowledgment retains record, Worker and Home reservation")

        policy("stop-error", first)
        assert control("stop")[0] == 503
        assert_reserved(client, first)
        for key in ("operation_id", "stop_operation_id", "stop_idempotency_key"):
            assert stopped_intent[key] == binding()[key], "Retry changed durable stop identity"
        passed("Docker HTTP 500 stop retry preserves durable operation and idempotency key")

        policy("inventory-error")
        assert control("stop")[0] == 503
        assert start_browser()[0] in {409, 502}, "Docker outage allowed a new start"
        assert binding()["status"] == "stopping"
        passed("Docker inventory failure keeps Home reserved")

        adapter.kill()
        adapter.wait(timeout=10)
        policy()
        adapter = start_adapter()
        assert binding()["status"] == "stopped"
        current = snapshot(client)
        assert current["records"] == current["workers"] == []
        for key in ("operation_id", "stop_operation_id", "stop_idempotency_key"):
            assert stopped_intent[key] == binding()[key]
        passed("Adapter SIGKILL and restart automatically finish persisted stop")
        for _ in range(2):
            assert control("stop")[0] == 200
        assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash
        passed("repeated stop is idempotent and persistent Home content survives")

        assert start_browser()[0] == 303
        current = snapshot(client)
        second = current["workers"][0]["instance_id"]
        assert second != first and binding()["operation_id"] != first_binding["operation_id"]
        assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash
        stale = {"profile_id": PROFILE, "operation_id": first_binding["operation_id"],
                 "application_id": "lifecycle-qa-firefox", "session_id": first_binding["session_id"],
                 "bootstrap_url": first_binding["bootstrap_url"]}
        code, _ = client.call("POST", "/api/profile-runtime/" + HOME + "/stop", stale, "stale-generation-check")
        assert code == 409
        assert snapshot(client)["workers"][0]["instance_id"] == second
        passed("new generation reuses Home and rejects the previous generation's stop")

        worker_before = json.loads(docker("inspect", second))[0]["State"]["StartedAt"]
        docker("exec", SERVER, "s6-svc", "-d", "/run/service/svc-sealskin")
        def api_down():
            try:
                request("POST", "/api/handshake/initiate")
                return False
            except (OSError, http.client.HTTPException):
                return True
        wait_for(api_down, "QA SealSkin control service to stop", seconds=20)
        import yaml
        sessions_file = root / "config/.config/sealskin/sessions.yml"
        sessions = yaml.safe_load(sessions_file.read_text())
        sid = binding()["session_id"]
        assert list(sessions) == [sid] and sessions[sid]["instance_id"] == second
        del sessions[sid]
        write_json(sessions_file, sessions)  # JSON is a valid YAML subset.
        docker("exec", SERVER, "s6-svc", "-u", "/run/service/svc-sealskin")
        wait_for(lambda: request("POST", "/api/handshake/initiate")[0] == 200, "QA SealSkin service restart")
        client = SecureClient(root)
        current = snapshot(client)
        assert current["records"] == [] and len(current["workers"]) == 1 and not current["workers"][0]["recorded"]
        code, response = control("reconcile")
        assert code == 409 and response["result"]["status"] == "unknown" and response["result"]["orphans"] == 1
        assert start_browser()[0] == 409
        assert json.loads(docker("inspect", second))[0]["State"]["StartedAt"] == worker_before
        assert control("stop")[0] == 200
        assert snapshot(client)["workers"] == []
        assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash
        passed("record loss plus SealSkin service restart quarantines labeled orphan; explicit stop recovers it")

        orphan = docker("run", "-d", "--name", "lifecycle-qa-unlabeled", "--label", "io.browser-platform.qa=lifecycle-20260913",
                        "--network", NETWORK, "--memory", "32m", "--pids-limit", "16", "--entrypoint", "/bin/sleep",
                        "-v", str(home) + ":/config", IMAGE, "infinity").strip()
        try:
            assert control("stop")[0] == 409 and start_browser()[0] == 409
            assert json.loads(docker("inspect", orphan))[0]["State"]["Running"]
            passed("unlabeled unrecorded mount blocks start and automatic removal")
        finally:
            target = json.loads(docker("inspect", orphan))[0]
            assert target["Config"]["Labels"].get("io.browser-platform.qa") == "lifecycle-20260913"
            docker("rm", "-f", orphan)
        assert control("reconcile")[0] == 200
        assert snapshot(client)["records"] == snapshot(client)["workers"] == []
        passed("final QA inventory is empty; Home sentinel is preserved", sentinel_sha256=sentinel_hash)
    finally:
        policy()
        if adapter and adapter.poll() is None:
            adapter.send_signal(signal.SIGTERM)
            adapter.wait(timeout=20)
        (root / "adapter-pid").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
