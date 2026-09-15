#!/usr/bin/env python3
"""Prepare reviewable entry-auth deployment files without changing live services."""

import argparse
import base64
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(value, indent=2) + "\n" if not isinstance(value, str) else value)


def adapt(path):
    result = subprocess.run(["caddy", "adapt", "--config", str(path), "--adapter", "caddyfile"], capture_output=True)
    if result.returncode:
        raise RuntimeError("CADDY_ADAPT_REJECTED")
    return json.loads(result.stdout)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--system-caddy", type=Path, default=Path("/etc/caddy/Caddyfile"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--uid", type=int, default=os.getuid())
    parser.add_argument("--gid", type=int, default=os.getgid())
    args = parser.parse_args()
    config_path, candidate, output = args.config.resolve(), args.candidate.resolve(), args.output.resolve()
    assert args.uid > 0 and args.gid > 0 and not output.exists()
    output.mkdir(mode=0o700)
    config = json.loads(config_path.read_text())
    before = {str(config_path): sha(config_path), str(args.system_caddy): sha(args.system_caddy)}
    entry = urlsplit(config["public_base_url"])
    session = urlsplit(config["sealskin"]["public_session_base_url"])
    assert entry.scheme == session.scheme == "https" and entry.port is None and session.port is None
    assert entry.hostname != session.hostname and config["listen_address"].startswith("127.0.0.1:")
    original = adapt(args.system_caddy)
    template = (ROOT / "Caddyfile.example").read_text().replace("mybrowser.example.com, mysession.example.com",
        entry.hostname + ", " + session.hostname).replace("127.0.0.1:8080", config["listen_address"])
    write(output / "entry-sites.Caddyfile", template)
    access = adapt(output / "entry-sites.Caddyfile")
    access_routes = [route for server in access["apps"]["http"]["servers"].values() for route in server["routes"]]
    assert len(access_routes) == 1
    new_caddy, closed_caddy = copy.deepcopy(original), copy.deepcopy(original)
    desired = {entry.hostname, session.hostname}
    changed = []
    for name, server in new_caddy["apps"]["http"]["servers"].items():
        for index, route in enumerate(server["routes"]):
            matches = route.get("match", [])
            hosts = {host for match in matches for host in match.get("host", [])}
            if not hosts & desired:
                continue
            assert hosts <= desired and all(set(match) == {"host"} for match in matches)
            route["handle"] = copy.deepcopy(access_routes[0]["handle"])
            closed_caddy["apps"]["http"]["servers"][name]["routes"][index]["handle"] = [
                {"handler": "static_response", "status_code": 503, "body": "Browser access temporarily unavailable\n",
                 "headers": {"Cache-Control": ["no-store"], "Referrer-Policy": ["no-referrer"]}}]
            changed.extend(hosts)
    assert set(changed) == desired and len(changed) == 2
    # Preserve other listeners/routes, including the existing port-80 site.
    for value in (new_caddy, closed_caddy):
        logging = value.setdefault("logging", {}).setdefault("logs", {})
        logging["default"] = copy.deepcopy(access["logging"]["logs"]["default"])
    write(output / "caddy.candidate.json", new_caddy)
    write(output / "caddy.maintenance.json", closed_caddy)
    write(output / "caddy.before.json", original)
    write(output / "Caddyfile.before", args.system_caddy.read_text())

    config = copy.deepcopy(config)
    path_fields = [(config, "state_file"), (config, "control_socket"),
        (config["sealskin"], "server_public_key_file"), (config["sealskin"], "client_private_key_file"),
        (config.get("limits", {}), "storage_path")]
    for owner, key in path_fields:
        if owner.get(key):
            owner[key] = str((config_path.parent / owner[key]).resolve())
    write(output / "adapter.before.json", config)
    config["sealskin"].update(api_base_url="https://127.0.0.1:8443", allow_unencrypted_http=False, lifecycle_enabled=True)
    config["access"] = {"users_file": str(config_path.parent / "secrets/entry-users.json"),
        "session_upstream_url": "https://127.0.0.1:8443", "session_ca_file": str(config_path.parent / "secrets/private-session-ca.pem"),
        "session_tls_name": session.hostname, "session_seconds": 1800, "ticket_seconds": 30}
    write(output / "adapter.candidate.json", config)
    spec = importlib.util.spec_from_file_location("release_tls", ROOT / "prepare-tls.py")
    tls = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tls)
    identity = tls.create(output / "private-tls", session.hostname, 365)
    images = json.loads((candidate / "images.json").read_text())
    write(output / "compose.entry-auth.yml", "services:\n  sealskin:\n    image: " + images["runtime"]["image"] +
          "\n    volumes:\n      - type: bind\n        source: /run/browser-platform/session-secrets\n" +
          "        target: /run/browser-platform-session-secrets\n        bind:\n          create_host_path: false\n")
    write(output / "browser-platform-session-auth.tmpfiles.conf",
          "d /run/browser-platform 0711 root root -\n" +
          f"d /run/browser-platform/session-secrets 0700 {args.uid} {args.gid} -\n")
    write(output / "docker-tmpfiles-ordering.conf", "[Unit]\nRequires=systemd-tmpfiles-setup.service\nAfter=systemd-tmpfiles-setup.service\n")
    checks = {}
    for name in ("caddy.candidate.json", "caddy.maintenance.json"):
        result = subprocess.run(["caddy", "validate", "--config", str(output / name)], capture_output=True)
        (output / (name + ".validation.log")).write_bytes(result.stdout + result.stderr)
        checks[name] = result.returncode == 0
    assert all(checks.values()), "CADDY_CANDIDATE_VALIDATION_FAILED"
    validation = output / "config-validation"
    validation.mkdir(mode=0o700)
    test_config = copy.deepcopy(config)
    test_config["access"]["users_file"] = str(validation / "users.json")
    write(validation / "adapter.json", test_config)
    command = [str(candidate / "bin/profile-accounts"), "put", "--config", str(validation / "adapter.json"),
               "--user", "qa-validation", "--profiles", ",".join(p["id"] for p in config["profiles"])]
    result = subprocess.run(command, input=base64.urlsafe_b64encode(os.urandom(24)), capture_output=True)
    assert result.returncode == 0, "ADAPTER_CANDIDATE_VALIDATION_FAILED"
    result = subprocess.run([str(candidate / "bin/profile-accounts"), "check", "--config", str(validation / "adapter.json")], capture_output=True)
    assert result.returncode == 0, "ADAPTER_REGISTRY_VALIDATION_FAILED"
    shutil.rmtree(validation)
    write(output / "adapter-validation.json", {"status": "pass", "candidate_config_accepted": True,
          "temporary_registry_checked": True, "production_accounts_created": False})
    assert before == {str(config_path): sha(config_path), str(args.system_caddy): sha(args.system_caddy)}
    binaries = {name: {"path": str(candidate / "bin" / name), "sha256": sha(candidate / "bin" / name)}
                for name in ("profile-adapter", "profile-accounts")}
    manifest = {"status": "REVIEW_ONLY_NOT_DEPLOYED", "prepared_at": datetime.now(timezone.utc).isoformat(),
        "candidate": str(candidate), "images": images, "binaries": binaries, "production_inputs": before,
        "changed_hosts": sorted(desired), "unrelated_routes_preserved": True, "private_tls": identity,
        "caddy_validation": checks, "accounts_provisioned": False,
        "prerequisites": ["R2 production Home backup/recovery and boot prerequisites",
                          "R4B Profile/app/policy migration to accepted r7 Worker",
                          "Explicit production account provisioning", "Approved production maintenance scope"],
        "files": {str(path.relative_to(output)): sha(path) for path in output.rglob("*") if path.is_file()}}
    write(output / "release-review.json", manifest)
    print(json.dumps({"status": manifest["status"], "output": str(output), "caddy_validation": checks,
                      "production_files_unchanged": True, "accounts_provisioned": False}))


if __name__ == "__main__":
    main()
