#!/usr/bin/env python3
"""Real duplicate launches and monitor/stop contention in a prepared private QA."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import threading
import time
import uuid

spec = importlib.util.spec_from_file_location("recovery", Path(__file__).with_name("check-dynamic-recovery.py"))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)
dynamic = recovery.dynamic
network, read, write = recovery.network, recovery.read, recovery.write


class Concurrency(recovery.Recovery):
    def __init__(self, qa):
        dynamic.Check.__init__(self, qa)
        self.evidence_root = self.qa.parent / "concurrency"
        self.evidence_root.mkdir(mode=0o700)
        self.addresses = read(self.out / "topology.json")["addresses"]

    def stop_request(self, suffix, snapshot):
        request = read(self.out / "requests.json")[suffix]
        body = {k: request[k] for k in ("profile_id", "application_id", "operation_id", "network_policy_id", "network_policy_sha256")}
        body.update(bootstrap_url=request["url"], session_id=snapshot["records"][0]["session_id"])
        return body

    def run(self):
        requests = read(self.out / "requests.json")
        barrier = threading.Barrier(8)

        def launch(suffix):
            client = network.SecureClient(self.qa)
            barrier.wait(timeout=15)
            started = time.time()
            status, response = client.call("POST", "/api/launch/url", requests[suffix])
            return {"home": suffix, "status": status, "response": response,
                    "started_at": started, "finished_at": time.time()}

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(launch, suffix) for suffix in ("a", "b") for _ in range(4)]
            results = [future.result(timeout=110) for future in futures]
        write(self.evidence_root / "launch-contention.json", results)
        for suffix in ("a", "b"):
            codes = sorted(r["status"] for r in results if r["home"] == suffix)
            assert codes == [200, 409, 409, 409], "Expected exactly one generation per Home"
        snapshots = {s: self.snapshot(s) for s in ("a", "b")}
        for value in snapshots.values():
            assert len(value["records"]) == len(value["workers"]) == 1
            assert len([v for v in value["resources"] if v["kind"] == "reservation"]) == 1
        identity = self.identities()
        write(self.evidence_root / "initial-identities.json", identity)
        journals = {s: self.journal(s) for s in ("a", "b")}
        assert len({j["endpoint"]["lease_id"] for j in journals.values()}) == 2
        self.journal_paths = {s: self.qa / "config/.config/sealskin/profile-network-runtime" /
                              (j["identity"]["home_hash"] + ".json") for s, j in journals.items()}
        for suffix in ("a", "b"):
            self.flow(suffix, "A").close()
            self.bypass(suffix)
        self.result("eight_concurrent_launches_two_unique_home_generations")

        target = min(journals, key=lambda s: journals[s]["identity"]["home_hash"])
        peer = "b" if target == "a" else "a"
        relay = journals[target]["allocation"]["relay_id"]
        worker = snapshots[target]["workers"][0]["instance_id"]
        body = self.stop_request(target, snapshots[target])
        marker = self.qa / "dynamic-held.json"
        marker.unlink(missing_ok=True)
        write(self.qa / "policy.json", {"mode": "dynamic-hold", "instance": relay,
              "stage": "create", "addresses": sorted(self.addresses.values())})
        self.dns(self.addresses["B"])
        network.wait(lambda: marker.exists() and read(marker).get("instance") == relay,
                     "monitor holds Home lock inside actual rule update", seconds=65)
        self.capture(target, self.evidence_root / "monitor-held.json")
        started = threading.Event()

        def stop():
            client = network.SecureClient(self.qa)
            before = time.time()
            started.set()
            status, response = client.call("POST", "/api/profile-runtime/network-qa-home-" + target + "/stop", body)
            return {"status": status, "response": response, "started_at": before, "finished_at": time.time()}

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(stop)
            assert started.wait(timeout=10)
            try:
                # Let the real HTTP request reach the controller. The peer API
                # and HTTPS must finish while the target stop is still waiting.
                time.sleep(1)
                assert not pending.done(), "Stop crossed the monitor Home lock"
                assert self.snapshot(peer)["workers"] == snapshots[peer]["workers"]
                self.flow(peer, "A").close()
                assert not pending.done(), "Stop removed a held generation"
                current = json.loads(network.docker("inspect", worker, relay).stdout)
                assert all(c["State"]["Running"] for c in current)
                assert read(self.journal_paths[target])["endpoint"].get("pending")
                write(self.evidence_root / "stop-waiting.json", {"at": time.time(), "peer_available": True,
                      "target_running": True, "pending_retained": True})
            finally:
                self.dns(self.addresses["A"])
                write(self.qa / "policy.json", {})
            stopped = pending.result(timeout=110)
        write(self.evidence_root / "stop-after-monitor.json", stopped)
        assert stopped["status"] == 204
        assert stopped["finished_at"] - stopped["started_at"] >= 1
        empty = self.snapshot(target)
        assert not any(empty[k] for k in ("records", "workers", "resources"))
        assert not self.journal_paths[target].exists()
        for identifier in identity[target]["containers"]:
            assert network.docker("inspect", identifier, check=False).returncode != 0
        self.result("stop_serializes_with_monitor_peer_remains_available_and_old_resources_removed")

        requests[target]["operation_id"] = uuid.uuid4().hex
        write(self.out / "requests.json", requests)
        restarted = self.launch(target)
        new = self.journal(target)
        assert restarted["workers"] != snapshots[target]["workers"]
        assert new["endpoint"]["lease_id"] != journals[target]["endpoint"]["lease_id"]
        assert new["endpoint"]["revision"] == 1
        status, response = self.client.call("POST", "/api/profile-runtime/network-qa-home-" + target + "/stop", body)
        write(self.evidence_root / "stale-stop.json", {"status": status, "response": response})
        assert status == 409
        assert self.snapshot(target)["workers"] == restarted["workers"]
        assert self.identities()[peer] == identity[peer]
        for suffix in ("a", "b"):
            self.flow(suffix, "A").close()
            self.bypass(suffix)
        self.evidence("after-stale-stop")
        self.result("new_generation_new_lease_stale_stop_rejected_peer_identity_unchanged")
        self.stop_all()
        write(self.evidence_root / "summary.json", {"result": "PASS", "checks": self.results,
              "scope": "eight launch requests/two Homes and actual monitor-stop contention; not a capacity limit or public DNS result"})


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    check = Concurrency(args.root)
    try:
        check.run()
    finally:
        write(check.qa / "policy.json", {})
        check.close_flows()


if __name__ == "__main__":
    main()
