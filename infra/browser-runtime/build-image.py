#!/usr/bin/env python3
"""Add the reviewed shutdown layer without overwriting a Worker version."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parent
FILES = (".dockerignore", "Dockerfile", "browser-shutdown.py", "wayland_shutdown.py", "before-desktop-stop", "install.py")


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if result.returncode and "permission denied" in result.stderr.lower():
        result = subprocess.run(["sg", "docker", "-c", shlex.join(["docker", *args])], capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-image", required=True, help="installed sha256 image ID")
    parser.add_argument("--tag-prefix", required=True, help="new repository:version prefix")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.base_image):
        parser.error("use an exact base image ID")
    if not re.fullmatch(r"[a-z0-9][a-z0-9/_.-]*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,90}", args.tag_prefix):
        parser.error("invalid tag prefix")
    if args.output.exists():
        parser.error("output already exists")
    base = json.loads(docker("image", "inspect", args.base_image).stdout)[0]
    if base["Id"] != args.base_image or base["Os"] != "linux" or base["Architecture"] != "amd64":
        parser.error("the reviewed base must be an installed Linux amd64 image")
    file_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}
    fingerprint = hashlib.sha256(json.dumps({"base": args.base_image, "files": file_hashes}, sort_keys=True).encode()).hexdigest()
    tag = args.tag_prefix + "-" + fingerprint[:16]
    existing = docker("image", "inspect", tag, check=False)
    if existing.returncode == 0:
        details = json.loads(existing.stdout)[0]
        labels = details["Config"].get("Labels") or {}
        if labels.get("io.browser-platform.shutdown-input-sha256") != fingerprint:
            raise SystemExit("existing tag has different or unknown inputs; refusing to replace it")
    else:
        # BuildKit treats a bare sha256 ID in FROM as a registry tag. Pin a
        # local alias and verify both its identity and the resulting layer prefix.
        alias = "browser-platform/worker-base:sha256-" + args.base_image[7:]
        prior = docker("image", "inspect", alias, check=False)
        if prior.returncode == 0 and json.loads(prior.stdout)[0]["Id"] != args.base_image:
            raise SystemExit("base alias points to a different image; refusing to replace it")
        if prior.returncode:
            docker("tag", args.base_image, alias)
        docker("build", "--pull=false", "--network=none", "--build-arg", "WORKER_BASE=" + alias,
               "--build-arg", "WORKER_BASE_ID=" + args.base_image,
               "--build-arg", "INPUT_SHA256=" + fingerprint, "-t", tag, str(ROOT))
    details = json.loads(docker("image", "inspect", tag).stdout)[0]
    layers = base["RootFS"]["Layers"]
    if details["RootFS"]["Layers"][:len(layers)] != layers:
        raise SystemExit("built image does not contain the pinned base layers")
    result = {"image": tag, "imageId": details["Id"], "baseImageId": args.base_image,
              "inputSHA256": fingerprint, "files": file_hashes}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
