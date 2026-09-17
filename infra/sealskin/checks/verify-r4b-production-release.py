#!/usr/bin/env python3
"""Independently verify an R4B private production package and live input identity."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess


PROJECT = Path(__file__).resolve().parents[3]
RUNTIME = PROJECT / "infra/sealskin/runtime/r4b-production-migration-2026-09-15"
PRODUCTION = PROJECT / "infra/sealskin"


def read(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise RuntimeError("unsafe package file: " + str(path))
    return json.loads(path.read_bytes())


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def revision(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def docker(*arguments: str) -> str:
    command = ["docker", *arguments]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode and "permission denied" in result.stderr.lower():
        result = subprocess.run(["sg", "docker", "-c", shlex.join(command)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Docker verification failed")
    return result.stdout


def identity(value):
    return {"id": value["Id"], "image": value["Image"], "started_at": value["State"]["StartedAt"],
            "pid": value["State"]["Pid"], "running": value["State"]["Running"]}


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package, output = args.package.resolve(strict=True), args.output.resolve()
    if output.exists() or package.stat().st_mode & 0o077:
        raise RuntimeError("unsafe package or existing verification output")
    output.mkdir(mode=0o700, parents=True)

    manifest, audit = read(package / "manifest.json"), read(package / "release-audit.json")
    if manifest["status"] != audit["status"] or audit["status"] != "READY_FOR_MAINTENANCE":
        raise RuntimeError("package is not ready for maintenance")
    if audit["production_changes_performed"] or not audit["ready_for_maintenance"]:
        raise RuntimeError("invalid release state")
    for name, expected in manifest["files"].items():
        path = package / name
        if not path.is_file() or path.is_symlink() or sha(path) != expected:
            raise RuntimeError("package manifest mismatch: " + name)
        mode = path.stat().st_mode & 0o777
        expected_mode = 0o700 if name.startswith("release-input/bin/") else 0o600
        if mode != expected_mode:
            raise RuntimeError("package mode mismatch: " + name)

    config = read(package / "adapter.candidate.json")
    profiles = {value["id"]: value for value in config["profiles"]}
    policies = read(package / "network-policies.candidate.json")
    personal_app = read(package / "application.personal.json")
    work_app = read(package / "application.work.json")
    personal = profiles["personal"]
    work = profiles["work"]
    policy = policies["policies"][personal["network_policy_id"]]
    if revision(policy) != personal["network_policy_sha256"]:
        raise RuntimeError("Personal policy digest mismatch")
    if (policy["profile_id"], policy["home_name"], policy["application_id"]) != (
            personal["id"], personal["home_name"], personal["application_id"]):
        raise RuntimeError("Personal policy ownership mismatch")
    if personal_app["id"] != personal["application_id"] or work_app["id"] != work["application_id"]:
        raise RuntimeError("application identity mismatch")
    if personal_app["provider_config"]["network_policy_sha256"] != personal["network_policy_sha256"]:
        raise RuntimeError("Personal App policy mismatch")
    required = {"browser_shutdown_version": 1, "session_auth_version": 1}
    if personal.get("required_runtime_capabilities") != required or work.get("required_runtime_capabilities") != required:
        raise RuntimeError("runtime capability requirement missing")
    for app in (personal_app, work_app):
        image = json.loads(docker("image", "inspect", app["provider_config"]["image"]))[0]
        labels = image["Config"].get("Labels", {})
        if labels.get("io.browser-platform.browser-shutdown") != "1" or labels.get("io.browser-platform.session-auth") != "1":
            raise RuntimeError("application image capability mismatch")

    account_check = subprocess.run([str(RUNTIME / "candidate-4/bin/profile-accounts"), "check", "--config",
                                    str(package / "adapter.account-staging.json")], capture_output=True)
    if account_check.returncode:
        raise RuntimeError("staged account registry rejected")
    for name in ("caddy.candidate.json", "caddy.maintenance.json"):
        validation = subprocess.run(["caddy", "validate", "--config", str(package / "entry-auth" / name)],
                                    capture_output=True)
        if validation.returncode:
            raise RuntimeError("Caddy package rejected")
    caddy_resume = (package / "entry-auth/caddy-api-resume.conf").read_text()
    if ("ExecStart=/usr/bin/caddy run --environ --config /etc/caddy/Caddyfile --resume" not in caddy_resume
            or "ExecReload=/usr/bin/caddy reload --config /var/lib/caddy/.config/caddy/autosave.json --force"
            not in caddy_resume):
        raise RuntimeError("Caddy API resume prerequisite is incomplete")
    compose = subprocess.run(["docker", "compose", "-f", str(PRODUCTION / "compose.yml"),
                              "-f", str(PRODUCTION / "compose.proxy.yml"),
                              "-f", str(package / "entry-auth/compose.entry-auth.yml"), "config"], capture_output=True)
    if compose.returncode:
        raise RuntimeError("Compose package rejected")

    if any(sha(Path(path)) != expected for path, expected in audit["source_sha256"].items()):
        raise RuntimeError("live production input drift")
    preserved = audit["current_runtime_preserved"]
    live = json.loads(docker("inspect", preserved["controller"]["id"], preserved["relay"]["id"],
                             preserved["work"]["id"]))
    if [identity(value) for value in live] != [preserved[name] for name in ("controller", "relay", "work")]:
        raise RuntimeError("production runtime identity drift")
    if read(RUNTIME / "window-r10/stage-1/cleanup-final.json")["status"] != "pass":
        raise RuntimeError("Mac QA cleanup is incomplete")

    result = {"status": "pass", "checked_at": datetime.now(timezone.utc).isoformat(),
              "package": str(package), "manifest_files": len(manifest["files"]),
              "profile_bindings": 2, "image_capability_checks": 2,
              "account_registry": "pass", "caddy_configs": 2, "caddy_api_resume": "pass", "compose": "pass",
              "production_inputs_unchanged": True, "production_runtime_identities_unchanged": True,
              "qa_cleanup": "pass", "production_changes_performed": False}
    with (output / "result.json").open("x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        raise SystemExit("R4B release verification refused: " + str(error))
