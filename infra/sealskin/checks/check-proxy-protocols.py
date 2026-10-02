#!/usr/bin/env python3
"""Run the upstream protocol/authentication matrix in the prepared Camoufox QA.

Each case stops the previous QA generation, publishes a new policy revision,
then uses the normal browser and Guard path. Production Homes are refused.
The private observer, QA controller and frozen browser must already be prepared.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

spec = importlib.util.spec_from_file_location("desktop", Path(__file__).with_name("qa-desktop.py"))
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)
network = desktop.network
CASES = [("socks5", "none"), ("socks5", "username_password"), ("http", "none"),
         ("http", "basic"), ("https", "none"), ("https", "basic")]


class Matrix:
    def __init__(self, qa, output):
        self.qa, self.output = qa.resolve(), output.resolve()
        self.checks = network.Checks(self.qa)
        self.info = json.loads((self.qa / "browser-worker.json").read_text())
        self.request = json.loads((self.qa / "browser-launch.json").read_text())
        assert self.info["engine"] == "camoufox" or self.info.get("native_engine") == self.info["engine"] in ("chromix", "firefox")
        assert (self.info["home"], self.info["profile"]) == ("network-qa-home-browser", "network-qa-browser")
        assert self.request["home_name"] == self.info["home"]
        assert self.request["application_id"] == "camoufox-network-qa-r4"
        self.observer = self.qa.parent / "observer"
        self.registry_path = self.qa / "config/.config/sealskin/profile-network-policies.json"
        self.registry = json.loads(self.registry_path.read_text())
        self.template = dict(self.registry["policies"]["network-browser-observer-r1"])
        self.app = json.loads((self.qa / "camoufox-app.json").read_text())
        self.images = json.loads((self.qa / "images.json").read_text())
        self.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.results = []
        self.marker = uuid.uuid4().hex
        self.refresh()
        # This modifies only the already verified QA control container. Website
        # DNS still belongs to the private upstream, never this hosts mapping.
        mapping = ("from pathlib import Path\n"
                   "p=Path('/etc/hosts')\nlines=[v for v in p.read_text().splitlines() if 'proxy.leak.qa.test' not in v]\n"
                   "p.write_text('\\n'.join(lines)+ '\\n' + " + repr(self.images["upstream_host"] + " proxy.leak.qa.test\n") + ")")
        network.docker("exec", "sealskin-network-qa", "python3", "-c", mapping)

    def refresh(self):
        self.checks.client = network.SecureClient(self.qa)
        admin = json.loads((self.qa / "admin.json").read_text())
        self.admin = network.SecureClient(self.qa, username=admin["username"],
            private=admin["private_key"].encode(), public=admin["server_public_key"].encode())

    def snapshot(self):
        status, value = self.checks.client.call("GET", "/api/profile-runtime/" + self.info["home"])
        assert status == 200 and value["network_upstream_version"] == 1
        return value

    def stop(self):
        self.refresh()
        value = self.snapshot()
        if value["records"] or value["workers"] or value["resources"]:
            stop = json.loads((self.qa / "browser-stop.json").read_text())
            assert stop["profile_id"] == "network-qa-browser" and stop["application_id"] == "camoufox-network-qa-r4"
            status, result = self.checks.client.call("POST", "/api/profile-runtime/" + self.info["home"] + "/stop", stop)
            assert status == 204 and result is None, "QA generation did not stop"
        value = self.snapshot()
        assert value["records"] == value["workers"] == value["resources"] == [], "QA Home remains occupied"

    def events(self):
        return [json.loads(line) for line in (self.observer / "events.jsonl").read_text().splitlines()]

    def configure(self, protocol, auth, case):
        self.stop()
        network.write_json(self.observer / "proxy-auth.json", {protocol: auth})
        network.write_json(self.observer / "mode.json", {})
        network.write_json(self.observer / "proxy-tls-mode.json", {})
        policy = dict(self.template)
        policy.update(upstream_protocol=protocol, upstream_auth=auth,
                      upstream_port={"socks5": 28191, "http": 28192, "https": 28193}[protocol])
        if auth == "none":
            for name in ("username_file", "username_sha256", "password_file", "password_sha256"):
                policy[name] = ""
        if protocol == "https":
            policy.update(upstream_host="proxy.leak.qa.test", upstream_tls_ca_file=policy["probe_ca_file"],
                          upstream_tls_ca_sha256=policy["probe_ca_sha256"])
        policy_id = "network-r5a-" + protocol + "-" + auth.replace("_", "-") + "-" + uuid.uuid4().hex[:8]
        revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.registry["policies"][policy_id] = policy
        network.write_json(self.registry_path, self.registry)
        provider = self.app["provider_config"]
        provider.update(network_policy_id=policy_id, network_policy_sha256=revision)
        status, _ = self.admin.call("PATCH", "/api/admin/apps/installed/" + self.app["id"], {"provider_config": provider})
        assert status == 200, "QA app policy update failed"
        network.write_json(self.qa / "camoufox-app.json", self.app)
        self.request.update(operation_id=uuid.uuid4().hex, network_policy_id=policy_id, network_policy_sha256=revision)
        network.write_json(self.qa / "browser-launch.json", self.request)
        stop = {key: self.request[key] for key in ("application_id", "profile_id", "operation_id", "network_policy_id", "network_policy_sha256")}
        stop["bootstrap_url"] = self.request["url"]
        network.write_json(self.qa / "browser-stop.json", stop)
        status, launch = self.checks.client.call("POST", "/api/launch/url", self.request)
        network.write_json(case / "launch-result.json", {"status": status, "result": launch})
        assert status == 200, "QA protocol preflight/launch failed"
        stop["session_id"] = launch["session_id"]
        network.write_json(self.qa / "browser-stop.json", stop)
        snapshot = self.snapshot()
        assert len(snapshot["workers"]) == 1
        self.info.update(instance_id=snapshot["workers"][0]["instance_id"], upstream_protocol=protocol, upstream_auth=auth)
        network.write_json(self.qa / "browser-worker.json", self.info)
        network.write_json(case / "policy.json", {"id": policy_id, "sha256": revision, "policy": policy})
        network.write_json(case / "generation.json", snapshot)
        if self.info.get("native_engine"):
            ns=importlib.util.spec_from_file_location("native_network",Path(__file__).with_name("native-network-client.py"));nm=importlib.util.module_from_spec(ns);ns.loader.exec_module(nm)
            self.control=nm.NativeDesktop(self.info["instance_id"],self.info["native_engine"])
            network.wait(lambda: network.docker("exec", self.info["instance_id"], "python3", "-c", 'import socket;socket.create_connection(("127.0.0.1",9222),1).close()', check=False).returncode == 0, "native browser debug readiness", seconds=90)
            self.control.navigate("https://entry.leak.qa.test/test")
        else:self.control = desktop.Desktop(self.info["instance_id"])
        network.wait(lambda: network.docker("exec", "--user", "1000", "-e", "DISPLAY=:1", self.info["instance_id"],
            "xdotool", "getactivewindow", "getwindowname", check=False).stdout.startswith("Private browser network check"),
            "protocol QA browser", seconds=60)
        relay = next(item["id"] for item in snapshot["resources"] if item["kind"] == "relay")
        relay_config = json.loads(network.docker("exec", relay, "cat", "/run/config/relay.json").stdout)
        assert relay_config["upstream_host"] == self.images["upstream_host"]
        if protocol == "https":
            assert relay_config["upstream_tls_server_name"] == "proxy.leak.qa.test"
        network.write_json(case / "relay-config.json", relay_config)
        return snapshot

    def transports(self, protocol, auth):
        observed = []
        event = {"socks5": "socks", "http": "http_connect", "https": "https_connect"}[protocol]
        for scheme, port in (("https", 443), ("http", 80)):
            self.control.navigate(scheme + "://entry.leak.qa.test/test")
            start = len(self.events())
            result = self.control.evaluate("qa.transport()")
            assert result["pageProtocol"] == scheme + ":", "browser upgraded or changed the requested website protocol"
            assert result["fetch"] and result["websocket"], "browser website or WebSocket failed"
            nonce = result["nonce"]
            events = self.events()[start:]
            for label in ("transport", "transport-ws"):
                target = label + "-" + nonce + ".leak.qa.test"
                assert any(e["event"] == event and e.get("target") == target and e["port"] == port
                           and e["auth"] == auth and e["atyp"] == 3 for e in events)
                assert any(e["event"] == "dns" and e["name"] == target and e["source"] == "127.0.0.1" for e in events)
            observed.append(result)
        return observed

    def resume(self, case):
        self.refresh()
        before = self.snapshot()
        resources = {v["kind"]: v["id"] for v in before["resources"]}
        worker = self.info["instance_id"]
        self.control.navigate("https://entry.leak.qa.test/test")
        written = self.control.evaluate("localStorage.setItem('proxy-resume'," + json.dumps(self.marker)
            + ");({href:location.href,value:localStorage.getItem('proxy-resume')})")
        assert written == {"href": "https://entry.leak.qa.test/test", "value": self.marker}
        details = json.loads(network.docker("inspect", worker).stdout)[0]
        assert details["Config"]["Labels"].get("io.browser-platform.browser-shutdown") == "1"
        services = network.docker("exec", worker, "s6-rc", "-a", "list").stdout.splitlines()
        assert "browser-platform-shutdown" in services, "pre-desktop shutdown service is not active"
        network.write_json(case / "resume-write.json", written)
        started = time.monotonic()
        network.docker("stop", "-t", "30", worker)
        stopped = json.loads(network.docker("inspect", worker).stdout)[0]
        assert stopped["State"]["ExitCode"] == 0 and not stopped["State"]["OOMKilled"]
        messages = [line for line in network.docker("logs", worker).stdout.splitlines()
                    if line.startswith("BROWSER_SHUTDOWN_")]
        assert messages[-1:] == ["BROWSER_SHUTDOWN_CONFIRMED"]
        network.write_json(case / "resume-stop.json", {"exitCode": 0, "elapsed": time.monotonic() - started,
            "shutdown": messages[-1]})
        network.docker("stop", "-t", "3", resources["guard"], resources["relay"])
        network.write_json(self.observer / "mode.json", {"mode": "offline"})
        body = json.loads((self.qa / "browser-stop.json").read_text())
        status, failure = self.checks.client.call("POST", "/api/profile-runtime/" + self.info["home"] + "/resume", body)
        assert status == 503, "offline upstream unexpectedly resumed browser"
        failure_status = status
        details = json.loads(network.docker("inspect", worker).stdout)[0]
        assert details["State"]["Status"] == "exited", "browser started before successful preflight"
        network.write_json(self.observer / "mode.json", {})
        status, success = self.checks.client.call("POST", "/api/profile-runtime/" + self.info["home"] + "/resume", body)
        assert status == 200 and success["resumed"] is True
        assert success["instance_id"] == worker
        assert success["steps"] == ["relay", "guard", "controller", "relay-accepting", "probe", "worker", "display", "committed"]
        after = self.snapshot()
        assert {v["kind"]: v["id"] for v in after["resources"]} == resources
        network.write_json(case / "resume-api.json", {"result": "API_VERIFIED_GUI_PENDING", "failedStatus": failure_status,
            "failure": failure, "success": success, "sameGeneration": True})
        self.control.navigate("https://entry.leak.qa.test/test")
        assert self.control.evaluate("localStorage.getItem('proxy-resume')") == self.marker
        assert self.control.evaluate("fetchCheck('resume')")
        network.write_json(case / "resume.json", {"result": "PASS", "failedStatus": failure_status,
            "failure": failure, "success": success, "sameGeneration": True, "homeDataPreserved": True})

    def run(self, protocol, auth):
        name = protocol + "-" + auth
        case = self.output / name
        case.mkdir(mode=0o700)
        print(json.dumps({"case": name, "stage": "launch"}), flush=True)
        start = len(self.events())
        self.configure(protocol, auth, case)
        print(json.dumps({"case": name, "stage": "network"}), flush=True)
        command = [sys.executable, str(Path(__file__).with_name("check-network-browser.py")),
                   "--root", str(self.qa), "--output", str(case / "network")]
        with (case / "network-check.log").open("w") as log:
            run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=360)
        assert run.returncode == 0, "browser network matrix failed; inspect private case log"
        network_results = json.loads((case / "network/browser-network-results.json").read_text())
        assert len(network_results) == (13 if protocol == "https" else 11) and all(v["result"] == "PASS" for v in network_results)
        transports = self.transports(protocol, auth)
        network.write_json(case / "transports.json", transports)
        if (protocol, auth) == ("https", "basic"):
            self.resume(case)
        events = self.events()[start:]
        (case / "observer-events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        record = {"case": name, "result": "PASS", "protocol": protocol, "auth": auth,
                  "browser": self.info.get("native_engine", "camoufox"), "networkChecks": len(network_results),
                  "httpHttpsWsWss": True, "checkedAt": datetime.now(timezone.utc).isoformat()}
        self.results.append(record)
        network.write_json(self.output / "protocol-matrix.json", self.results)
        print(json.dumps(record), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", choices=[p + "-" + a for p, a in CASES], help="default: all six cases")
    args = parser.parse_args()
    matrix = Matrix(args.root, args.output)
    try:
        for protocol, auth in CASES:
            if not args.cases or protocol + "-" + auth in args.cases:
                matrix.run(protocol, auth)
        matrix.stop()
        network.write_json(matrix.output / "stopped.json", {"result": "PASS", "generationResources": 0})
    except Exception as exc:
        network.write_json(matrix.output / "failure.json", {"result": "FAIL", "type": type(exc).__name__,
            "message": str(exc), "qaRetainedForInspection": True})
        raise


if __name__ == "__main__":
    main()
