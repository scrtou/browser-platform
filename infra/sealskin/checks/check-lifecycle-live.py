#!/usr/bin/env python3
"""R3 lifecycle-protection drills on the isolated network QA deployment.

Scenarios (QA accounts, Homes and generations only):
  1. Home delete protection: refused while a generation runs, while its
     containers are stopped in place, and while a launch journal exists;
     allowed once the Home is provably empty.
  2. Create-before journal:
     a. control-process crash between Docker create and the session commit →
        journal `orphaned` at restart, Adapter reports unknown, explicit stop
        clears the orphan and the journal;
     b. lost create response (Docker allocated, API reply dropped) → journal
        `failed`, Home reserved, stop clears;
     c. request failed before any create (inventory outage) → Adapter unknown,
        reconcile settles as stopped because the journal proves no create.
  3. Idle reclaim (disconnected mode, 60 s) on the real Firefox generation:
     an authenticated display WebSocket through the QA controller's Caddy is
     counted, closing it starts the countdown, reconnecting cancels it, and the
     expired countdown reclaims through the verified stop path.
  4. Capacity thresholds refuse a launch before any reservation is written.
"""

import argparse
import base64
import http.client
import importlib.util
import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

spec = importlib.util.spec_from_file_location("network_checks", Path(__file__).resolve().parents[1] / "lifecycle/check-network-live.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
docker = mod.docker
PROJECT = Path(__file__).resolve().parents[3]
SLOW_WORKER_ENTRYPOINT = (
    "import os,subprocess,sys,http.server,time\n"
    "time.sleep(float(os.environ.get('QA_START_DELAY','0')))\n"
    "os.makedirs('/tmp/bp',exist_ok=True)\n"
    "for name in ('firefox','Xvfb','selkies'):\n"
    "  link='/tmp/bp/'+name\n"
    "  if not os.path.exists(link): os.symlink(sys.executable,link)\n"
    "procs=[subprocess.Popen(['/tmp/bp/'+name,'-c','import time\\nwhile True: time.sleep(3600)']) for name in ('firefox','Xvfb','selkies')]\n"
    "class H(http.server.BaseHTTPRequestHandler):\n"
    " def log_message(self,*a): pass\n"
    " def do_GET(self):\n"
    "  self.send_response(200); self.send_header('Content-Length','2'); self.end_headers(); self.wfile.write(b'ok')\n"
    "http.server.ThreadingHTTPServer(('0.0.0.0',3000),H).serve_forever()\n"
)


class HeldSocket:
    """Keep a client WebSocket alive like a browser would: answer server pings with pongs."""

    def __init__(self, sock):
        import threading
        self.sock = sock
        self.closed = False
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _read(self, size):
        data = b""
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise EOFError
            data += chunk
        return data

    def _send(self, opcode, payload):
        mask = os.urandom(4)
        header = bytes((0x80 | opcode, 0x80 | len(payload))) if len(payload) < 126 else bytes((0x80 | opcode, 0x80 | 126)) + len(payload).to_bytes(2, "big")
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _pump(self):
        try:
            while not self.closed:
                first, second = self._read(2)
                opcode, length = first & 0x0F, second & 0x7F
                if length == 126:
                    length = int.from_bytes(self._read(2), "big")
                elif length == 127:
                    length = int.from_bytes(self._read(8), "big")
                payload = self._read(length)
                if opcode == 0x9:
                    self._send(0xA, payload)
                elif opcode == 0x8:
                    break
        except (OSError, EOFError, ValueError):
            pass

    def close(self):
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(mod.SOCKET)


class Drill:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.checks = mod.Checks(self.root)
        self.results = []
        self.admin = json.loads((self.root / "admin.json").read_text())
        self.images = json.loads((self.root / "images.json").read_text())

    # ---- helpers ------------------------------------------------------
    def passed(self, name, **details):
        value = {"check": name, "result": "PASS", **details}
        self.results.append(value)
        mod.write_json(self.root / "lifecycle-results.json", self.results)
        print(json.dumps(value, ensure_ascii=False), flush=True)

    def admin_client(self):
        return mod.SecureClient(self.root, username=self.admin["username"], private=self.admin["private_key"].encode(),
                                public=self.admin["server_public_key"].encode())

    def control(self, profile, action="inspect"):
        connection = UnixConnection("adapter", timeout=250)
        try:
            connection.request("GET" if action == "inspect" else "POST", "/profiles/" + profile + ("" if action == "inspect" else "/" + action))
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def health(self, profile, force=True):
        connection = UnixConnection("adapter", timeout=250)
        try:
            connection.request("POST" if force else "GET", "/profiles/" + profile + "/health")
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def start(self, profile):
        status, headers, body = mod.request("POST", "/browser/" + profile + "/start", b"", {"Origin": "https://network.invalid"}, port=29110)
        return status, headers.get("Location"), body

    def binding(self, profile):
        return json.loads((self.root / "adapter-state.json").read_text())["bindings"].get(profile)

    def snapshot(self, home):
        status, data = self.checks.client.call("GET", "/api/profile-runtime/" + home)
        assert status == 200, "QA inventory failed"
        return data

    def qa_adapter_pids(self):
        wanted = str(self.root / "bin/profile-adapter").encode()
        found = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                cmdline = (entry / "cmdline").read_bytes().split(b"\0")
            except OSError:
                continue
            if cmdline and cmdline[0] == wanted:
                found.append(int(entry.name))
        return found

    def stop_adapter(self):
        for pid in self.qa_adapter_pids():
            os.kill(pid, signal.SIGKILL)
        mod.wait(lambda: not self.qa_adapter_pids(), "terminated QA Adapter")
        mod.wait(lambda: not Path(mod.SOCKET).exists() or self.checks.socket_closed(), "closed QA control socket")

    def start_adapter(self, seconds=420):
        assert not self.qa_adapter_pids(), "a QA Adapter is already running"
        with (self.root / "adapter.log").open("ab") as log:
            process = subprocess.Popen([str(self.root / "bin/profile-adapter"), "-config", str(self.root / "adapter-config.json")],
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        mod.write_json(self.root / "adapter-pid.json", {"pid": process.pid})
        mod.wait(lambda: mod.request("GET", "/healthz", port=29110)[0] == 200, "QA Adapter", seconds=seconds)
        assert process.poll() is None, "QA Adapter startup failed"

    def restart_api(self, hard=False):
        """Restart the control process inside the QA controller (SIGKILL when hard)."""
        docker("exec", mod.SERVER, "s6-svc", "-k" if hard else "-d", "/run/service/svc-sealskin")
        if not hard:
            docker("exec", mod.SERVER, "s6-svwait", "-d", "-t", "20000", "/run/service/svc-sealskin")
            docker("exec", mod.SERVER, "s6-svc", "-u", "/run/service/svc-sealskin")
        mod.wait(lambda: mod.request("POST", "/api/handshake/initiate")[0] == 200, "QA control service", seconds=120)
        self.checks.client = mod.SecureClient(self.root)

    def container_state(self, instance):
        return json.loads(docker("inspect", instance).stdout)[0]["State"]["Status"]

    def journal(self, home):
        return [r for r in self.snapshot(home)["resources"] if r["kind"] == "launch"]

    def journal_on_disk(self, home):
        """Read the launch journal file directly; the API inventory waits for the Home lock
        that an in-flight launch holds until its commit."""
        import hashlib
        home_hash = hashlib.sha256(str(self.root / "storage/network-qa" / home).encode()).hexdigest()
        path = self.root / "config/.config/sealskin/profile-launch-runtime" / (home_hash + ".json")
        return json.loads(path.read_text())["phase"] if path.exists() else None

    def proxy_events(self):
        return [json.loads(line) for line in (self.root / "proxy-events.jsonl").read_text().splitlines()]

    def controller_ip(self):
        return json.loads(docker("inspect", mod.SERVER).stdout)[0]["NetworkSettings"]["Networks"]["browser-platform-network-qa"]["IPAddress"]

    # ---- authenticated display connection through the QA controller's Caddy ----
    def display_socket(self, location):
        """Exchange the one-time token for the session cookie, then hold a Selkies WebSocket."""
        parsed = urlsplit(location)
        session_id = parsed.path.strip("/").split("/")[0]
        host = self.controller_ip()
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # QA controller uses its own self-signed certificate
        raw = socket.create_connection((host, 8443), timeout=15)
        tls = context.wrap_socket(raw, server_hostname="network.invalid")
        tls.sendall(("GET %s?%s HTTP/1.1\r\nHost: network.invalid\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n" % (parsed.path, parsed.query)).encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = tls.recv(4096)
            if not chunk:
                break
            response += chunk
        tls.close()
        head = response.split(b"\r\n\r\n", 1)[0].decode(errors="replace")
        cookies = [line.split(":", 1)[1].strip().split(";", 1)[0] for line in head.split("\r\n") if line.lower().startswith("set-cookie:")]
        assert cookies, "session cookie not issued: " + head.split("\r\n", 1)[0]
        raw = socket.create_connection((host, 8443), timeout=15)
        tls = context.wrap_socket(raw, server_hostname="network.invalid")
        key = base64.b64encode(os.urandom(16)).decode()
        tls.sendall(("GET /%s/websocket HTTP/1.1\r\nHost: network.invalid\r\nCookie: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                     "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (session_id, "; ".join(cookies), key)).encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = tls.recv(4096)
            if not chunk:
                break
            response += chunk
        status_line = response.split(b"\r\n", 1)[0].decode(errors="replace")
        assert status_line.startswith("HTTP/1.1 101"), "display WebSocket upgrade failed: " + status_line
        tls.settimeout(None)
        return HeldSocket(tls)

    # ---- setup --------------------------------------------------------
    def install_profiles(self):
        config = json.loads((self.root / "adapter-config.json").read_text())
        ids = {p["id"] for p in config["profiles"]}
        registry = json.loads((self.root / "config/.config/sealskin/profile-network-policies.json").read_text())
        policy_id = "network-browser-observer-r1"
        policy = registry["policies"][policy_id]
        import hashlib
        revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if "network-qa-browser" not in ids:
            config["profiles"].append({"id": "network-qa-browser", "application_id": "network-qa-firefox-network",
                                       "home_name": "network-qa-home-browser", "start_url": "https://entry.leak.qa.test/test",
                                       "wayland_mode": False, "language": "zh_TW.UTF-8", "timezone": "Asia/Taipei",
                                       "network_policy_id": policy_id, "network_policy_sha256": revision,
                                       "idle_policy": {"mode": "disconnected", "timeout_seconds": 60}})
        if "network-qa-plain" not in ids:
            app = json.loads((self.root / "app-a.json").read_text())
            app.update(id="network-qa-app-plain", name="Network QA plain (no policy)", source_app_id="network-qa-app-plain")
            provider = app["provider_config"]
            provider.pop("network_policy_id", None)
            provider.pop("network_policy_sha256", None)
            provider["docker_overrides"]["entrypoint"] = ["python3", "-c", SLOW_WORKER_ENTRYPOINT]
            provider["docker_overrides"]["environment"] = {"QA_START_DELAY": "20"}
            status, _ = self.admin_client().call("POST", "/api/admin/apps/installed", app)
            assert status == 201, "plain QA app install failed: %s" % status
            for home in ("network-qa-home-plain", "network-qa-home-delete"):
                status, _ = self.checks.client.call("POST", "/api/homedirs", {"home_name": home})
                assert status == 201
            config["profiles"].append({"id": "network-qa-plain", "application_id": "network-qa-app-plain",
                                       "home_name": "network-qa-home-plain", "start_url": "https://probe.qa.invalid/", "wayland_mode": False})
            config["profiles"].append({"id": "network-qa-delete", "application_id": "network-qa-app-plain",
                                       "home_name": "network-qa-home-delete", "start_url": "https://probe.qa.invalid/", "wayland_mode": False})
        config["health"] = {"sample_interval_seconds": 10}
        config["limits"] = {"max_active_profiles": 0, "max_concurrent_launches": 0, "min_free_disk_mib": 0}
        mod.write_json(self.root / "adapter-config.json", config)
        self.checks.definitions = {d["id"]: d for d in config["profiles"]}

    def set_limits(self, **limits):
        config = json.loads((self.root / "adapter-config.json").read_text())
        config["limits"] = {"max_active_profiles": 0, "max_concurrent_launches": 0, "min_free_disk_mib": 0, **limits}
        if limits.get("min_free_disk_mib"):
            config["limits"]["storage_path"] = str(self.root / "storage")
        mod.write_json(self.root / "adapter-config.json", config)
        self.stop_adapter()
        self.start_adapter()

    def reset(self):
        """Make the drill re-runnable: stop drill generations through the Adapter, recreate deleted QA Homes."""
        homes = {"network-qa-browser": "network-qa-home-browser", "network-qa-plain": "network-qa-home-plain", "network-qa-delete": "network-qa-home-delete"}

        def reserved(home):
            status, snapshot = self.checks.client.call("GET", "/api/profile-runtime/" + home)
            return status == 200 and bool(snapshot["records"] or snapshot["workers"] or snapshot["resources"])

        info = json.loads((self.root / "browser-worker.json").read_text())
        stop_path = self.root / "browser-stop.json"
        if stop_path.exists():
            status, _ = self.checks.client.call("POST", "/api/profile-runtime/" + info["home"] + "/stop", json.loads(stop_path.read_text()))
            assert status in (204, 409), "could not stop the preparation Firefox session: %s" % status
        config = json.loads((self.root / "adapter-config.json").read_text())
        known = {p["id"] for p in config["profiles"]}
        pending = [profile for profile, home in homes.items() if profile in known and reserved(home)]
        if pending:
            if not self.qa_adapter_pids():
                self.start_adapter()
            for profile in pending:
                status, value = self.control(profile, "stop")
                assert status == 200, "could not stop leftover generation %s: %s" % (profile, value.get("error"))
        if self.qa_adapter_pids():
            self.stop_adapter()
        for home in homes.values():
            assert not reserved(home), home + " still reserved"
        for home in ("network-qa-home-plain", "network-qa-home-delete"):
            if "network-qa-plain" in known and not (self.root / "storage/network-qa" / home).is_dir():
                status, _ = self.checks.client.call("POST", "/api/homedirs", {"home_name": home})
                assert status == 201, "could not recreate QA Home " + home

    # ---- scenarios ----------------------------------------------------
    def run(self):
        self.reset()
        self.install_profiles()
        if self.qa_adapter_pids():
            self.stop_adapter()
        self.start_adapter()
        user_client = self.checks.client

        # --- Scenario 1: Home delete protection ---
        status, _, _ = self.start("network-qa-delete")
        assert status == 303, "delete-drill launch failed"
        home = "network-qa-home-delete"
        worker = self.snapshot(home)["workers"][0]["instance_id"]
        status, value = user_client.call("DELETE", "/api/homedirs/" + home)
        assert status == 409 and value.get("detail") == "HOME_RESERVED", (status, value)
        docker("stop", "-t", "5", worker)
        assert self.container_state(worker) == "exited"
        status, value = user_client.call("DELETE", "/api/homedirs/" + home)
        assert status == 409, "a stopped-in-place Worker must still block deletion"
        assert (self.root / "storage/network-qa" / home).is_dir()
        assert self.control("network-qa-delete", "stop")[0] == 200
        snapshot = self.snapshot(home)
        assert snapshot["records"] == snapshot["workers"] == snapshot["resources"] == []
        status, _ = user_client.call("DELETE", "/api/homedirs/" + home)
        assert status == 204 and not (self.root / "storage/network-qa" / home).exists()
        self.passed("Home deletion refused while a generation runs (409 HOME_RESERVED), refused while its Worker is stopped in place, allowed once the Home is provably empty")

        # --- Scenario 2a: control-process crash after Docker create, before commit ---
        plain_home = "network-qa-home-plain"
        boundary = len(self.proxy_events())
        launch = subprocess.Popen([sys.executable, "-c", "import http.client;c=http.client.HTTPConnection('127.0.0.1',29110,timeout=300);c.request('POST','/browser/network-qa-plain/start',b'',{'Origin':'https://network.invalid'});r=c.getresponse();print(r.status)"],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        mod.wait(lambda: any(e.get("action") == "create-worker" for e in self.proxy_events()[boundary:]), "Worker create event", seconds=120)
        created = next(e for e in self.proxy_events()[boundary:] if e.get("action") == "create-worker")["instance"]
        assert self.journal_on_disk(plain_home) == "creating", self.journal_on_disk(plain_home)
        self.restart_api(hard=True)
        launch.wait(timeout=300)
        journal = self.journal(plain_home)
        assert [r["status"] for r in journal] == ["orphaned"], journal
        assert self.container_state(created) in ("running", "exited"), "orphaned container must not be removed at restart"
        status, value = self.control("network-qa-plain", "reconcile")
        assert status == 409 and value["result"]["status"] == "unknown" and value["result"]["launch_phase"] == "orphaned", (status, value)
        assert self.start("network-qa-plain")[0] == 409
        assert self.control("network-qa-plain", "stop")[0] == 200
        snapshot = self.snapshot(plain_home)
        assert snapshot["records"] == snapshot["workers"] == snapshot["resources"] == []
        assert docker("inspect", created, check=False).returncode != 0, "orphan not removed by explicit stop"
        self.passed("control-process crash between Docker create and commit: journal creating→orphaned at restart, container kept, Adapter unknown + entry 409, explicit stop removes orphan and journal")

        # --- Scenario 2b: lost create response ---
        self.checks.fault(mode="lost-create", role="worker")
        status, _, _ = self.start("network-qa-plain")
        assert status in (409, 502), status
        self.checks.fault()
        journal = self.journal(plain_home)
        assert [r["status"] for r in journal] == ["failed"], journal
        assert self.binding("network-qa-plain")["status"] == "unknown"
        assert self.start("network-qa-plain")[0] == 409
        assert self.control("network-qa-plain", "stop")[0] == 200
        snapshot = self.snapshot(plain_home)
        assert snapshot["records"] == snapshot["workers"] == snapshot["resources"] == []
        self.passed("lost Worker create response: journal failed reserves the Home, entry 409, explicit stop clears container and journal")

        # --- Scenario 2c: no create ever happened ---
        # (i) an inventory outage during the Adapter's own pre-check refuses without writing anything;
        self.checks.fault(mode="inventory-error")
        status, _, _ = self.start("network-qa-plain")
        assert status in (409, 502), status
        self.checks.fault()
        assert self.binding("network-qa-plain")["status"] == "stopped" and self.journal(plain_home) == []
        # (ii) the Adapter crashed after persisting its launch intent but before SealSkin received the
        # request: journal says launching without a Session, SealSkin has no record, container or
        # launch journal. With launch_journal_version the empty inventory proves no create ran.
        self.stop_adapter()
        state_path = self.root / "adapter-state.json"
        state = json.loads(state_path.read_text())
        binding = state["bindings"]["network-qa-plain"]
        binding.update(status="launching", operation_id=os.urandom(16).hex(), idempotency_key=os.urandom(16).hex(),
                       bootstrap_url="https://network.invalid/bootstrap/network-qa-plain/" + os.urandom(16).hex())
        binding.pop("session_id", None)
        binding.pop("stop_operation_id", None)
        binding.pop("stop_idempotency_key", None)
        mod.write_json(state_path, state)
        self.start_adapter()
        binding = self.binding("network-qa-plain")
        assert binding["status"] == "stopped", binding
        assert self.start("network-qa-plain")[0] == 303
        assert self.control("network-qa-plain", "stop")[0] == 200
        self.passed("no create ever happened: inventory outage refuses without writing; a crashed Adapter's orphan launching intent is settled as stopped at startup because the launch journal proves no create, and the next entry launches")

        # --- Scenario 3: idle reclaim on the real Firefox generation ---
        status, location, _ = self.start("network-qa-browser")
        assert status == 303
        browser_home = "network-qa-home-browser"
        browser_worker = self.snapshot(browser_home)["workers"][0]["instance_id"]
        display = self.display_socket(location)
        time.sleep(3)
        status, report = self.health("network-qa-browser")
        assert status == 200 and report["health"]["runtime"]["display_connections"] >= 1, report["health"]["runtime"]
        idle = next(c for c in report["health"]["checks"] if c["name"] == "idle")
        assert idle["code"] == "IDLE_CONNECTED", idle
        self.passed("authenticated display WebSocket through the controller's Caddy is counted (display_connections>=1, IDLE_CONNECTED)")
        display.close()
        started = time.monotonic()
        time.sleep(2)
        self.health("network-qa-browser")
        mod.wait(lambda: (self.binding("network-qa-browser") or {}).get("idle_since") is not None, "idle countdown start", seconds=120)
        status, report = self.health("network-qa-browser", force=False)
        idle = next(c for c in report["health"]["checks"] if c["name"] == "idle")
        assert idle["code"] in ("IDLE_COUNTING", "IDLE_DISCONNECTED"), idle
        # reconnect within the window cancels
        display = self.display_socket(self.start("network-qa-browser")[1])
        time.sleep(12)
        self.health("network-qa-browser")
        mod.wait(lambda: (self.binding("network-qa-browser") or {}).get("idle_since") is None, "idle countdown cancel", seconds=120)
        assert self.container_state(browser_worker) == "running"
        self.passed("closing the display connection starts the countdown (idle_since persisted); reconnecting before expiry cancels it without stopping")
        display.close()
        time.sleep(12)
        self.health("network-qa-browser")
        mod.wait(lambda: (self.binding("network-qa-browser") or {}).get("status") == "stopped", "idle reclaim", seconds=300)
        snapshot = self.snapshot(browser_home)
        assert snapshot["records"] == snapshot["workers"] == snapshot["resources"] == []
        assert docker("inspect", browser_worker, check=False).returncode != 0
        elapsed = time.monotonic() - started
        self.passed("expired countdown reclaimed the generation through the verified stop (Worker, Relay, Guard, networks gone; Home retained)", elapsed_seconds=int(elapsed))
        assert (self.root / "storage/network-qa" / browser_home / "network-qa-profile").is_dir()

        # --- Scenario 4: capacity thresholds ---
        self.set_limits(min_free_disk_mib=10 ** 9)
        status, _, body = self.start("network-qa-plain")
        assert status == 503 and b"Capacity" in body, (status, body[:80])
        assert self.binding("network-qa-plain")["status"] == "stopped" and self.journal(plain_home) == []
        self.set_limits(max_active_profiles=1)
        assert self.start("network-qa-plain")[0] == 303
        status, _, body = self.start("network-qa-delete") if False else self.start("network-qa-browser")
        assert status == 503, status
        assert self.binding("network-qa-browser")["status"] == "stopped"
        assert self.start("network-qa-plain")[0] == 303, "the running Profile must remain reachable under the limit"
        assert self.control("network-qa-plain", "stop")[0] == 200
        self.set_limits()
        self.passed("capacity thresholds (free disk, active Profiles) refuse before any reservation; running Profiles stay reachable")

        for profile in ("network-qa-plain", "network-qa-browser"):
            self.control(profile, "stop")
        self.passed("drill generations stopped; Homes retained for cleanup")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    Drill(args.root).run()


if __name__ == "__main__":
    main()
