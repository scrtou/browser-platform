#!/usr/bin/env python3
"""Upgrade isolated static generations, mix a dynamic peer, then cleanly revert.

Uses exact current production image bytes in QA only. Does not mount production
configuration, Home, credentials or Session state. Public QA is separate.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
import uuid

spec = importlib.util.spec_from_file_location("recovery", Path(__file__).with_name("check-dynamic-recovery.py"))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)
dynamic = recovery.dynamic
network, read, write = recovery.network, recovery.read, recovery.write


class Compatibility(recovery.Recovery):
    def __init__(self, qa, controller, relay):
        dynamic.Check.__init__(self, qa)
        self.evidence_root = self.qa.parent / "compatibility"
        self.evidence_root.mkdir(mode=0o700)
        self.addresses = read(self.out / "topology.json")["addresses"]
        self.candidate = read(self.out / "images.json")["controller"]
        self.baseline, self.old_relay = controller, relay
        for value in (controller, relay, self.candidate):
            assert value.startswith("sha256:") and len(value) == 71
            assert json.loads(network.docker("image", "inspect", value).stdout)[0]["Id"] == value

    def replace_controller(self, image, name):
        assert image in (self.candidate, self.baseline)
        if image == self.baseline:
            # Never feed a legacy controller any remaining dynamic transaction.
            for path in (self.qa / "config/.config/sealskin/profile-network-runtime").glob("*.json"):
                assert not read(path).get("endpoint"), "Clean dynamic generations before rollback"
        value = json.loads(network.docker("inspect", self.controller_id).stdout)[0]
        assert value["Name"] == "/sealskin-network-qa"
        assert value["Config"]["Labels"].get("io.browser-platform.qa") == "network-20260913"
        mounts = {m["Destination"]: m for m in value["Mounts"]}
        assert set(mounts) == {"/config", "/storage", "/var/run/docker.sock", "/run/browser-platform-session-secrets"}
        assert mounts["/config"]["Source"] == str(self.qa / "config")
        assert mounts["/storage"]["Source"] == str(self.qa / "storage")
        write(self.evidence_root / (name + "-before.json"), value)
        network.docker("stop", "-t", "5", self.controller_id)
        network.docker("rm", self.controller_id)
        command = ["run", "-d", "--name", "sealskin-network-qa", "--label", "io.browser-platform.qa=network-20260913",
            "--network", "browser-platform-network-qa", "--memory", "512m", "--cpus", "1.5", "--pids-limit", "256",
            "-e", "PUID=1000", "-e", "PGID=1000", "-e", "TZ=Etc/UTC", "-e", "HOST_URL=network.invalid",
            "-p", "127.0.0.1:28110:8000"]
        for mount in mounts.values():
            assert mount["Type"] == "bind"
            command += ["-v", mount["Source"] + ":" + mount["Destination"] + ("" if mount["RW"] else ":ro")]
        self.controller_id = network.docker(*command, image).stdout.strip()
        network.wait(lambda: network.request("POST", "/api/handshake/initiate")[0] == 200, "replacement QA controller", seconds=90)
        self.client = network.SecureClient(self.qa)
        admin = read(self.qa / "admin.json")
        self.admin = network.SecureClient(self.qa, username=admin["username"], private=admin["private_key"].encode())
        write(self.evidence_root / (name + "-after.json"), json.loads(network.docker("inspect", self.controller_id).stdout)[0])

    def policies(self, old):
        path = self.qa / "config/.config/sealskin/profile-network-policies.json"
        registry = read(path)
        requests = read(self.out / "requests.json")
        allow = read(self.qa / "allow.json")
        allow["images"] = list(set(allow["images"] + [self.old_relay]))
        allow["guard_images"] = list(set(allow["guard_images"] + [self.old_relay]))
        write(self.qa / "allow.json", allow)
        for suffix in (("a", "b") if old else ("b",)):
            assert not self.snapshot(suffix)["resources"]
            original_id = requests[suffix]["network_policy_id"]
            policy = dict(registry["policies"][original_id])
            if old:
                policy.update(relay_image=self.old_relay, upstream_host=self.addresses["A"])
                # The compatibility serializer omits empty optional DNS fields.
                # Hash the canonical legacy snapshot rather than explicit empties.
                policy.pop("bootstrap_resolver_id", None)
                policy.pop("bootstrap_resolver_ip", None)
            else:
                policy.update(relay_image=self.images["relay"], upstream_host="proxy.leak.qa.test",
                              bootstrap_resolver_id="qa-dynamic", bootstrap_resolver_ip=read(self.out / "topology.json")["resolver"])
            policy_id = "network-qa-socks-" + suffix + ("-static-r2" if old else "-dynamic-r3")
            registry["policies"][policy_id] = policy
            revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            status, apps = self.admin.call("GET", "/api/admin/apps/installed")
            assert status == 200
            app = next(a for a in apps if a["id"] == requests[suffix]["application_id"])
            app["provider_config"].update(network_policy_id=policy_id, network_policy_sha256=revision)
            status, _ = self.admin.call("PUT", "/api/admin/apps/installed/" + app["id"], app)
            assert status == 200
            requests[suffix].update(network_policy_id=policy_id, network_policy_sha256=revision, operation_id=uuid.uuid4().hex)
        write(path, registry)
        write(self.out / "requests.json", requests)

    def run(self):
        assert all(not self.snapshot(s)["resources"] for s in ("a", "b"))
        self.policies(old=True)
        self.replace_controller(self.baseline, "baseline")
        for suffix in ("a", "b"):
            self.launch(suffix)
            assert not self.journal(suffix).get("endpoint")
        original = self.identities()
        write(self.evidence_root / "static-identities.json", original)
        old_flow = {s: self.flow(s, "A") for s in ("a", "b")}
        self.result("production_image_bytes_create_two_isolated_static_generations")

        self.replace_controller(self.candidate, "upgrade")
        for suffix in ("a", "b"):
            network.wait(lambda: self.journal(suffix)["controller_id"] == self.controller_id,
                         "candidate attaches existing static generation", seconds=35)
            assert not self.journal(suffix).get("endpoint")
            old_flow[suffix].get("A")
            self.flow(suffix, "A").close()
            self.bypass(suffix)
        assert self.identities() == original
        self.result("candidate_upgrades_static_generations_without_restarting_worker_guard_relay")

        old_flow["b"].close()
        self.stop("b")
        self.policies(old=False)
        self.launch("b")
        assert self.journal("b")["endpoint"]["revision"] == 1
        assert self.identities()["a"] == original["a"]
        self.dns(self.addresses["B"])
        self.wait_endpoint("b", self.addresses["B"], 2)
        self.flow("b", "B").close()
        old_flow["a"].get("A")
        self.flow("a", "A").close()
        assert not self.journal("a").get("endpoint")
        assert self.identities()["a"] == original["a"]
        for suffix in ("a", "b"):
            self.bypass(suffix)
            write(self.evidence_root / ("mixed-" + suffix + ".json"), self.journal(suffix))
        self.result("static_numeric_home_and_dynamic_domain_peer_coexist_during_refresh")

        self.stop("b")
        self.replace_controller(self.baseline, "controlled-rollback")
        network.wait(lambda: self.journal("a")["controller_id"] == self.controller_id,
                     "legacy controller reattaches static generation", seconds=35)
        assert self.identities_one("a") == original["a"]
        old_flow["a"].get("A")
        self.flow("a", "A").close()
        self.bypass("a")
        self.result("legacy_rollback_after_dynamic_cleanup_preserves_static_generation")
        self.stop_all()
        self.replace_controller(self.candidate, "restore-candidate-empty")
        write(self.evidence_root / "summary.json", {"result": "PASS", "checks": self.results,
              "scope": "isolated current image bytes and legacy file credentials; no production Home/Secret Store migration or client acceptance"})

    def identities_one(self, suffix):
        snapshot = self.snapshot(suffix)
        record = self.journal(suffix)
        ids = [snapshot["workers"][0]["instance_id"], record["allocation"]["relay_id"], record["allocation"]["guard_id"]]
        containers = json.loads(network.docker("inspect", *ids).stdout)
        return {"records": snapshot["records"], "containers": {c["Id"]: {
            "image": c["Image"], "pid": c["State"]["Pid"], "started_at": c["State"]["StartedAt"],
            "network_mode": c["HostConfig"]["NetworkMode"]} for c in containers}}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--baseline-controller", required=True)
    parser.add_argument("--baseline-relay", required=True)
    args = parser.parse_args()
    check = Compatibility(args.root, args.baseline_controller, args.baseline_relay)
    try:
        check.run()
    finally:
        check.close_flows()


if __name__ == "__main__":
    main()
