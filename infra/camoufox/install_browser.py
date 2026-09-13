#!/usr/bin/env python3
"""Install only the audited browser archive; never resolve a latest release."""

import configparser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    source, pins_file, managed_file, destination = map(Path, sys.argv[1:])
    pins = json.loads(pins_file.read_text())
    if digest(source) != pins["browser"]["sha256"]:
        raise SystemExit("BROWSER_ARCHIVE_MISMATCH")
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or stat.S_ISLNK(mode):
                raise SystemExit("BROWSER_ARCHIVE_UNSAFE_PATH")
            target = destination.joinpath(*path.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as src, target.open("xb") as dst:
                while chunk := src.read(1024 * 1024):
                    dst.write(chunk)
            target.chmod(0o755 if mode & 0o111 else 0o644)

    application = configparser.ConfigParser()
    application.read(destination / "application.ini")
    for key, value in pins["browser"]["application"].items():
        if application["App"].get(key) != value:
            raise SystemExit("BROWSER_VERSION_MISMATCH")
    for name in ("camoufox", "camoufox-bin"):
        (destination / name).chmod(0o755)
    (destination / "version.json").write_text(json.dumps({
        "version": pins["browser"]["version"],
        "release": pins["browser"]["build"],
    }) + "\n")
    with (destination / "camoufox.cfg").open("a") as cfg:
        cfg.write(managed_file.read_text())
    # Keep upstream autoconfig and append our locked preferences after it.
    (destination / "defaults/pref/browser-platform.js").write_text(
        'pref("general.config.filename", "camoufox.cfg");\n'
        'pref("general.config.obscure_value", 0);\n'
        'pref("general.config.sandbox_enabled", false);\n'
    )
    fonts = (destination / "fontconfig/linux/fonts.conf").read_text()
    fonts = fonts.replace('<dir prefix="cwd">fonts</dir>', f"<dir>{destination}/fonts</dir>")
    (destination / "fontconfig/browser-platform.conf").write_text(fonts)
    manifest = {
        str(path.relative_to(destination)): digest(path)
        for path in sorted(destination.rglob("*")) if path.is_file()
    }
    manifest_file = destination.parent / "browser-manifest.json"
    manifest_file.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    print("BROWSER_BUNDLE_VERIFIED files=" + str(len(manifest)))


if __name__ == "__main__":
    main()
