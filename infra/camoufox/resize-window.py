#!/usr/bin/env python3
"""Create a new frozen window revision without regenerating the device.

The original BrowserForge result remains provenance. Only the explicit native
window overrides change; the candidate still needs full acceptance before use.
"""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from acceptance import docker
from environment import decode, encode, publish, validate_spec


def resize(artifact, environment_id, revision, width, height):
    spec = artifact["spec"]
    validate_spec(spec)
    if environment_id == spec["id"] or type(revision) is not int or revision <= spec["revision"]:
        raise ValueError("use a new environment ID and a higher revision")
    if any(key in artifact["resolvedConfig"] for key in ("window.innerWidth", "window.innerHeight")):
        raise ValueError("an artifact with fixed inner dimensions needs a separate reviewed revision")
    candidate = copy.deepcopy(artifact)
    candidate["spec"].update(id=environment_id, revision=revision, window={"width": width, "height": height})
    validate_spec(candidate["spec"])
    candidate.update(id=environment_id + "-artifact-1", createdAt=datetime.now(timezone.utc).isoformat())
    candidate["resolvedConfig"].update({
        "window.outerWidth": width, "window.outerHeight": height,
        "window.screenX": (spec["screen"]["width"] - width) // 2,
        "window.screenY": (spec["screen"]["height"] - height) // 2,
    })
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("output already exists")
    source = args.artifact.resolve(strict=True)
    if not source.is_file() or source.stat().st_size > 2 * 1024 * 1024:
        parser.error("source must be a bounded regular artifact")
    raw = source.read_bytes()
    original = decode(raw)
    candidate = resize(original, args.id, args.revision, args.width, args.height)
    image = original["runtimeImageDigest"]
    inspected = docker(["image", "inspect", image], timeout=15)
    if inspected.returncode or json.loads(inspected.stdout)[0]["Id"] != image:
        parser.error("the exact artifact-bound image must be installed")
    candidate_raw = encode(candidate)
    candidate_sha = hashlib.sha256(candidate_raw).hexdigest()
    source_sha = hashlib.sha256(raw).hexdigest()
    with tempfile.TemporaryDirectory(prefix="camoufox-window-") as temporary:
        directory = Path(temporary)
        (directory / "source.json").write_bytes(raw)
        (directory / "candidate.json").write_bytes(candidate_raw)
        result = docker(["run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--user", f"{os.getuid()}:{os.getgid()}",
            "--mount", f"type=bind,src={directory},dst=/revision,readonly",
            "--entrypoint", "/opt/camoufox-python/bin/python", image, "-c",
            "import sys;sys.path.insert(0,'/usr/local/lib/browser-platform');import environment;"
            "environment.load_artifact('/revision/source.json',sys.argv[1],check_environment=False);"
            "environment.load_artifact('/revision/candidate.json',sys.argv[2],check_environment=False);"
            "print('WINDOW_CANDIDATE_VALIDATED')", source_sha, candidate_sha], timeout=90)
        if result.returncode or result.stdout.strip() != "WINDOW_CANDIDATE_VALIDATED":
            raise ValueError("the artifact-bound image rejected the window revision")
    if source.read_bytes() != raw:
        raise ValueError("source artifact changed during preparation")
    digest = publish(args.output, candidate)
    print(json.dumps({"status": "candidate", "artifact": str(args.output), "sha256": digest,
        "sourceSHA256": source_sha, "image": image, "requiresFullAcceptance": True,
        "originalFingerprintSeedsPreferencesPreserved": True, "window": candidate["spec"]["window"]}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit("Window revision refused: " + str(error))
