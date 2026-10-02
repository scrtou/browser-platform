#!/usr/bin/env python3
"""Crash a scoped QA controller at real dynamic endpoint transaction boundaries.

Requires check-dynamic-upstream.py prepare. Does not inject synthetic leases:
the running monitor creates pending, installs nft and writes the endpoint.
Only the mount-verified QA controller is killed/replaced; browser Workers stay.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import time

spec = importlib.util.spec_from_file_location("dynamic_checks", Path(__file__).with_name("check-dynamic-upstream.py"))
dynamic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dynamic)
network, read, write = dynamic.network, dynamic.read, dynamic.write


class Recovery(dynamic.Check):
    def __init__(self, qa):
        super().__init__(qa)
        self.evidence_root = self.qa.parent / "recovery"
        self.evidence_root.mkdir(mode=0o700)
        self.addresses = read(self.out / "topology.json")["addresses"]

    def result(self, name):
        self.results.append({"check": name, "result": "PASS", "at": time.time()})
        write(self.evidence_root / "results.json", self.results)
        print("PASS " + name, flush=True)

    def identities(self):
        value = {}
        for suffix in ("a", "b"):
            snapshot = self.snapshot(suffix)
            record = self.journal(suffix)
            ids = [snapshot["workers"][0]["instance_id"], record["allocation"]["relay_id"], record["allocation"]["guard_id"]]
            containers = json.loads(network.docker("inspect", *ids).stdout)
            value[suffix] = {"records": snapshot["records"], "containers": {c["Id"]: {
                "image": c["Image"], "pid": c["State"]["Pid"], "started_at": c["State"]["StartedAt"],
                "network_mode": c["HostConfig"]["NetworkMode"]} for c in containers}}
        return value

    def capture(self, suffix, path):
        # The monitor owns the Home lock at an injected crash point. Read its
        # durable journal directly; the normal inspection API correctly waits
        # for that lock and would otherwise let the bounded gate time out.
        record = read(self.journal_paths[suffix])
        assert record["identity"]["owner"] == "network-qa"
        assert record["identity"]["home"] == "network-qa-home-" + suffix
        identity = record["identity"]
        runtime = self.qa / "config/.config/sealskin/profile-network-runtime" / (identity["home_hash"] + "-" + identity["operation"])
        nft = json.loads(network.docker("exec", "--user", "0:0", record["allocation"]["relay_id"],
                                     "nft", "-j", "list", "ruleset").stdout)
        accepted = set()
        for row in nft["nftables"]:
            expressions = row.get("rule", {}).get("expr", [])
            if any("accept" in e for e in expressions):
                for expr in expressions:
                    match = expr.get("match", {})
                    if match.get("left") == {"payload": {"protocol": "ip", "field": "daddr"}}:
                        target = match["right"]
                        accepted.update([target] if isinstance(target, str) else target["set"])
        value = {"reservation": record, "lease": read(runtime / "upstream-endpoint.json"),
                 "config": read(runtime / "relay-network.json"), "nft": nft, "accepted_ipv4": sorted(accepted)}
        write(path, value)
        return value

    def kill_controller(self, case, replace, recovery_fault=None):
        controller = json.loads(network.docker("inspect", self.controller_id).stdout)[0]
        assert controller["Name"] == "/sealskin-network-qa"
        assert controller["Config"]["Labels"].get("io.browser-platform.qa") == "network-20260913"
        assert any(m["Destination"] == "/config" and m["Source"] == str(self.qa / "config") for m in controller["Mounts"])
        assert any(m["Destination"] == "/storage" and m["Source"] == str(self.qa / "storage") for m in controller["Mounts"])
        write(case / "controller-before.json", controller)
        network.docker("kill", "--signal", "KILL", self.controller_id)
        assert json.loads(network.docker("inspect", self.controller_id).stdout)[0]["State"]["Status"] == "exited"
        # The blocked old request is released as a failure, never as a late write.
        write(self.qa / "policy.json", {"mode": "dynamic-apply-error", "instance": recovery_fault} if recovery_fault else {})
        self.dns(self.addresses["A"])
        if replace:
            network.docker("rm", self.controller_id)
            allowed = {"/config", "/storage", "/var/run/docker.sock", "/run/browser-platform-session-secrets"}
            assert {m["Destination"] for m in controller["Mounts"]} == allowed
            command = ["run", "-d", "--name", "sealskin-network-qa", "--label", "io.browser-platform.qa=network-20260913",
                "--network", "browser-platform-network-qa", "--memory", "512m", "--cpus", "1.5", "--pids-limit", "256",
                "-e", "PUID=1000", "-e", "PGID=1000", "-e", "TZ=Etc/UTC", "-e", "HOST_URL=network.invalid",
                "-p", "127.0.0.1:28110:8000"]
            for mount in controller["Mounts"]:
                assert mount["Type"] == "bind"
                command += ["-v", mount["Source"] + ":" + mount["Destination"] + ("" if mount["RW"] else ":ro")]
            self.controller_id = network.docker(*command, controller["Image"]).stdout.strip()
            assert self.controller_id != controller["Id"]
        else:
            network.docker("start", self.controller_id)
        network.wait(lambda: network.request("POST", "/api/handshake/initiate")[0] == 200, "restarted QA controller", seconds=90)
        self.client = network.SecureClient(self.qa)
        admin = read(self.qa / "admin.json")
        self.admin = network.SecureClient(self.qa, username=admin["username"], private=admin["private_key"].encode())
        write(case / "controller-after.json", json.loads(network.docker("inspect", self.controller_id).stdout)[0])

    def run(self):
        for suffix in ("a", "b"):
            self.launch(suffix)
        journals = {s: self.journal(s) for s in ("a", "b")}
        self.journal_paths = {s: self.qa / "config/.config/sealskin/profile-network-runtime" /
                              (j["identity"]["home_hash"] + ".json") for s, j in journals.items()}
        workers = {s: self.snapshot(s)["workers"][0]["instance_id"] for s in ("a", "b")}
        identity = self.identities()
        write(self.evidence_root / "initial-identities.json", identity)
        old = {s: self.flow(s, "A") for s in ("a", "b")}
        # Hold the first sorted journal so the serial monitor has not yet moved
        # the peer. This makes each pre-crash network state unambiguous.
        target = min(("a", "b"), key=lambda s: self.journal(s)["identity"]["home_hash"])
        relay = self.journal(target)["allocation"]["relay_id"]
        cases = [("pending_before_rules", "create", sorted(self.addresses.values()), ["A"], "A", False),
                 ("new_lease_before_commit", "create", [self.addresses["B"]], ["A", "B"], "B", True),
                 ("new_rules_before_ack", "result", [self.addresses["B"]], ["B"], "B", False)]
        for name, stage, held_addresses, allowed, lease, replace in cases:
            case = self.evidence_root / name
            case.mkdir(mode=0o700)
            marker = self.qa / "dynamic-held.json"
            if marker.exists():
                marker.unlink()
            before = self.journal(target)
            assert before["endpoint"]["selected_ipv4"] == self.addresses["A"]
            write(self.qa / "policy.json", {"mode": "dynamic-hold", "instance": relay,
                  "stage": stage, "addresses": held_addresses})
            self.dns(self.addresses["B"])
            network.wait(lambda: marker.exists() and read(marker).get("instance") == relay
                         and read(marker).get("stage") == stage, "actual endpoint transaction crash point", seconds=65)
            captured = self.capture(target, case / "interrupted.json")
            assert captured["reservation"]["endpoint"]["pending"] == {
                "revision": before["endpoint"]["revision"] + 1, "selected_ipv4": self.addresses["B"]}
            assert captured["lease"]["upstream_ip"] == self.addresses[lease]
            assert captured["accepted_ipv4"] == sorted(self.addresses[a] for a in allowed)
            ca = (self.qa / "config/.config/sealskin/network-secrets/probe-ca.pem").read_text()
            flow = dynamic.Flow(workers[target], journals[target]["allocation"]["relay_ip"], ca,
                                self.out / "worker-errors.log")
            self.flows.append(flow)
            flow.get(lease)
            flow.close()
            self.kill_controller(case, replace)
            network.wait(lambda: not self.journal(target)["endpoint"].get("pending"), "startup pending rollback", seconds=35)
            after = self.capture(target, case / "recovered.json")
            assert after["lease"]["upstream_ip"] == self.addresses["A"]
            assert after["accepted_ipv4"] == [self.addresses["A"]]
            assert after["reservation"]["endpoint"]["revision"] == before["endpoint"]["revision"]
            assert after["reservation"]["controller_id"] == self.controller_id
            assert self.identities() == identity
            for suffix in ("a", "b"):
                old[suffix].get("A")
                self.flow(suffix, "A").close()
                self.bypass(suffix)
            write(case / "identities.json", self.identities())
            self.result(name + ("_replacement" if replace else "_restart"))
        self.close_flows()
        case = self.evidence_root / "failed_recovery_retry"
        case.mkdir(mode=0o700)
        marker = self.qa / "dynamic-held.json"
        marker.unlink()
        write(self.qa / "policy.json", {"mode": "dynamic-hold", "instance": relay,
              "stage": "create", "addresses": [self.addresses["B"]]})
        self.dns(self.addresses["B"])
        network.wait(lambda: marker.exists(), "pending before failed recovery", seconds=65)
        self.capture(target, case / "interrupted.json")
        self.kill_controller(case, False, recovery_fault=relay)
        network.wait(lambda: json.loads(network.docker("inspect", relay).stdout)[0]["State"]["Status"] == "exited",
                     "failed startup rollback stops Relay", seconds=35)
        failed = self.journal(target)
        assert failed["endpoint"].get("pending")
        assert failed["endpoint"]["last_error"]["code"] == "NETWORK_DYNAMIC_ENDPOINT_ROLLBACK_FAILED"
        write(case / "failed.json", failed)
        self.bypass(target)
        peer = "b" if target == "a" else "a"
        self.flow(peer, "A").close()
        # Explicit repair of the already verified QA Relay, then a replacement
        # controller retries the durable pending transaction.
        current = json.loads(network.docker("inspect", relay).stdout)[0]
        labels = current["Config"]["Labels"]
        assert labels["io.browser-platform.owner"] == "network-qa"
        assert labels["io.browser-platform.operation"] == failed["identity"]["operation"]
        write(self.qa / "policy.json", {})
        network.docker("start", relay)
        retry = case / "retry"
        retry.mkdir(mode=0o700)
        self.kill_controller(retry, True)
        network.wait(lambda: self.journal(target)["controller_id"] == self.controller_id,
                     "successful retry reconnects controller", seconds=35)
        restored = self.capture(target, retry / "recovered.json")
        assert not restored["reservation"]["endpoint"].get("pending")
        assert not restored["reservation"]["endpoint"].get("last_error")
        assert restored["accepted_ipv4"] == [self.addresses["A"]]
        after = self.identities()
        for suffix in ("a", "b"):
            assert after[suffix]["records"] == identity[suffix]["records"]
            for identifier, state in identity[suffix]["containers"].items():
                if identifier != relay:
                    assert after[suffix]["containers"][identifier] == state
            self.flow(suffix, "A").close()
            self.bypass(suffix)
        write(retry / "identities.json", after)
        self.result("failed_recovery_stops_owned_relay_then_successful_retry_reconnects")
        self.close_flows()
        self.stop_all()
        write(self.evidence_root / "summary.json", {"result": "PASS", "checks": self.results,
              "scope": "real isolated controller interruption/recovery; no production or target-client validation"})


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    check = Recovery(args.root)
    try:
        check.run()
    finally:
        write(check.qa / "policy.json", {})
        check.close_flows()


if __name__ == "__main__":
    main()
