#!/usr/bin/env python3
"""Add managed Firefox proxy policy to an exact reviewed Work image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
SOURCES = {
    "Dockerfile": ROOT / "Dockerfile",
    "browser-platform-autoconfig.js": PROJECT / "infra/firefox-proxy/browser-platform-autoconfig.js",
    "browser-platform.cfg": PROJECT / "infra/firefox-proxy/browser-platform.cfg",
}


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if result.returncode and "permission denied" in result.stderr.lower():
        result = subprocess.run(
            ["sg", "docker", "-c", shlex.join(["docker", *args])],
            capture_output=True,
            text=True,
        )
    if check and result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-image", required=True, help="installed sha256 image ID")
    parser.add_argument("--tag-prefix", required=True, help="new repository:version prefix")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.base_image):
        parser.error("use an exact base image ID")
    if not re.fullmatch(r"[a-z0-9][a-z0-9/_.-]*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,90}", args.tag_prefix):
        parser.error("invalid tag prefix")
    if args.output.exists():
        parser.error("output already exists")
    base = json.loads(docker("image", "inspect", args.base_image).stdout)[0]
    labels = base.get("Config", {}).get("Labels") or {}
    if (
        base["Id"] != args.base_image
        or base["Os"] != "linux"
        or base["Architecture"] != "amd64"
        or labels.get("io.browser-platform.browser-shutdown") != "1"
        or labels.get("io.browser-platform.session-auth") != "1"
    ):
        parser.error("base must be the installed reviewed Work shutdown/session-auth image")
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in SOURCES.items()}
    fingerprint = hashlib.sha256(
        json.dumps({"base": args.base_image, "files": hashes}, sort_keys=True).encode()
    ).hexdigest()
    tag = args.tag_prefix + "-" + fingerprint[:16]
    existing = docker("image", "inspect", tag, check=False)
    if existing.returncode == 0:
        details = json.loads(existing.stdout)[0]
        current = details.get("Config", {}).get("Labels") or {}
        if current.get("io.browser-platform.managed-firefox-network-input-sha256") != fingerprint:
            raise SystemExit("existing tag has different inputs; refusing to replace it")
    else:
        alias = "browser-platform/work-base:sha256-" + args.base_image[7:]
        prior = docker("image", "inspect", alias, check=False)
        if prior.returncode == 0 and json.loads(prior.stdout)[0]["Id"] != args.base_image:
            raise SystemExit("base alias points to a different image; refusing to replace it")
        if prior.returncode:
            docker("tag", args.base_image, alias)
        with tempfile.TemporaryDirectory(prefix="browser-platform-work-network-") as raw:
            context = Path(raw)
            for name, source in SOURCES.items():
                shutil.copyfile(source, context / name)
            docker(
                "build", "--pull=false", "--network=none",
                "--build-arg", "WORK_BASE=" + alias,
                "--build-arg", "WORK_BASE_ID=" + args.base_image,
                "--build-arg", "INPUT_SHA256=" + fingerprint,
                "-t", tag, str(context),
            )
    details = json.loads(docker("image", "inspect", tag).stdout)[0]
    base_layers = base["RootFS"]["Layers"]
    if details["RootFS"]["Layers"][: len(base_layers)] != base_layers:
        raise SystemExit("built image does not contain the pinned Work base layers")
    result = {
        "image": tag,
        "imageId": details["Id"],
        "baseImageId": args.base_image,
        "inputSHA256": fingerprint,
        "files": hashes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
