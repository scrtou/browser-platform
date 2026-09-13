#!/usr/bin/env python3
"""Run scoped real-Docker network lifecycle checks against a prepared QA server.

Requires prepare-network-qa.py's private fixtures. Only network-qa accounts, Homes,
containers and private bridge listeners are mutated. Session URLs stay private.
"""

import argparse
import base64
import http.client
import json
import os
import shlex
import signal
import socket
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SERVER = "sealskin-network-qa"
SOCKET = "/tmp/browser-platform-network-qa.sock"
PREFIX = "io.browser-platform."


def write_json(path, data):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(data, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def docker(*args, check=True):
    result = subprocess.run(
        ["sg", "docker", "-c", shlex.join(["docker", *args])],
        capture_output=True,
        text=True,
    )
    if check and result.returncode:
        raise RuntimeError("QA Docker operation failed: " + result.stderr[:300])
    return result


def request(method, path, body=None, headers=None, port=28110):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=110)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def wait(predicate, description, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (OSError, http.client.HTTPException, json.JSONDecodeError):
            pass
        time.sleep(0.3)
    raise RuntimeError("Timed out waiting for " + description)


class SecureClient:
    def __init__(
        self, root, username="network-qa", private=None, public=None, port=28110
    ):
        self.username, self.port = username, port
        self.private = private or (root / "client-private.pem").read_bytes()
        public = serialization.load_pem_public_key(
            public or (root / "server-public.pem").read_bytes()
        )
        status, _, raw = request("POST", "/api/handshake/initiate", port=port)
        assert status == 200, "QA handshake failed"
        value = json.loads(raw)
        public.verify(
            base64.b64decode(value["signature"]),
            base64.b64decode(value["nonce"]),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
            hashes.SHA256(),
        )
        self.key = os.urandom(32)
        wrapped = public.encrypt(
            self.key,
            padding.OAEP(
                mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None
            ),
        )
        status, _, raw = request(
            "POST",
            "/api/handshake/exchange",
            json.dumps({"encrypted_session_key": base64.b64encode(wrapped).decode()}),
            {"Content-Type": "application/json"},
            port,
        )
        assert status == 200, "QA key exchange failed"
        self.session = json.loads(raw)["session_id"]

    def call(self, method, path, value=None):
        now = int(time.time())
        headers = {
            "Authorization": "Bearer "
            + jwt.encode(
                {"sub": self.username, "iat": now, "exp": now + 300},
                self.private,
                algorithm="RS256",
            ),
            "X-Session-ID": self.session,
            "Content-Type": "application/json",
        }
        body = None
        if value is not None:
            headers["X-Idempotency-Key"] = uuid.uuid4().hex
            iv = os.urandom(12)
            cipher = AESGCM(self.key).encrypt(iv, json.dumps(value).encode(), None)
            body = json.dumps(
                {
                    "iv": base64.b64encode(iv).decode(),
                    "ciphertext": base64.b64encode(cipher).decode(),
                }
            )
        status, _, raw = request(method, path, body, headers, self.port)
        if not raw:
            return status, None
        envelope = json.loads(raw)
        if "iv" not in envelope:
            assert status >= 400, "Unencrypted QA success response"
            return status, envelope
        plain = AESGCM(self.key).decrypt(
            base64.b64decode(envelope["iv"]),
            base64.b64decode(envelope["ciphertext"]),
            None,
        )
        return status, json.loads(plain)


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET)


