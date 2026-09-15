#!/usr/bin/env python3
"""Run the R5E browser client against an explicitly prepared private QA root."""

import argparse
import copy
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit
import uuid

CHECKS = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


entry = module("combination_entry_runner", CHECKS / "run-entry-auth.py")
prepare = module("combination_prepare", CHECKS / "prepare-release-combination.py")
recovery = module("combination_recovery", CHECKS / "check-coherence-recovery.py")
network = entry.network
require = prepare.require


class Coordinator(entry.Coordinator):
    def __init__(self, qa, output, phase):
        self.qa, self.output = qa, output
        self.config = json.loads((qa / "adapter-config.json").read_text())
        self.active = json.loads((qa / "access/active-candidate.json").read_text())
        self.candidate = Path(self.active["candidate"])
        self.accounts = json.loads((qa / "access/test-accounts.json").read_text())
        self.profiles = {p["id"]: p for p in self.config["profiles"]}
        self.display = Path(self.active["display_runtime_root"])
        self.credentials = Path(self.active["credential_runtime_root"])
        self.key_directory = Path(self.active["key_directory"])
        self.state = (qa / self.config["state_file"]).resolve()
        self.website_origin = self.active["website_origin"]
        self.endpoint_bundle = Path(self.active["endpoint_bundle"])
        self.endpoint = json.loads((self.endpoint_bundle / "before/config.json").read_text())
        self.metadata = qa / "config/.config/sealskin"
        require(qa == self.candidate / "qa" and self.candidate.parent.name == "r5e-release-combination-2026-09-15",
                "R5E_QA_SCOPE_REQUIRED")
        resource_path = self.candidate / "resources.json"
        if not resource_path.exists():
            resource_path = self.candidate.parent / "resources.json"
        resources = json.loads(resource_path.read_text())
        require(resources["qa"] == str(qa) and resources["candidate"] == str(self.candidate)
                and resources["display"] == str(self.display) and resources["credentials"] == str(self.credentials)
                and resources["key_directory"] == str(self.key_directory), "R5E_RESOURCE_REGISTRY_MISMATCH")
        require(self.config["sealskin"]["username"] == "network-qa" and self.config["listen_address"] == "127.0.0.1:29110"
                and self.state == qa / "adapter-state.json", "R5E_ADAPTER_SCOPE_REQUIRED")
        require(set(self.profiles) == {"network-qa-entry-a", "network-qa-entry-b"} and
                {p["home_name"] for p in self.profiles.values()} == {"network-qa-home-entry-a", "network-qa-home-entry-b"},
                "R5E_PROFILE_SCOPE_REQUIRED")
        require(self.website_origin == f"https://{self.endpoint['website_names'][0]}:{self.endpoint['ports']['https']}",
                "R5E_WEBSITE_ORIGIN_MISMATCH")
        for path in (self.display, self.credentials, self.key_directory):
            prepare.owned_directory(path)
        require(self.display.parent == self.credentials.parent == Path("/dev/shm"), "R5E_TMPFS_ROOT_REQUIRED")
        self.controller()
        self.client = network.SecureClient(qa)
        admin = json.loads((qa / "admin.json").read_text())
        self.admin = network.SecureClient(qa, username=admin["username"], private=admin["private_key"].encode(),
                                         public=admin["server_public_key"].encode())
        self.binding_faults, self.events, self.sequence = {}, [], 0
        self.original_config = copy.deepcopy(self.config)
        self.original_registry = Path(self.config["access"]["users_file"]).read_bytes()
        self.accounts.update(ticket_seconds=self.config["access"]["ticket_seconds"], combination_phase=phase)
        self.asset_fault = None
        self.endpoint_changed = False

    def controller(self):
        value = super().controller()
        mounts = {m["Destination"]: m for m in value["Mounts"] if m["Type"] == "bind"}
        require(mounts["/run/browser-platform-secrets"]["Source"] == str(self.credentials)
                and mounts["/run/browser-platform-key"]["Source"] == str(self.key_directory)
                and not mounts["/run/browser-platform-key"]["RW"]
                and mounts["/run/browser-platform-host/ipv4-fib-trie"]["Source"] == "/proc/1/net/fib_trie",
                "R5E_COMBINED_MOUNTS_MISMATCH")
        return value

    def record(self, stem, value):
        self.sequence += 1
        network.write_json(self.output / f"{self.sequence:03}-{stem}.json", value)
        return value

    def network_journal(self, profile):
        _, binding, _ = self.worker(profile)
        candidates = [json.loads(path.read_text()) for path in (self.metadata / "profile-network-runtime").glob("*.json")]
        candidates = [v for v in candidates if v["identity"]["operation"] == binding["operation_id"]]
        require(len(candidates) == 1 and candidates[0]["identity"]["owner"] == "network-qa"
                and candidates[0]["identity"]["profile"] == profile, "R5E_GENERATION_JOURNAL_MISMATCH")
        return candidates[0]

    def command(self, action, profile):
        require(action in {"coherence", "resume", "stop", "health", "probe"} and profile in self.profiles, "QA_CONTROL_ACTION_INVALID")
        result = subprocess.run([str(self.candidate / "bin/profile-adapter"), "-config", str(self.qa / "adapter-config.json"),
                                 "-" + action + "-profile", profile], capture_output=True, text=True, timeout=110)
        self.record(action + "-" + profile, {"exit_code": result.returncode, "stdout": result.stdout,
                                            "stderr": result.stderr, "at": time.time()})
        return result

    def report(self, profile, allowed=None, address=None):
        require(profile in self.profiles and allowed in (None, True, False), "QA_REPORT_ARGUMENT_INVALID")
        require(address is None or address in self.endpoint["peer_ipv4"] + self.endpoint["client_ipv4"], "QA_EXIT_ARGUMENT_INVALID")
        for attempt in range(4):
            deadline = time.monotonic() + 40
            while time.time() - self.network_journal(profile).get("coherence_attempt_at", 0) < 10.2:
                require(time.monotonic() < deadline, "QA_SAMPLING_INTERVAL_EXCEEDED")
                time.sleep(.2)
            result = self.command("coherence", profile)
            require(result.returncode == 0, "QA_COHERENCE_COMMAND_FAILED")
            value = json.loads(result.stdout)
            report = value["report"]
            require(report["binding"]["profile_id"] == profile and report["binding"]["home_name"] == self.profiles[profile]["home_name"],
                    "QA_REPORT_BINDING_MISMATCH")
            if (allowed is None or report["allowed"] == allowed) and (address is None or report.get("exit", {}).get("browser_ip") == address):
                return report
        raise RuntimeError("QA_COHERENCE_RESULT_UNEXPECTED")

    def reports(self, allowed=True):
        return {profile: self.report(profile, allowed) for profile in self.profiles}

    def snapshot_one(self, profile, browser_storage=False):
        worker, binding, _ = self.worker(profile)
        value = {"worker": worker["Id"], "started_at": worker["State"]["StartedAt"], "image": worker["Image"],
                 "home": self.profiles[profile]["home_name"], "application": self.profiles[profile]["application_id"],
                 "session": binding["session_id"], "operation": binding["operation_id"]}
        return {"identity": value, "storage": self.observe(worker["Id"], profile) if browser_storage else {}}

    def stop_profile(self, profile):
        require(profile in self.profiles, "QA_PROFILE_UNKNOWN")
        inventory = self.inventory(profile)
        binding = self.journal().get("bindings", {}).get(profile)
        if any(inventory[k] for k in ("records", "workers", "resources")) or binding and binding.get("status") != "stopped":
            result = self.command("stop", profile)
            require(result.returncode == 0, "QA_NORMAL_STOP_FAILED")
        require(not any(self.inventory(profile)[k] for k in ("records", "workers", "resources")), "QA_STOP_INCOMPLETE")
        return {"stopped": True, "home_preserved": True}

    def configure(self, variant):
        require(variant in {"baseline", "strict-timezone", "strict-country", "advisory", "rotation", "revocation", "recovery"}, "QA_VARIANT_INVALID")
        for profile in self.profiles:
            self.stop_profile(profile)
        entry.stage.stop_process(self.qa, "adapter", self.candidate / "bin/profile-adapter")
        registry_path = self.metadata / "profile-network-policies.json"
        registry = json.loads(registry_path.read_text())
        revision = uuid.uuid4().hex[:12]
        new_refs = None
        if variant in {"revocation", "recovery"}:
            storage = module("r5e_versioned_store", self.candidate / "build/payload/app/secret_store.py")
            store = storage.FileSecretStore(self.metadata / "proxy-secret-store", self.key_directory / "master.key")
            secret_id = self.active["secret_id"] + "-revoke-" + revision if variant == "revocation" else self.active["secret_id"]
            version = 1 if variant == "revocation" else 2
            credentials = json.loads((self.endpoint_bundle / "before/credentials.json").read_text())
            grants = [{"owner": "network-qa", "profile": p["id"], "home": p["home_name"], "app": p["application_id"]}
                      for p in self.profiles.values()]
            if not store.revision_path(secret_id, version).exists():
                store.put(secret_id, version, grants, username=credentials["username"], password=credentials["password"])
            new_refs = storage.references(secret_id, version)
        changes = {}
        for profile, definition in self.profiles.items():
            policy = copy.deepcopy(self.active["policies"][profile])
            suffix = profile[-1]
            if suffix == "a":
                if new_refs:
                    policy.update(username_secret_ref=new_refs["username"], password_secret_ref=new_refs["password"])
                if variant in {"strict-timezone", "advisory"}:
                    policy["coherence"]["allowed_timezones"] = ["Asia/Tokyo"]
                if variant in {"strict-country", "advisory"}:
                    policy["coherence"]["allowed_countries"] = ["TW"]
                if variant == "advisory":
                    policy["coherence"]["mode"] = "advisory"
            if variant == "rotation":
                proxy = self.active["policies"]["network-qa-entry-a"]
                for key in ("mode", "upstream_host", "upstream_port", "upstream_protocol", "upstream_auth",
                            "username_secret_ref", "password_secret_ref"):
                    policy[key] = proxy[key]
                for key in ("approved_resolver_id", "approved_resolver_ip"):
                    policy.pop(key, None)
                policy["coherence"].update(allowed_countries=["JP", "HK"], on_exit_change="recheck" if suffix == "a" else "block")
            policy = prepare.normalize(policy)
            policy_id = f"r5e-{variant}-{suffix}-{revision}"
            require(policy_id not in registry["policies"], "QA_IMMUTABLE_POLICY_CONFLICT")
            registry["policies"][policy_id] = policy
            changes[profile] = {"id": policy_id, "policy": policy, "sha256": prepare.digest(policy)}
        network.write_json(registry_path, registry)
        for profile, value in changes.items():
            app = copy.deepcopy(self.active["applications"][profile])
            app["provider_config"].update(network_policy_id=value["id"], network_policy_sha256=value["sha256"])
            status, response = self.admin.call("PATCH", "/api/admin/apps/installed/" + app["id"], {"provider_config": app["provider_config"]})
            self.record("publish-app-" + profile, {"status": status, "response": response})
            require(status == 200, "QA_APP_POLICY_PUBLISH_FAILED")
            self.profiles[profile].update(network_policy_id=value["id"], network_policy_sha256=value["sha256"])
        self.config["profiles"] = list(self.profiles.values())
        network.write_json(self.qa / "adapter-config.json", self.config)
        entry.stage.start_adapter(self.qa, self.candidate / "bin/profile-adapter")
        self.record("variant-" + variant, changes)
        return {"variant": variant, "profiles_empty": True, "new_immutable_revisions": True}

    def endpoint_change(self, operation, value):
        require(operation == "mode" and value in {"online", "offline"} or operation == "rotation" and value in {"local", "peer"},
                "QA_ENDPOINT_ACTION_INVALID")
        ssh = entry.PROJECT / "infra/sealskin/runtime/r5c2-dns-ttl-2026-09-14/public-endpoints-setup"
        self.sequence += 1
        output = self.output / f"{self.sequence:03}-remote-{operation}-{value}"
        command = [sys.executable, str(CHECKS / "public-dns-endpoint/manage.py"), operation,
                   "--deployment", str(self.endpoint_bundle.parent / "deployment-before.json"),
                   "--ssh-key", str(ssh / "ssh/r5c2-test-key"), "--known-hosts", str(ssh / "known_hosts"),
                   "--output", str(output), "--mode" if operation == "mode" else "--exit", value]
        self.endpoint_changed = True
        result = subprocess.run(command, capture_output=True, text=True, timeout=40)
        self.record("remote-command", {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        require(result.returncode == 0, "QA_ENDPOINT_OPERATION_FAILED")
        return {"operation": operation, "value": value}

    def histories(self):
        return {profile: self.network_journal(profile).get("coherence_exit_history") for profile in self.profiles}

    def revoke(self, profile):
        require(profile == "network-qa-entry-a", "QA_REVOCATION_PROFILE_REQUIRED")
        helper = module("r5e_revocation_checks", CHECKS / "check-release-revocation.py")
        return helper.run(self, network, entry.desktop, profile)

    def private_gate(self, profile):
        _, binding, _ = self.worker(profile)
        status, sessions = self.client.call("GET", "/api/sessions")
        require(status == 200, "QA_SESSION_LIST_UNAVAILABLE")
        session = next(s for s in sessions if s["session_id"] == binding["session_id"])
        parsed = urlsplit(session["session_url"])
        token = parse_qs(parsed.query)["access_token"][0]
        context = ssl.create_default_context(cafile=self.config["access"]["session_ca_file"])
        with socket.create_connection(("127.0.0.1", 28443), timeout=15) as raw:
            with context.wrap_socket(raw, server_hostname="network.invalid") as tls:
                tls.sendall((f"GET {parsed.path} HTTP/1.1\r\nHost: network.invalid\r\n"
                             f"X-Browser-Platform-Session-Access: {token}\r\nConnection: close\r\n\r\n").encode())
                response = http.client.HTTPResponse(tls)
                response.begin()
                body = response.read(1048577)
                result = {"status": response.status, "set_cookie": bool(response.getheader("Set-Cookie")),
                          "body_sha256": hashlib.sha256(body).hexdigest(), "correct_private_capability": True}
        self.record("private-gate-" + profile, result)
        return result

    def materials(self, profile=None):
        records = {}
        expected_image = json.loads((self.candidate / "worker-build.json").read_text())["imageId"]
        credentials = json.loads((self.endpoint_bundle / "before/credentials.json").read_text())
        require(profile is None or profile in self.profiles, "QA_MATERIAL_PROFILE_INVALID")
        for profile in ([profile] if profile else self.profiles):
            worker, binding, inventory = self.worker(profile)
            require(worker["Image"] == expected_image, "QA_R7_IMAGE_MISMATCH")
            display = self.display / ("session-" + binding["session_id"])
            require(set(p.name for p in display.iterdir()) == {"binding.json", "basic.htpasswd", "master-token"}, "QA_DISPLAY_MATERIAL_MISSING")
            relay = json.loads(network.docker("inspect", next(r["id"] for r in inventory["resources"] if r["kind"] == "relay")).stdout)[0]
            journal = self.network_journal(profile)
            mounts = {m["Destination"]: m for m in relay["Mounts"]}
            if journal["policy"]["mode"] == "proxy_required":
                credential_path = Path(mounts["/run/secrets"]["Source"])
                require(credential_path.parent == self.credentials and not mounts["/run/secrets"]["RW"], "QA_CREDENTIAL_BIND_MISMATCH")
                require(set(p.name for p in credential_path.iterdir()) == {"username", "password", "lease"}, "QA_CREDENTIAL_MATERIAL_MISSING")
                for field in ("username", "password"):
                    require((credential_path / field).read_text() == credentials[field], "QA_CREDENTIAL_VALUE_MISMATCH")
            else:
                require("/run/secrets" not in mounts, "QA_DIRECT_HAS_CREDENTIALS")
            require(not any(Path(m["Source"]).is_relative_to(self.credentials) or "proxy-secret-store" in m["Source"]
                            or "master-key" in m["Source"] for m in worker["Mounts"]), "QA_WORKER_SECRET_EXPOSURE")
            for secret in (credentials["password"], credentials["peer_password"]):
                require(secret not in json.dumps([worker["Config"], relay["Config"], inventory]), "QA_CONTAINER_SECRET_EXPOSURE")
            records[profile] = {"worker": worker["Id"], "worker_image": worker["Image"], "relay": relay["Id"],
                                "worker_mounts": worker["Mounts"], "relay_mounts": relay["Mounts"], "mode": journal["policy"]["mode"]}
        self.record("material-boundaries", records)
        return {"r7_and_material_boundaries": True, "profiles": len(records)}

    def geoip(self, unavailable):
        if unavailable:
            require(self.asset_fault is None, "QA_ASSET_ALREADY_WITHHELD")
            reference = self.active["policies"]["network-qa-entry-a"]["coherence"]["geoip_file"]
            source = self.qa / "config" / reference.removeprefix("/config/")
            require(source.parent == self.metadata / "coherence-assets" and source.resolve() == source, "QA_ASSET_SCOPE_INVALID")
            held = self.output / "withheld-geoip.csv"
            require(not held.exists(), "QA_ASSET_HOLD_EXISTS")
            self.asset_fault = (source, held, hashlib.sha256(source.read_bytes()).hexdigest())
            source.rename(held)
        else:
            require(self.asset_fault is not None, "QA_ASSET_NOT_WITHHELD")
            source, held, sha = self.asset_fault
            require(not source.exists() and hashlib.sha256(held.read_bytes()).hexdigest() == sha, "QA_ASSET_CHANGED")
            held.rename(source)
            self.asset_fault = None
        return self.reports(allowed=not unavailable)

    def controller_restart(self):
        value = super().controller_restart()
        value["fresh_reports"] = self.reports()
        return value

    def resume_combined(self, profile):
        before, binding, inventory = self.worker(profile)
        journal = self.network_journal(profile)
        ids = {"worker": before["Id"], "relay": journal["allocation"]["relay_id"], "guard": journal["allocation"]["guard_id"]}
        containers = {k: json.loads(network.docker("inspect", v).stdout)[0] for k, v in ids.items()}
        self.record("resume-before", {"containers": containers, "journal": journal, "binding": binding})
        for role in ("worker", "relay", "guard"):
            value = containers[role]
            require(value["Config"]["Labels"][network.PREFIX + "operation"] == binding["operation_id"], "QA_RESUME_OWNERSHIP_MISMATCH")
            network.docker("stop", "-t", "60" if role == "worker" else "10", ids[role])
        stopped = json.loads(network.docker("inspect", ids["worker"]).stdout)[0]
        require(stopped["State"]["Status"] == "exited" and stopped["State"]["ExitCode"] == 0, "QA_BROWSER_NORMAL_EXIT_FAILED")
        paths = [self.display / ("session-" + binding["session_id"])]
        secret_mount = next((m for m in containers["relay"]["Mounts"] if m["Destination"] == "/run/secrets"), None)
        if secret_mount:
            path = Path(secret_mount["Source"])
            require(path.parent == self.credentials, "QA_RESUME_CREDENTIAL_SCOPE_INVALID")
            paths.append(path)
        for path in paths:
            prepare.owned_directory(path)
            for child in path.iterdir():
                info = child.lstat()
                require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
                        and stat.S_IMODE(info.st_mode) == 0o600, "QA_RESUME_MATERIAL_UNSAFE")
            shutil.rmtree(path)
        for attempt in range(4):
            if attempt:
                time.sleep(10.2)
            socket_path = Path(self.config["control_socket"])
            require(str(socket_path) == network.SOCKET and socket_path.is_socket()
                    and socket_path.stat().st_uid == os.geteuid() and stat.S_IMODE(socket_path.stat().st_mode) == 0o600,
                    "QA_CONTROL_SOCKET_MISMATCH")
            connection = network.UnixConnection("adapter", timeout=110)
            try:
                connection.request("POST", "/profiles/" + profile + "/resume")
                response = connection.getresponse()
                status, value = response.status, json.loads(response.read())
            finally:
                connection.close()
            self.record("resume-control-" + str(attempt + 1), {"status": status, "response": value})
            if status == 200:
                break
            require(status == 503, "QA_RESUME_NONRETRYABLE")
        require(status == 200, "QA_RESUME_NOT_READY")
        report = self.report(profile, True)
        after = {k: json.loads(network.docker("inspect", v).stdout)[0] for k, v in ids.items()}
        require(all(v["State"]["Running"] and v["State"]["StartedAt"] != containers[k]["State"]["StartedAt"] for k, v in after.items()),
                "QA_RESUME_PROCESSES_NOT_RESTARTED")
        _, after_binding, _ = self.worker(profile)
        require(binding["session_id"] == after_binding["session_id"] and binding["operation_id"] == after_binding["operation_id"],
                "QA_RESUME_BINDING_CHANGED")
        self.materials()
        self.record("resume-after", {"containers": after, "report": report, "binding": after_binding})
        return {"same_generation": True, "display_and_store_rematerialized": True, "fresh_report": report}

    def expiry(self, profile):
        before = self.report(profile, True)
        journal = self.network_journal(profile)
        worker, _, _ = self.worker(profile)
        gate = self.metadata / "profile-network-runtime" / (journal["identity"]["home_hash"] + "-" + journal["identity"]["operation"]) / "coherence/gate.json"
        nonce = uuid.uuid4().hex
        command = ["docker", "exec", worker["Id"], "python3", "-u", "-c", recovery.WEBSOCKET,
                   journal["allocation"]["relay_ip"], self.endpoint["website_names"][0], str(self.endpoint["ports"]["http"]), nonce, "100"]
        path = self.output / "expiry-tunnel.log"
        with path.open("w") as log:
            process = subprocess.Popen(["sg", "docker", "-c", shlex.join(command)], stdout=log, stderr=subprocess.STDOUT)
        network.wait(lambda: '"event": "ready"' in path.read_text(), "R5E website tunnel", seconds=15)
        controller = self.controller()
        snapshot = self.snapshot()
        stopped = False
        try:
            network.docker("stop", "-t", "10", controller["Id"])
            stopped = True
            actual_gate = json.loads(gate.read_text())
            self.record("expired-gate-source", actual_gate)
            process.wait(timeout=80)
            require(process.returncode == 0, "QA_WEBSITE_TUNNEL_FAILED")
            result = json.loads(path.read_text().splitlines()[-1])
            delay = result["finished_at"] - actual_gate["expires_ms"] / 1000
            require(result["result"] == "CLOSED" and result["echoes"] > 0 and -.5 <= delay <= 3,
                    "QA_TUNNEL_NOT_CLOSED_AT_EXPIRY")
        finally:
            if stopped:
                network.docker("start", controller["Id"])
                network.wait(lambda: network.request("POST", "/api/handshake/initiate")[0] == 200, "R5E controller recovery", seconds=45)
                self.client = network.SecureClient(self.qa)
        require(self.snapshot() == snapshot, "QA_EXPIRY_CHANGED_GENERATION")
        after = self.report(profile, True)
        require(before["binding"] == after["binding"], "QA_EXPIRY_CHANGED_BINDING")
        return self.record("expiry-result", {"closed_on_expiry": True, "delay_seconds": delay, "same_generation": True,
                                             "fresh_nonce": before["nonce"] != after["nonce"]})

    def dispatch(self, request):
        action = request.get("action")
        schemas = {"reports": {"allowed"}, "report": {"profile", "allowed", "address"}, "private_gate": {"profile"},
                   "materials": {"profile"}, "geoip": {"unavailable"}, "resume_combined": {"profile"}, "expiry": {"profile"},
                   "snapshot_one": {"profile", "browser_storage"}, "stop_profile": {"profile"}, "stop_all": set(),
                   "configure": {"variant"}, "endpoint": {"operation", "value"}, "histories": set(),
                   "revoke": {"profile"}, "inventory_counts": {"profile"}}
        if action not in schemas:
            return super().dispatch(request)
        require(set(request) <= schemas[action] | {"action"}, "QA_ACTION_FIELDS_INVALID")
        if action == "reports":
            return self.reports(request.get("allowed", True))
        if action == "report":
            return self.report(request["profile"], request.get("allowed"), request.get("address"))
        if action == "materials":
            return self.materials(request.get("profile"))
        if action == "geoip":
            require(type(request["unavailable"]) is bool, "QA_ASSET_ACTION_INVALID")
            return self.geoip(request["unavailable"])
        if action == "configure":
            return self.configure(request["variant"])
        if action == "endpoint":
            return self.endpoint_change(request["operation"], request["value"])
        if action == "histories":
            return self.histories()
        if action == "stop_all":
            return {profile: self.stop_profile(profile) for profile in self.profiles}
        if action == "snapshot_one":
            require(type(request.get("browser_storage", False)) is bool, "QA_STORAGE_ARGUMENT_INVALID")
            return self.snapshot_one(request["profile"], request.get("browser_storage", False))
        if action == "inventory_counts":
            value = self.inventory(request["profile"])
            return {key: len(value[key]) for key in ("records", "workers", "resources")}
        require(request["profile"] in self.profiles, "QA_PROFILE_UNKNOWN")
        return getattr(self, action)(request["profile"])

    def restore_faults(self):
        if self.asset_fault:
            source, held, sha = self.asset_fault
            require(not source.exists() and hashlib.sha256(held.read_bytes()).hexdigest() == sha, "QA_ASSET_RESTORE_CONFLICT")
            held.rename(source)
            self.asset_fault = None
        if self.endpoint_changed:
            self.endpoint_change("rotation", "local")
            self.endpoint_change("mode", "online")
        super().restore_faults()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("base", "faults", "resume", "policies", "rotation", "revocation", "recovered"), required=True)
    args = parser.parse_args()
    factory = lambda qa, output: Coordinator(qa, output, args.phase)
    return entry.run(args.root.resolve(), args.output.resolve(), factory, "release-combination-client.py", scope="r5e", copy_fixture=False)


if __name__ == "__main__":
    raise SystemExit(main())
