#!/usr/bin/env python3
"""Install or roll back an exact, hash-checked SealSkin lifecycle payload.

The running API must be restarted separately after installation. Worker
containers are never touched by this tool.
"""

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def atomic_write(path, data):
    fd, temporary = tempfile.mkstemp(prefix=".lifecycle-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o644)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def check_dependencies(manifest):
    """Reject a missing/wrong runtime before changing any application file."""
    for dependency in manifest.get("python_dependencies", []):
        try:
            installed = importlib.metadata.version(dependency["name"])
            module = importlib.import_module(dependency["module"])
            if installed != dependency["version"] or getattr(module, "__version__", None) != installed:
                raise ValueError("Dependency version mismatch")
            if dependency["name"] == "dnspython":
                for name in ("dns.message", "dns.query"):
                    importlib.import_module(name)
            elif dependency["name"] == "Babel":
                data = importlib.import_module("babel.core").get_global("likely_subtags")
                if data.get("en") != "en_Latn_US" or data.get("zh_TW") != "zh_Hant_TW":
                    raise ValueError("CLDR data missing or mismatched")
        except (ImportError, ValueError, importlib.metadata.PackageNotFoundError):
            raise SystemExit(f"Runtime dependency missing or mismatched: {dependency['name']}") from None


def check_rollback_state(manifest):
    if "session_secrets.py" not in manifest["files"]:
        return
    from app.settings import settings
    database = Path(settings.sessions_db_path)
    if os.path.lexists(database.parent / "session-secrets"):
        raise SystemExit("Encrypted Session state requires a matched offline recovery bundle before code rollback.")
    if database.exists():
        import yaml
        try:
            value = yaml.safe_load(database.read_bytes())
        except Exception:
            raise SystemExit("Session state cannot be verified for rollback.") from None
        if isinstance(value, dict) and "session_state_version" in value:
            raise SystemExit("Encrypted Session state requires a matched offline recovery bundle before code rollback.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--app-dir", type=Path)
    args = parser.parse_args()
    import app
    destination = args.app_dir or Path(app.__path__[0])
    payload = Path(__file__).resolve().parent
    manifest = json.loads((payload / "manifest.json").read_text())
    if not args.rollback:
        check_dependencies(manifest)
    else:
        check_rollback_state(manifest)
    files = manifest["files"]
    stage = "before" if args.rollback else "after"
    inputs = payload / ("original" if args.rollback else "app")
    for name, hashes in files.items():
        if name.startswith("/") or ".." in Path(name).parts:
            raise SystemExit("Invalid payload path.")
        if digest(destination / name) not in (hashes["before"], hashes["after"]):
            raise SystemExit(f"Installed source drift: {name}")
        if digest(inputs / name) != hashes[stage]:
            raise SystemExit(f"Payload hash mismatch: {name}")
    if not args.check:
        for name, hashes in files.items():
            path = destination / name
            if hashes[stage] is None:
                if path.exists():
                    path.unlink()
            else:
                atomic_write(path, (inputs / name).read_bytes())
            for cache in (path.parent / "__pycache__").glob(path.stem + ".*.pyc"):
                cache.unlink()
        for name, hashes in files.items():
            if digest(destination / name) != hashes[stage]:
                raise SystemExit(f"Installed hash mismatch: {name}")
    print(json.dumps({"release": manifest["release"], "files": len(files),
                      "mode": "check" if args.check else stage}))


if __name__ == "__main__":
    main()
