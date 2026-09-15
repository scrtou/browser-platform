#!/usr/bin/env python3
"""R2 boot-recovery drills on the isolated network QA deployment.

Scenarios (all on QA accounts, Homes and generations only):
  1. real Firefox generation (Adapter-owned): write data, stop every container
     in place (as a daemon/host restart leaves them), restart the QA controller
     and the QA Adapter; startup reconciliation resumes Relay → Guard → probe →
     Worker; the same containers come back and the data is still there;
  2. probe failure (upstream offline) keeps the Worker stopped, the entry
     refuses, explicit resume after recovery succeeds;
  3. legacy (no-policy) generation resumes and the Session address is refreshed;
  4. offline backup refuses a running Profile, succeeds after confirmed stop,
     verifies, restores into a new Home and a new generation reads the data.
"""

import argparse
import base64
import hashlib
import http.client
import importlib.util
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

spec = importlib.util.spec_from_file_location("network_checks", Path(__file__).resolve().parents[1] / "lifecycle/check-network-live.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
docker = mod.docker
PROJECT = Path(__file__).resolve().parents[3]
LEGACY_ENTRYPOINT = (
    "import os,subprocess,sys,http.server\n"
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
        self.qa_dir = self.root
        self.admin = json.loads((self.root / "admin.json").read_text())

    # ---- helpers -------------------------------------------------------
    def passed(self, name, **details):
        value = {"check": name, "result": "PASS", **details}
        self.results.append(value)
        mod.write_json(self.root / "boot-results.json", self.results)
        print(json.dumps(value, ensure_ascii=False), flush=True)

    def admin_client(self):
        return mod.SecureClient(self.root, username=self.admin["username"], private=self.admin["private_key"].encode(),
                                public=self.admin["server_public_key"].encode())

    def control(self, profile, action="inspect", path_suffix=""):
        connection = UnixConnection("adapter", timeout=250)
        try:
            path = "/profiles/" + profile + ("" if action == "inspect" else "/" + action) + path_suffix
            connection.request("GET" if action in ("inspect", "health") else "POST", path)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def health(self, profile):
        connection = UnixConnection("adapter", timeout=250)
        try:
            connection.request("POST", "/profiles/" + profile + "/health")
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def start(self, profile):
        status, headers, _ = mod.request("POST", "/browser/" + profile + "/start", b"", {"Origin": "https://network.invalid"}, port=29110)
        return status, headers.get("Location")

    def launch(self, profile, home):
        """Launch through the Adapter; tolerate a slow first Firefox start on a loaded host.

        A 45 s Adapter timeout against SealSkin's 60 s readiness wait leaves the
        binding unknown; reconcile claims the session once SealSkin finished, or
        an explicit stop clears the partial generation before one retry.
        """
        for attempt in range(3):
            status, _ = self.start(profile)
            if status == 303:
                return
            time.sleep(45)
            status, value = self.control(profile, "reconcile")
            if status == 200 and value["result"]["status"] == "running":
                return
            assert self.control(profile, "stop")[0] == 200, "could not clear a partial generation"
            snapshot = self.snapshot(home)
            assert snapshot["records"] == snapshot["workers"] == snapshot["resources"] == []
        raise AssertionError("Adapter launch of " + profile + " failed three times")

    def binding(self, profile):
        return json.loads((self.root / "adapter-state.json").read_text())["bindings"][profile]

    def snapshot(self, home):
        status, data = self.checks.client.call("GET", "/api/profile-runtime/" + home)
        assert status == 200, "QA inventory failed"
        return data

    def adapter_pid(self):
        return json.loads((self.root / "adapter-pid.json").read_text())["pid"]

    def qa_adapter_pids(self):
        """Every live process running this QA root's Adapter binary (the binary may have been rebuilt)."""
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
        pids = self.qa_adapter_pids()
        assert pids, "no QA Adapter process is running"
        for pid in pids:
            os.kill(pid, signal.SIGKILL)
        mod.wait(lambda: not self.qa_adapter_pids(), "terminated QA Adapter")
        mod.wait(lambda: not Path(mod.SOCKET).exists() or self.checks.socket_closed(), "closed QA control socket")

    def start_adapter(self, seconds=420):
        assert not self.qa_adapter_pids(), "a QA Adapter is already running; the service lock would refuse a second one"
        with (self.root / "adapter.log").open("ab") as log:
            process = subprocess.Popen([str(self.root / "bin/profile-adapter"), "-config", str(self.root / "adapter-config.json")],
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        mod.write_json(self.root / "adapter-pid.json", {"pid": process.pid})
        mod.wait(lambda: mod.request("GET", "/healthz", port=29110)[0] == 200, "QA Adapter", seconds=seconds)
        assert process.poll() is None, "QA Adapter startup failed"

    def restart_controller(self):
        docker("restart", "-t", "10", mod.SERVER)
        mod.wait(lambda: mod.request("POST", "/api/handshake/initiate")[0] == 200, "QA control service", seconds=120)
        self.checks.client = mod.SecureClient(self.root)

    def identity(self, instance):
        return self.checks.identity(instance)

    def resources(self, home):
        return {item["kind"]: item["id"] for item in self.snapshot(home)["resources"]}

    def container_state(self, instance):
        return json.loads(docker("inspect", instance).stdout)[0]["State"]["Status"]

    def stop_in_place(self, *instances):
        """Stop containers without removing them: what restart=no leaves after a daemon/host restart."""
        for instance in instances:
            docker("stop", "-t", "10", instance)
        for instance in instances:
            assert self.container_state(instance) == "exited", "container not stopped in place"

    def wait_observer(self):
        """Wait until the restarted observer prints a fresh ready line and its published SOCKS port accepts.

        The Relay reaches the observer through the docker0 gateway's published
        port from the egress bridge; the QA controller sits on the observer's own
        bridge where hairpin to that published port is not available, so the
        readiness check is made from the host instead.
        """
        started = json.loads(docker("inspect", "network-qa-observer").stdout)[0]["State"]["StartedAt"]
        mod.wait(lambda: "private network observer ready" in docker("logs", "--since", started, "network-qa-observer").stdout,
                 "observer ready line", seconds=60)
        gateway = json.loads((self.root / "images.json").read_text())["upstream_host"]

        def accepts():
            try:
                with socket.create_connection((gateway, 28191), timeout=2):
                    return True
            except OSError:
                return False

        mod.wait(accepts, "observer published SOCKS port", seconds=60)

    def evaluate(self, worker, expression, navigate=False):
        source = (PROJECT / "infra/firefox-proxy/check-bidi.py").read_text().split("\ndef main()", 1)[0]
        source += '\nb=BiDi(WebSocket("127.0.0.1",9228))\nb.command("session.new",{"capabilities":{}})\ntry:\n c=b.command("browsingContext.getTree",{})["contexts"][0]["context"]\n'
        if navigate:
            source += ' b.command("browsingContext.navigate",{"context":c,"url":"https://entry.leak.qa.test/test","wait":"complete"})\n'
        source += ' print(json.dumps({"value":b.evaluate(c,' + repr(expression) + ')}))\nfinally:\n b.command("session.end",{})\n b.websocket.socket.close()\n'
        return json.loads(docker("exec", worker, "python3", "-c", source).stdout)["value"]

    def navigate(self, worker, url):
        """Navigate the QA Firefox tab; leaving a page finalizes its LocalStorage snapshot."""
        source = (PROJECT / "infra/firefox-proxy/check-bidi.py").read_text().split("\ndef main()", 1)[0]
        source += '\nb=BiDi(WebSocket("127.0.0.1",9228))\nb.command("session.new",{"capabilities":{}})\ntry:\n c=b.command("browsingContext.getTree",{})["contexts"][0]["context"]\n'
        source += ' b.command("browsingContext.navigate",{"context":c,"url":' + repr(url) + ',"wait":"complete"})\n print("ok")\nfinally:\n b.command("session.end",{})\n b.websocket.socket.close()\n'
        docker("exec", worker, "python3", "-c", source)

    def wait_bidi(self, worker):
        check = 'import socket; s=socket.create_connection(("127.0.0.1",9228),timeout=1);s.close()'
        mod.wait(lambda: docker("exec", worker, "python3", "-c", check, check=False).returncode == 0, "QA Firefox BiDi", seconds=180)

    def probe_browser_worker(self, worker, relay_ip, success=True):
        """Probe through the Relay to the browser policy's HTTPS target with the observer CA.

        The browser generation's upstream is the private observer, which only
        serves *.leak.qa.test; the network-qa-a/b probe target does not apply.
        """
        build = json.loads((self.root / "images.json").read_text())["build"]
        script = (self.root.parent / build / "payload/app/network_probe.py").read_text()
        ca = (self.root.parent / "observer/ca.pem").read_text()
        source = script.replace("ssl.create_default_context(cafile=ca_file or None)", "ssl.create_default_context(cadata=" + repr(ca) + ")")
        result = docker("exec", worker, "python3", "-c", source, relay_ip, "https://preflight.leak.qa.test/", "5", "", check=False)
        assert (result.returncode == 0) == success, "browser Worker proxy probe result differs from expected"
        if success:
            assert all(json.loads(result.stdout).values()), "browser Worker direct path was not blocked"

    def firefox_pid(self, worker):
        source = "import json\nfrom pathlib import Path\nout=[]\nfor p in Path('/proc').glob('[0-9]*'):\n try:\n  args=p.joinpath('cmdline').read_bytes().split(b'\\0')\n  if b'--remote-debugging-port' in args and b'9228' in args: out.append(int(p.name))\n except (OSError,IndexError): pass\nprint(json.dumps(out))\n"
        return json.loads(docker("exec", worker, "python3", "-c", source).stdout)

    # ---- setup ---------------------------------------------------------
    def install_profiles(self):
        """Add an Adapter-owned real Firefox Profile and a legacy no-policy Profile to the QA deployment."""
        config = json.loads((self.root / "adapter-config.json").read_text())
        ids = {p["id"] for p in config["profiles"]}
        registry = json.loads((self.root / "config/.config/sealskin/profile-network-policies.json").read_text())
        policy_id = "network-browser-observer-r1"
        policy = registry["policies"][policy_id]
        revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if "network-qa-browser" not in ids:
            config["profiles"].append({"id": "network-qa-browser", "application_id": "network-qa-firefox-network",
                                       "home_name": "network-qa-home-browser", "start_url": "https://entry.leak.qa.test/test",
                                       "wayland_mode": False, "network_policy_id": policy_id, "network_policy_sha256": revision})
        if "network-qa-legacy" not in ids:
            app = json.loads((self.root / "app-a.json").read_text())
            app.update(id="network-qa-app-legacy", name="Network QA legacy (no policy)", source_app_id="network-qa-app-legacy")
            provider = app["provider_config"]
            provider.pop("network_policy_id", None)
            provider.pop("network_policy_sha256", None)
            provider["docker_overrides"]["entrypoint"] = ["python3", "-c", LEGACY_ENTRYPOINT]
            status, _ = self.admin_client().call("POST", "/api/admin/apps/installed", app)
            assert status == 201, "legacy QA app install failed: %s" % status
            status, _ = self.checks.client.call("POST", "/api/homedirs", {"home_name": "network-qa-home-legacy"})
            assert status == 201
            config["profiles"].append({"id": "network-qa-legacy", "application_id": "network-qa-app-legacy",
                                       "home_name": "network-qa-home-legacy", "start_url": "https://probe.qa.invalid/", "wayland_mode": False})
        config["health"] = {"sample_interval_seconds": 0}
        mod.write_json(self.root / "adapter-config.json", config)
        self.checks.definitions = {d["id"]: d for d in config["profiles"]}

    def wait_local_storage(self, home, nonce, origin_dir="https+++entry.leak.qa.test"):
        """Firefox flushes LocalStorage and cookies lazily; wait until the value is on disk.

        A daemon or host restart stops the Worker hard, so only data that has
        already reached the Home directory can be expected to survive. The
        drill therefore waits for the written value itself to appear in the
        LocalStorage and cookie databases (main file or WAL) before stopping.
        """
        profile = self.root / "storage/network-qa" / home / "network-qa-profile"
        ls_dir = profile / "storage/default" / origin_dir / "ls"
        needle = nonce.encode()

        needles = (needle, nonce.encode("utf-16-le"))

        def on_disk(paths):
            return any(path.is_file() and any(n in path.read_bytes() for n in needles) for path in paths)

        mod.wait(lambda: on_disk([ls_dir / "data.sqlite", ls_dir / "data.sqlite-wal"]), "Firefox LocalStorage flush", seconds=120)
        mod.wait(lambda: on_disk([profile / "cookies.sqlite", profile / "cookies.sqlite-wal"]), "Firefox cookie flush", seconds=120)
        time.sleep(2)

    def reset(self):
        """Make the drill re-runnable: clear the preparation session and any Adapter-owned generation."""
        homes = {"network-qa-browser": "network-qa-home-browser", "network-qa-legacy": "network-qa-home-legacy",
                 "network-qa-restored": "network-qa-home-restored"}

        def reserved(home):
            status, snapshot = self.checks.client.call("GET", "/api/profile-runtime/" + home)
            return status == 200 and bool(snapshot["records"] or snapshot["workers"] or snapshot["resources"])

        # A previous aborted run may have left the observer upstream stopped (scenario 2).
        state = json.loads(docker("inspect", "network-qa-observer").stdout)[0]["State"]["Status"]
        if state != "running":
            docker("start", "network-qa-observer")
            self.wait_observer()
        for name in ("network-qa-squatter",):
            docker("rm", "-f", name, check=False)
        info = json.loads((self.root / "browser-worker.json").read_text())
        stop_path = self.root / "browser-stop.json"
        if stop_path.exists():
            # The preparation Firefox session was launched directly; a 409 means the
            # Home now belongs to an Adapter generation, handled below.
            status, _ = self.checks.client.call("POST", "/api/profile-runtime/" + info["home"] + "/stop", json.loads(stop_path.read_text()))
            assert status in (204, 409), "could not stop the preparation Firefox session: %s" % status
        pending = [profile for profile, home in homes.items() if profile in self.checks.definitions and reserved(home)]
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

    # ---- scenarios -----------------------------------------------------
    def run(self, only_backup=False):
        self.reset()
        self.install_profiles()
        self.start_adapter()
        if only_backup:
            self.backup_scenario(None)
            self.passed("drill generations stopped; Homes retained for cleanup")
            return

        # --- Scenario 1: Adapter-owned real Firefox generation ---
        home = "network-qa-home-browser"
        self.launch("network-qa-browser", home)
        worker = self.snapshot(home)["workers"][0]["instance_id"]
        resources = self.resources(home)
        self.wait_bidi(worker)
        nonce = os.urandom(8).hex()
        self.evaluate(worker, "localStorage.setItem('bp-r2', '%s'); document.cookie='bp_r2=%s; max-age=2592000; secure'; 'ok'" % (nonce, nonce), navigate=True)
        self.navigate(worker, "about:blank")
        self.wait_local_storage(home, nonce)
        assert self.evaluate(worker, "localStorage.getItem('bp-r2')", navigate=True) == nonce
        before = {name: self.identity(instance) for name, instance in [("worker", worker), ("relay", resources["relay"]), ("guard", resources["guard"])]}
        firefox_before = self.firefox_pid(worker)
        binding_before = self.binding("network-qa-browser")
        self.passed("real Firefox generation launched through the Adapter; data written", nonce_len=len(nonce))

        boundary = len((self.root / "proxy-events.jsonl").read_text().splitlines())
        self.stop_in_place(worker, resources["guard"], resources["relay"])
        self.restart_controller()
        snapshot = self.snapshot(home)
        assert snapshot["workers"][0]["status"] == "exited" and len(snapshot["resources"]) == 5
        self.stop_adapter()
        self.start_adapter()
        binding = self.binding("network-qa-browser")
        assert binding["status"] == "running" and binding["operation_id"] == binding_before["operation_id"] and binding["session_id"] == binding_before["session_id"], binding
        after = {name: self.identity(instance) for name, instance in [("worker", worker), ("relay", resources["relay"]), ("guard", resources["guard"])]}
        assert all(after[name]["id"] == before[name]["id"] for name in after), "resume replaced a container"
        assert all(self.container_state(instance) == "running" for instance in (worker, resources["relay"], resources["guard"]))
        assert self.resources(home) == resources, "resume changed the allocation"
        events = [json.loads(line) for line in (self.root / "proxy-events.jsonl").read_text().splitlines()[boundary:]]
        creates = [e for e in events if e.get("action", "").startswith("create-") and e.get("action") != "create-probe"]
        assert not creates, "resume created containers: %s" % [e["action"] for e in creates]
        order = [e["action"] for e in events if e.get("action") in ("start", "create-probe", "remove")]
        assert order[:5] == ["start", "start", "create-probe", "start", "remove"] and order[5] == "start", order
        self.wait_bidi(worker)
        assert self.firefox_pid(worker) and self.firefox_pid(worker) != firefox_before
        stored = self.evaluate(worker, "localStorage.getItem('bp-r2')", navigate=True)
        assert stored == nonce, "LocalStorage after resume: %r (expected the written nonce)" % (stored,)
        cookies = self.evaluate(worker, "document.cookie")
        assert nonce in cookies, "cookie after resume: %r" % (cookies,)
        relay_ip = json.loads(docker("inspect", resources["relay"]).stdout)[0]["NetworkSettings"]["Networks"][json.loads(docker("network", "inspect", resources["internal"]).stdout)[0]["Name"]]["IPAddress"]
        self.probe_browser_worker(worker, relay_ip)
        self.checks.direct_blocked(worker)
        status, report = self.health("network-qa-browser")
        assert status == 200 and report["health"]["overall"] == "healthy", report
        assert self.start("network-qa-browser")[0] == 303
        self.passed("all containers stopped + controller and Adapter restarted: startup reconciliation resumed Relay→Guard→probe→Worker with the same containers, Home data intact, proxy proven, direct blocked, health healthy",
                    containers_created_during_resume=0, docker_action_order=order[:6])

        # --- Scenario 2: probe failure keeps the Worker stopped ---
        # The browser generation's upstream is the private observer; stopping it
        # makes the Relay's upstream dial fail, so the one-shot probe cannot pass.
        self.stop_in_place(worker, resources["guard"], resources["relay"])
        docker("stop", "-t", "2", "network-qa-observer")
        status, value = self.control("network-qa-browser", "reconcile")
        assert status == 503 and value["result"]["status"] == "unknown", (status, value)
        assert self.container_state(worker) == "exited", "Worker started although the probe failed"
        assert "NETWORK_PROBE_FAILED" in self.binding("network-qa-browser")["last_error"]
        assert self.start("network-qa-browser")[0] == 409
        status, report = self.health("network-qa-browser")
        assert status == 200 and report["health"]["overall"] == "unknown"
        assert self.resources(home) == resources
        docker("start", "network-qa-observer")
        self.wait_observer()
        status, value = self.control("network-qa-browser", "resume")
        assert status == 200 and value["result"]["status"] == "running", (status, value)
        assert self.container_state(worker) == "running" and self.binding("network-qa-browser")["status"] == "running"
        self.wait_bidi(worker)
        assert self.evaluate(worker, "localStorage.getItem('bp-r2')", navigate=True) == nonce
        self.probe_browser_worker(worker, relay_ip)
        self.checks.direct_blocked(worker)
        self.passed("probe failure during resume left the Worker stopped and the entry refused (409); explicit resume after upstream recovery succeeded with the same Worker and data")

        # --- Scenario 3: legacy generation (no policy) ---
        legacy_home = "network-qa-home-legacy"
        self.launch("network-qa-legacy", legacy_home)
        legacy_worker = self.snapshot(legacy_home)["workers"][0]["instance_id"]
        sessions = self.checks.client.call("GET", "/api/sessions")[1]
        legacy_binding = self.binding("network-qa-legacy")
        ip_before = json.loads(docker("inspect", legacy_worker).stdout)[0]["NetworkSettings"]["Networks"]["browser-platform-network-qa"]["IPAddress"]
        self.stop_in_place(legacy_worker)
        # occupy the old address so the resumed Worker must get a new one
        squatter = docker("run", "-d", "--name", "network-qa-squatter", "--label", "io.browser-platform.qa=network-20260913", "--network", "browser-platform-network-qa",
                          "--ip", ip_before, "--memory", "32m", "--entrypoint", "python3", json.loads((self.root / "images.json").read_text())["probe"], "-c", "import time; time.sleep(600)").stdout.strip()
        try:
            status, value = self.control("network-qa-legacy", "reconcile")
            assert status == 200 and value["result"]["status"] == "running" and value["result"]["session_id"] == legacy_binding["session_id"], (status, value)
            assert self.container_state(legacy_worker) == "running"
            ip_after = json.loads(docker("inspect", legacy_worker).stdout)[0]["NetworkSettings"]["Networks"]["browser-platform-network-qa"]["IPAddress"]
            assert ip_after != ip_before, "expected a new address after the old one was taken"
            status, report = self.health("network-qa-legacy")
            assert status == 200 and report["health"]["overall"] == "healthy", report
            proxied = docker("exec", mod.SERVER, "python3", "-c", "import urllib.request,sys; r=urllib.request.urlopen('http://%s:3000/%s/',timeout=3); print(r.status)" % (ip_after, legacy_binding["session_id"]))
            assert proxied.stdout.strip() == "200"
        finally:
            docker("rm", "-f", squatter)
        self.passed("legacy no-policy generation resumed after an in-place stop; the Session record was refreshed to the Worker's new address and the display endpoint answers",
                    ip_changed=True)

        self.backup_scenario(nonce)

        # --- cleanup of drill generations ---
        for profile, home_name in (("network-qa-restored", restored_home_name()), ("network-qa-legacy", legacy_home)):
            assert self.control(profile, "stop")[0] == 200
            snapshot = self.snapshot(home_name)
            assert snapshot["records"] == snapshot["workers"] == snapshot["resources"] == []
        self.passed("drill generations stopped; Homes retained for cleanup")

    def backup_scenario(self, nonce):
        """Scenario 4: offline backup / restore. With nonce None, write fresh data first."""
        home = "network-qa-home-browser"
        if nonce is None:
            self.launch("network-qa-browser", home)
            worker = self.snapshot(home)["workers"][0]["instance_id"]
            self.wait_bidi(worker)
            nonce = os.urandom(8).hex()
            self.evaluate(worker, "localStorage.setItem('bp-r2', '%s'); document.cookie='bp_r2=%s; max-age=2592000; secure'; 'ok'" % (nonce, nonce), navigate=True)
            self.navigate(worker, "about:blank")
            self.wait_local_storage(home, nonce)
        restored_home = restored_home_name()
        tool = PROJECT / "infra/sealskin/lifecycle/backup-home.py"
        backups = self.root.parent / "backups"
        common = ["--config", str(self.root / "adapter-config.json"), "--profile", "network-qa-browser", "--storage", str(self.root / "storage"),
                  "--sealskin-config", str(self.root / "config/.config/sealskin"), "--output", str(backups)]
        refused = subprocess.run([sys.executable, str(tool), "backup", *common], capture_output=True, text=True)
        assert refused.returncode != 0 and "not confirmed stopped" in (refused.stderr + refused.stdout)
        assert self.control("network-qa-browser", "stop")[0] == 200
        self.checks.assert_empty("browser")
        done = subprocess.run([sys.executable, str(tool), "backup", *common], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        backup = json.loads(done.stdout.strip().splitlines()[-1])
        archive = backups / backup["backup"]
        verified = subprocess.run([sys.executable, str(tool), "verify", str(archive)], capture_output=True, text=True)
        assert verified.returncode == 0, verified.stderr
        target = self.root / "storage/network-qa" / restored_home
        restored = subprocess.run([sys.executable, str(tool), "restore", str(archive), "--target", str(target)], capture_output=True, text=True)
        assert restored.returncode == 0, restored.stderr
        registry_path = self.root / "config/.config/sealskin/profile-network-policies.json"
        registry = json.loads(registry_path.read_text())
        policy = dict(registry["policies"]["network-browser-observer-r1"])
        policy["home_name"] = restored_home
        policy["profile_id"] = "network-qa-restored"
        policy["application_id"] = "network-qa-firefox-restored"
        revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        registry["policies"]["network-browser-restored-r1"] = policy
        mod.write_json(registry_path, registry)
        status, apps = self.admin_client().call("GET", "/api/admin/apps/installed")
        app = next(a for a in apps if a["id"] == "network-qa-firefox-network")
        app.update(id="network-qa-firefox-restored", name="Restored QA Firefox")
        app["provider_config"].update(network_policy_id="network-browser-restored-r1", network_policy_sha256=revision)
        status, _ = self.admin_client().call("POST", "/api/admin/apps/installed", app)
        assert status == 201, status
        config = json.loads((self.root / "adapter-config.json").read_text())
        config["profiles"].append({"id": "network-qa-restored", "application_id": "network-qa-firefox-restored", "home_name": restored_home,
                                   "start_url": "https://entry.leak.qa.test/test", "wayland_mode": False,
                                   "language": "zh_TW.UTF-8", "timezone": "Asia/Taipei",
                                   "network_policy_id": "network-browser-restored-r1", "network_policy_sha256": revision})
        mod.write_json(self.root / "adapter-config.json", config)
        self.checks.definitions = {d["id"]: d for d in config["profiles"]}
        self.stop_adapter()
        self.start_adapter()
        self.launch("network-qa-restored", restored_home)
        restored_worker = self.snapshot(restored_home)["workers"][0]["instance_id"]
        self.wait_bidi(restored_worker)
        assert self.evaluate(restored_worker, "localStorage.getItem('bp-r2')", navigate=True) == nonce
        assert nonce in self.evaluate(restored_worker, "document.cookie")
        assert (self.root / "storage/network-qa" / restored_home / "network-qa-profile/storage/default/https+++entry.leak.qa.test/ls/data.sqlite").is_file()
        self.passed("offline backup refused while running, succeeded after confirmed stop, verified, restored into a new Home; a new generation on the restored Home reads the original data",
                    archive=archive.name, files=backup["files"], archive_sha256=backup["archive_sha256"][:16])
        assert self.control("network-qa-restored", "stop")[0] == 200


def restored_home_name():
    return "network-qa-home-restored"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--only-backup", action="store_true", help="run only the backup/restore scenario")
    args = parser.parse_args()
    Drill(args.root).run(only_backup=args.only_backup)


if __name__ == "__main__":
    main()
