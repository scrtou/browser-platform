#!/usr/bin/env python3
"""Install or roll back an exact, hash-checked SealSkin lifecycle payload.

The running API must be restarted separately after installation. Worker
containers are never touched by this tool.
"""

import argparse
import hashlib
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
