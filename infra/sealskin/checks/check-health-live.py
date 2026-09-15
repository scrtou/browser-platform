#!/usr/bin/env python3
"""R1 runtime-health scenarios on the isolated network QA deployment.

Requires prepare-network-qa.py fixtures under --root and the health-v1 control
image. Every check reads the Adapter health API (private socket and public
entry site) and proves that health queries never create, restart or stop
Workers. Only network-qa Homes, Workers and generation resources are touched.
"""

import argparse
import http.client
import importlib.util
import json
import socket
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "network_checks", Path(__file__).resolve().parents[1] / "lifecycle/check-network-live.py"
)
checks_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks_module)
docker = checks_module.docker
SOCKET = checks_module.SOCKET

# Worker override used by the QA app: a Python HTTP server on 3000 standing in
# for the display endpoint, plus a long-lived "browser" and "display server".
QA_WORKER_ENTRYPOINT = (
    "import os,subprocess,sys,http.server\n"
    "os.makedirs('/tmp/bp',exist_ok=True)\n"
    "for name in ('firefox','Xvfb','selkies'):\n"
    "  link='/tmp/bp/'+name\n"
    "  if not os.path.exists(link): os.symlink(sys.executable,link)\n"
    "procs=[subprocess.Popen(['/tmp/bp/'+name,'-c','import time\\nwhile True: time.sleep(3600)']) for name in ('firefox','Xvfb','selkies')]\n"
    "class H(http.server.BaseHTTPRequestHandler):\n"
    " def log_message(self,*a): pass\n"
    " def do_GET(self):\n"
    "  if os.path.exists('/tmp/display-down'):\n"
    "   self.send_response(503); self.end_headers(); return\n"
    "  self.send_response(200); self.send_header('Content-Length','2'); self.end_headers(); self.wfile.write(b'ok')\n"
    "http.server.ThreadingHTTPServer(('0.0.0.0',3000),H).serve_forever()\n"
)


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET)


