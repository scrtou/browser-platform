#!/usr/bin/env python3
"""Bind unchanged frozen browser settings to a reviewed descendant Worker.

This creates a candidate revision. It does not create or reuse an acceptance
report, generate a fingerprint, or modify an existing artifact/application.
"""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from acceptance import docker
from environment import encode


def inspect(image):
    result = docker(["image", "inspect", image], timeout=15)
    if result.returncode:
        raise SystemExit("the exact image must be installed")
    value = json.loads(result.stdout)[0]
    if value["Id"] != image:
        raise SystemExit("an exact image ID is required")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("output already exists")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image):
        parser.error("image must be a full sha256 image ID")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", args.id):
        parser.error("invalid environment ID")
    old = json.loads(args.artifact.read_bytes())
    if args.id == old["spec"]["id"] or args.revision <= old["spec"]["revision"]:
        parser.error("use a new environment ID and a higher revision")
    base, image = inspect(old["runtimeImageDigest"]), inspect(args.image)
    labels = image["Config"].get("Labels") or {}
    layers = base["RootFS"]["Layers"]
    if (labels.get("io.browser-platform.browser-shutdown") != "1"
            or labels.get("io.browser-platform.worker-base") != base["Id"]
            or image["RootFS"]["Layers"][:len(layers)] != layers):
        parser.error("new image must be a reviewed Worker layer over this artifact's exact image")
    if labels.get("io.browser-platform.session-auth") and (
            labels.get("io.browser-platform.session-auth") != "1"
            or not re.fullmatch(r"[a-f0-9]{64}", labels.get("io.browser-platform.session-auth-input-sha256", ""))):
        parser.error("unsupported Worker access layer")
    candidate = copy.deepcopy(old)
    candidate.update(id=args.id + "-artifact-1", createdAt=datetime.now(timezone.utc).isoformat(),
                     runtimeImageDigest=args.image)
    candidate["spec"].update(id=args.id, revision=args.revision)
    raw = encode(candidate)
    digest = hashlib.sha256(raw).hexdigest()
    with tempfile.TemporaryDirectory(prefix="camoufox-rebind-") as temporary:
        path = Path(temporary) / "candidate.json"
        path.write_bytes(raw)
        verified = docker(["run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--user", f"{os.getuid()}:{os.getgid()}",
            "--mount", f"type=bind,src={path},dst=/candidate.json,readonly",
            "--entrypoint", "/opt/camoufox-python/bin/python", args.image, "-c",
            "import sys;sys.path.insert(0,'/usr/local/lib/browser-platform');import environment;"
            "environment.load_artifact('/candidate.json',sys.argv[1],check_environment=False);"
            "print('CANDIDATE_VALIDATED')", digest], timeout=60)
        if verified.returncode or verified.stdout.strip() != "CANDIDATE_VALIDATED":
            raise SystemExit("new image rejected the unchanged frozen browser configuration")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(raw)
    print(json.dumps({"status": "candidate", "artifact": str(args.output), "sha256": digest,
                      "image": args.image, "requiresFullAcceptance": True,
                      "fingerprintConfigSeedsPreferencesPreserved": True}))


if __name__ == "__main__":
    main()
