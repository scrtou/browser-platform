#!/usr/bin/env python3
"""Retire the original and restored R5E QA resources, preserving private evidence."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import stat


CHECKS = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


runner = module("r5e_cleanup_runner", CHECKS / "run-release-combination.py")
entry_cleanup = module("r5e_cleanup_production", CHECKS / "cleanup-entry-auth.py")
network, require = runner.network, runner.require


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "source", "backup-result", "client-result", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    qa, source, output = args.root.resolve(), args.source.resolve(), args.output.resolve()
    work = qa.parent.parent
    require(work.name == "r5e-release-combination-2026-09-15" and source.parent.parent == work
            and source.parent.name == "candidate-1" and re.fullmatch(r"recovered-[1-9][0-9]*", qa.parent.name)
            and output.parent == work and not output.exists(), "EXACT_R5E_CLEANUP_SCOPE_REQUIRED")
    output.mkdir(mode=0o700)
    c = runner.Coordinator(qa, output, "recovered")
    for path in (args.backup_result.resolve(), args.client_result.resolve()):
        require(path.is_relative_to(work), "QA_ACCEPTANCE_PATH_OUTSIDE_SCOPE")
    backup = json.loads(args.backup_result.read_text())
    client = json.loads(args.client_result.read_text())
    require(backup["result"] == "PREPARED" and Path(backup["target"]) == qa.parent
            and client["status"] == "pass" and Path(client["candidate"]) == qa.parent
            and "S05-new-private-root-restores-r7-Store-assets-login-and-three-browser-stores" in client["checks"],
            "R5E_RECOVERY_ACCEPTANCE_REQUIRED")
    baseline = json.loads((work / "production-before.json").read_text())
    network.write_json(output / "production-before-cleanup.json", entry_cleanup.production(baseline))
    authority = json.loads(network.docker("inspect", "r5c2-public-dns-authority").stdout)[0]
    authority_identity = (authority["Id"], authority["State"]["StartedAt"])
    for profile in c.profiles:
        c.stop_profile(profile)
    status, sessions = c.client.call("GET", "/api/sessions")
    require(status == 200 and not sessions, "R5E_SESSIONS_REMAIN")
    scopes = []
    for root in (source, qa):
        scope = hashlib.sha256(str(root / "config/.config/sealskin/sessions.yml").encode()).hexdigest()
        selector = "label=io.browser-platform.scope=" + scope
        require(not network.docker("ps", "-aq", "--filter", selector).stdout.strip()
                and not network.docker("network", "ls", "-q", "--filter", selector).stdout.strip(), "R5E_GENERATION_REMAINS")
        require(not list((root / "config/.config/sealskin/profile-network-runtime").glob("*.json")), "R5E_RESERVATIONS_REMAIN")
        journal = json.loads((root / "adapter-state.json").read_text())
        require(all(b["status"] == "stopped" for b in journal.get("bindings", {}).values()), "R5E_BINDING_NOT_STOPPED")
        scopes.append(scope)
    for name in ("adapter", "front-caddy", "proxy"):
        require(not (source / (name + "-pid.json")).exists(), "SOURCE_QA_PROCESS_NOT_RETIRED")
        previous = json.loads((source / (name + "-stopped.json")).read_text())["pid"]
        command = Path("/proc", str(previous), "cmdline")
        require(not command.exists() or str(source).encode() not in command.read_bytes(), "SOURCE_QA_PROCESS_REMAINS")
    old_active = json.loads((source / "access/active-candidate.json").read_text())
    require(network.docker("inspect", old_active["controller"], check=False).returncode != 0,
            "SOURCE_CONTROLLER_REMAINS")
    for label in ("r5e-entry-client", "r5e-revocation-wire"):
        require(not network.docker("ps", "-aq", "--filter", "label=io.browser-platform.qa=" + label).stdout.strip(),
                "R5E_AUXILIARY_CONTAINER_REMAINS")
    expected = {network.SERVER: (qa / "config", "/config"), "network-qa-upstream": (source / "upstream", "/qa")}
    known = network.docker("ps", "-a", "--filter", "label=io.browser-platform.qa=network-20260913",
                           "--format", "{{.Names}}").stdout.splitlines()
    require(set(known) == set(expected), "UNEXPECTED_BASE_QA_FIXTURES")
    fixtures = json.loads(network.docker("inspect", *expected).stdout)
    ids, volumes = {v["Id"] for v in fixtures}, []
    for value in fixtures:
        origin, destination = expected[value["Name"].lstrip("/")]
        require(value["Config"]["Labels"].get("io.browser-platform.qa") == "network-20260913"
                and any(m.get("Source") == str(origin) and m["Destination"] == destination for m in value["Mounts"]),
                "QA_FIXTURE_OWNER_MISMATCH")
        for mount in value["Mounts"]:
            if mount["Type"] == "volume":
                name = mount["Name"]
                require(re.fullmatch(r"[a-f0-9]{64}", name) is not None, "QA_VOLUME_NOT_ANONYMOUS")
                references = network.docker("ps", "-aq", "--no-trunc", "--filter", "volume=" + name).stdout.split()
                require(set(references) <= ids, "QA_VOLUME_HAS_OTHER_OWNER")
                volumes.append(name)
    network.write_json(output / "fixture-inspects.json", fixtures)
    base = json.loads(network.docker("network", "inspect", "browser-platform-network-qa").stdout)[0]
    require(base["Labels"].get("io.browser-platform.qa") == "network-20260913" and set(base["Containers"]) == ids,
            "QA_BASE_NETWORK_OWNER_MISMATCH")
    runner.entry.stage.stop_process(qa, "front-caddy", "caddy")
    runner.entry.stage.stop_process(qa, "adapter", c.candidate / "bin/profile-adapter")
    for value in fixtures:
        network.docker("stop", "-t", "10", value["Id"])
        network.docker("rm", "-v", value["Id"])
    require(not json.loads(network.docker("network", "inspect", base["Id"]).stdout)[0]["Containers"], "QA_BASE_NETWORK_OCCUPIED")
    network.docker("network", "rm", base["Id"])
    runner.entry.stage.stop_process(qa, "proxy", "qa-network-docker-proxy.py")
    for name in ("adapter", "front-caddy", "proxy"):
        (qa / (name + "-pid.json")).rename(qa / (name + "-stopped.json"))
    for path in (Path(network.SOCKET), runner.entry.stage.SOCKET):
        if path.exists():
            info = path.lstat()
            require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid(), "QA_SOCKET_OWNER_MISMATCH")
            with socket.socket(socket.AF_UNIX) as probe:
                probe.settimeout(.5)
                require(probe.connect_ex(str(path)) != 0, "QA_SOCKET_STILL_ACTIVE")
            path.unlink()
    roots = [Path(old_active[field]) for field in ("display_runtime_root", "credential_runtime_root")]
    roots += [c.display, c.credentials]
    require(len(set(roots)) == 4, "QA_TMPFS_ROOTS_NOT_DISTINCT")
    for path in roots:
        require(path.parent == Path("/dev/shm") and path.name.startswith("browser-platform-r5e-"), "QA_TMPFS_PATH_OUTSIDE_SCOPE")
        runner.prepare.owned_directory(path)
        require(not list(path.iterdir()), "QA_TMPFS_MATERIALS_REMAIN")
        path.rmdir()
    require(all(network.docker("volume", "inspect", name, check=False).returncode != 0 for name in volumes), "QA_VOLUMES_REMAIN")

    def closed():
        for port in (28110, 28443, 29110, 29443):
            with socket.socket() as probe:
                probe.settimeout(.3)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    return False
        return True

    network.wait(closed, "R5E retired listeners", seconds=10)
    current = json.loads(network.docker("inspect", "r5c2-public-dns-authority").stdout)[0]
    require((current["Id"], current["State"]["StartedAt"]) == authority_identity, "BASE_AUTHORITY_CHANGED")
    network.write_json(output / "production-after.json", entry_cleanup.production(baseline))
    result = {"status": "pass", "generation_scopes": scopes, "generation_resources_remaining": 0,
              "fixtures_removed": sorted(expected), "fixture_network_removed": True, "anonymous_volumes_removed": volumes,
              "source_and_restored_processes_stopped": True, "empty_tmpfs_roots_removed": len(roots),
              "qa_ports_closed": [28110, 28443, 29110, 29443], "private_disk_evidence_retained": True,
              "production_unchanged": True, "public_dns_authority_preserved": True,
              "external_endpoint_and_DNS_cleanup": "separate scoped evidence required"}
    network.write_json(output / "result.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