class HealthChecks:
    def __init__(self, root):
        self.root = root.resolve()
        self.checks = checks_module.Checks(self.root)
        self.results = []

    def passed(self, name, **details):
        value = {"check": name, "result": "PASS", **details}
        self.results.append(value)
        checks_module.write_json(self.root / "health-results.json", self.results)
        print(json.dumps(value, ensure_ascii=False), flush=True)

    def health(self, suffix, action="health", cached=False):
        connection = UnixConnection("adapter", timeout=100)
        try:
            path = "/profiles/network-qa-" + suffix + "/health" + ("?cached=1" if cached else "")
            connection.request("GET" if action == "health" else "POST", path)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def public_health(self, suffix, cached=False):
        status, headers, raw = checks_module.request(
            "GET", "/browser/network-qa-" + suffix + "/health" + ("?cached=1" if cached else ""), port=29110
        )
        return status, headers, raw

    def entry(self, suffix, recheck=False):
        status, headers, raw = checks_module.request(
            "GET", "/browser/network-qa-" + suffix + "/" + ("?recheck=1" if recheck else ""), port=29110
        )
        return status, raw.decode()

    def check_named(self, report, name):
        return next(c for c in report["checks"] if c["name"] == name)

    def worker(self, suffix):
        snapshot = self.checks.snapshot(suffix)
        assert len(snapshot["workers"]) == 1
        return snapshot["workers"][0]["instance_id"]

    def identity(self, instance):
        return self.checks.identity(instance)

    def exec_worker(self, instance, *command, check=True):
        return docker("exec", instance, *command, check=check)

    def wait_probe_window(self):
        time.sleep(10.5)

    def probe(self, suffix):
        self.wait_probe_window()
        status, value = self.health(suffix, "probe")
        assert status == 200, "forced probe failed: %s" % value.get("error")
        return value["health"]

    def prepare_app(self):
        """Point the QA app at the process-emulating Worker entrypoint (QA controller only)."""
        admin = json.loads((self.root / "admin.json").read_text())
        client = checks_module.SecureClient(
            self.root, username=admin["username"], private=admin["private_key"].encode(),
            public=admin["server_public_key"].encode(),
        )
        app_id = self.checks.definitions["network-qa-a"]["application_id"]
        status, value = client.call("PATCH", "/api/admin/apps/installed/" + app_id,
                                    {"provider_config": {"docker_overrides": {"entrypoint": ["python3", "-c", QA_WORKER_ENTRYPOINT]}}})
        assert status == 200, "QA app update failed: %s" % status
        assert value["provider_config"]["docker_overrides"]["entrypoint"][2] == QA_WORKER_ENTRYPOINT

    def run(self):
        self.prepare_app()
        self.checks.start_adapter()
        status, _ = self.checks.start("a")
        assert status == 303, "QA launch failed"
        worker = self.worker("a")
        original = self.identity(worker)
        relay = self.checks.resource("a", "relay")
        guard = self.checks.resource("a", "guard")

        def wait_healthy():
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                report = self.probe("a")
                if report["overall"] == "healthy":
                    return report
            raise RuntimeError("QA generation never became healthy: " + json.dumps(report, ensure_ascii=False))

        report = wait_healthy()
        codes = {c["name"]: c["code"] for c in report["checks"]}
        assert codes["browser"] == "BROWSER_RUNNING" and codes["display"] == "DISPLAY_READY"
        assert codes["proxy"] == "PROXY_OK" and codes["session"] == "SESSION_RUNNING" and codes["worker"] == "WORKER_RUNNING"
        assert report["binding"]["operation_id"] == self.checks.binding("a")["operation_id"]
        assert report["binding"]["session_id"] == self.checks.binding("a")["session_id"]
        assert report["binding"]["network_policy_id"] == self.checks.definitions["network-qa-a"]["network_policy_id"]
        assert report["runtime"]["network_phase"] == "running" and report["recovery"] is None
        assert time.time() - 5 < report_ts(report["checked_at"]) and report_ts(report["expires_at"]) - report_ts(report["checked_at"]) == 60
        self.passed("H01 healthy managed generation binds Profile, operation, Session, policy revision and sampling time", codes=codes)

        status, headers, raw = self.public_health("a")
        public = json.loads(raw)
        assert status == 200 and headers.get("Cache-Control") == "no-store"
        assert "operation_id" not in public["binding"] and "session_id" not in public["binding"]
        assert public["overall"] == "healthy" and public["cached"] is True
        assert "access_token" not in raw.decode() and "bootstrap" not in raw.decode()
        self.passed("public entry health is sanitized, cached and token-free")

        cached_status, cached = self.health("a", cached=True)
        assert cached_status == 200 and cached["health"]["cached"] is True and cached["health"]["checked_at"] == report["checked_at"]
        throttle_status, throttled = self.health("a", "probe")
        assert throttle_status == 429 and throttled["health"]["checked_at"] == report["checked_at"]
        self.passed("cache reuse within TTL and forced probe throttled to one per 10 seconds")

        # Repeated queries never create or restart instances.
        for _ in range(30):
            assert self.health("a")[0] == 200
            assert self.public_health("a")[0] == 200
        status, body = self.entry("a")
        assert status == 200 and "document.forms[0].submit()" in body
        assert self.identity(worker) == original
        snapshot = self.checks.snapshot("a")
        assert len(snapshot["workers"]) == 1 and len(snapshot["resources"]) == 5
        events = [json.loads(line) for line in (self.root / "proxy-events.jsonl").read_text().splitlines()]
        creates = [e for e in events if e.get("action", "").startswith("create")]
        self.passed("repeated health, public and entry queries create nothing", docker_creates=len(creates), worker_unchanged=True)
        create_count = len(creates)

        # Scenario: browser exits while the Worker, display and Session survive.
        self.exec_worker(worker, "pkill", "-x", "firefox")
        report = self.probe("a")
        assert report["overall"] == "unhealthy" and self.check_named(report, "browser")["code"] == "BROWSER_EXITED"
        assert self.check_named(report, "display")["code"] == "DISPLAY_READY"
        assert report["recovery"]["blocking"] is True and report["recovery"]["code"] == "BROWSER_EXITED"
        status, body = self.entry("a")
        assert status == 200 and "document.forms[0].submit()" not in body and "继续进入会话" in body and "FireFox" in body
        status, headers, _ = checks_module.request("POST", "/browser/network-qa-a/start", b"", {"Origin": "https://network.invalid"}, port=29110)
        assert status == 303, "manual continue must still reach the Session"
        assert self.identity(worker) == original
        self.passed("browser exit yields UNHEALTHY BROWSER_EXITED, blocking recovery hint on the entry, manual continue still works, no relaunch")

        # Browser comes back: report recovers without any lifecycle action.
        docker("exec", "-d", worker, "/tmp/bp/firefox", "-c", "import time\nwhile True: time.sleep(3600)")
        report = wait_healthy()
        assert self.identity(worker) == original
        self.passed("browser restart inside the Worker returns the report to HEALTHY without a relaunch")

        # Scenario: display endpoint fails while processes exist.
        self.exec_worker(worker, "touch", "/tmp/display-down")
        report = self.probe("a")
        display = self.check_named(report, "display")
        assert report["overall"] == "unhealthy" and display["code"].startswith("DISPLAY_ENDPOINT_HTTP_503")
        assert report["recovery"]["blocking"] is True and self.check_named(report, "browser")["code"] == "BROWSER_RUNNING"
        self.exec_worker(worker, "rm", "-f", "/tmp/display-down")
        self.exec_worker(worker, "pkill", "-x", "selkies")
        report = self.probe("a")
        assert report["overall"] == "unhealthy" and self.check_named(report, "display")["code"] == "DISPLAY_STREAMER_MISSING"
        docker("exec", "-d", worker, "/tmp/bp/selkies", "-c", "import time\nwhile True: time.sleep(3600)")
        report = wait_healthy()
        self.passed("display endpoint failure and missing streamer are reported separately from browser state, then recover")

        # Scenario: Relay stopped; browser and display remain, proxy fails, no direct path.
        docker("stop", "-t", "2", relay)
        report = self.probe("a")
        proxy = self.check_named(report, "proxy")
        assert report["overall"] == "unhealthy" and proxy["code"] == "PROXY_RELAY_NOT_RUNNING" and proxy["required"]
        assert self.check_named(report, "browser")["code"] == "BROWSER_RUNNING"
        assert report["recovery"]["blocking"] is True and report["recovery"]["code"] == "PROXY_RELAY_NOT_RUNNING"
        self.checks.direct_blocked(worker)
        docker("start", relay)
        report = wait_healthy()
        assert self.identity(worker) == original
        self.passed("Relay stop yields UNHEALTHY PROXY_RELAY_NOT_RUNNING with a blocking hint, direct paths stay blocked, restart recovers")

        # Scenario: upstream offline -> Relay accepts but upstream probe cannot complete.
        self.checks.upstream("offline")
        report = self.probe("a")
        proxy = self.check_named(report, "proxy")
        assert proxy["status"] in {"unknown", "fail"} and proxy["code"].startswith("PROXY_")
        assert report["overall"] in {"unknown", "unhealthy"}
        self.checks.upstream()
        report = wait_healthy()
        self.passed("upstream outage is reported through the Relay probe and recovers", upstream_code=proxy["code"])

        # Scenario: Guard stopped -> namespace holder gone, proxy fails.
        docker("stop", "-t", "2", guard)
        report = self.probe("a")
        assert report["overall"] == "unhealthy" and self.check_named(report, "proxy")["code"] == "PROXY_GUARD_NOT_RUNNING"
        self.passed("Guard stop is reported as PROXY_GUARD_NOT_RUNNING; no automatic Guard restart")

        # Explicit lifecycle cleanup after Guard loss, then offline report.
        assert self.checks.control("a", "stop")[0] == 200
        self.checks.assert_empty("a")
        report = self.probe("a")
        assert report["overall"] == "offline" and report["recovery"]["code"] == "PROFILE_STOPPED" and not report["recovery"]["blocking"]
        assert all(c["status"] == "not_applicable" for c in report["checks"] if c["name"] in {"session", "worker", "browser", "display", "proxy"})
        self.passed("confirmed stop reports OFFLINE, distinct from unknown")

        # Scenario: control plane unavailable -> UNKNOWN, not offline; entry falls back.
        docker("exec", checks_module.SERVER, "s6-svc", "-d", "/run/service/svc-sealskin")
        docker("exec", checks_module.SERVER, "s6-svwait", "-d", "-t", "20000", "/run/service/svc-sealskin")
        try:
            report = self.probe("a")
            control = self.check_named(report, "control")
            assert report["overall"] == "unknown" and control["status"] == "unknown" and control["code"].startswith("CONTROL_")
            assert report["recovery"]["blocking"] is False
            status, body = self.entry("a")
            assert status == 200 and "document.forms[0].submit()" in body
        finally:
            docker("exec", checks_module.SERVER, "s6-svc", "-u", "/run/service/svc-sealskin")
            checks_module.wait(lambda: checks_module.request("POST", "/api/handshake/initiate")[0] == 200, "QA control service")
            self.checks.client = checks_module.SecureClient(self.root)
        self.passed("control-plane outage yields UNKNOWN (never offline or healthy) and the entry keeps its auto-submit fallback")

        # Scenario: expiry. The cached report from before the outage must be marked stale.
        report = self.probe("a")
        assert report["overall"] == "offline"
        time.sleep(61)
        status, cached = self.health("a", cached=True)
        assert status == 200 and cached["health"]["stale"] is True and cached["health"]["overall"] == "unknown"
        assert self.check_named(cached["health"], "freshness")["code"] == "REPORT_EXPIRED"
        self.passed("expired report is marked stale and UNKNOWN; not reused as offline or healthy")

        # Final: no Docker creates happened during any health scenario.
        events = [json.loads(line) for line in (self.root / "proxy-events.jsonl").read_text().splitlines()]
        creates = [e for e in events if e.get("action", "").startswith("create")]
        assert len(creates) == create_count, "health scenarios created Docker resources"
        self.passed("no Docker create during any health scenario", docker_creates=len(creates))


def report_ts(value):
    import re
    from datetime import datetime
    value = re.sub(r"\.[0-9]+", "", value).replace("Z", "+00:00")
    return datetime.fromisoformat(value).timestamp()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    HealthChecks(args.root).run()


if __name__ == "__main__":
    main()
