#!/usr/bin/env python3
"""R7G public endpoint rotation using owned QA DNS, bundles and browser Workers.

The existing public endpoint packager/deployer must finish first. Credentials
stay in private run files. This is controlled public QA, not supplier drift.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("dynamic", HERE / "check-dynamic-upstream.py")
dynamic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dynamic)
network, read, write = dynamic.network, dynamic.read, dynamic.write


def replace_zone(current, names, records):
    """Preserve unrelated records, replacing only exact run-owned names."""
    assert names and all(re.fullmatch(r"(?:\*\.)?(?:direct|bootstrap|upstream|observe)-[a-f0-9]{16}\.dns-qa\.azhen\.de\.", n) for n in names)
    assert all(row.split()[0] in names for row in records)
    found = re.findall(r"(?m)^(\s*)([0-9]{10})(\s*; serial[^\n]*)$", current)
    assert len(found) == 1, "Unrecognized SOA serial format"
    serial = int(found[0][1]) + 1
    lines = [line for line in current.splitlines() if not line.split() or line.split()[0] not in names]
    value = re.sub(r"(?m)^(\s*)[0-9]{10}(\s*; serial[^\n]*)$", lambda m: m[1] + str(serial) + m[2], "\n".join(lines))
    return value.rstrip() + "\n" + "\n".join(records) + "\n", serial


class PublicFlow:
    def __init__(self, worker, config, error_log):
        self.errors = error_log.open("ab")
        self.process = subprocess.Popen(["docker", "exec", "-i", "--user", "1000:1000", worker,
            "python3", "-u", "-c", (HERE / "dynamic-public-worker.py").read_text()],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors, text=True)
        self.process.stdin.write(json.dumps(config) + "\n")
        self.process.stdin.flush()

    def request(self, command):
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()
        assert select.select([self.process.stdout], [], [], 20)[0], "Worker public response timeout"
        line = self.process.stdout.readline()
        assert line, "Worker public client failed; see private log"
        return json.loads(line)

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.write("close\n")
            self.process.stdin.flush()
        self.process.wait(timeout=15)
        self.errors.close()


class Public(dynamic.Check):
    def __init__(self, qa):
        super().__init__(qa)
        self.root = self.qa.parent
        self.plan = read(self.root / "dns-plan/plan.json")
        self.bundle = read(self.root / "bundle/bundle.json")
        self.node = read(self.root / "bundle/before/config.json")
        self.names = {n.rstrip(".") for n in self.plan["names"].values()} | {self.node["coherence_domain"]}
        self.addresses = {"A": self.bundle["nodes"]["before"]["ipv4"], "B": self.bundle["nodes"]["after"]["ipv4"]}
        self.authority_config = read(self.root / "public-config.json")
        sys.path.insert(0, str(self.root / "build/dependencies/dnspython-2.8.0-py3-none-any.whl"))

    def authority(self):
        config = self.authority_config
        value = json.loads(network.docker("inspect", config["authority_id"]).stdout)[0]
        assert value["Image"] == config["authority_image"]
        assert value["Name"] == "/r5c2-public-dns-authority"
        assert value["Config"]["Labels"].get("io.browser-platform.qa-role") == "public-dns-authority"
        assert len(value["Mounts"]) == 1
        mount = value["Mounts"][0]
        assert mount["Source"] == config["authority_directory"] and mount["Destination"] == "/qa" and not mount["RW"]
        directory = Path(config["authority_directory"])
        assert directory.resolve() == directory and not (directory / "db.zone").is_symlink()
        return value, directory

    def publish(self, address=None):
        import dns.exception
        import dns.message
        import dns.query
        value, directory = self.authority()
        assert value["State"]["Running"]
        zone = directory / "db.zone"
        original = zone.read_text()
        names = {n + "." for n in self.names}
        records = []
        if address:
            assert address in self.addresses.values()
            for name in sorted(names):
                target = address if name == self.plan["names"]["bootstrap"] else self.addresses["A"]
                records.append(f"{name} 15 IN A {target}")
        changed, serial = replace_zone(original, names, records)
        write(self.out / ("zone-" + str(serial) + ".json"), {"before": original, "after": changed, "at": time.time()})
        fd, temporary = tempfile.mkstemp(prefix=".r7g-zone-", dir=directory)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(changed)
                os.fchmod(stream.fileno(), zone.stat().st_mode & 0o777)
                stream.flush()
                os.fsync(stream.fileno())
            assert zone.read_text() == original, "Concurrent zone change; retry after review"
            os.replace(temporary, zone)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        q = dns.message.make_query("dns-qa.azhen.de", "SOA")
        def loaded():
            try:
                response = dns.query.udp(q, "23.19.231.152", timeout=2)
            except dns.exception.Timeout:
                return False
            return bool(response.answer) and response.answer[0][0].serial == serial
        network.wait(loaded, "public authority serial reload", seconds=15)
        answers = {}
        for transport in ("udp", "tcp"):
            response = getattr(dns.query, transport)(dns.message.make_query(self.plan["names"]["bootstrap"], "A"), "23.19.231.152", timeout=4)
            if address:
                assert [str(v) for rr in response.answer for v in rr] == [address]
            else:
                assert not response.answer
            answers[transport] = response.to_text()
        write(self.out / ("authority-" + str(serial) + ".json"), {"answers": answers, "serial": serial, "at": time.time()})

    def prepare(self, worker_image):
        self.out.mkdir(mode=0o700)
        write(self.out / "fixtures.json", {})
        assert all(not self.snapshot(s)["resources"] for s in ("a", "b"))
        for role in ("before", "after"):
            deployment = read(self.root / ("deployment-" + role + ".json"))
            assert deployment["exit_code"] == 0 and deployment["remote"]["launch"]["run_id"] == self.bundle["run_id"]
        value, directory = self.authority()
        assert value["State"]["Status"] in ("exited", "running")
        assert not any(n in (directory / "db.zone").read_text() for n in self.names), "QA names already exist"
        write(self.out / "authority-before.json", value)
        if not value["State"]["Running"]:
            network.docker("start", value["Id"])
        self.publish(self.addresses["A"])
        worker = json.loads(network.docker("image", "inspect", worker_image).stdout)[0]
        assert worker["Id"] == worker_image and worker["Config"]["Labels"].get("io.browser-platform.session-auth") == "1"
        allow = read(self.qa / "allow.json")
        assert allow.get("display_runtime_root")
        allow["images"] = list(set(allow["images"] + [worker_image]))
        allow["dynamic_images"] = [self.images["relay"]]
        write(self.qa / "allow.json", allow)
        secrets = self.qa / "config/.config/sealskin/network-secrets"
        credentials = read(self.root / "bundle/before/credentials.json")
        for kind in ("username", "password"):
            (secrets / kind).write_text(credentials[kind])
            (secrets / kind).chmod(0o600)
        (secrets / "probe-ca.pem").write_bytes((self.root / "bundle/ca/ca.pem").read_bytes())
        registry_path = self.qa / "config/.config/sealskin/profile-network-policies.json"
        registry = read(registry_path)
        requests = {}
        for suffix in ("a", "b"):
            policy_id = "network-qa-socks-" + suffix + "-r1"
            policy = registry["policies"][policy_id]
            policy.update(mode="proxy_required", upstream_host=self.node["proxy_name"], upstream_port=18180,
                upstream_protocol="socks5", upstream_auth="username_password", bootstrap_resolver_id="qa-public-cloudflare",
                bootstrap_resolver_ip="1.1.1.1", probe_url="https://" + self.node["website_names"][0] + ":18443/probe",
                probe_timeout_seconds=10)
            for kind, name in (("username", "username"), ("password", "password"), ("probe_ca", "probe-ca.pem")):
                policy[kind + "_sha256"] = hashlib.sha256((secrets / name).read_bytes()).hexdigest()
            revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            app = read(self.qa / ("app-" + suffix + ".json"))
            app["provider_config"].update(network_policy_sha256=revision, image=worker_image,
                docker_overrides={"mem_limit": "1024m", "nano_cpus": 1000000000, "shm_size": "256m", "pids_limit": 512})
            status, _ = self.admin.call("PUT", "/api/admin/apps/installed/" + app["id"], app)
            assert status == 200
            requests[suffix] = {"application_id": app["id"], "profile_id": "network-qa-" + suffix,
                "home_name": "network-qa-home-" + suffix, "operation_id": uuid.uuid4().hex, "wayland_mode": True,
                "url": policy["probe_url"], "network_policy_id": policy_id, "network_policy_sha256": revision}
        write(registry_path, registry)
        write(self.out / "requests.json", requests)
        write(self.out / "images.json", {**self.images, "worker": worker_image})
        self.passed("public_bundles_dns_and_two_home_policies_ready")

    def flow(self, suffix, expected):
        worker = self.snapshot(suffix)["workers"][0]["instance_id"]
        config = {"relay": self.journal(suffix)["allocation"]["relay_ip"],
                  "ca": (self.root / "bundle/ca/ca.pem").read_text(),
                  "observer": self.node["coherence_domain"], "website": self.node["website_names"][0]}
        flow = PublicFlow(worker, config, self.out / "worker-errors.log")
        self.flows.append(flow)
        assert flow.request("echo")["endpoint"] == "before"
        result = flow.request("whoami")
        write(self.out / ("whoami-" + result["nonce"] + ".json"), result)
        assert result["public_ip"] == expected and result["source_kind"] == "socket", "Observed public source differs from selected proxy"
        return flow

    def run(self):
        snapshots = {s: self.launch(s) for s in ("a", "b")}
        before = {s: self.journal(s) for s in ("a", "b")}
        assert all(v["endpoint"]["revision"] == 1 for v in before.values())
        assert len({v["endpoint"]["lease_id"] for v in before.values()}) == 2
        old = {s: self.flow(s, self.addresses["A"]) for s in ("a", "b")}
        self.evidence("public-initial")
        self.passed("two_home_public_authenticated_https_and_wss")
        self.publish(self.addresses["B"])
        for suffix in ("a", "b"):
            self.wait_endpoint(suffix, self.addresses["B"], 2)
            assert old[suffix].request("echo")["endpoint"] == "before"
            self.flow(suffix, self.addresses["B"]).close()
            assert self.snapshot(suffix)["records"] == snapshots[suffix]["records"]
            assert self.snapshot(suffix)["workers"] == snapshots[suffix]["workers"]
            self.bypass(suffix)
        self.evidence("public-switched")
        self.passed("public_recursive_dns_new_connections_B_retained_WSS_same_generation")
        self.publish(self.addresses["A"])
        for suffix in ("a", "b"):
            self.wait_endpoint(suffix, self.addresses["A"], 3)
            self.flow(suffix, self.addresses["A"]).close()
            assert old[suffix].request("echo")["endpoint"] == "before"
            self.bypass(suffix)
        self.evidence("public-returned")
        self.passed("public_A_B_A_roundtrip_and_worker_bypass_rejected")
        self.stop_all()
        write(self.out / "summary.json", {"result": "PASS", "checks": self.results,
              "scope": "controlled public QA recursive DNS/authenticated SOCKS5/two Workers; no supplier natural drift or GUI validation"})

    def stop_all(self):
        super().stop_all()
        self.publish()
        if not read(self.out / "authority-before.json")["State"]["Running"]:
            value, _ = self.authority()
            network.docker("stop", "-t", "5", value["Id"])
        write(self.out / "public-cleanup.json", {"owned_records_removed": True, "authority_original_running_state_restored": True,
              "remote_endpoints": "require scoped manage.py stop/collect/purge"})


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--worker-image")
    parser.add_argument("action", choices=("prepare", "run", "stop"))
    args = parser.parse_args()
    check = Public(args.root)
    try:
        if args.action == "prepare":
            assert args.worker_image
            check.prepare(args.worker_image)
        elif args.action == "run":
            check.run()
        else:
            check.stop_all()
    finally:
        check.close_flows()


if __name__ == "__main__":
    main()
