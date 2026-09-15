#!/usr/bin/env python3
"""Exercise versioned secrets through the actual isolated controller and browser.

Requires fresh prepare-network-qa.py with the two secret binds and the normal r6
Camoufox browser fixture. All credentials and detailed evidence stay in ROOT.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import traceback
import uuid


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


matrix = module("proxy_matrix", Path(__file__).with_name("check-proxy-protocols.py"))
shutdown = module("shutdown_checks", Path(__file__).with_name("check-browser-shutdown.py"))
network = matrix.network
STORAGE = shutdown.STORAGE.replace("r5a", "r5b")


class SecretChecks(matrix.Matrix):
    def __init__(self, qa, output):
        super().__init__(qa, output)
        metadata = self.qa / "config/.config/sealskin"
        metadata.chmod(0o700)
        self.runtime = Path(json.loads((self.qa / "allow.json").read_text())["credential_runtime_root"])
        assert self.runtime.parent == Path("/dev/shm") and self.runtime.resolve() == self.runtime
        self.key = self.qa.parent / "master-key/master.key"
        payload = self.qa.parent / self.images["build"] / "payload"
        manifest = json.loads((payload / "manifest.json").read_text())
        source = payload / "app/secret_store.py"
        assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["files"]["secret_store.py"]["after"]
        self.storage = module("qa_secret_store", source)
        if not (metadata / "proxy-secret-store").exists():
            self.store = self.storage.FileSecretStore.initialize(metadata / "proxy-secret-store", self.key)
        else:
            self.store = self.storage.FileSecretStore(metadata / "proxy-secret-store", self.key)
        network.write_json(metadata / "profile-secret-store.json", {
            "version": 1, "key_file": "/run/browser-platform-key/master.key", "runtime_dir": "/run/browser-platform-secrets"})
        inputs = self.qa.parent / "secret-fixture.json"
        if not inputs.exists():
            network.write_json(inputs, {str(v): {"username": "r5b-" + secrets.token_hex(8), "password": secrets.token_urlsafe(24)}
                                       for v in range(1, 8)})
        self.inputs = json.loads(inputs.read_text())
        self.principal = {"owner": "network-qa", "profile": self.info["profile"], "home": self.info["home"], "app": self.app["id"]}
        self.records = []
        self.put(1)
        self.stop()

    def passed(self, name, **details):
        value = {"check": name, "result": "PASS", **details}
        self.records.append(value)
        network.write_json(self.output / "secret-results.json", self.records)
        print(json.dumps(value), flush=True)

    def put(self, version, identifier="r5b-proxy", principal=None):
        refs = self.storage.references(identifier, version)
        if not self.store.revision_path(identifier, version).exists():
            self.store.put(identifier, version, [principal or self.principal], **self.inputs[str(version)])
        return refs

    def publish(self, protocol="https", version=1, refs=None, *, stop=True):
        if stop:
            self.stop()
        self.refresh()
        # Docker reconstructs /etc/hosts on restart. Keep the private upstream
        # fixture resolvable before every new allocation, including recovery QA.
        mapping = ("from pathlib import Path\np=Path('/etc/hosts')\n"
                   "lines=[v for v in p.read_text().splitlines() if 'proxy.leak.qa.test' not in v]\n"
                   "p.write_text('\\n'.join(lines)+'\\n'+" + repr(self.images["upstream_host"] + " proxy.leak.qa.test\n") + ")")
        network.docker("exec", "sealskin-network-qa", "python3", "-c", mapping)
        auth = "username_password" if protocol == "socks5" else "basic"
        network.write_json(self.observer / "proxy-auth.json", {protocol: auth})
        network.write_json(self.observer / "proxy-credentials.json", self.inputs[str(version)])
        network.write_json(self.observer / "mode.json", {})
        network.write_json(self.observer / "proxy-tls-mode.json", {})
        policy = dict(self.template)
        refs = refs or self.put(version)
        policy.update(upstream_protocol=protocol, upstream_auth=auth,
                      upstream_port={"socks5": 28191, "http": 28192, "https": 28193}[protocol],
                      username_file="", username_sha256="", password_file="", password_sha256="",
                      username_secret_ref=refs["username"], password_secret_ref=refs["password"])
        if protocol == "https":
            policy.update(upstream_host="proxy.leak.qa.test", upstream_tls_ca_file=policy["probe_ca_file"],
                          upstream_tls_ca_sha256=policy["probe_ca_sha256"])
        policy_id = "network-r5b-" + protocol + "-" + uuid.uuid4().hex[:12]
        revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.registry["policies"][policy_id] = policy
        network.write_json(self.registry_path, self.registry)
        self.app["provider_config"].update(network_policy_id=policy_id, network_policy_sha256=revision)
        status, _ = self.admin.call("PATCH", "/api/admin/apps/installed/" + self.app["id"], {"provider_config": self.app["provider_config"]})
        assert status == 200, "QA policy binding failed"
        network.write_json(self.qa / "camoufox-app.json", self.app)
        self.request.update(operation_id=uuid.uuid4().hex, network_policy_id=policy_id, network_policy_sha256=revision)
        network.write_json(self.qa / "browser-launch.json", self.request)
        body = {k: self.request[k] for k in ("application_id", "profile_id", "operation_id", "network_policy_id", "network_policy_sha256")}
        body["bootstrap_url"] = self.request["url"]
        network.write_json(self.qa / "browser-stop.json", body)
        return policy

    def launch(self, protocol="https", version=1, refs=None):
        policy = self.publish(protocol, version, refs)
        status, value = self.checks.client.call("POST", "/api/launch/url", self.request)
        network.write_json(self.output / ("launch-" + self.request["operation_id"] + ".json"), {"status": status, "result": value})
        assert status == 200, "Secret-backed launch failed"
        self.adopt(value, protocol)
        return policy, self.snapshot()

    def adopt(self, launch, protocol="https"):
        body = json.loads((self.qa / "browser-stop.json").read_text())
        body["session_id"] = launch["session_id"]
        network.write_json(self.qa / "browser-stop.json", body)
        current = self.snapshot()
        assert current["secret_store_version"] == 1 and len(current["workers"]) == 1
        self.info.update(instance_id=current["workers"][0]["instance_id"], upstream_protocol=protocol,
                         upstream_auth="username_password" if protocol == "socks5" else "basic")
        network.write_json(self.qa / "browser-worker.json", self.info)
        self.control = matrix.desktop.Desktop(self.info["instance_id"])
        network.wait(lambda: self.control.available_title().startswith("Private browser network check"),
                     "normal launcher fixture navigation", seconds=60)
        self.control.navigate("https://entry.leak.qa.test/test")

    def materials(self, current, version):
        worker = json.loads(network.docker("inspect", self.info["instance_id"]).stdout)[0]
        relay_id = next(v["id"] for v in current["resources"] if v["kind"] == "relay")
        relay = json.loads(network.docker("inspect", relay_id).stdout)[0]
        mount = next(v for v in relay["Mounts"] if v["Destination"] == "/run/secrets")
        path = Path(mount["Source"])
        assert not mount["RW"] and path.parent == self.runtime
        assert set(p.name for p in path.iterdir()) == {"username", "password", "lease"}
        assert path.stat().st_uid == 1000 and path.stat().st_mode & 0o777 == 0o700
        for field in ("username", "password"):
            assert (path / field).read_text() == self.inputs[str(version)][field]
            assert (path / field).stat().st_mode & 0o777 == 0o600
        assert not any(Path(v["Source"]).is_relative_to(self.runtime) for v in worker["Mounts"])
        assert not any("master-key" in v["Source"] or "proxy-secret-store" in v["Source"] for v in relay["Mounts"] + worker["Mounts"])
        process_status = network.docker("exec", relay_id, "cat", "/proc/1/status").stdout
        assert next(line for line in process_status.splitlines() if line.startswith("Uid:")).split()[1:] == ["1000"] * 4
        for value in self.inputs.values():
            for secret in value.values():
                assert secret not in json.dumps([worker["Config"], relay["Config"], current])
        network.write_json(self.output / ("materials-" + self.request["operation_id"] + ".json"), {
            "result": "PASS", "worker": worker["Id"], "relay": relay_id,
            "workerMounts": worker["Mounts"], "relayMounts": relay["Mounts"],
            "relayProcessUID": 1000, "credentialDirectoryMode": "0700", "credentialFileMode": "0600",
            "configAndEnvironmentCredentialFree": True,
            "configurationSHA256": hashlib.sha256(json.dumps([worker["Config"], relay["Config"]], sort_keys=True).encode()).hexdigest()})
        return path, relay_id

    def protocols(self):
        for protocol in ("socks5", "http", "https"):
            print(json.dumps({"stage": "secret-protocol", "protocol": protocol}), flush=True)
            policy, current = self.launch(protocol)
            path, _ = self.materials(current, 1)
            case = self.output / protocol
            case.mkdir(mode=0o700)
            transports = self.transports(protocol, policy["upstream_auth"])
            network.write_json(case / "transports.json", transports)
            with (case / "network.log").open("w") as log:
                result = subprocess.run([sys.executable, str(Path(__file__).with_name("check-network-browser.py")),
                                         "--root", str(self.qa), "--output", str(case / "network")],
                                        stdout=log, stderr=subprocess.STDOUT, timeout=360)
            assert result.returncode == 0, "Secret-backed network checks failed"
            checks = json.loads((case / "network/browser-network-results.json").read_text())
            assert all(v["result"] == "PASS" for v in checks)
            self.stop()
            assert not path.exists()
            self.passed("secret-protocol-" + protocol, networkChecks=len(checks), authenticated=True,
                        exclusiveReadonlyTmpfs=True, stoppedMaterialsRemoved=True)

    def refusal(self, label, refs, expected, mutation=None):
        self.publish(refs=refs)
        if mutation:
            mutation()
        status, value = self.checks.client.call("POST", "/api/launch/url", self.request)
        current = self.snapshot()
        network.write_json(self.output / (label + ".json"), {"status": status, "result": value, "inventory": current})
        assert status == expected and current["records"] == current["workers"] == current["resources"] == []
        code = "SECRET_ACCESS_DENIED" if label.startswith("authorization-") else {
            "unknown-reference": "SECRET_FILE_UNAVAILABLE", "missing-master-key": "SECRET_FILE_UNAVAILABLE",
            "mixed-version": "NETWORK_POLICY_REGISTRY_INVALID", "path-escape": "NETWORK_POLICY_REGISTRY_INVALID",
            "revoked-reference": "SECRET_REVOKED"}[label]
        assert value["detail"] == code
        assert not list(self.runtime.iterdir())
        policy_id = self.request["network_policy_id"]
        network.write_json(self.output / (label + "-policy.json"), {"id": policy_id, "policy": self.registry["policies"][policy_id]})
        # An invalid fixture makes the entire registry fail closed. Remove only
        # this proven-empty QA revision so later cases exercise their own cause.
        self.registry["policies"].pop(policy_id)
        network.write_json(self.registry_path, self.registry)
        self.passed(label, status=status, code=code, newWorkers=0, newResources=0)

    def authorization(self):
        for dimension in ("owner", "profile", "home", "app"):
            refs = self.put(1, "forbidden-" + dimension, {**self.principal, dimension: "different-" + dimension})
            self.refusal("authorization-" + dimension, refs, 403)
        refs = self.storage.references("unknown", 1)
        self.refusal("unknown-reference", refs, 503)
        self.refusal("mixed-version", {"username": "secret://r5b-proxy/username/1", "password": "secret://r5b-proxy/password/2"}, 503)
        self.refusal("path-escape", {"username": "secret://../username/1", "password": "secret://../password/1"}, 503)
        key_held = self.key.with_suffix(".unavailable")
        try:
            self.refusal("missing-master-key", self.put(1), 503, lambda: self.key.rename(key_held))
        finally:
            if key_held.exists(): key_held.rename(self.key)
        status, result = self.checks.client.call("POST", "/api/admin/profile-secrets/revoke", {
            "secret_ref": "secret://r5b-proxy/password/1", "operation_id": uuid.uuid4().hex})
        assert status == 403 and not self.store.revocation_path("r5b-proxy", 1).exists()
        self.passed("revoke-requires-admin", status=status)

    def rotation(self):
        _, current = self.launch("https", 1)
        original = self.info["instance_id"]
        directory, _ = self.materials(current, 1)
        self.put(2)
        assert self.snapshot()["workers"][0]["instance_id"] == original
        assert (directory / "password").read_text() == self.inputs["1"]["password"]
        try:
            self.store.put("r5b-proxy", 1, [self.principal], **self.inputs["2"])
            raise AssertionError("immutable secret version overwritten")
        except self.storage.SecretError as error:
            assert error.code == "SECRET_VERSION_EXISTS"
        _, current = self.launch("https", 2)
        self.materials(current, 2)
        assert self.info["instance_id"] != original and self.control.evaluate("fetchCheck('rotation')")
        self.stop()
        self.passed("immutable-rotation", oldGenerationUnchanged=True, replacementAuthenticated=True)

    def revoke(self):
        refs = self.put(3, "r5b-revoke-" + uuid.uuid4().hex[:12])
        _, before = self.launch("https", 3, refs)
        directory, relay = self.materials(before, 3)
        worker = self.info["instance_id"]
        expression = """new Promise((resolve,reject)=>{window.leaseClosed=false;window.leaseSocket=new WebSocket('wss://lease-%s.leak.qa.test/ws');leaseSocket.onopen=()=>leaseSocket.send('lease-probe');leaseSocket.onmessage=()=>resolve(true);leaseSocket.onerror=()=>reject(Error('lease setup'));leaseSocket.onclose=()=>window.leaseClosed=true;})""" % uuid.uuid4().hex
        assert self.control.evaluate(expression)
        assert self.control.evaluate("window.onbeforeunload=e=>{e.preventDefault();e.returnValue='';};true")
        request = {"secret_ref": refs["password"], "operation_id": uuid.uuid4().hex}
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.admin.call, "POST", "/api/admin/profile-secrets/revoke", request)
            network.wait(lambda: not json.loads(network.docker("inspect", relay).stdout)[0]["State"]["Running"], "revoked Relay exit", seconds=6)
            blocked_after = time.monotonic() - started
            status, value = future.result(timeout=30)
        after = self.snapshot()
        network.write_json(self.output / "revoke-refused.json", {"status": status, "result": value, "blockedAfter": blocked_after, "inventory": after})
        assert status == 503 and value["detail"] == "SECRET_REVOKED_CLEANUP_PENDING"
        assert after["workers"][0]["instance_id"] == worker and (directory / "lease").read_bytes() == b"revoked\n"
        assert json.loads(network.docker("inspect", worker).stdout)[0]["State"]["Running"]
        self.control.key("Escape")
        assert self.control.evaluate("window.onbeforeunload=null;true")
        assert self.control.evaluate("window.leaseClosed")
        start = len(self.events())
        assert self.control.evaluate("fetchCheck('revoked').catch(()=>false)") is False
        assert not any(e.get("target", "").startswith("revoked-") for e in self.events()[start:])
        probe = 'import socket,json; s=socket.socket();s.settimeout(.5)\ntry:\n s.connect((' + repr(self.info['observer_ip']) + ',443)); result=True\nexcept OSError: result=False\nprint(json.dumps(result))'
        assert json.loads(network.docker("exec", worker, "python3", "-c", probe).stdout) is False
        self.refresh()
        status, result = self.admin.call("POST", "/api/admin/profile-secrets/revoke", request)
        assert status == 200 and result["cleanup_complete"] and result["egress_blocked"]
        assert not directory.exists()
        self.refusal("revoked-reference", refs, 409)
        self.passed("active-revocation-and-retry", relayExitSeconds=round(blocked_after, 3), existingWebSocketClosed=True,
                    closeRefusalRetainedWorker=True, browserAndDirectRequestsBlocked=True, cleanupRetry=True)

    def recovery(self):
        _, current = self.launch("https", 4)
        directory, relay = self.materials(current, 4)
        worker = self.info["instance_id"]
        marker = uuid.uuid4().hex
        expected = {"href": "https://entry.leak.qa.test/test", "cookie": marker, "localStorage": marker, "indexedDB": marker}
        assert self.control.evaluate("(" + STORAGE + ")(true," + json.dumps(marker) + ")") == expected
        guard = next(v["id"] for v in current["resources"] if v["kind"] == "guard")
        network.docker("stop", "-t", "30", worker)
        network.docker("stop", "-t", "3", relay, guard)
        assert not json.loads(network.docker("inspect", relay).stdout)[0]["State"]["Running"]
        shutil.rmtree(directory)
        control = json.loads(network.docker("inspect", "sealskin-network-qa").stdout)[0]
        assert any(m["Source"] == str(self.qa / "config") and m["Destination"] == "/config" for m in control["Mounts"])
        network.docker("restart", "-t", "15", control["Id"])
        network.wait(lambda: network.request("POST", "/api/handshake/initiate")[0] == 200, "restarted secret controller")
        self.refresh()
        body = json.loads((self.qa / "browser-stop.json").read_text())
        missing = self.key.with_suffix(".unavailable")
        try:
            self.key.rename(missing)
            status, value = self.checks.client.call("POST", "/api/profile-runtime/" + self.info["home"] + "/resume", body)
            assert status == 503 and not json.loads(network.docker("inspect", worker).stdout)[0]["State"]["Running"]
            assert not directory.exists()
        finally:
            if missing.exists(): missing.rename(self.key)
        status, value = self.checks.client.call("POST", "/api/profile-runtime/" + self.info["home"] + "/resume", body)
        network.write_json(self.output / "resume.json", {"status": status, "result": value})
        assert status == 200 and value["instance_id"] == worker and value["resumed"]
        self.materials(self.snapshot(), 4)
        self.control = matrix.desktop.Desktop(worker)
        network.wait(lambda: self.control.available_title().startswith("Private browser network check"),
                     "resumed launcher fixture navigation", seconds=60)
        self.control.navigate("https://entry.leak.qa.test/test")
        assert self.control.evaluate("(" + STORAGE + ")(false,null)") == expected
        self.key.rename(missing)
        try:
            network.wait(lambda: not json.loads(network.docker("inspect", relay).stdout)[0]["State"]["Running"], "lost-key Relay block", seconds=7)
            assert json.loads(network.docker("inspect", worker).stdout)[0]["State"]["Running"]
            assert self.control.evaluate("fetchCheck('lost-key').catch(()=>false)") is False
        finally:
            if missing.exists(): missing.rename(self.key)
        self.stop()
        self.passed("controller-and-tmpfs-recovery", sameGeneration=True, missingKeyRefusesResume=True,
                    missingKeyBlocksActiveRelay=True, cookieLocalStorageIndexedDBPreserved=True)

    def concurrent(self):
        refs = self.put(6, "r5b-concurrent-" + uuid.uuid4().hex[:12])
        self.publish(version=6, refs=refs)
        self.refresh()
        with ThreadPoolExecutor(max_workers=2) as pool:
            launching = pool.submit(self.checks.client.call, "POST", "/api/launch/url", self.request)
            network.wait(lambda: bool(list(self.runtime.iterdir())) or launching.done(), "in-flight credential generation", seconds=30)
            if launching.done():
                status, value = launching.result()
                network.write_json(self.output / "concurrent-launch-ended.json", {"status": status, "result": value})
            assert not launching.done(), "race fixture missed the in-flight create"
            revoking = pool.submit(self.admin.call, "POST", "/api/admin/profile-secrets/revoke", {
                "secret_ref": refs["password"], "operation_id": uuid.uuid4().hex})
            launch_status, launch_value = launching.result(timeout=90)
            revoke_status, revoke_value = revoking.result(timeout=45)
        current = self.snapshot()
        network.write_json(self.output / "concurrent.json", {"launchStatus": launch_status, "revokeStatus": revoke_status,
                           "revokeResult": revoke_value, "inventory": current})
        assert launch_status == 200 and revoke_status == 200 and revoke_value["cleanup_complete"]
        assert current["records"] == current["workers"] == current["resources"] == [] and not list(self.runtime.iterdir())
        self.passed("concurrent-create-revoke", noMissedGeneration=True, noRemainingMaterials=True)

    def interrupted_revoke(self):
        refs = self.put(2, "r5b-interrupted-" + uuid.uuid4().hex[:12])
        _, current = self.launch("https", 2, refs)
        directory, relay = self.materials(current, 2)
        worker = self.info["instance_id"]
        controller = json.loads(network.docker("inspect", "sealskin-network-qa").stdout)[0]
        assert any(m["Source"] == str(self.qa / "config") and m["Destination"] == "/config" for m in controller["Mounts"])
        network.docker("stop", "-t", "15", controller["Id"])
        request = {"secret_ref": refs["password"], "operation_id": uuid.uuid4().hex}
        # QA fault injection represents a crash after the durable commit and
        # before any lease update. This is never an operator revocation path.
        self.store.revoke(request["secret_ref"], request["operation_id"])
        assert (directory / "lease").read_bytes().startswith(b"active:")
        network.docker("start", controller["Id"])
        network.wait(lambda: network.request("POST", "/api/handshake/initiate")[0] == 200, "revocation recovery control")
        network.wait(lambda: not json.loads(network.docker("inspect", relay).stdout)[0]["State"]["Running"], "startup revocation enforcement", seconds=7)
        assert (directory / "lease").read_bytes() == b"revoked\n"
        assert json.loads(network.docker("inspect", worker).stdout)[0]["State"]["Running"]
        assert self.control.evaluate("fetchCheck('recovered-revocation').catch(()=>false)") is False
        self.refresh()
        status, result = self.admin.call("POST", "/api/admin/profile-secrets/revoke", request)
        assert status == 200 and result["cleanup_complete"] and not directory.exists()
        self.passed("crash-after-revocation-commit", startupBlockedExistingRelay=True, cleanupRetry=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checks", nargs="+", choices=["protocols", "authorization", "rotation", "revoke", "recovery", "concurrent", "interrupted_revoke"],
                        default=["protocols", "authorization", "rotation", "revoke", "recovery", "concurrent", "interrupted_revoke"])
    args = parser.parse_args()
    runner = SecretChecks(args.root, args.output)
    try:
        for name in args.checks:
            print(json.dumps({"stage": name}), flush=True)
            getattr(runner, name)()
        runner.stop()
    except BaseException as exc:
        (runner.output / "failure.txt").write_text(traceback.format_exc())
        print(json.dumps({"result": "FAIL", "type": type(exc).__name__, "privateEvidenceRetained": True}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
