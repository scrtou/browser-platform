#!/usr/bin/env python3
"""Real monitor/DNS/nft/SOCKS5 integration on prepare-network-qa.py fixtures.

Uses two API-created browser Workers and an automated HTTPS client. Never
accepts production identities. Failed evidence is retained; --stop releases
only recorded QA generations through the normal lifecycle API.
"""
import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import select
import subprocess
import time
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("network", HERE.parent / "lifecycle/check-network-live.py")
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)
write = network.write_json
LABEL = "io.browser-platform.qa=network-20260913"


def read(path):
    return json.loads(path.read_text())


class Flow:
    def __init__(self, worker, relay, ca, error_log):
        self.errors = error_log.open("ab")
        self.process = subprocess.Popen(["docker", "exec", "-i", "--user", "1000:1000", worker,
            "python3", "-u", "-c", (HERE / "dynamic-worker-client.py").read_text()],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors, text=True)
        self.process.stdin.write(json.dumps({"relay": relay, "ca": ca}) + "\n")
        self.process.stdin.flush()

    def get(self, expected):
        self.process.stdin.write("get\n")
        self.process.stdin.flush()
        assert select.select([self.process.stdout], [], [], 15)[0], "Worker HTTPS response timeout"
        line = self.process.stdout.readline()
        assert line, "Worker client exited; see private log"
        assert json.loads(line) == {"endpoint": expected, "status": 200}

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write("close\n")
            self.process.stdin.flush()
        self.process.wait(timeout=15)
        self.errors.close()


