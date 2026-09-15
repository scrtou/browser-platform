#!/usr/bin/env python3
"""Build an immutable access layer on an installed, exact Worker image."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("worker_build", ROOT.parent / "browser-runtime/build-image.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
docker = helper.docker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--tag-prefix", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.base_image) or args.output.exists():
        parser.error("use an exact installed image and a new output")
    if not re.fullmatch(r"[a-z0-9][a-z0-9/_.-]*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,90}", args.tag_prefix):
        parser.error("invalid tag prefix")
    base = json.loads(docker("image", "inspect", args.base_image).stdout)[0]
    if (base["Os"] != "linux" or base["Architecture"] != "amd64"
            or (base["Config"].get("Labels") or {}).get("io.browser-platform.browser-shutdown") != "1"):
        parser.error("reviewed Linux amd64 Worker with normal browser shutdown required")
    files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
             for name in (".dockerignore", "Dockerfile", "session_access.py", "install.py", "build-image.py")}
    fingerprint = hashlib.sha256(json.dumps({"base": args.base_image, "files": files}, sort_keys=True).encode()).hexdigest()
    tag = args.tag_prefix + "-" + fingerprint[:16]
    prior = docker("image", "inspect", tag, check=False)
    if prior.returncode == 0:
        if (json.loads(prior.stdout)[0]["Config"].get("Labels") or {}).get("io.browser-platform.session-auth-input-sha256") != fingerprint:
            raise SystemExit("existing tag has different inputs")
    else:
        alias = "browser-platform/worker-base:sha256-" + args.base_image[7:]
        existing = docker("image", "inspect", alias, check=False)
        if existing.returncode == 0 and json.loads(existing.stdout)[0]["Id"] != args.base_image:
            raise SystemExit("base alias mismatch")
        if existing.returncode:
            docker("tag", args.base_image, alias)
        docker("build", "--pull=false", "--network=none", "--build-arg", "WORKER_BASE=" + alias,
               "--build-arg", "WORKER_BASE_ID=" + args.base_image, "--build-arg", "INPUT_SHA256=" + fingerprint,
               "-t", tag, str(ROOT))
    image = json.loads(docker("image", "inspect", tag).stdout)[0]
    layers = base["RootFS"]["Layers"]
    if image["RootFS"]["Layers"][:len(layers)] != layers:
        raise SystemExit("Worker base layers changed")
    result = {"image": tag, "imageId": image["Id"], "baseImageId": args.base_image,
              "inputSHA256": fingerprint, "files": files}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
