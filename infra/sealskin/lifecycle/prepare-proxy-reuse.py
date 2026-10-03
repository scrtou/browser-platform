#!/usr/bin/env python3
"""Prepare the R6W two-file controller delta against the exact R6J1 image.

Builds no images and changes no running resources. Uses the pinned upstream
archive and versioned patches; excludes unreleased dynamic-upstream changes.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import tarfile
import tempfile

BASE = "sha256:ad21dd6de070fce88e59a6c32fd213c017fcb587dffd3cac907693cb7b3b6525"
BASE_TAG = "browser-platform/sealskin:r6j1-log-only-20261001"
COMMIT = "2b13a42483c1dc7d367d5c340437bdc8ecd84bb4"
FILES = ("secret_store.py", "environment_management.py")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    actual = subprocess.check_output(["docker", "image", "inspect", BASE_TAG, "--format", "{{.Id}}"], text=True).strip()
    if actual != BASE:
        raise SystemExit("BASE_TAG_MISMATCH")
    args.output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="proxy-reuse-source-") as temporary:
        work = Path(temporary)
        archive = subprocess.check_output(["git", "-C", str(args.source), "archive", COMMIT, "server"])
        (work / "source.tar").write_bytes(archive)
        with tarfile.open(work / "source.tar") as handle:
            for entry in handle:
                target = (work / entry.name).resolve()
                if not target.is_relative_to(work) or not (entry.isdir() or entry.isfile()):
                    raise SystemExit("Unexpected upstream archive entry")
                if entry.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with handle.extractfile(entry) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
        patches = ("profile-lifecycle.patch", "environment-management.patch", "proxy-create-authorization.patch")
        before = {}
        for name in patches:
            if name == patches[-1]:
                for file in FILES:
                    before[file] = digest((work / "server/app" / file).read_bytes())
                    code = "import hashlib; print(hashlib.sha256(open('/usr/lib/python3.14/site-packages/app/" + file + "','rb').read()).hexdigest())"
                    actual = subprocess.check_output(["docker", "run", "--rm", "--network", "none", "--entrypoint", "python3", BASE, "-c", code], text=True).strip()
                    if actual != before[file]:
                        raise SystemExit("BASE_SOURCE_MISMATCH: " + file)
            subprocess.run(["git", "apply", "--check", str(package / name)], cwd=work, check=True)
            subprocess.run(["git", "apply", str(package / name)], cwd=work, check=True)
        payload = args.output / "payload"
        payload.mkdir()
        files = {}
        for name in FILES:
            raw = (work / "server/app" / name).read_bytes()
            (payload / name).write_bytes(raw)
            files[name] = {"before": before[name], "after": digest(raw)}
        (args.output / "Dockerfile").write_text("FROM " + BASE_TAG + "\nCOPY --chmod=644 payload/*.py /usr/lib/python3.14/site-packages/app/\nLABEL io.browser-platform.proxy-create-authorization=\"1\"\n")
        manifest = {"base_image": BASE, "upstream_commit": COMMIT, "files": files,
                    "patches": {name: digest((package / name).read_bytes()) for name in patches}}
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Prepared exact two-file controller delta; no running resources changed")


if __name__ == "__main__":
    main()
