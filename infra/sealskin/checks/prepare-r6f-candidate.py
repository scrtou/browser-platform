#!/usr/bin/env python3
"""Prepare an R6F isolated review candidate without changing production."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess


PROJECT = Path(__file__).resolve().parents[3]
RUNTIME = PROJECT / "infra/sealskin/runtime"
INPUTS = tuple(
    str(path.relative_to(PROJECT))
    for path in sorted((PROJECT / "adapter").rglob("*.go"))
) + (
    "infra/camoufox/environment-job.py",
    "infra/sealskin/lifecycle/environment-management.patch",
    "infra/camoufox/versions.json",
)
PRODUCTION_INPUTS = (
    PROJECT / "infra/sealskin/adapter-config.json",
    PROJECT / "infra/sealskin/adapter-state.json",
    PROJECT / "infra/sealskin/config/.config/sealskin/profile-network-policies.json",
    PROJECT / "infra/sealskin/compose.yml",
    PROJECT / "infra/sealskin/compose.proxy.yml",
    Path("/etc/caddy/Caddyfile"),
)
IMAGES = (
    "browser-platform/camoufox:0.5.6-beta.30-r9-desktop",
    "browser-platform/sealskin:0.3.2-entry-auth-v1-2ba57382ce75c8f9-pkg-1661ffdddfdf",
    "browser-platform/sealskin:0.3.2-entry-auth-v1-2ba57382ce75c8f9-pkg-1661ffdddfdf-checks",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], *, cwd: Path = PROJECT) -> str:
    result = subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout


def image_id(ref: str) -> str:
    value = json.loads(run(["docker", "image", "inspect", ref]))
    if len(value) != 1 or not value[0].get("Id", "").startswith("sha256:"):
        raise RuntimeError(f"invalid image identity: {ref}")
    return value[0]["Id"]


def build_binary(name: str, package: str, output_dir: Path) -> None:
    """Build with the fixed Go image used by the R6F checks."""
    command = ["docker", "run", "--rm", "--network", "none", "--user",
               f"{os.getuid()}:{os.getgid()}",
               "--tmpfs", "/tmp:rw,exec", "-e", "GOCACHE=/tmp/go-build",
               "-v", f"{PROJECT}:/repo:ro", "-v", f"{output_dir.parent}:/out:rw",
               "-w", "/repo/adapter", "golang:1.27-alpine", "/usr/local/go/bin/go", "build",
               "-buildvcs=false", "-trimpath", "-o", f"/out/{output_dir.name}/{name}", package]
    run(command)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"output already exists: {output}")
    output.mkdir(mode=0o700, parents=True)
    (output / "bin").mkdir(mode=0o700)

    # Build only into the new private candidate directory. No production path is used.
    for name, package in (("profile-adapter", "./cmd/profile-adapter"),
                          ("profile-accounts", "./cmd/profile-accounts")):
        target = output / "bin" / name
        build_binary(name, package, output / "bin")
        os.chmod(target, 0o700)

    input_hashes = {path: sha(PROJECT / path) for path in INPUTS}
    production_hashes = {}
    for path in PRODUCTION_INPUTS:
        if path.is_file() and not path.is_symlink():
            production_hashes[str(path)] = sha(path)
        else:
            production_hashes[str(path)] = None

    # Capture only stable, non-sensitive service/container facts.
    services = {
        "docker": run(["systemctl", "is-active", "docker"]).strip(),
        "caddy": run(["systemctl", "is-active", "caddy"]).strip(),
    }
    containers = []
    names = run(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"])
    for line in names.splitlines():
        name, image, status = line.split("\t", 2)
        containers.append({"name": name, "image": image, "status": status})

    binaries = {name: sha(output / "bin" / name) for name in ("profile-adapter", "profile-accounts")}
    manifest = {
        "schema": "browser-platform/r6f-candidate/v2",
        "status": "ISOLATED_REVIEW_ONLY",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": run(["git", "rev-parse", "HEAD"]).strip(),
        "source_inputs_sha256": input_hashes,
        "production_input_sha256": production_hashes,
        "binaries": binaries,
        "images": [{"ref": ref, "id": image_id(ref)} for ref in IMAGES],
        "production_changed": False,
        "deployment_authorized": False,
        "services": services,
        "containers": containers,
        "rollback_material": "infra/sealskin/runtime/r4b-production-migration-2026-09-15/release-ready-2",
        "not_tested": [
            "R6F full isolated controller/Worker composition",
            "real custom artifact in Trilium/macOS",
            "production install",
            "real upstream proxy credentials",
            "R6F combination-root end-to-end restore",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    os.chmod(output / "manifest.json", 0o600)
    (output / "bin.sha256").write_text(
        "".join(f"{digest}  {output / 'bin' / name}\n" for name, digest in binaries.items())
    )
    os.chmod(output / "bin.sha256", 0o600)
    print(json.dumps({"output": str(output), "source_commit": manifest["source_commit"],
                      "production_changed": False, "images": len(IMAGES)}, indent=2))


if __name__ == "__main__":
    main()
