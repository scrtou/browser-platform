#!/usr/bin/env python3
"""Consistent offline backup, verification and restore of one browser Home.

`backup` refuses to run while the Profile is not confirmed stopped: the running
Adapter's private control socket must report `stopped` with an empty runtime
inventory, so no browser, Worker or network resource can write to the Home
during the snapshot. The archive is one zstd-compressed tar plus a manifest with
per-file SHA-256 digests and the context needed to restore the same behaviour
(application, image ID, environment artifact digest, network policy revision).

`restore` only writes into an empty directory and re-verifies every digest.
`control-state` snapshots the control-plane state files (no Home data). Secrets
(keys, network-secrets, SSL keys) are listed by digest but only archived when
`--include-secrets` is given; such archives must be stored encrypted.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import os
import shlex
import socket
import stat
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_VERSION = 1
PREFIX = "io.browser-platform."


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str):
        super().__init__("adapter", timeout=90)
        self.unix_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.unix_path)


def control(socket_path: str, profile: str, action: str = "inspect") -> tuple[int, dict]:
    connection = UnixConnection(socket_path)
    try:
        connection.request("GET" if action == "inspect" else "POST",
                           "/profiles/" + profile + ("" if action == "inspect" else "/" + action))
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def manifest_for(archive: Path) -> Path:
    """`<name>.tar.zst` ↔ `<name>.manifest.json` (and `<name>.tar` for control-state)."""
    name = archive.name
    for suffix in (".tar.zst", ".tar"):
        if name.endswith(suffix):
            return archive.with_name(name[: -len(suffix)] + ".manifest.json")
    return archive.with_suffix(".manifest.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def walk(root: Path) -> list[dict]:
    """List regular files, symlinks and directories under root with digests."""
    entries = []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(info.st_mode):
            entries.append({"path": relative, "type": "symlink", "target": os.readlink(path), "mode": stat.S_IMODE(info.st_mode)})
        elif stat.S_ISDIR(info.st_mode):
            entries.append({"path": relative, "type": "dir", "mode": stat.S_IMODE(info.st_mode)})
        elif stat.S_ISREG(info.st_mode):
            entries.append({"path": relative, "type": "file", "size": info.st_size, "mode": stat.S_IMODE(info.st_mode),
                            "mtime": int(info.st_mtime), "sha256": sha256_file(path)})
        else:
            raise SystemExit(f"Unsupported file type in Home: {relative}")
    return entries


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text())
    base = path.resolve().parent
    def resolve(value):
        return str((base / value).resolve()) if value and not os.path.isabs(value) else value
    config["state_file"] = resolve(config["state_file"])
    config["control_socket"] = resolve(config.get("control_socket") or "") or config["state_file"] + ".control.sock"
    return config


def docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if result.returncode:
        result = subprocess.run(["sg", "docker", "-c", shlex.join(["docker", *args])], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit("docker command failed: " + result.stderr[:200])
    return result.stdout


def app_context(sealskin_config_dir: Path, application_id: str) -> dict:
    """Read the pinned image and environment identity of the Profile's application."""
    import yaml
    apps = yaml.safe_load((sealskin_config_dir / "installed_apps.yml").read_text()) or []
    app = next((a for a in apps if a.get("id") == application_id), None)
    if not app:
        raise SystemExit(f"application {application_id} not found in installed_apps.yml")
    provider = (app.get("overrides") or {}).get("provider_config") or {}
    env = {e["name"]: e["value"] for e in provider.get("env", []) if isinstance(e, dict)}
    image = provider.get("image", "")
    image_id = docker("image", "inspect", image, "--format", "{{.Id}}").strip() if image else ""
    return {"application_id": application_id, "image": image, "image_id": image_id,
            "environment_id": env.get("BROWSER_PLATFORM_ENVIRONMENT_ID", ""),
            "artifact_sha256": env.get("BROWSER_PLATFORM_ARTIFACT_SHA256", ""),
            "acceptance_sha256": env.get("BROWSER_PLATFORM_ACCEPTANCE_SHA256", ""),
            "network_policy_id": provider.get("network_policy_id", ""),
            "network_policy_sha256": provider.get("network_policy_sha256", "")}


def require_stopped(config: dict, profile: str) -> dict:
    status, value = control(config["control_socket"], profile)
    if status != 200:
        raise SystemExit(f"Profile {profile} inspect returned HTTP {status}: {value.get('error')}")
    result = value["result"]
    if result["status"] != "stopped" or result["records"] or result["workers"] or result["resources"]:
        raise SystemExit(f"Profile {profile} is not confirmed stopped (status={result['status']}, records={result['records']}, "
                         f"workers={result['workers']}, resources={result['resources']}); stop it first")
    return result


