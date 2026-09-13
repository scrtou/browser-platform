#!/usr/bin/env python3
"""Fetch the exact official release from versions.json and verify its SHA-256."""

import hashlib
import json
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parent
release = json.loads((root / "versions.json").read_text())["browser"]
directory = root / ".build"
directory.mkdir(exist_ok=True)
archive = directory / "browser.zip"
if not archive.exists():
    temporary = directory / "browser.zip.part"
    try:
        request = urllib.request.Request(release["url"], headers={"User-Agent": "browser-platform"})
        with urllib.request.urlopen(request, timeout=60) as source, temporary.open("wb") as target:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        with temporary.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != release["sha256"]:
                raise SystemExit("BROWSER_ARCHIVE_MISMATCH")
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
with archive.open("rb") as source:
    if hashlib.file_digest(source, "sha256").hexdigest() != release["sha256"]:
        raise SystemExit("BROWSER_ARCHIVE_MISMATCH")
print("BROWSER_ARCHIVE_VERIFIED " + release["tag"])
