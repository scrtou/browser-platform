#!/usr/bin/env python3
"""Retire a passed R5D QA scope, retaining its private disk evidence.

Profiles stop through the existing lifecycle owner. Only the three verified QA
fixtures, their exact anonymous volumes, private processes and empty tmpfs are
removed. Any unexpected owner or remaining reservation stops cleanup.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess


spec = importlib.util.spec_from_file_location("entry_runner", Path(__file__).with_name("run-entry-auth.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
network = runner.network


def production(baseline):
    values = json.loads(network.docker("inspect", *baseline["containers"]).stdout)
    containers = {v["Name"].lstrip("/"): {"id": v["Id"], "image": v["Image"],
        "started_at": v["State"]["StartedAt"], "pid": v["State"]["Pid"]} for v in values}
    files = {name: hashlib.sha256((runner.PROJECT / name).read_bytes()).hexdigest() for name in baseline["files"]}
    assert containers == baseline["containers"] and files == baseline["files"], "PRODUCTION_BASELINE_CHANGED"
    return {"containers": containers, "files": files}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--client-result", type=Path, required=True)
    parser.add_argument("--security-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    qa, output = args.root.resolve(), args.output.resolve()
    assert not output.exists() and qa.parent.parent in output.parents
    output.mkdir(mode=0o700)
    coordinator = runner.Coordinator(qa, output)
    for path in (args.client_result.resolve(), args.security_result.resolve()):
        assert qa.parent.parent in path.parents
        report = json.loads(path.read_text())
        assert report["status"] == "pass" and Path(report["candidate"]) == coordinator.candidate
    baseline = json.loads((qa.parent.parent / "production-before.json").read_text())
    network.write_json(output / "production-before-cleanup.json", production(baseline))
    authority = json.loads(network.docker("inspect", "r5c2-public-dns-authority").stdout)[0]
    authority_identity = (authority["Id"], authority["State"]["StartedAt"])
    scope = hashlib.sha256(str(qa / "config/.config/sealskin/sessions.yml").encode()).hexdigest()
    names = network.docker("ps", "-aq", "--filter", "label=io.browser-platform.scope=" + scope).stdout.split()
    generations = json.loads(network.docker("inspect", *names).stdout) if names else []
    for value in generations:
        assert value["Config"]["Labels"].get("io.browser-platform.owner") == "network-qa"
        assert value["Config"]["Labels"].get("io.browser-platform.home") in {p["home_name"] for p in coordinator.profiles.values()}
    network.write_json(output / "generation-inspects.json", generations)
    shutil.copy2(qa / "adapter-state.json", output / "adapter-state-before-stop.json")
    for profile in coordinator.profiles:
        coordinator.worker(profile)  # Prove exact running identity before stop.
        command = [str(coordinator.candidate / "bin/profile-adapter"), "--config", str(qa / "adapter-config.json"),
                   "--stop-profile", profile]
        result = subprocess.run(command, capture_output=True, timeout=150)
        (output / (profile + "-stop.json")).write_bytes(result.stdout)
        (output / (profile + "-stop.log")).write_bytes(result.stderr)
        assert result.returncode == 0, "QA_LIFECYCLE_STOP_FAILED"
        inventory = coordinator.inventory(profile)
        assert not any(inventory[k] for k in ("records", "workers", "resources"))
    status, sessions = coordinator.client.call("GET", "/api/sessions")
    assert status == 200 and not sessions
    selector = "label=io.browser-platform.scope=" + scope
    assert not network.docker("ps", "-aq", "--filter", selector).stdout.strip()
    assert not network.docker("network", "ls", "-q", "--filter", selector).stdout.strip()
    reservations = qa / "config/.config/sealskin/profile-network-runtime"
    assert not list(reservations.glob("*.json"))
    assert not list(coordinator.display.iterdir()), "QA_DISPLAY_MATERIALS_REMAIN"
    shutil.copy2(qa / "adapter-state.json", output / "adapter-state-after-stop.json")
    assert all(v["status"] == "stopped" for v in coordinator.journal()["bindings"].values())

    expected = {network.SERVER: (qa / "config", "/config"),
                "network-qa-upstream": (qa / "upstream", "/qa"),
                "network-qa-observer": (qa.parent / "observer", "/qa-observer")}
    known = network.docker("ps", "-a", "--filter", "label=io.browser-platform.qa=network-20260913",
                           "--format", "{{.Names}}").stdout.splitlines()
    assert set(known) == set(expected)
    fixtures = json.loads(network.docker("inspect", *expected).stdout)
    fixture_ids = {v["Id"] for v in fixtures}
    volumes = []
    for value in fixtures:
        name = value["Name"].lstrip("/")
        source, target = expected[name]
        assert any(m.get("Source") == str(source) and m["Destination"] == target for m in value["Mounts"])
        assert value["Config"]["Labels"].get("io.browser-platform.qa") == "network-20260913"
        for mount in value["Mounts"]:
            if mount["Type"] == "volume":
                identifier = mount["Name"]
                assert re.fullmatch(r"[a-f0-9]{64}", identifier)
                refs = network.docker("ps", "-aq", "--no-trunc", "--filter", "volume=" + identifier).stdout.split()
                assert set(refs) <= fixture_ids
                volumes.append(identifier)
    network.write_json(output / "fixture-inspects.json", fixtures)
    base_network = json.loads(network.docker("network", "inspect", "browser-platform-network-qa").stdout)[0]
    assert base_network["Labels"].get("io.browser-platform.qa") == "network-20260913"
    assert set(base_network["Containers"]) == fixture_ids
    runner.stage.stop_process(qa, "front-caddy", "caddy")
    runner.stage.stop_process(qa, "adapter", coordinator.candidate / "bin/profile-adapter")
    for value in fixtures:
        network.docker("stop", "-t", "10", value["Id"])
        network.docker("rm", "-v", value["Id"])
    assert not json.loads(network.docker("network", "inspect", base_network["Id"]).stdout)[0]["Containers"]
    network.docker("network", "rm", base_network["Id"])
    runner.stage.stop_process(qa, "proxy", runner.PROJECT / "infra/sealskin/lifecycle/qa-network-docker-proxy.py")
    for path in (Path(network.SOCKET), runner.stage.SOCKET):
        if path.exists():
            value = path.lstat()
            assert stat.S_ISSOCK(value.st_mode) and value.st_uid == os.getuid()
            with socket.socket(socket.AF_UNIX) as probe:
                probe.settimeout(.5)
                assert probe.connect_ex(str(path)) != 0
            path.unlink()
    info = coordinator.display.lstat()
    assert stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700
    coordinator.display.rmdir()
    assert all(network.docker("volume", "inspect", name, check=False).returncode != 0 for name in volumes)

    def listeners_closed():
        for port in (28110, 28443, 29110, 29443):
            with socket.socket() as probe:
                probe.settimeout(.3)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    return False
        return True

    network.wait(listeners_closed, "retired QA listeners", seconds=10)
    current_authority = json.loads(network.docker("inspect", "r5c2-public-dns-authority").stdout)[0]
    assert (current_authority["Id"], current_authority["State"]["StartedAt"]) == authority_identity
    after = production(baseline)
    network.write_json(output / "production-after.json", after)
    result = {"status": "pass", "profiles_stopped_via_lifecycle": sorted(coordinator.profiles),
        "generation_containers_removed": len(generations), "generation_networks_remaining": 0,
        "fixtures_removed": sorted(expected), "fixture_network_removed": True, "anonymous_volumes_removed": volumes,
        "private_processes_stopped": ["adapter", "front-caddy", "proxy"], "display_tmpfs_removed": True,
        "qa_ports_closed": [28110, 28443, 29110, 29443], "private_disk_evidence_retained": True,
        "production_unchanged": True, "public_dns_authority_preserved": True}
    network.write_json(output / "result.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