def backup(args) -> None:
    config = load_config(args.config)
    definition = next((p for p in config["profiles"] if p["id"] == args.profile), None)
    if not definition:
        raise SystemExit(f"Profile {args.profile} not in adapter config")
    before = require_stopped(config, args.profile)
    home = (args.storage / config["sealskin"]["username"] / definition["home_name"]).resolve()
    if not home.is_dir():
        raise SystemExit(f"Home directory missing: {home}")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = args.output / f"{args.profile}-{definition['home_name']}-{stamp}.tar.zst"
    manifest_path = manifest_for(archive)
    if archive.exists() or manifest_path.exists():
        raise SystemExit("archive already exists")
    entries = walk(home)
    with archive.open("wb") as raw:
        os.fchmod(raw.fileno(), 0o600)
        zstd = subprocess.Popen(["zstd", "-q", "-T0", "-19", "-c"], stdin=subprocess.PIPE, stdout=raw)
        try:
            with tarfile.open(fileobj=zstd.stdin, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                tar.add(str(home), arcname=".", recursive=True)
            zstd.stdin.close()
        except BrokenPipeError as exc:
            zstd.wait()
            raise SystemExit("zstd stopped reading the archive stream") from exc
        if zstd.wait():
            raise SystemExit("zstd failed")
        raw.flush()
        os.fsync(raw.fileno())
    after = require_stopped(config, args.profile)
    if walk(home) != entries:
        archive.unlink()
        raise SystemExit("Home changed during the snapshot; backup discarded")
    context = app_context(args.sealskin_config, definition["application_id"])
    context.update({"adapter_home": definition["home_name"], "adapter_profile": args.profile,
                    "profile_network_policy_id": definition.get("network_policy_id", ""),
                    "profile_network_policy_sha256": definition.get("network_policy_sha256", "")})
    manifest = {"version": MANIFEST_VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
                "profile": args.profile, "home_name": definition["home_name"], "username": config["sealskin"]["username"],
                "home_path": str(home), "archive": archive.name, "archive_sha256": sha256_file(archive),
                "archive_size": archive.stat().st_size, "files": len([e for e in entries if e["type"] == "file"]),
                "bytes": sum(e.get("size", 0) for e in entries), "stopped_before": before, "stopped_after": after,
                "context": context, "entries": entries}
    manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    manifest_path.chmod(0o600)
    print(json.dumps({"backup": archive.name, "files": manifest["files"], "bytes": manifest["bytes"],
                      "archive_sha256": manifest["archive_sha256"], "image_id": context["image_id"],
                      "artifact_sha256": context["artifact_sha256"]}))


def read_manifest(archive: Path) -> dict:
    manifest = json.loads(manifest_for(archive).read_text())
    if manifest.get("version") != MANIFEST_VERSION:
        raise SystemExit("unsupported manifest version")
    if sha256_file(archive) != manifest["archive_sha256"]:
        raise SystemExit("archive digest mismatch")
    return manifest


def extract(archive: Path, target: Path) -> None:
    zstd = subprocess.Popen(["zstd", "-q", "-d", "-c", str(archive)], stdout=subprocess.PIPE)
    with tarfile.open(fileobj=zstd.stdout, mode="r|") as tar:
        for member in tar:
            name = os.path.normpath(member.name)
            if name.startswith("..") or os.path.isabs(name):
                raise SystemExit("unsafe archive member")
            if member.issym() or member.islnk():
                link = os.path.normpath(os.path.join(os.path.dirname(name), member.linkname))
                if member.islnk() or link.startswith(".."):
                    raise SystemExit("unsafe link in archive")
            if not (member.isdir() or member.isfile() or member.issym()):
                raise SystemExit("unsupported archive member type")
            if hasattr(tarfile, "tar_filter"):
                tar.extract(member, path=str(target), set_attrs=True, filter="tar")
            else:
                # Python < 3.11.4: the explicit checks above already refuse
                # absolute paths, parent traversal, hard links and devices.
                tar.extract(member, path=str(target), set_attrs=True)
    if zstd.wait():
        raise SystemExit("zstd decompression failed")


def compare(manifest: dict, root: Path) -> list[str]:
    actual = {e["path"]: e for e in walk(root)}
    expected = {e["path"]: e for e in manifest["entries"]}
    problems = []
    for path, entry in expected.items():
        current = actual.get(path)
        if not current:
            problems.append("missing " + path)
        elif entry["type"] != current["type"] or entry.get("sha256") != current.get("sha256") or entry.get("target") != current.get("target"):
            problems.append("differs " + path)
    for path in actual:
        if path not in expected:
            problems.append("extra " + path)
    return problems


def verify(args) -> None:
    manifest = read_manifest(args.archive)
    with __import__("tempfile").TemporaryDirectory(prefix="home-verify-") as directory:
        target = Path(directory) / "home"
        target.mkdir(mode=0o700)
        extract(args.archive, target)
        problems = compare(manifest, target)
    if problems:
        raise SystemExit("verification failed: " + "; ".join(problems[:10]))
    print(json.dumps({"verified": True, "archive": args.archive.name, "files": manifest["files"], "context": manifest["context"]}))


def restore(args) -> None:
    manifest = read_manifest(args.archive)
    target = args.target.resolve()
    if target.exists() and any(target.iterdir()):
        raise SystemExit("restore target must be empty")
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    extract(args.archive, target)
    problems = compare(manifest, target)
    if problems:
        raise SystemExit("restored tree differs from manifest: " + "; ".join(problems[:10]))
    os.chmod(target, 0o700)
    print(json.dumps({"restored": True, "target": str(target), "files": manifest["files"], "context": manifest["context"]}))


def control_state(args) -> None:
    """Archive control-plane state (no browser Home). Secrets only with --include-secrets."""
    root = args.sealskin_config.resolve()
    if (os.path.lexists(root / "session-secrets") or os.path.lexists(root / "sessions.yml")
            or load_config(args.config).get("access") is not None):
        raise SystemExit("Session state and entry accounts require secure-backup.py; no plaintext archive was created.")
    public = ["installed_apps.yml", "profile-network-policies.json", "sessions.yml", "app_stores.yml", "Caddyfile"]
    secret_dirs = ["keys", "network-secrets", "ssl"]
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = args.output / f"control-state-{stamp}.tar"
    listing = []
    with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as tar:
        for name in public:
            path = root / name
            if path.exists():
                tar.add(str(path), arcname=name)
                listing.append({"path": name, "sha256": sha256_file(path), "archived": True})
        for name in secret_dirs:
            base = root.parent.parent / name if name == "ssl" else root / name
            if not base.exists():
                continue
            for path in sorted(base.rglob("*")):
                if path.is_file():
                    rel = name + "/" + path.relative_to(base).as_posix()
                    listing.append({"path": rel, "sha256": sha256_file(path), "archived": bool(args.include_secrets)})
                    if args.include_secrets:
                        tar.add(str(path), arcname=rel)
        adapter = {"config": args.config.resolve(), "state": Path(load_config(args.config)["state_file"])}
        for label, path in adapter.items():
            if path.exists():
                tar.add(str(path), arcname="adapter/" + path.name)
                listing.append({"path": "adapter/" + path.name, "sha256": sha256_file(path), "archived": True})
    archive.chmod(0o600)
    manifest = {"version": MANIFEST_VERSION, "created_at": datetime.now(timezone.utc).isoformat(), "archive": archive.name,
                "archive_sha256": sha256_file(archive), "includes_secrets": bool(args.include_secrets), "entries": listing}
    manifest_path = manifest_for(archive)
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n")
    manifest_path.chmod(0o600)
    print(json.dumps({"control_state": archive.name, "entries": len(listing), "includes_secrets": bool(args.include_secrets)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup", help="offline backup of one stopped Profile's Home")
    b.add_argument("--config", type=Path, required=True, help="Adapter config (control socket is derived from it)")
    b.add_argument("--profile", required=True)
    b.add_argument("--storage", type=Path, required=True, help="SealSkin storage root (contains <user>/<home>)")
    b.add_argument("--sealskin-config", type=Path, required=True, help="SealSkin config/.config/sealskin directory")
    b.add_argument("--output", type=Path, required=True)
    b.set_defaults(func=backup)
    v = sub.add_parser("verify", help="re-extract and verify an archive against its manifest")
    v.add_argument("archive", type=Path)
    v.set_defaults(func=verify)
    r = sub.add_parser("restore", help="restore an archive into an empty directory")
    r.add_argument("archive", type=Path)
    r.add_argument("--target", type=Path, required=True)
    r.set_defaults(func=restore)
    c = sub.add_parser("control-state", help="archive control-plane state files")
    c.add_argument("--config", type=Path, required=True)
    c.add_argument("--sealskin-config", type=Path, required=True)
    c.add_argument("--output", type=Path, required=True)
    c.add_argument("--include-secrets", action="store_true")
    c.set_defaults(func=control_state)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
