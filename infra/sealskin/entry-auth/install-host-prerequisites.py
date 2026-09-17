#!/usr/bin/env python3
"""Check or install the host tmpfiles and Docker ordering for display secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile


TMPFILES_TARGET = Path("/etc/tmpfiles.d/browser-platform-session-auth.conf")
ORDERING_TARGET = Path("/etc/systemd/system/docker.service.d/browser-platform-tmpfiles.conf")
CADDY_RESUME_TARGET = Path("/etc/systemd/system/caddy.service.d/browser-platform-api-resume.conf")
RUNTIME_TARGET = Path("/run/browser-platform/session-secrets")


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_install(source: Path, target: Path, mode: int) -> None:
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + target.name + ".", dir=target.parent)
    try:
        os.fchmod(descriptor, mode)
        with source.open("rb") as input_stream, os.fdopen(descriptor, "wb", closefd=False) as output_stream:
            shutil.copyfileobj(input_stream, output_stream)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def expected(package: Path):
    manifest = json.loads((package / "manifest.json").read_text())
    if manifest.get("status") != "READY_FOR_MAINTENANCE" or manifest.get("production_changes_performed"):
        raise RuntimeError("package is not an uninstalled maintenance candidate")
    sources = {
        TMPFILES_TARGET: package / "entry-auth/browser-platform-session-auth.tmpfiles.conf",
        ORDERING_TARGET: package / "entry-auth/docker-tmpfiles-ordering.conf",
        CADDY_RESUME_TARGET: package / "entry-auth/caddy-api-resume.conf",
    }
    for source in sources.values():
        name = str(source.relative_to(package))
        if (not source.is_file() or source.is_symlink()
                or manifest["files"].get(name) != sha(source)):
            raise RuntimeError("host prerequisite input does not match the package manifest")
    return sources


def check(package: Path):
    sources = expected(package)
    installed = {str(target): target.is_file() and not target.is_symlink()
                 and sha(target) == sha(source) and stat.S_IMODE(target.stat().st_mode) == 0o644
                 for target, source in sources.items()}
    definition = [line.split() for line in sources[TMPFILES_TARGET].read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#")]
    runtime_definition = next(parts for parts in definition if parts[1] == str(RUNTIME_TARGET))
    expected_runtime = {"mode": oct(int(runtime_definition[2], 8)),
                        "uid": int(runtime_definition[3]), "gid": int(runtime_definition[4])}
    runtime = {"exists": RUNTIME_TARGET.is_dir() and not RUNTIME_TARGET.is_symlink()}
    if runtime["exists"]:
        info = RUNTIME_TARGET.stat()
        runtime.update(mode=oct(stat.S_IMODE(info.st_mode)), uid=info.st_uid, gid=info.st_gid)
    runtime["matches"] = runtime["exists"] and all(runtime[key] == value for key, value in expected_runtime.items())
    show = subprocess.run(["systemctl", "show", "docker.service", "-p", "Requires", "-p", "After"],
                          capture_output=True, text=True)
    ordering = show.returncode == 0 and "systemd-tmpfiles-setup.service" in show.stdout
    caddy_show = subprocess.run(["systemctl", "show", "caddy.service", "-p", "ExecStart", "-p", "ExecReload"],
                                capture_output=True, text=True)
    caddy_resume = (caddy_show.returncode == 0 and " --resume" in caddy_show.stdout
                    and "/var/lib/caddy/.config/caddy/autosave.json" in caddy_show.stdout)
    return {"status": "installed" if all(installed.values()) and runtime["matches"] and ordering and caddy_resume else "pending",
            "files": installed, "runtime": runtime, "docker_tmpfiles_ordering_active": ordering,
            "caddy_api_resume_active": caddy_resume}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    package = args.package.resolve(strict=True)
    sources = expected(package)
    if args.apply:
        if os.geteuid() != 0:
            raise RuntimeError("--apply requires root")
        for target, source in sources.items():
            if target.exists() and (target.is_symlink() or not target.is_file()):
                raise RuntimeError("unsafe existing host prerequisite target")
            atomic_install(source, target, 0o644)
        subprocess.run(["systemd-tmpfiles", "--create", str(TMPFILES_TARGET)], check=True)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        # Restart verification remains an explicit R2 maintenance action. This
        # installer does not restart Docker or the host.
    result = check(package)
    print(json.dumps(result, sort_keys=True))
    if args.apply and result["status"] != "installed":
        raise RuntimeError("host prerequisite installation could not be verified")


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit("host prerequisite operation refused: " + str(error))
