#!/usr/bin/env python3
"""Real dynamic endpoint refresh plus isolated Secret Store leases/revocation."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import time
import uuid

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


recovery = module("recovery", Path(__file__).with_name("check-dynamic-recovery.py"))
dynamic = recovery.dynamic
network, read, write = recovery.network, recovery.read, recovery.write


class Secrets(recovery.Recovery):
    def __init__(self, qa):
        dynamic.Check.__init__(self, qa)
        self.evidence_root = self.qa.parent / "secret-combination"
        self.evidence_root.mkdir(mode=0o700, exist_ok=True)
        self.addresses = read(self.out / "topology.json")["addresses"]
        self.material_root = Path(read(self.qa / "allow.json")["credential_runtime_root"])
        assert self.material_root.parent == Path("/dev/shm") and self.material_root.resolve() == self.material_root
        source = self.qa.parent / "build/payload/app/secret_store.py"
        manifest = read(self.qa.parent / "build/payload/manifest.json")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["files"]["secret_store.py"]["after"]
        self.storage = module("qa_secret_store", source)
        self.store = self.storage.FileSecretStore(self.qa / "config/.config/sealskin/proxy-secret-store",
                                                 self.qa.parent / "secret-combination-key/master.key")
        self.credentials = read(self.out / "A/mode.json")
        self.refs = {}

    def publish(self):
        path = self.qa / "config/.config/sealskin/profile-network-policies.json"
        registry = read(path)
        requests = read(self.out / "requests.json")
        status, apps = self.admin.call("GET", "/api/admin/apps/installed")
        assert status == 200
        for suffix in ("a", "b"):
            assert not self.snapshot(suffix)["resources"]
            request = requests[suffix]
            identifier = "dynamic-qa-" + suffix + "-" + uuid.uuid4().hex[:12]
            self.store.put(identifier, 1, [{"owner": "network-qa", "profile": request["profile_id"],
                "home": request["home_name"], "app": request["application_id"]}], **self.credentials)
            refs = self.storage.references(identifier, 1)
            self.refs[suffix] = refs
            policy = dict(registry["policies"][request["network_policy_id"]])
            policy.update(username_file="", username_sha256="", password_file="", password_sha256="",
                          username_secret_ref=refs["username"], password_secret_ref=refs["password"])
            policy_id = "network-qa-store-" + suffix
            registry["policies"][policy_id] = policy
            revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            app = next(a for a in apps if a["id"] == request["application_id"])
            app["provider_config"].update(network_policy_id=policy_id, network_policy_sha256=revision)
            status, _ = self.admin.call("PUT", "/api/admin/apps/installed/" + app["id"], app)
            assert status == 200
            request.update(network_policy_id=policy_id, network_policy_sha256=revision)
        write(path, registry)
        write(self.out / "requests.json", requests)
        write(self.evidence_root / "references.json", self.refs)

    def materials(self, suffix):
        snap, record = self.snapshot(suffix), self.journal(suffix)
        assert snap["secret_store_version"] == 1
        containers = json.loads(network.docker("inspect", snap["workers"][0]["instance_id"], record["allocation"]["relay_id"]).stdout)
        worker, relay = containers
        mount = next(m for m in relay["Mounts"] if m["Destination"] == "/run/secrets")
        directory = Path(mount["Source"])
        assert not mount["RW"] and directory.parent == self.material_root
        assert directory.stat().st_mode & 0o777 == 0o700
        assert {p.name for p in directory.iterdir()} == {"username", "password", "lease"}
        for kind in ("username", "password"):
            assert (directory / kind).read_text() == self.credentials[kind]
            assert (directory / kind).stat().st_mode & 0o777 == 0o600
        assert not any(Path(m["Source"]).is_relative_to(self.material_root) for m in worker["Mounts"])
        assert not any("master.key" in m["Source"] or "proxy-secret-store" in m["Source"] for c in containers for m in c["Mounts"])
        for value in self.credentials.values():
            assert value not in json.dumps([c["Config"] for c in containers])
            assert value not in json.dumps(record)
        lease = (directory / "lease").read_bytes()
        assert lease.startswith(b"active:")
        return directory, hashlib.sha256(lease).hexdigest()

    def run(self):
        self.publish()
        for suffix in ("a", "b"):
            self.launch(suffix)
        identity = self.identities()
        write(self.evidence_root / "initial-identities.json", identity)
        journals = {s: self.journal(s) for s in ("a", "b")}
        self.journal_paths = {s: self.qa / "config/.config/sealskin/profile-network-runtime" /
                              (j["identity"]["home_hash"] + ".json") for s, j in journals.items()}
        material = {s: self.materials(s) for s in ("a", "b")}
        assert material["a"][0] != material["b"][0]
        old = {s: self.flow(s, "A") for s in ("a", "b")}
        self.result("two_dynamic_homes_use_separate_readonly_secret_leases")
        self.dns(self.addresses["B"])
        for suffix in ("a", "b"):
            self.wait_endpoint(suffix, self.addresses["B"], 2)
            assert self.materials(suffix) == material[suffix]
            self.flow(suffix, "B").close()
            old[suffix].get("A")
            self.bypass(suffix)
        assert self.identities() == identity
        self.result("endpoint_refresh_preserves_secret_lease_and_process_identity")

        target = min(journals, key=lambda s: journals[s]["identity"]["home_hash"])
        peer = "b" if target == "a" else "a"
        relay = journals[target]["allocation"]["relay_id"]
        marker = self.qa / "dynamic-held.json"
        marker.unlink(missing_ok=True)
        write(self.qa / "policy.json", {"mode": "dynamic-hold", "instance": relay,
              "stage": "create", "addresses": sorted(self.addresses.values())})
        self.dns(self.addresses["A"])
        network.wait(lambda: marker.exists() and read(marker).get("instance") == relay, "monitor before concurrent revoke", seconds=65)
        self.capture(target, self.evidence_root / "monitor-held.json")
        body = {"secret_ref": self.refs[target]["password"], "operation_id": uuid.uuid4().hex}
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.admin.call, "POST", "/api/admin/profile-secrets/revoke", body)
            try:
                network.wait(lambda: (material[target][0] / "lease").read_bytes() == b"revoked\n", "credential lease revoked while Home locked", seconds=6)
                network.wait(lambda: not json.loads(network.docker("inspect", relay).stdout)[0]["State"]["Running"],
                             "revoked Relay exits before cleanup obtains Home lock", seconds=6)
                assert not pending.done(), "Revocation cleanup crossed the monitor Home lock"
                flow = old[target]
                flow.process.stdin.write("get\n")
                flow.process.stdin.flush()
                assert select.select([flow.process.stdout], [], [], 10)[0]
                assert flow.process.stdout.readline() == ""
                assert flow.process.wait(timeout=10) != 0
                self.bypass_direct(journals[target], identity[target])
                self.flow(peer, "B").close()
                write(self.evidence_root / "revoked-before-cleanup.json", {"relay_exited": True, "lease_revoked": True,
                      "old_connection_closed": True, "peer_available": True, "cleanup_waits_for_home": True})
            finally:
                self.dns(self.addresses["B"])
                write(self.qa / "policy.json", {})
            status, result = pending.result(timeout=110)
        write(self.evidence_root / "revoke-result.json", {"status": status, "result": result})
        assert status == 200 and result["egress_blocked"] and result["cleanup_complete"]
        assert not material[target][0].exists()
        snap = self.snapshot(target)
        assert not any(snap[k] for k in ("records", "workers", "resources"))
        requests = read(self.out / "requests.json")
        request = requests[target]
        request["operation_id"] = uuid.uuid4().hex
        write(self.out / "requests.json", requests)
        status, value = self.client.call("POST", "/api/launch/url", request)
        write(self.evidence_root / "revoked-launch.json", {"status": status, "response": value})
        assert status == 409 and value["detail"] == "SECRET_REVOKED"
        denied = self.snapshot(target)
        assert not denied["records"] and not denied["workers"]
        assert self.materials(peer) == material[peer]
        self.flow(peer, "B").close()
        self.result("revocation_during_refresh_closes_egress_cleans_and_rejects_relaunch_peer_healthy")
        self.stop_all()
        assert not any(self.material_root.iterdir())
        write(self.evidence_root / "summary.json", {"result": "PASS", "checks": self.results,
              "scope": "isolated dynamic endpoint and Secret Store composition; no production credentials or Home migration"})

    def bypass_direct(self, journal, identity):
        # The normal snapshot API waits on the held Home lock. Use the verified
        # initial Worker identity to check rejection while revocation is pending.
        worker = next(k for k, v in identity["containers"].items() if v["network_mode"].startswith("container:"))
        value = json.loads(network.docker("exec", "--user", "1000:1000", worker, "python3", "-c",
                          (Path(__file__).with_name("worker-bypass.py")).read_text()).stdout)
        assert len(value) == 4 and all(v["blocked"] for v in value.values())
        write(self.evidence_root / "revoked-bypass.json", value)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    check = Secrets(args.root)
    try:
        check.run()
    finally:
        write(check.qa / "policy.json", {})
        check.close_flows()


if __name__ == "__main__":
    main()
