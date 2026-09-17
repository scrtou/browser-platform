#!/usr/bin/env python3
"""Bind package, host prerequisites and live production state before R4B maintenance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import urllib.request


PROJECT = Path(__file__).resolve().parents[3]
RUNTIME = PROJECT / "infra/sealskin/runtime/r4b-production-migration-2026-09-15"
PRODUCTION = PROJECT / "infra/sealskin"
TARGET_HOME = PRODUCTION / "storage/profile-adapter/personal-camoufox-r9"
MINIMUM_FREE_BYTES = 10 * 1024 * 1024 * 1024


def read(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise RuntimeError("unsafe or unavailable input: " + str(path))
    return json.loads(path.read_bytes())


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(arguments: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("preflight command failed: " + arguments[0])
    return result


def docker(*arguments: str) -> str:
    raw = ["docker", *arguments]
    result = subprocess.run(raw, capture_output=True, text=True)
    if result.returncode and "permission denied" in result.stderr.lower():
        result = subprocess.run(["sg", "docker", "-c", shlex.join(raw)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Docker preflight failed")
    return result.stdout


def profile(name: str):
    binary = RUNTIME / "candidate-4/bin/profile-adapter"
    result = command([str(binary), "-config", str(PRODUCTION / "adapter-config.json"),
                      "-inspect-profile", name])
    return json.loads(result.stdout)


def service(*arguments: str, user: bool = False) -> str:
    command_line = ["systemctl"] + (["--user"] if user else []) + list(arguments)
    return command(command_line).stdout.strip()


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package, output = args.package.resolve(strict=True), args.output.resolve()
    if output.exists():
        raise RuntimeError("output already exists")
    output.mkdir(mode=0o700, parents=True)

    verification_dir = output / "package-verification"
    verified = command([sys.executable, str(PRODUCTION / "checks/verify-r4b-production-release.py"),
                        "--package", str(package), "--output", str(verification_dir)], timeout=180)
    (output / "package-verification.log").write_text(verified.stdout + verified.stderr)
    os.chmod(output / "package-verification.log", 0o600)
    package_result = read(verification_dir / "result.json")
    if package_result["status"] != "pass":
        raise RuntimeError("release package verification failed")

    host = command([sys.executable, str(PRODUCTION / "entry-auth/install-host-prerequisites.py"),
                    "--package", str(package)])
    host_result = json.loads(host.stdout)
    if host_result["status"] != "installed":
        raise RuntimeError("host prerequisites are not installed")

    audit = read(package / "release-audit.json")
    if audit["status"] != "READY_FOR_MAINTENANCE" or audit["production_changes_performed"]:
        raise RuntimeError("release package state is not review-only")
    if any(sha(Path(path)) != expected for path, expected in audit["source_sha256"].items()):
        raise RuntimeError("production input drift")

    personal, work = profile("personal"), profile("work")
    empty_keys = ("records", "workers", "resources", "relays", "guards", "networks")
    if personal["status"] != "stopped" or any(personal[key] for key in empty_keys):
        raise RuntimeError("Personal is not safely stopped")
    if work["status"] != "running" or work["records"] != 1 or work["workers"] != 1:
        raise RuntimeError("Work running generation drift")
    if any(work[key] for key in ("resources", "relays", "guards", "networks")):
        raise RuntimeError("unexpected legacy Work resources")
    if TARGET_HOME.exists():
        raise RuntimeError("target Personal Home already exists")

    services = {
        "docker_enabled": service("is-enabled", "docker.service"),
        "docker_active": service("is-active", "docker.service"),
        "adapter_enabled": service("is-enabled", "profile-adapter.service", user=True),
        "adapter_active": service("is-active", "profile-adapter.service", user=True),
        "linger": command(["loginctl", "show-user", str(os.getuid()), "-p", "Linger", "--value"]).stdout.strip(),
    }
    if services != {"docker_enabled": "enabled", "docker_active": "active",
                    "adapter_enabled": "enabled", "adapter_active": "active", "linger": "yes"}:
        raise RuntimeError("service or linger precondition failed")

    caddy = urllib.request.urlopen("http://127.0.0.1:2019/config/", timeout=10)
    if caddy.status != 200 or not json.loads(caddy.read()):
        raise RuntimeError("Caddy administration endpoint is unavailable")
    free_bytes = os.statvfs(PROJECT).f_bavail * os.statvfs(PROJECT).f_frsize
    if free_bytes < MINIMUM_FREE_BYTES:
        raise RuntimeError("insufficient maintenance free space")

    image_results = {}
    for role, identifier in (("personal", audit["profiles"]["personal"]["image"]),
                             ("work", audit["profiles"]["work"]["image"])):
        value = json.loads(docker("image", "inspect", identifier))[0]
        labels = value["Config"].get("Labels", {})
        capabilities = {"browser_shutdown": labels.get("io.browser-platform.browser-shutdown"),
                        "session_auth": labels.get("io.browser-platform.session-auth")}
        if value["Id"] != identifier or set(capabilities.values()) != {"1"}:
            raise RuntimeError("target image capability drift")
        image_results[role] = {"id": identifier, **capabilities}

    backups = {}
    backup_root = RUNTIME.parent / "r2c-production-home-maintenance-2026-09-15"
    for name, expected in (("personal.age", "231c08a0d886d48d47fc264733234fc3956517d3dd2c481f2be6e57ff043c206"),
                           ("work.age", "c0488ecf99ddf02fe438d53667f6d6ff6d58a4ed6bc7d431ae3cecb3f03976e2")):
        path = backup_root / name
        actual = sha(path)
        if actual != expected:
            raise RuntimeError("production Home backup drift")
        backups[name] = {"sha256": actual, "size": path.stat().st_size}

    result = {
        "status": "READY_TO_DEPLOY",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "package": str(package),
        "package_verification": "pass",
        "host_prerequisites": host_result,
        "services": services,
        "profiles": {"personal": {key: personal[key] for key in ("status", *empty_keys)},
                     "work": {key: work[key] for key in ("status", "records", "workers", "resources",
                                                                  "relays", "guards", "networks")}},
        "target_home_absent": True,
        "images": image_results,
        "backups": backups,
        "free_bytes": free_bytes,
        "caddy_admin": "pass",
        "qa_cleanup": audit["qa_cleanup"]["status"],
        "production_inputs_unchanged": True,
        "production_changes_performed": False,
        "maintenance_effect": {"entry_hosts": "503 during maintenance", "work": "will restart",
                               "personal": "will create a new r9 Home", "rollback": "prepared"},
        "post_deploy_required": ["production login and both Profile checks",
                                 "target Mac Personal display/input check",
                                 "logout persistence, Docker restart and VPS reboot recovery"],
    }
    with (output / "result.json").open("x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("status", "package_verification", "target_home_absent",
                                                    "free_bytes", "production_changes_performed")}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        raise SystemExit("R4B go-live preflight refused: " + str(error))