class Checks:
    def __init__(self, root):
        self.root = root.resolve()
        config = json.loads((self.root / "adapter-config.json").read_text())
        assert self.root.name == "qa" and config["sealskin"]["username"] == "network-qa"
        assert config["sealskin"]["api_base_url"] == "http://127.0.0.1:28110"
        self.definitions = {d["id"]: d for d in config["profiles"]}
        server = json.loads(docker("inspect", SERVER).stdout)[0]
        assert server["Config"]["Labels"].get(PREFIX + "qa") == "network-20260913"
        self.client = SecureClient(self.root)
        path = self.root / "live-results.json"
        self.results = json.loads(path.read_text()) if path.exists() else []

    def passed(self, name, **details):
        value = {"check": name, "result": "PASS", **details}
        self.results.append(value)
        write_json(self.root / "live-results.json", self.results)
        print(json.dumps(value), flush=True)

    def start_adapter(self):
        with (self.root / "adapter.log").open("ab") as log:
            process = subprocess.Popen(
                [
                    str(self.root / "bin/profile-adapter"),
                    "-config",
                    str(self.root / "adapter-config.json"),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        write_json(self.root / "adapter-pid.json", {"pid": process.pid})
        wait(lambda: request("GET", "/healthz", port=29110)[0] == 200, "QA Adapter")
        assert process.poll() is None, "QA Adapter startup failed"

    def restart_adapter(self):
        pid = json.loads((self.root / "adapter-pid.json").read_text())["pid"]
        assert (self.root / "bin/profile-adapter").resolve() == Path(
            os.readlink(f"/proc/{pid}/exe")
        ).resolve()
        os.kill(pid, signal.SIGKILL)
        wait(
            lambda: not Path(SOCKET).exists() or self.socket_closed(),
            "terminated QA Adapter",
        )
        self.start_adapter()

    def socket_closed(self):
        try:
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.connect(SOCKET)
            connection.close()
            return False
        except OSError:
            return True

    def control(self, suffix, action="inspect"):
        profile = "network-qa-" + suffix
        connection = UnixConnection("adapter", timeout=100)
        try:
            path = (
                "/profiles/" + profile + ("" if action == "inspect" else "/" + action)
            )
            connection.request("GET" if action == "inspect" else "POST", path)
            response = connection.getresponse()
            data = json.loads(response.read())
            return response.status, data
        finally:
            connection.close()

    def binding(self, suffix):
        return json.loads((self.root / "adapter-state.json").read_text())["bindings"][
            "network-qa-" + suffix
        ]

    def snapshot(self, suffix):
        home = self.definitions["network-qa-" + suffix]["home_name"]
        status, data = self.client.call("GET", "/api/profile-runtime/" + home)
        assert status == 200 and data["network_runtime_version"] == 1, (
            "QA inventory failed"
        )
        return data

    def start(self, suffix):
        status, headers, _ = request(
            "POST",
            "/browser/network-qa-" + suffix + "/start",
            b"",
            {"Origin": "https://network.invalid"},
            port=29110,
        )
        return status, headers.get("Location")

    def fault(self, **value):
        write_json(self.root / "policy.json", value)

    def upstream(self, mode=None):
        write_json(self.root / "upstream-mode.json", {"mode": mode} if mode else {})
        if (self.root / "upstream").is_dir():
            write_json(
                self.root / "upstream/upstream-mode.json",
                {"mode": mode} if mode else {},
            )

    def resource(self, suffix, kind):
        return next(
            item for item in self.snapshot(suffix)["resources"] if item["kind"] == kind
        )["id"]

    def identity(self, instance):
        value = json.loads(docker("inspect", instance).stdout)[0]
        return {
            "id": value["Id"],
            "pid": value["State"]["Pid"],
            "started_at": value["State"]["StartedAt"],
        }

    def namespace_container(self, instance):
        container = json.loads(docker("inspect", instance).stdout)[0]
        mode = container.get("HostConfig", {}).get("NetworkMode", "")
        if mode.startswith("container:"):
            guard = json.loads(docker("inspect", mode.split(":", 1)[1]).stdout)[0]
            assert guard["Config"]["Labels"].get(PREFIX + "role") == "guard"
            assert guard["Config"]["Labels"].get(PREFIX + "operation") == container["Config"]["Labels"][PREFIX + "operation"]
            return guard
        return container

    def stop_body(self, suffix, binding=None):
        value = binding or self.binding(suffix)
        return {
            "profile_id": "network-qa-" + suffix,
            "application_id": value["application_id"],
            "operation_id": value["operation_id"],
            "session_id": value.get("session_id", ""),
            "bootstrap_url": value["bootstrap_url"],
            "network_policy_id": value["network_policy_id"],
            "network_policy_sha256": value["network_policy_sha256"],
        }

    def assert_empty(self, suffix):
        value = self.snapshot(suffix)
        assert value["records"] == value["workers"] == value["resources"] == [], (
            "QA resources still reserve Home"
        )
        assert self.binding(suffix)["status"] == "stopped", (
            "Adapter did not commit stopped"
        )

    def restart_controller(self):
        docker("exec", SERVER, "s6-svc", "-d", "/run/service/svc-sealskin")
        docker(
            "exec",
            SERVER,
            "s6-svwait",
            "-d",
            "-t",
            "20000",
            "/run/service/svc-sealskin",
        )
        docker("exec", SERVER, "s6-svc", "-u", "/run/service/svc-sealskin")
        wait(
            lambda: request("POST", "/api/handshake/initiate")[0] == 200,
            "QA control service",
        )
        self.client = SecureClient(self.root)

    def probe_worker(self, instance, relay, success=True):
        build = json.loads((self.root / "images.json").read_text()).get(
            "build", "build-v1"
        )
        script = self.root.parent / build / "payload/app/network_probe.py"
        source = script.read_text()
        ca = (
            self.root / "config/.config/sealskin/network-secrets/probe-ca.pem"
        ).read_text()
        source = source.replace(
            "ssl.create_default_context(cafile=ca_file or None)",
            "ssl.create_default_context(cadata=" + repr(ca) + ")",
        )
        result = docker(
            "exec",
            instance,
            "python3",
            "-c",
            source,
            relay,
            "https://probe.qa.invalid/",
            "4",
            "",
            check=False,
        )
        assert (result.returncode == 0) == success, (
            "QA Worker proxy probe result differs from expected"
        )
        if success:
            assert all(json.loads(result.stdout).values()), (
                "QA Worker direct path was not blocked"
            )

    def direct_blocked(self, instance, extra=()):
        source = """import socket,json
results=[]
for family,host,port in [(socket.AF_INET,"1.1.1.1",443),(socket.AF_INET6,"2606:4700:4700::1111",443)]+EXTRA:
 try:
  s=socket.socket(family,socket.SOCK_STREAM); s.settimeout(1); results.append(s.connect_ex((host,port))!=0); s.close()
 except OSError: results.append(True)
try: socket.getaddrinfo("probe.qa.invalid",443); results.append(False)
except socket.gaierror: results.append(True)
print(json.dumps(results))
""".replace("EXTRA", repr(list(extra)))
        value = json.loads(docker("exec", instance, "python3", "-c", source).stdout)
        assert value and all(value), "A forbidden direct path was reachable"

    def initial(self):
        if (self.root / "adapter-state.json").exists():
            values = json.loads((self.root / "adapter-state.json").read_text())[
                "bindings"
            ]
            assert all(value["status"] == "stopped" for value in values.values()), (
                "Initial retry requires confirmed stopped Profiles"
            )
        else:
            self.start_adapter()
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(lambda _: self.start("a"), range(20)))
        assert all(status == 303 for status, _ in results), (
            "20 concurrent starts did not all succeed"
        )
        assert len({url for _, url in results}) == 1, (
            "Concurrent starts returned different sessions"
        )
        assert self.start("b")[0] == 303, "Second Profile launch failed"
        workers = {}
        for suffix in ("a", "b"):
            snapshot = self.snapshot(suffix)
            assert len(snapshot["records"]) == len(snapshot["workers"]) == 1
            assert sorted(r["kind"] for r in snapshot["resources"]) == [
                "egress",
                "guard",
                "internal",
                "relay",
                "reservation",
            ]
            assert all(r["owned"] for r in snapshot["resources"])
            worker = snapshot["workers"][0]["instance_id"]
            workers[suffix] = worker
            container = json.loads(docker("inspect", worker).stdout)[0]
            assert snapshot["network_enforcement_version"] == 1
            assert container["HostConfig"]["NetworkMode"] == "container:" + self.resource(suffix, "guard")
            assert not container["NetworkSettings"]["Networks"]
            assert len(self.namespace_container(worker)["NetworkSettings"]["Networks"]) == 1
            internal = json.loads(
                docker("network", "inspect", self.resource(suffix, "internal")).stdout
            )[0]
            assert internal["Internal"] and not internal["EnableIPv6"]
            relay = json.loads(
                docker("inspect", self.resource(suffix, "relay")).stdout
            )[0]
            assert len(relay["NetworkSettings"]["Networks"]) == 2
            relay_ip = relay["NetworkSettings"]["Networks"][internal["Name"]][
                "IPAddress"
            ]
            self.probe_worker(worker, relay_ip)
            home = (
                self.root
                / "storage/network-qa"
                / self.definitions["network-qa-" + suffix]["home_name"]
            )
            (home / "network-sentinel.txt").write_text(
                "Home " + suffix + " persistent 中文\n"
            )
        assert self.resource("a", "internal") != self.resource("b", "internal")
        assert self.resource("a", "egress") != self.resource("b", "egress")
        self.passed(
            "20 concurrent requests use one generation; two Profiles have distinct internal/egress networks and Relay"
        )
        b_worker = self.namespace_container(workers["b"])
        b_relay = json.loads(docker("inspect", self.resource("b", "relay")).stdout)[0]
        targets = [
            (
                2,
                next(iter(b_worker["NetworkSettings"]["Networks"].values()))[
                    "IPAddress"
                ],
                3000,
            )
        ]
        targets.extend(
            (2, value["IPAddress"], 1080)
            for value in b_relay["NetworkSettings"]["Networks"].values()
        )
        self.direct_blocked(workers["a"], targets)
        a_worker = self.namespace_container(workers["a"])
        self.direct_blocked(
            workers["b"],
            [
                (
                    2,
                    next(iter(a_worker["NetworkSettings"]["Networks"].values()))[
                        "IPAddress"
                    ],
                    3000,
                )
            ],
        )
        self.passed(
            "real Worker HTTPS uses authenticated SOCKS5 domain requests; direct IPv4/IPv6/DNS and cross-Profile TCP are blocked"
        )
        original = {suffix: self.identity(worker) for suffix, worker in workers.items()}
        relay_id = self.resource("a", "relay")
        relay = json.loads(docker("inspect", relay_id).stdout)[0]
        internal_name = next(iter(a_worker["NetworkSettings"]["Networks"]))
        relay_ip = relay["NetworkSettings"]["Networks"][internal_name]["IPAddress"]
        self.upstream("offline")
        self.probe_worker(workers["a"], relay_ip, False)
        self.direct_blocked(workers["a"])
        assert self.start("a")[0] == 303
        self.upstream()
        docker("stop", "-t", "2", relay_id)
        self.direct_blocked(workers["a"])
        assert self.start("a")[0] == 303
        docker("start", relay_id)
        self.probe_worker(workers["a"], relay_ip)
        assert original == {
            suffix: self.identity(worker) for suffix, worker in workers.items()
        }
        self.passed(
            "Relay and upstream outages keep direct paths blocked and preserve both live Worker processes"
        )
        self.restart_controller()
        for suffix in ("a", "b"):
            assert self.control(suffix, "reconcile")[0] == 200
            assert self.start(suffix)[0] == 303
        assert original == {
            suffix: self.identity(worker) for suffix, worker in workers.items()
        }
        self.passed(
            "SealSkin service restart preserves both Workers and generation resources"
        )
        definition = self.definitions["network-qa-a"]
        body = {
            "url": "https://probe.qa.invalid/",
            "application_id": definition["application_id"],
            "home_name": definition["home_name"],
            "profile_id": definition["id"],
            "operation_id": uuid.uuid4().hex,
            "network_policy_id": definition["network_policy_id"],
            "network_policy_sha256": definition["network_policy_sha256"],
        }
        for changes in (
            {"network_policy_sha256": "f" * 64},
            {"network_policy_id": None, "network_policy_sha256": None},
        ):
            assert (
                self.client.call("POST", "/api/launch/url", {**body, **changes})[0]
                == 422
            )
        assert original == {
            suffix: self.identity(worker) for suffix, worker in workers.items()
        }
        self.passed(
            "missing and wrong policy references are rejected before allocation"
        )

    def faults(self):
        first = self.binding("a")
        worker = self.snapshot("a")["workers"][0]["instance_id"]
        relay, internal = self.resource("a", "relay"), self.resource("a", "internal")
        other = self.identity(self.snapshot("b")["workers"][0]["instance_id"])
        for mode in ("false-ack", "stop-error"):
            self.fault(mode=mode, instance=worker)
            status, value = self.control("a", "stop")
            assert status == 503 and value["result"]["status"] == "stopping"
            snapshot = self.snapshot("a")
            assert (
                snapshot["workers"][0]["status"] == "running"
                and len(snapshot["resources"]) == 5
            )
            assert self.start("a")[0] == 409
        self.passed(
            "false Docker stop acknowledgement and stop error retain Worker, Relay, networks and Home reservation"
        )
        self.fault(mode="stop-error", instance=relay)
        status, value = self.control("a", "reconcile")
        snapshot = self.snapshot("a")
        assert (
            status == 503
            and snapshot["records"] == snapshot["workers"] == []
            and {"reservation", "internal", "egress", "relay"}.issubset({r["kind"] for r in snapshot["resources"]})
        )
        assert value["result"]["status"] == "stopping"
        stop_key = self.binding("a")["stop_idempotency_key"]
        self.passed(
            "Relay stop failure after Worker deletion keeps network cleanup pending"
        )
        self.restart_adapter()
        assert (
            self.binding("a")["status"] == "stopping"
            and self.binding("a")["stop_idempotency_key"] == stop_key
        )
        self.fault(mode="network-remove-error", instance=internal)
        status, _ = self.control("a", "reconcile")
        assert status == 503
        resources = self.snapshot("a")["resources"]
        assert any(
            r["kind"] == "reservation" and r["status"] == "stopping" for r in resources
        )
        assert not any(r["kind"] == "relay" for r in resources)
        self.fault()
        assert self.control("a", "reconcile")[0] == 200
        self.assert_empty("a")
        assert self.binding("a")["stop_idempotency_key"] == stop_key
        assert self.control("a", "stop")[0] == 200
        assert other == self.identity(other["id"])
        self.passed(
            "Adapter SIGKILL and network removal failure resume the original stop until all resources disappear"
        )
        assert self.start("a")[0] == 303
        current = self.identity(self.snapshot("a")["workers"][0]["instance_id"])
        home = self.definitions["network-qa-a"]["home_name"]
        assert (
            self.client.call(
                "POST",
                "/api/profile-runtime/" + home + "/stop",
                self.stop_body("a", first),
            )[0]
            == 409
        )
        assert current == self.identity(current["id"])
        self.passed("a previous generation cannot stop the new generation")
        internal = self.resource("a", "internal")
        image = json.loads((self.root / "images.json").read_text())["probe"]
        foreign = docker(
            "run",
            "-d",
            "--name",
            "network-qa-foreign-endpoint",
            "--label",
            PREFIX + "qa=network-20260913",
            "--network",
            internal,
            "--memory",
            "32m",
            "--entrypoint",
            "python3",
            image,
            "-c",
            "import time; time.sleep(300)",
        ).stdout.strip()
        try:
            assert self.control("a", "stop")[0] == 503
            assert self.snapshot("a")["workers"] == []
            assert self.resource("a", "relay")
            assert self.identity(foreign)["pid"] != 0
        finally:
            docker("rm", "-f", foreign)
        assert self.control("a", "reconcile")[0] == 200
        self.assert_empty("a")
        assert other == self.identity(other["id"])
        self.passed(
            "foreign network attachment blocks Relay/network cleanup and the other Profile remains unchanged"
        )

    def partial(self):
        self.assert_empty("a")
        self.upstream("offline")
        assert self.start("a")[0] == 409
        snapshot = self.snapshot("a")
        assert snapshot["records"] == snapshot["workers"] == []
        assert any(r["kind"] == "reservation" for r in snapshot["resources"])
        assert self.start("a")[0] == 409
        self.upstream()
        assert self.control("a", "stop")[0] == 200
        self.assert_empty("a")
        self.passed(
            "failed prelaunch upstream probe never creates a Worker; explicit cleanup removes the partial allocation"
        )
        for role in ("internal", "relay", "guard", "worker"):
            self.fault(mode="lost-create", role=role)
            assert self.start("a")[0] == 409
            snapshot = self.snapshot("a")
            assert snapshot["resources"] and self.binding("a")["status"] == "unknown"
            self.fault()
            if role == "relay":
                self.restart_controller()
            assert self.start("a")[0] == 409
            assert self.control("a", "stop")[0] == 200
            self.assert_empty("a")
            self.passed(
                "lost "
                + role
                + " create response is found by generation and cleaned without another launch"
            )
        secret = self.root / "config/.config/sealskin/network-secrets/password"
        original = secret.read_bytes()
        try:
            secret.write_bytes(b"changed-qa-credential")
            assert self.start("a")[0] >= 400
            snapshot = self.snapshot("a")
            assert (
                snapshot["records"]
                == snapshot["workers"]
                == snapshot["resources"]
                == []
            )
        finally:
            secret.write_bytes(original)
        self.passed("credential SHA-256 drift is rejected before any Docker allocation")
        assert self.start("a")[0] == 303
        sid = self.binding("a")["session_id"]
        self.fault(mode="stop-error", instance=self.resource("a", "relay"))
        # Same endpoint the SealSkin sessions UI uses.
        status, _ = self.client.call("DELETE", "/api/sessions/" + sid)
        assert status == 503, "Direct UI stop did not expose pending network cleanup"
        assert self.snapshot("a")["records"] == self.snapshot("a")["workers"] == []
        assert any(
            r["kind"] == "reservation" and r["status"] == "stopping"
            for r in self.snapshot("a")["resources"]
        )
        self.fault()
        assert self.control("a", "reconcile")[0] == 200
        self.assert_empty("a")
        self.passed(
            "direct SealSkin UI stop persists cleanup intent even after its Session record disappears"
        )

    def finish(self):
        self.fault()
        self.upstream()
        for suffix in ("a", "b"):
            assert self.control(suffix, "stop")[0] == 200
            self.assert_empty(suffix)
            home = (
                self.root
                / "storage/network-qa"
                / self.definitions["network-qa-" + suffix]["home_name"]
            )
            assert (
                home / "network-sentinel.txt"
            ).read_text() == "Home " + suffix + " persistent 中文\n"
        self.passed(
            "final stops remove all generation resources and preserve both persistent Homes"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--stage", choices=["initial", "faults", "partial", "finish"], required=True
    )
    args = parser.parse_args()
    checks = Checks(args.root)
    getattr(checks, args.stage)()


if __name__ == "__main__":
    main()
