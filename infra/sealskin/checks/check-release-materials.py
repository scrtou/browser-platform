#!/usr/bin/env python3
"""Verify a pinned private release-materials bundle without applying it.

This checks bytes, paths and private permissions, not deployment readiness.
The manifest digest must come from the separately retained acceptance record.
No services, containers, configuration or browser state are changed.
"""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat


class Rejected(Exception):
    pass


def require(condition, code):
    if not condition:
        raise Rejected(code)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "DUPLICATE_JSON_KEY")
        value[key] = item
    return value


def path_parts(name):
    require(isinstance(name, str) and name != "manifest.json", "INVALID_PATH")
    parts = name.split("/")
    require(not PurePosixPath(name).is_absolute() and
            all(p not in ("", ".", "..") and "\\" not in p and "\x00" not in p for p in parts),
            "INVALID_PATH")
    return parts


def private_fd(fd, directory=False):
    info = os.fstat(fd)
    require((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) and
            info.st_mode & 0o077 == 0, "UNSAFE_FILE_OR_PERMISSIONS")
    return info


def open_member(root_fd, parts):
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = child
            private_fd(current, directory=True)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        try:
            private_fd(fd)
        except Exception:
            os.close(fd)
            raise
        return fd
    finally:
        os.close(current)


def digest_member(root_fd, parts, content=False):
    with os.fdopen(open_member(root_fd, parts), "rb") as stream:
        before = os.fstat(stream.fileno())
        digest, size, chunks = hashlib.sha256(), 0, []
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
            if content:
                require(size <= 4 * 1024 * 1024, "MANIFEST_TOO_LARGE")
                chunks.append(chunk)
        after = os.fstat(stream.fileno())
        require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "FILE_CHANGED")
        return digest.hexdigest(), size, b"".join(chunks)


def verify(root, manifest_sha256):
    require(bool(re.fullmatch(r"[0-9a-f]{64}", manifest_sha256)), "INVALID_MANIFEST_PIN")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        private_fd(root_fd, directory=True)
        digest, _, raw = digest_member(root_fd, ["manifest.json"], content=True)
        require(digest == manifest_sha256, "MANIFEST_DIGEST_MISMATCH")
        manifest = json.loads(raw, object_pairs_hook=unique_object)
        require(isinstance(manifest, dict) and set(manifest) == {"schema", "purpose", "files"},
                "INVALID_MANIFEST")
        require(manifest["schema"] == "browser-platform-materials-v1" and
                manifest["purpose"] == "audit-only" and isinstance(manifest["files"], list) and
                len(manifest["files"]) > 0, "INVALID_MANIFEST")
        seen, roles, total = set(), Counter(), 0
        for item in manifest["files"]:
            require(isinstance(item, dict) and set(item) == {"path", "sha256", "size", "role"},
                    "INVALID_ENTRY")
            parts = path_parts(item["path"])
            require(item["path"] not in seen, "DUPLICATE_PATH")
            seen.add(item["path"])
            require(isinstance(item["sha256"], str) and bool(re.fullmatch(r"[0-9a-f]{64}", item["sha256"])) and
                    type(item["size"]) is int and item["size"] >= 0 and
                    item["role"] in ("source", "binary", "config", "catalog", "backup", "receipt",
                                     "evidence", "tool", "instructions"), "INVALID_ENTRY")
            actual, size, _ = digest_member(root_fd, parts)
            require(actual == item["sha256"] and size == item["size"], "MEMBER_DIGEST_MISMATCH")
            roles[item["role"]] += 1
            total += size
        # Inventory through the retained directory FD, rejecting unlisted payloads.
        def inventory(fd, prefix=""):
            found = set()
            for name in os.listdir(fd):
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                path = prefix + name
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        private_fd(child, directory=True)
                        found.update(inventory(child, path + "/"))
                    finally:
                        os.close(child)
                else:
                    require(stat.S_ISREG(info.st_mode), "UNSAFE_FILE_OR_PERMISSIONS")
                    found.add(path)
            return found
        require(inventory(root_fd) == seen | {"manifest.json"}, "UNLISTED_PAYLOAD")
        require(digest_member(root_fd, ["manifest.json"])[0] == manifest_sha256, "MANIFEST_CHANGED")
        return {"result": "VERIFIED", "files": len(seen), "bytes": total,
                "roles": dict(roles), "applies_changes": False}
    finally:
        os.close(root_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        result = verify(args.bundle, args.manifest_sha256)
    except (Rejected, OSError, ValueError, TypeError) as error:
        # Never print payload values, paths or exception text from the filesystem.
        result = {"result": "REJECTED", "code": str(error) if isinstance(error, Rejected) else "INVALID_OR_UNREADABLE_BUNDLE"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
