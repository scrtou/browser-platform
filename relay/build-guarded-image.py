#!/usr/bin/env python3
"""Build and retain a content-versioned image for managed network namespaces."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default="go", help="Go compiler executable")
    parser.add_argument("--output", type=Path, help="Write the image reference manifest")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    build = root / "build"
    build.mkdir(exist_ok=True)
    environment = {**os.environ, "CGO_ENABLED": "0", "GOOS": "linux", "GOTOOLCHAIN": "local"}
    subprocess.run(
        [args.go, "build", "-buildvcs=false", "-trimpath", "-o", str(build / "profile-relay"), "./cmd/profile-relay"],
        cwd=root, env=environment, check=True,
    )
    inputs = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ("Dockerfile.guarded", "network-guard.py", "build/profile-relay", ".dockerignore")
    }
    revision = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    image = "browser-platform/profile-relay:guard-v1-" + revision[:16]
    inspect = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True)
    if inspect.returncode == 0:
        details = json.loads(inspect.stdout)[0]
        if details["Config"].get("Labels", {}).get("io.browser-platform.network-guard-inputs") != revision:
            raise SystemExit("Existing version tag has different or unproven inputs; it was not overwritten.")
    else:
        subprocess.run(
            ["docker", "build", "--pull=false", "--file", str(root / "Dockerfile.guarded"),
             "--label", "io.browser-platform.network-guard-inputs=" + revision, "--tag", image, str(root)],
            check=True,
        )
        details = json.loads(run("docker", "image", "inspect", image))[0]
    manifest = {"image": image, "image_id": details["Id"], "inputs_sha256": inputs,
                "inputs_revision": revision, "go_version": run(args.go, "version").strip()}
    output = args.output or build / "guard-image.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print(json.dumps({"image": image, "image_id": details["Id"], "manifest": str(output)}))


if __name__ == "__main__":
    main()
