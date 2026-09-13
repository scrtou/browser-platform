#!/usr/bin/env python3
"""Prepare a reproducible Docker payload from the pinned upstream Git commit."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

COMMIT = "2b13a42483c1dc7d367d5c340437bdc8ecd84bb4"
IMAGE = "lscr.io/linuxserver/sealskin:0.3.2-ls58@sha256:d52c155eb78882b27c7780e77df335939d46cd06a514c9fa310039307542ee6a"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    base_hashes = json.loads((package / "upstream-sha256.json").read_text())
    output = args.output.resolve()
    with tempfile.TemporaryDirectory(prefix="browser-platform-lifecycle-build-") as directory:
        work = Path(directory)
        archive = work / "source.tar"
        subprocess.run(["git", "-C", str(args.source), "archive", "--format=tar", "-o", str(archive), COMMIT, "server"], check=True)
        with tarfile.open(archive) as handle:
            for entry in handle:
                target = (work / entry.name).resolve()
                if not target.is_relative_to(work) or not (entry.isdir() or entry.isfile()):
                    raise SystemExit("Unexpected upstream archive entry.")
                if entry.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with handle.extractfile(entry) as source, target.open("wb") as destination:
                        shutil.copyfileobj(source, destination)
        for name, expected in base_hashes.items():
            if sha((work / "server/app" / name).read_bytes()) != expected:
                raise SystemExit(f"Upstream source mismatch: {name}")
        subprocess.run(["git", "apply", "--check", str(package / "profile-lifecycle.patch")], cwd=work, check=True)
        subprocess.run(["git", "apply", str(package / "profile-lifecycle.patch")], cwd=work, check=True)
        output.mkdir(parents=True, exist_ok=False)
        payload = output / "payload"
        files = {}
        for name in sorted([*base_hashes, "profile_runtime.py", "network_runtime.py", "network_probe.py"]):
            after = (work / "server/app" / name).read_bytes()
            target = payload / "app" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(after)
            before = None
            if name in base_hashes:
                before = subprocess.check_output(["git", "-C", str(args.source), "show", f"{COMMIT}:server/app/{name}"])
                original = payload / "original" / name
                original.parent.mkdir(parents=True, exist_ok=True)
                original.write_bytes(before)
            files[name] = {"before": sha(before) if before is not None else None, "after": sha(after)}
        release = "0.3.2-network-v2-" + sha(json.dumps(files, sort_keys=True).encode())[:16]
        manifest = {"release": release, "upstream_commit": COMMIT, "base_image": IMAGE,
                    "patch_sha256": sha((package / "profile-lifecycle.patch").read_bytes()), "files": files}
        (payload / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        shutil.copy2(package / "install.py", payload / "install.py")
        shutil.copytree(work / "server/tests", output / "tests")
        (output / "pytest.ini").write_text("[pytest]\nasyncio_mode = auto\n")
        (output / "Dockerfile").write_text(f"""FROM {IMAGE} AS runtime
COPY payload /opt/browser-platform/sealskin-lifecycle
RUN python3 /opt/browser-platform/sealskin-lifecycle/install.py
LABEL io.browser-platform.sealskin-lifecycle=\"{release}\"

FROM runtime AS checks
RUN apk add --no-cache build-base py3-pip
RUN python3 -m pip install --break-system-packages pytest==9.0.2 pytest-asyncio==1.3.0
COPY tests /checks/tests
COPY pytest.ini /checks/pytest.ini
""")
        (output / "release.json").write_text(json.dumps({"release": release, "image": "browser-platform/sealskin:" + release}, indent=2) + "\n")
        print(json.dumps({"release": release, "output": str(output), "files": len(files)}))


if __name__ == "__main__":
    main()
