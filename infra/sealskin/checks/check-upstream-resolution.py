#!/usr/bin/env python3
"""Change a QA controller hostname mapping and verify generation-bound resolution.

This uses only the QA controller's /etc/hosts; it does not alter public DNS or
the production controller. Website DNS is tested separately by the observer.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    qa = args.root.resolve()
    project = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("checks", project / "infra/sealskin/lifecycle/check-network-live.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    checks = mod.Checks(qa)
    admin = json.loads((qa / "admin.json").read_text())
    client = mod.SecureClient(qa, username=admin["username"], private=admin["private_key"].encode(), public=admin["server_public_key"].encode())
    status, apps = client.call("GET", "/api/admin/apps/installed")
    assert status == 200
    app = copy.deepcopy(next(value for value in apps if value["id"] == "network-qa-app-a"))
    app.update(id="network-qa-app-resolution", name="Private upstream resolution QA")
    profile, home, policy_id = "network-qa-resolution", "network-qa-home-resolution", "network-qa-resolution-r1"
    registry_path = qa / "config/.config/sealskin/profile-network-policies.json"
    registry = json.loads(registry_path.read_text())
    policy = dict(registry["policies"][app["provider_config"]["network_policy_id"]])
    policy.update(profile_id=profile, home_name=home, application_id=app["id"], upstream_host="upstream.freeze.qa.test")
    revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert policy_id not in registry["policies"]
    registry["policies"][policy_id] = policy
    mod.write_json(registry_path, registry)
    app["provider_config"].update(network_policy_id=policy_id, network_policy_sha256=revision)
    assert client.call("POST", "/api/admin/apps/installed", app)[0] == 201
    assert checks.client.call("POST", "/api/homedirs", {"home_name": home})[0] == 201
    original = mod.docker("exec", mod.SERVER, "cat", "/etc/hosts").stdout
    images = json.loads((qa / "images.json").read_text())

    def mapping(address):
        contents = original + "\n" + address + " upstream.freeze.qa.test\n"
        mod.docker("exec", mod.SERVER, "python3", "-c", "from pathlib import Path;Path('/etc/hosts').write_text(" + repr(contents) + ")")

    def launch():
        request = dict(url="https://probe.qa.invalid/", application_id=app["id"], home_name=home, profile_id=profile,
                       operation_id=uuid.uuid4().hex, network_policy_id=policy_id, network_policy_sha256=revision,
                       wayland_mode=False, launch_in_room_mode=False)
        stop = {key: request[key] for key in ("application_id", "profile_id", "operation_id", "network_policy_id", "network_policy_sha256")}
        stop["bootstrap_url"] = request["url"]
        mod.write_json(qa / "resolution-stop.json", stop)
        return checks.client.call("POST", "/api/launch/url", request), stop

    def snapshot():
        status, value = checks.client.call("GET", "/api/profile-runtime/" + home)
        assert status == 200
        return value

    def cleanup(stop):
        assert checks.client.call("POST", "/api/profile-runtime/" + home + "/stop", stop)[0] == 204
        value = snapshot()
        assert value["records"] == value["workers"] == value["resources"] == []

    try:
        mapping(images["upstream_host"])
        (status, _), stop = launch()
        assert status == 200
        before = snapshot()
        worker = before["workers"][0]["instance_id"]
        identity = checks.identity(worker)
        resources = {value["kind"]: value["id"] for value in before["resources"]}
        journal = qa / "config/.config/sealskin/profile-network-runtime" / (resources["reservation"] + ".json")
        first = json.loads(journal.read_text())
        assert first["upstream_ipv4"] == [images["upstream_host"]]
        mapping("192.0.2.99")
        checks.probe_worker(worker, first["allocation"]["relay_ip"])
        mod.docker("restart", "-t", "2", resources["relay"])
        checks.probe_worker(worker, first["allocation"]["relay_ip"])
        assert identity == checks.identity(worker)
        cleanup(stop)
        (status, _), stop = launch()
        assert status == 503
        second = json.loads(journal.read_text())
        assert second["upstream_ipv4"] == ["192.0.2.99"]
        assert snapshot()["workers"] == snapshot()["records"] == []
        assert second["allocation"]["guard_id"] != first["allocation"]["guard_id"]
        assert mod.docker("inspect", first["allocation"]["guard_id"], check=False).returncode != 0
        reused = second["allocation"]["relay_ip"] == first["allocation"]["relay_ip"]
        cleanup(stop)
        report = dict(result="PASS", live_generation_keeps_frozen_upstream_after_mapping_change=True,
                      relay_restart_keeps_frozen_upstream=True, next_generation_resolves_new_address=True,
                      failed_new_upstream_creates_no_worker=True, old_guard_removed_before_new_generation=True,
                      internal_address_reused=reused, generation_cleanup_complete=True,
                      resolution_source="QA controller hosts mapping, not public DNS rotation")
        mod.write_json(qa.parent / "upstream-resolution-results.json", report)
        print(json.dumps(report))
    finally:
        mod.docker("exec", mod.SERVER, "python3", "-c", "from pathlib import Path;Path('/etc/hosts').write_text(" + repr(original) + ")")


if __name__ == "__main__":
    main()
