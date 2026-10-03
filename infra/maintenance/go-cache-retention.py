#!/usr/bin/env python3
"""Inventory and clear one explicitly selected, idle Go build cache.

Plans contain content hashes and must live outside the cache. This tool never
discovers deletion targets, removes release artifacts, or prunes Docker data.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess


MARKER = "This directory holds cached build artifacts"
CACHE_FILE = re.compile(r"[0-9a-f]{2}/[0-9a-f]{64}-[ad]")


def checked_path(path):
    path = Path(os.path.abspath(path))
    if path.resolve(strict=True) != path or not path.is_dir():
        raise ValueError("cache path must be a directory without symlink ancestors")
    return path


def inventory(path):
    path = checked_path(path)
    marker = path / "README"
    if marker.is_symlink() or MARKER not in marker.read_text():
        raise ValueError("not a Go build cache")
    entries = {}
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            item = Path(base) / name
            rel = item.relative_to(path).as_posix()
            info = item.lstat()
            if stat.S_ISDIR(info.st_mode):
                if not re.fullmatch(r"[0-9a-f]{2}", rel):
                    raise ValueError("unexpected cache directory")
                continue
            if not stat.S_ISREG(info.st_mode) or not (
                rel in {"README", "trim.txt"} or CACHE_FILE.fullmatch(rel)
            ):
                raise ValueError("unexpected cache file or symlink")
            entries[rel] = {
                "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
                "size": info.st_size,
                "mtime_ns": info.st_mtime_ns,
                "mode": stat.S_IMODE(info.st_mode),
                "uid": info.st_uid,
            }
    return entries


def ensure_idle(path):
    commands = subprocess.check_output(["ps", "-eo", "comm="], text=True).splitlines()
    if any(command.strip() in {"go", "compile", "link", "cgo"} for command in commands):
        raise ValueError("Go build process is active")
    ids = subprocess.check_output(["docker", "ps", "-aq"], text=True).split()
    containers = json.loads(subprocess.check_output(["docker", "inspect", *ids], text=True)) if ids else []
    for container in containers:
        for mount in container.get("Mounts", []):
            source = Path(mount["Source"])
            if source == path or source in path.parents or path in source.parents:
                raise ValueError("cache intersects a Docker mount")


def plan(runtime, cache):
    runtime, cache = checked_path(runtime), checked_path(cache)
    if runtime.name != "runtime" or len(cache.relative_to(runtime).parts) < 2:
        raise ValueError("cache must be inside a task directory under runtime")
    ensure_idle(cache)
    return {"version": 1, "kind": "go-build-cache", "runtime": str(runtime),
            "cache": str(cache), "entries": inventory(cache)}


def clear(expected, mapped=None):
    if expected.get("version") != 1 or expected.get("kind") != "go-build-cache":
        raise ValueError("unsupported cache plan")
    if mapped is not None:
        if Path(mapped) != Path("/cache") or not Path("/.dockerenv").exists():
            raise ValueError("mapped clearing requires an isolated /cache container mount")
        cache = checked_path(mapped)
    else:
        current = plan(Path(expected["runtime"]), Path(expected["cache"]))
        if current != expected:
            raise ValueError("cache changed since plan")
        cache = Path(expected["cache"])
    if inventory(cache) != expected["entries"]:
        raise ValueError("cache changed since plan")
    if not shutil.rmtree.avoids_symlink_attacks:
        raise ValueError("safe directory deletion is unavailable")
    for child in cache.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    if any(cache.iterdir()):
        raise ValueError("cache changed during clearing; inspect the retained directory")
    return {"result": "PASS", "files_removed": len(expected["entries"]),
            "logical_bytes_removed": sum(item["size"] for item in expected["entries"].values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("plan")
    prepare.add_argument("--runtime", type=Path, required=True)
    prepare.add_argument("--cache", type=Path, required=True)
    prepare.add_argument("--out", type=Path, required=True)
    apply = commands.add_parser("apply")
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--mapped-cache", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == "plan":
        result = plan(args.runtime, args.cache)
        output = Path(os.path.abspath(args.out))
        if Path(result["cache"]) in output.resolve().parents:
            raise ValueError("plan must be saved outside the cache")
        with output.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print("PASS cache plan created; no files removed")
    else:
        print(json.dumps(clear(json.loads(args.plan.read_text()), args.mapped_cache)))


if __name__ == "__main__":
    main()
