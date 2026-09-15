#!/usr/bin/env python3
"""Exercise approved bootstrap DNS in the normal isolated Camoufox QA.

The fixture has real UDP/TCP and nonzero TTL records, but no public delegation
or recursive cache. Public DNS acceptance is a separate, still required run.
"""

import argparse
import importlib.util
import ipaddress
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("protocols", Path(__file__).with_name("check-proxy-protocols.py"))
protocols = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocols)
network = protocols.network
DNS_NAME = "network-qa-bootstrap-dns"
LABEL = "io.browser-platform.qa=network-20260913"


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class BootstrapChecks:
    def __init__(self, qa, output, build):
        self.qa, self.output, self.build = qa.resolve(), output.resolve(), build.resolve()
        assert self.qa.name == "qa" and self.build.parent == self.qa.parent
        self.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.matrix = protocols.Matrix(self.qa, self.output / "browser")
        self.matrix.request["url"] = "https://entry.leak.qa.test/test"
        self.matrix.request.pop("initial_url", None)
        self.dns = self.output / "dns"
        self.dns.mkdir(mode=0o700, exist_ok=False)
        topology = json.loads(network.docker("network", "inspect", "browser-platform-network-qa").stdout)[0]
        self.resolver = str(ipaddress.ip_network(topology["IPAM"]["Config"][0]["Subnet"])[21])
        assert all(v.get("IPv4Address", "").split("/")[0] != self.resolver for v in topology.get("Containers", {}).values())
        self.endpoint = self.matrix.images["upstream_host"]
        self.matrix.template.update(mode="proxy_required", bootstrap_resolver_id="qa-bootstrap",
                                    bootstrap_resolver_ip=self.resolver)
        self.results = []
        self.stage = "prepare"

    def passed(self, name, **details):
        value = {"check": name, "result": "PASS", "checkedAt": datetime.now(timezone.utc).isoformat(), **details}
        self.results.append(value)
        network.write_json(self.output / "results.json", self.results)
        print(json.dumps(value), flush=True)

    def mode(self, **options):
        network.write_json(self.dns / "mode.json", {"addresses": [self.endpoint], "ttl_seconds": 3,
                                                    "cname": True, "truncate": True, **options})

    def hosts(self, address=None):
        # Only the exact QA hostname is touched, including after controller
        # replacement; preserve that new container's other hosts entries.
        script = "from pathlib import Path\np=Path('/etc/hosts')\n"
        script += "lines=[line for line in p.read_text().splitlines() if 'proxy.leak.qa.test' not in line.split()]\n"
        if address:
            script += "lines.append(" + repr(address + " proxy.leak.qa.test") + ")\n"
        script += "p.write_text('\\n'.join(lines)+'\\n')\n"
        network.docker("exec", network.SERVER, "python3", "-c", script)

    def journal(self):
        snapshot = self.matrix.snapshot()
        assert snapshot["network_bootstrap_dns_version"] == 1
        key = next(row["id"] for row in snapshot["resources"] if row["kind"] == "reservation")
        value = json.loads((self.qa / "config/.config/sealskin/profile-network-runtime" / (key + ".json")).read_text())
        assert value["identity"]["owner"] == "network-qa" and value["identity"]["home"] == "network-qa-home-browser"
        return value

    def start_dns(self):
        assert network.docker("inspect", DNS_NAME, check=False).returncode != 0
        self.mode()
        release = json.loads((self.build / "release.json").read_text())
        network.docker("run", "-d", "--name", DNS_NAME, "--label", LABEL,
            "--network", "browser-platform-network-qa", "--ip", self.resolver,
            "--user", "1000:1000", "--cap-drop", "ALL", "--read-only",
            "--security-opt", "no-new-privileges:true", "--sysctl", "net.ipv4.ip_unprivileged_port_start=0",
            "--memory", "64m", "--pids-limit", "32",
            "-v", str(self.dns) + ":/qa-dns", "-v", str(Path(__file__).with_name("bootstrap-dns-fixture.py")) + ":/run/fixture.py:ro",
            "--entrypoint", "python3", release["image"], "/run/fixture.py", "--root", "/qa-dns")
        network.wait(lambda: "Private bootstrap DNS fixture ready" in network.docker("logs", DNS_NAME).stdout,
                     "private bootstrap DNS fixture")
        self.hosts("192.0.2.99")

    def attempt(self, case):
        self.matrix.stop()
        self.matrix.request["operation_id"] = uuid.uuid4().hex
        network.write_json(self.qa / "browser-launch.json", self.matrix.request)
        body = {key: self.matrix.request[key] for key in (
            "application_id", "profile_id", "operation_id", "network_policy_id", "network_policy_sha256")}
        body["bootstrap_url"] = self.matrix.request["url"]
        network.write_json(self.qa / "browser-stop.json", body)
        started = time.monotonic()
        status, value = self.matrix.checks.client.call("POST", "/api/launch/url", self.matrix.request)
        network.write_json(case / "launch-result.json", {"status": status, "result": value, "elapsed": time.monotonic() - started})
        assert status == 503 and self.matrix.snapshot()["workers"] == self.matrix.snapshot()["records"] == []
        return self.journal()

    def run(self, faults_only=False):
        self.start_dns()
        if faults_only:
            self.run_faults()
            return
        self.stage = "approved-path"
        case = self.output / self.stage
        case.mkdir(mode=0o700)
        self.matrix.configure("https", "none", case)
        initial = self.journal()
        observed = initial["bootstrap_dns"]
        assert observed["source"] == "approved_resolver" and observed["resolver"] == {
            "id": "qa-bootstrap", "ip": self.resolver, "port": 53}
        assert observed["addresses"] == [self.endpoint] and observed["ttl_seconds"] == 3
        assert [q["transports"] for q in observed["queries"]] == [["udp", "tcp"], ["udp", "tcp"]]
        assert len(events(self.dns / "events.jsonl")) == 4
        network.write_json(case / "dns-observation.json", observed)
        self.matrix.transports("https", "none")
        with (case / "browser-network.log").open("w") as log:
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("check-network-browser.py")),
                "--root", str(self.qa), "--output", str(case / "browser-network")], stdout=log, stderr=subprocess.STDOUT)
        assert result.returncode == 0, "browser bypass matrix failed; inspect private evidence"
        self.matrix.refresh()  # The browser fault matrix deliberately restarts the QA API.
        self.passed("approved numeric DNS overrides wrong hosts mapping and preserves remote website DNS",
                    udpTCP=True, cname=True, ttlSeconds=3, httpHttpsWsWss=True, browserBypassMatrix=True)

        self.stage = "frozen-generation"
        self.mode(addresses=["192.0.2.99"])
        while time.time() <= observed["expires_at"] + 0.1:
            time.sleep(0.1)
        count = len(events(self.dns / "events.jsonl"))
        self.matrix.transports("https", "none")
        network.docker("restart", "-t", "3", initial["allocation"]["relay_id"])
        self.matrix.transports("https", "none")
        assert self.journal()["bootstrap_dns"] == observed and len(events(self.dns / "events.jsonl")) == count
        self.passed("active generation and Relay restart retain the endpoint after observed TTL expires")

        self.stage = "controller-replacement"
        with (self.output / "controller-replacement.log").open("w") as log:
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("recreate-network-controller.py")),
                "--root", str(self.qa), "--build", str(self.build)], stdout=log, stderr=subprocess.STDOUT)
        assert result.returncode == 0, "controller reattachment failed; inspect private evidence"
        self.matrix.refresh()
        self.hosts("192.0.2.99")
        assert self.journal()["bootstrap_dns"] == observed and len(events(self.dns / "events.jsonl")) == count
        self.matrix.transports("https", "none")
        self.passed("replacement controller reattaches without resolving or changing the live generation")

        self.stage = "resume"
        case = self.output / self.stage
        case.mkdir(mode=0o700)
        self.mode(fault="drop")
        self.matrix.resume(case)
        assert self.journal()["bootstrap_dns"] == observed and len(events(self.dns / "events.jsonl")) == count
        self.passed("same-generation resume retains frozen DNS during resolver outage and preserves browser storage")

        self.stage = "new-generation"
        case = self.output / self.stage
        case.mkdir(mode=0o700)
        self.mode(addresses=["192.0.2.99"])
        changed = self.attempt(case)
        assert changed["identity"]["operation"] != initial["identity"]["operation"]
        assert changed["bootstrap_dns"]["selected_ipv4"] == "192.0.2.99" and changed["allocation"]
        self.matrix.stop()
        self.passed("new generation resolves the updated endpoint and a failed upstream creates no Worker")
        self.run_faults()

    def run_faults(self):
        for fault, expected in (("servfail", "NETWORK_BOOTSTRAP_DNS_SERVFAIL"),
                                ("nxdomain", "NETWORK_BOOTSTRAP_DNS_NXDOMAIN"),
                                ("drop", "NETWORK_BOOTSTRAP_DNS_TIMEOUT"),
                                ("bad-id", "NETWORK_BOOTSTRAP_DNS_INVALID"),
                                ("mixed", "NETWORK_UPSTREAM_ADDRESS_INVALID")):
            self.stage = "fault-" + fault
            case = self.output / self.stage
            case.mkdir(mode=0o700)
            self.mode(fault=fault if fault != "mixed" else "", addresses=[self.endpoint, "127.0.0.1"] if fault == "mixed" else [self.endpoint])
            failed = self.attempt(case)
            assert failed["bootstrap_dns_error"]["code"] == expected and "allocation" not in failed
            resources = self.matrix.snapshot()["resources"]
            assert "reservation" in {v["kind"] for v in resources}
            assert all(v["kind"] in {"reservation", "launch"} and
                       v["operation_id"] == failed["identity"]["operation"] for v in resources)
            self.matrix.stop()
            self.passed("DNS failure retains the reservation without allocating network resources", fault=fault, code=expected)

        self.stage = "numeric"
        case = self.output / self.stage
        case.mkdir(mode=0o700)
        self.mode(fault="drop")
        count = len(events(self.dns / "events.jsonl"))
        self.matrix.configure("socks5", "none", case)
        numeric = self.journal()["bootstrap_dns"]
        assert numeric["source"] == "numeric" and numeric["ttl_seconds"] is None and numeric["resolver"] is None
        self.matrix.transports("socks5", "none")
        assert len(events(self.dns / "events.jsonl")) == count
        self.matrix.stop()
        self.passed("numeric upstream bypasses DNS even when the configured resolver is unavailable")
        network.write_json(self.qa / "live-results.json", self.results)

    def cleanup_fixture(self):
        self.hosts()
        result = network.docker("inspect", DNS_NAME, check=False)
        if result.returncode == 0:
            value = json.loads(result.stdout)[0]
            assert value["Config"]["Labels"].get("io.browser-platform.qa") == "network-20260913"
            assert any(m["Source"] == str(self.dns) and m["Destination"] == "/qa-dns" for m in value["Mounts"])
            network.docker("stop", "-t", "3", DNS_NAME)
            network.docker("rm", DNS_NAME)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--faults-only", action="store_true",
                        help="Continue failed DNS/numeric cases in a new output directory; retain earlier phase evidence")
    args = parser.parse_args()
    run = BootstrapChecks(args.root, args.output, args.build)
    try:
        run.run(faults_only=args.faults_only)
    except Exception as exc:
        network.write_json(run.output / "failure.json", {"stage": run.stage, "error": type(exc).__name__,
                                                        "checkedAt": datetime.now(timezone.utc).isoformat()})
        raise
    finally:
        # Generation journals/resources are kept on failure for inspection and
        # explicit lifecycle cleanup, never force-removed by this checker.
        run.cleanup_fixture()


if __name__ == "__main__":
    main()