class Check:
    def __init__(self, qa):
        self.qa = qa.resolve()
        assert self.qa.name == "qa" and "runtime" in self.qa.parts
        self.out = self.qa.parent / "dynamic"
        controller = json.loads(network.docker("inspect", network.SERVER).stdout)[0]
        assert controller["Config"]["Labels"].get("io.browser-platform.qa") == "network-20260913"
        assert any(m["Source"] == str(self.qa / "config") and m["Destination"] == "/config" for m in controller["Mounts"])
        self.images = read(self.qa / "images.json")
        self.images["controller"] = controller["Image"]
        self.controller_id = controller["Id"]
        self.client = network.SecureClient(self.qa)
        admin = read(self.qa / "admin.json")
        self.admin = network.SecureClient(self.qa, username=admin["username"], private=admin["private_key"].encode())
        self.flows = []
        self.results = []

    def passed(self, name):
        self.results.append({"check": name, "result": "PASS", "at": time.time()})
        write(self.out / "results.json", self.results)
        print("PASS " + name, flush=True)

    def snapshot(self, suffix):
        status, data = self.client.call("GET", "/api/profile-runtime/network-qa-home-" + suffix)
        assert status == 200
        return data

    def journal(self, suffix):
        snap = self.snapshot(suffix)
        identifier = next(r["id"] for r in snap["resources"] if r["kind"] == "reservation")
        record = read(self.qa / "config/.config/sealskin/profile-network-runtime" / (identifier + ".json"))
        assert record["identity"]["owner"] == "network-qa"
        assert record["identity"]["home"] == "network-qa-home-" + suffix
        return record

    def dns(self, address=None, fault=""):
        write(self.out / "dns/mode.json", {"addresses": [address or self.addresses["A"]],
              "ttl_seconds": 2, "fault": fault})

    def fixture(self, name, directory, image, command, *options):
        assert network.docker("inspect", name, check=False).returncode != 0
        result = network.docker("run", "-d", "--name", name, "--label", LABEL,
            "--network", "browser-platform-network-qa" if name.endswith("-dns") else "bridge", "--memory", "64m", "--pids-limit", "64",
            "--user", "1000:1000", "--cap-drop", "ALL", "--read-only", "--security-opt", "no-new-privileges:true",
            *options, "--entrypoint", "python3", image, *command)
        identifier = result.stdout.strip()
        saved = read(self.out / "fixtures.json") if (self.out / "fixtures.json").exists() else {}
        saved[name] = {"id": identifier, "directory": str(directory)}
        write(self.out / "fixtures.json", saved)

    def prepare(self, worker_image):
        self.out.mkdir(mode=0o700)
        write(self.out / "images.json", {**self.images, "worker": worker_image})
        assert all(not self.snapshot(s)["resources"] for s in ("a", "b"))
        topology = json.loads(network.docker("network", "inspect", "browser-platform-network-qa").stdout)[0]
        self.addresses = {"A": self.images["upstream_host"], "B": topology["IPAM"]["Config"][0]["Gateway"]}
        assert self.addresses["A"] != self.addresses["B"]
        resolver = str(ipaddress.ip_network(topology["IPAM"]["Config"][0]["Subnet"])[21])
        assert all(m.get("IPv4Address", "").split("/")[0] != resolver for m in topology.get("Containers", {}).values())
        write(self.out / "topology.json", {"addresses": self.addresses, "resolver": resolver})
        credentials = {"username": "qa-" + uuid.uuid4().hex, "password": uuid.uuid4().hex}
        # Two dedicated fixture endpoints replace the preparer's unused default
        # listener only inside the labelled, mount-verified QA container.
        original = json.loads(network.docker("inspect", "network-qa-upstream").stdout)[0]
        assert original["Config"]["Labels"].get("io.browser-platform.qa") == "network-20260913"
        assert any(m["Source"] == str(self.qa / "upstream") for m in original["Mounts"])
        network.docker("stop", "-t", "3", original["Id"])
        for marker, address in self.addresses.items():
            directory = self.out / marker
            directory.mkdir(mode=0o700)
            for source, dest in (("mock-server.pem", "server.pem"), ("mock-server-key.pem", "server-key.pem")):
                (directory / dest).write_bytes((self.qa / source).read_bytes())
                (directory / dest).chmod(0o600)
            write(directory / "mode.json", credentials)
            self.fixture("network-qa-dynamic-" + marker.lower(), directory, self.images["probe"],
                ["/run/fixture.py", "--root", "/qa-dynamic", "--marker", marker],
                "-p", address + ":28181:28181", "-v", str(directory) + ":/qa-dynamic",
                "-v", str(HERE / "dynamic-upstream-fixture.py") + ":/run/fixture.py:ro")
        (self.out / "dns").mkdir(mode=0o700)
        self.dns()
        self.fixture("network-qa-dynamic-dns", self.out / "dns", self.images["controller"],
            ["/run/fixture-dns.py", "--root", "/qa-dns"], "--ip", resolver,
            "--sysctl", "net.ipv4.ip_unprivileged_port_start=0",
            "-v", str(self.out / "dns") + ":/qa-dns", "-v", str(HERE / "bootstrap-dns-fixture.py") + ":/run/fixture-dns.py:ro")
        for name in read(self.out / "fixtures.json"):
            network.wait(lambda: "ready" in network.docker("logs", name).stdout, "dynamic fixture")
        # The controller and each generation's Relay must both reach the same
        # endpoint. Keep endpoint containers off the control bridge: Docker's
        # same-bridge published-port hairpin is not a usable preflight path.
        for address in self.addresses.values():
            network.docker("exec", self.controller_id, "python3", "-c",
                "import socket; socket.create_connection((" + repr(address) + ",28181),timeout=3).close()")
        allow = read(self.qa / "allow.json")
        worker = json.loads(network.docker("image", "inspect", worker_image).stdout)[0]
        assert worker["Id"] == worker_image
        assert worker["Config"]["Labels"].get("io.browser-platform.session-auth") == "1"
        assert allow.get("display_runtime_root"), "prepare-network-qa.py needs --display-runtime-root"
        allow["images"] = list(set(allow["images"] + [worker_image]))
        allow["dynamic_images"] = [self.images["relay"]]
        write(self.qa / "allow.json", allow)
        registry_path = self.qa / "config/.config/sealskin/profile-network-policies.json"
        registry = read(registry_path)
        requests = {}
        for suffix in ("a", "b"):
            policy_id = "network-qa-socks-" + suffix + "-r1"
            policy = registry["policies"][policy_id]
            for kind, value in credentials.items():
                source = self.qa / "config/.config/sealskin/network-secrets" / kind
                source.write_text(value)
                source.chmod(0o600)
                policy[kind + "_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            policy.update(mode="proxy_required", upstream_host="proxy.leak.qa.test", upstream_protocol="socks5",
                          upstream_auth="username_password", bootstrap_resolver_id="qa-dynamic", bootstrap_resolver_ip=resolver)
            revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            app = read(self.qa / ("app-" + suffix + ".json"))
            app["provider_config"].update(network_policy_sha256=revision, image=worker_image,
                docker_overrides={"mem_limit": "1024m", "nano_cpus": 1000000000, "shm_size": "256m", "pids_limit": 512})
            status, _ = self.admin.call("PUT", "/api/admin/apps/installed/" + app["id"], app)
            assert status == 200
            requests[suffix] = {"application_id": app["id"], "profile_id": "network-qa-" + suffix,
                "home_name": "network-qa-home-" + suffix, "operation_id": uuid.uuid4().hex, "wayland_mode": True,
                "url": "https://probe.qa.invalid/", "network_policy_id": policy_id, "network_policy_sha256": revision}
        write(registry_path, registry)
        write(self.out / "requests.json", requests)
        self.passed("private_authenticated_fixtures_ready")

    def launch(self, suffix):
        request = read(self.out / "requests.json")[suffix]
        status, response = self.client.call("POST", "/api/launch/url", request)
        write(self.out / ("launch-" + suffix + ".json"), {"status": status, "response": response})
        assert status == 200, "QA launch failed; see private result"
        return self.snapshot(suffix)

    def flow(self, suffix, expected):
        worker = self.snapshot(suffix)["workers"][0]["instance_id"]
        relay = self.journal(suffix)["allocation"]["relay_ip"]
        ca = (self.qa / "config/.config/sealskin/network-secrets/probe-ca.pem").read_text()
        flow = Flow(worker, relay, ca, self.out / "worker-errors.log")
        self.flows.append(flow)
        flow.get(expected)
        return flow

    def bypass(self, suffix):
        worker = self.snapshot(suffix)["workers"][0]["instance_id"]
        value = json.loads(network.docker("exec", "--user", "1000:1000", worker, "python3", "-c",
                          (HERE / "worker-bypass.py").read_text()).stdout)
        write(self.out / ("bypass-" + suffix + ".json"), value)
        assert len(value) == 4 and all(v["blocked"] for v in value.values())

    def wait_endpoint(self, suffix, address, revision):
        network.wait(lambda: self.journal(suffix)["endpoint"]["selected_ipv4"] == address
                     and self.journal(suffix)["endpoint"]["revision"] == revision, "monitor endpoint refresh", seconds=65)

    def evidence(self, name):
        for suffix in ("a", "b"):
            record = self.journal(suffix)
            write(self.out / (name + "-" + suffix + ".json"), record)
            relay = record["allocation"]["relay_id"]
            rules = network.docker("exec", "--user", "0:0", relay, "nft", "-j", "list", "ruleset").stdout
            value = json.loads(rules)
            write(self.out / (name + "-nft-" + suffix + ".json"), value)
            accepted = []
            for row in value["nftables"]:
                expressions = row.get("rule", {}).get("expr", [])
                if not any("accept" in e for e in expressions):
                    continue
                for e in expressions:
                    match = e.get("match", {})
                    if match.get("left") == {"payload": {"protocol": "ip", "field": "daddr"}}:
                        accepted.append(match["right"])
            assert accepted == [record["endpoint"]["selected_ipv4"]], "Live nft permits an unexpected endpoint"

    def exec_boundary(self):
        record = self.journal("a")
        relay = record["allocation"]["relay_id"]
        worker = self.snapshot("a")["workers"][0]["instance_id"]
        command = ["python3", "-B", "/usr/local/lib/browser-platform/network-guard.py",
                   "--network-config", "/run/browser-platform-network/relay-network.json", "--apply-only"]
        for target, user, args in ((worker, "0:0", command), (relay, "1000:1000", command),
                                   (relay, "0:0", ["sh", "-c", "true"])):
            result = network.docker("-H", "unix:///tmp/browser-platform-network-qa-docker.sock",
                "exec", "--user", user, target, *args, check=False)
            assert result.returncode != 0 and "QA only permits" in result.stderr
        self.passed("real_socket_rejects_worker_wrong_user_arbitrary_command")

    def run(self):
        self.addresses = read(self.out / "topology.json")["addresses"]
        snapshots = {s: self.launch(s) for s in ("a", "b")}
        initial = {s: self.journal(s) for s in ("a", "b")}
        assert len({v["endpoint"]["lease_id"] for v in initial.values()}) == 2
        old = {s: self.flow(s, "A") for s in ("a", "b")}
        self.exec_boundary()
        self.evidence("initial")
        self.passed("two_home_authenticated_https")
        self.dns(self.addresses["B"])
        for s in ("a", "b"):
            self.wait_endpoint(s, self.addresses["B"], 2)
            old[s].get("A")
            self.flow(s, "B").close()
            assert self.snapshot(s)["records"] == snapshots[s]["records"]
            assert self.snapshot(s)["workers"] == snapshots[s]["workers"]
            self.bypass(s)
        self.evidence("switched")
        self.passed("monitor_dns_two_homes_old_A_new_B_same_generation_no_bypass")
        config = read(self.out / "A/mode.json")
        config["reject_auth"] = True
        write(self.out / "A/mode.json", config)
        self.dns(self.addresses["A"])
        for s in ("a", "b"):
            network.wait(lambda: self.journal(s)["endpoint"].get("last_error", {}).get("code") ==
                         "NETWORK_DYNAMIC_ENDPOINT_SWITCH_FAILED", "authentication rollback", seconds=65)
            assert self.journal(s)["endpoint"]["selected_ipv4"] == self.addresses["B"]
            assert self.journal(s)["endpoint"]["revision"] == 2
            self.flow(s, "B").close()
            old[s].get("A")
            self.bypass(s)
        self.evidence("auth-rollback")
        self.passed("authentication_failure_real_probe_rollback_old_flows_alive")
        self.dns(fault="servfail")
        for s in ("a", "b"):
            network.wait(lambda: self.journal(s)["endpoint"].get("last_error", {}).get("code") ==
                         "NETWORK_BOOTSTRAP_DNS_SERVFAIL", "DNS failure retention", seconds=65)
            self.flow(s, "B").close()
        self.evidence("dns-retained")
        self.passed("dns_failure_retains_working_endpoint")
        config["reject_auth"] = False
        write(self.out / "A/mode.json", config)
        self.dns(self.addresses["A"])
        for s in ("a", "b"):
            self.wait_endpoint(s, self.addresses["A"], 3)
            self.flow(s, "A").close()
        self.evidence("recovered")
        self.passed("monitor_recovers_after_fault")
        self.close_flows()
        self.stop("a")
        assert self.snapshot("b")["workers"] == snapshots["b"]["workers"]
        requests = read(self.out / "requests.json")
        requests["a"]["operation_id"] = uuid.uuid4().hex
        write(self.out / "requests.json", requests)
        restarted = self.launch("a")
        assert restarted["workers"] != snapshots["a"]["workers"]
        assert self.journal("a")["endpoint"]["lease_id"] != initial["a"]["endpoint"]["lease_id"]
        assert self.journal("a")["endpoint"]["revision"] == 1
        self.flow("a", "A").close()
        self.flow("b", "A").close()
        self.passed("new_generation_independent_lease_peer_unchanged")
        self.close_flows()
        relay = self.journal("a")["allocation"]["relay_id"]
        write(self.qa / "policy.json", {"mode": "dynamic-apply-error", "instance": relay})
        self.dns(self.addresses["B"])
        try:
            network.wait(lambda: json.loads(network.docker("inspect", relay).stdout)[0]["State"]["Status"] == "exited",
                         "rollback failure stops actual Relay", seconds=65)
            record = self.journal("a")
            assert record["endpoint"].get("pending")
            assert record["endpoint"]["last_error"]["code"] == "NETWORK_DYNAMIC_ENDPOINT_ROLLBACK_FAILED"
            assert self.snapshot("a")["workers"] == restarted["workers"]
            self.bypass("a")
            write(self.out / "guard-failure-a.json", record)
            self.wait_endpoint("b", self.addresses["B"], 4)
            self.flow("b", "B").close()
            assert self.snapshot("b")["workers"] == snapshots["b"]["workers"]
            self.passed("rule_update_and_rollback_failure_stops_owned_relay_peer_healthy_no_bypass")
        finally:
            write(self.qa / "policy.json", {})
        self.stop_all()
        write(self.out / "summary.json", {"result": "PASS", "checks": self.results,
              "scope": "automated HTTPS client inside isolated browser Worker; no GUI acceptance, production or public DNS delegation"})

    def close_flows(self):
        for flow in self.flows:
            flow.close()
        self.flows = []

    def stop(self, suffix):
        snap = self.snapshot(suffix)
        if snap["records"] or snap["workers"] or snap["resources"]:
            request = read(self.out / "requests.json")[suffix]
            body = {k: request[k] for k in ("profile_id", "application_id", "operation_id", "network_policy_id", "network_policy_sha256")}
            body["bootstrap_url"] = request["url"]
            if snap["records"]:
                body["session_id"] = snap["records"][0]["session_id"]
            status, result = self.client.call("POST", "/api/profile-runtime/network-qa-home-" + suffix + "/stop", body)
            write(self.out / ("stop-" + suffix + ".json"), {"status": status, "result": result})
            assert status == 204, "QA stop incomplete"
        snap = self.snapshot(suffix)
        assert not any(snap[k] for k in ("records", "workers", "resources"))

    def stop_all(self):
        self.close_flows()
        for suffix in ("a", "b"):
            self.stop(suffix)
        fixtures = read(self.out / "fixtures.json")
        for name, expected in fixtures.items():
            found = network.docker("inspect", expected["id"], check=False)
            if found.returncode:
                continue
            value = json.loads(found.stdout)[0]
            assert value["Name"] == "/" + name and value["Config"]["Labels"].get("io.browser-platform.qa") == "network-20260913"
            assert any(m["Source"] == expected["directory"] for m in value["Mounts"])
            network.docker("rm", "-f", expected["id"])
        write(self.out / "cleanup.json", {"generations_empty": True, "fixtures_removed": True})


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--worker-image", help="Exact compatible Session-auth browser image")
    parser.add_argument("action", choices=["prepare", "run", "stop"])
    args = parser.parse_args()
    check = Check(args.root)
    try:
        if args.action == "prepare":
            assert args.worker_image, "--worker-image is required for prepare"
            check.prepare(args.worker_image)
        elif args.action == "run":
            check.run()
        else:
            check.stop_all()
    finally:
        check.close_flows()


if __name__ == "__main__":
    main()
