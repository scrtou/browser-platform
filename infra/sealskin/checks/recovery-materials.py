#!/usr/bin/env python3
"""Inventory explicitly selected recovery inputs without following symlinks.

The private plan maps archive names to absolute files/directories. An inventory
does not make running browser files or unrelated checkpoints consistent.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def inventory(plan):
    result = {}
    for prefix, source in sorted(plan.items()):
        name = PurePosixPath(prefix)
        if name.is_absolute() or ".." in name.parts or str(name) != prefix or prefix == ".":
            raise ValueError("unsafe archive prefix")
        root = Path(source)
        if not root.is_absolute() or root.is_symlink() or root.resolve() != root:
            raise ValueError("source must be absolute and have no symlink ancestors")
        paths = [root]
        if root.is_dir():
            for parent, directories, files in os.walk(root, followlinks=False):
                paths.extend(Path(parent) / leaf for leaf in sorted(directories + files))
        for path in paths:
            relative = str(path.relative_to(root))
            key = prefix if relative == "." else prefix + "/" + relative
            if key in result:
                raise ValueError("overlapping archive prefixes")
            node = path.lstat()
            row = {"mode": stat.S_IMODE(node.st_mode)}
            if stat.S_ISREG(node.st_mode):
                row.update(kind="file", size=node.st_size, sha256=digest(path))
                after = path.stat()
                if (node.st_ino, node.st_size, node.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                    raise ValueError("source changed while hashing")
            elif stat.S_ISDIR(node.st_mode):
                row["kind"] = "directory"
            elif stat.S_ISLNK(node.st_mode):
                # Store link text, never traverse a browser lock or old path.
                row.update(kind="symlink", target=os.readlink(path))
            else:
                raise ValueError("special node requires explicit recovery handling")
            result[key] = row
    return result


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    rows = inventory(json.loads(args.plan.read_text()))
    if args.verify:
        if rows != json.loads(args.manifest.read_text())["entries"]:
            raise SystemExit("RECOVERY_MATERIAL_CHANGED")
    else:
        with args.manifest.open("x") as output:
            json.dump({"version": 1, "consistent_business_backup": False, "entries": rows}, output, indent=2)
            output.write("\n")
    print("PASS recovery inputs:", len(rows), "entries; verification:", args.verify)


if __name__ == "__main__":
    main()
