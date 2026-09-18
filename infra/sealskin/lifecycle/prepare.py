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
import urllib.request

COMMIT = "2b13a42483c1dc7d367d5c340437bdc8ecd84bb4"
IMAGE = "lscr.io/linuxserver/sealskin:0.3.2-ls58@sha256:d52c155eb78882b27c7780e77df335939d46cd06a514c9fa310039307542ee6a"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dependency-directory", type=Path,
                        help="Use pre-downloaded locked wheels for an offline preparation")
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    base_hashes = json.loads((package / "upstream-sha256.json").read_text())
    dependencies = json.loads((package / "python-dependencies.json").read_text())
    if dependencies["version"] != 1:
        raise SystemExit("Unsupported dependency lock version.")
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
        patches = ("profile-lifecycle.patch", "environment-management.patch")
        for patch_name in patches:
            subprocess.run(["git", "apply", "--check", str(package / patch_name)], cwd=work, check=True)
            subprocess.run(["git", "apply", str(package / patch_name)], cwd=work, check=True)
        output.mkdir(parents=True, exist_ok=False)
        payload = output / "payload"
        files = {}
        for name in sorted([*base_hashes, "profile_runtime.py", "profile_health.py", "profile_resume.py", "launch_journal.py", "network_runtime.py", "network_probe.py", "network_direct.py", "network_dns.py", "secret_store.py", "secret_runtime.py",
                            "coherence_policy.py", "coherence_geoip.py", "coherence_report.py", "coherence_runtime.py", "coherence_exec.py", "browser_observe.py",
                            "session_secrets.py", "session_runtime.py", "safe_output.py", "environment_management.py", "proxy_probe.py"]):
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
        release = "0.3.2-entry-auth-v1-" + sha(json.dumps({"files": files, "dependencies": dependencies}, sort_keys=True).encode())[:16]
        build_inputs = {name: sha((package / name).read_bytes()) for name in
                        ("prepare.py", "install.py", "python-dependencies.json", "upstream-sha256.json", *patches)}
        packaging_sha = sha(json.dumps(build_inputs, sort_keys=True).encode())
        manifest = {"release": release, "upstream_commit": COMMIT, "base_image": IMAGE,
                    "patch_sha256": build_inputs["profile-lifecycle.patch"],
                    "patches": {name: build_inputs[name] for name in patches}, "files": files,
                    "python_dependencies": dependencies["runtime"], "build_inputs": build_inputs,
                    "packaging_sha256": packaging_sha}
        (payload / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        shutil.copy2(package / "install.py", payload / "install.py")
        wheels = output / "dependencies"
        wheels.mkdir()
        requirements = []
        for dependency in [*dependencies["runtime"], *dependencies["build"]]:
            name = dependency["wheel"]
            if Path(name).name != name or not name.endswith(".whl"):
                raise SystemExit("Invalid locked wheel name.")
            if args.dependency_directory:
                data = (args.dependency_directory / name).read_bytes()
            else:
                if not dependency["url"].startswith("https://files.pythonhosted.org/"):
                    raise SystemExit("Unexpected wheel origin.")
                with urllib.request.urlopen(dependency["url"], timeout=30) as response:
                    data = response.read(10 * 1024 * 1024 + 1)
            if len(data) > 10 * 1024 * 1024 or sha(data) != dependency["sha256"]:
                raise SystemExit("Locked wheel hash mismatch.")
            (wheels / name).write_bytes(data)
            if dependency in dependencies["runtime"]:
                requirements.append(f"{dependency['name']}=={dependency['version']} --hash=sha256:{dependency['sha256']}")
        (wheels / "requirements.txt").write_text("\n".join(requirements) + "\n")
        shutil.copytree(work / "server/tests", output / "tests")
        (output / "pytest.ini").write_text("[pytest]\nasyncio_mode = auto\n")
        pip_wheel = next(value["wheel"] for value in dependencies["build"] if value["name"] == "pip")
        (output / "Dockerfile").write_text(f"""FROM {IMAGE} AS runtime
COPY dependencies /opt/browser-platform/python-dependencies
RUN PYTHONPATH=/opt/browser-platform/python-dependencies/{pip_wheel} python3 -m pip install --break-system-packages --no-index --no-deps --require-hashes \\
    --find-links=/opt/browser-platform/python-dependencies -r /opt/browser-platform/python-dependencies/requirements.txt
COPY payload /opt/browser-platform/sealskin-lifecycle
RUN python3 /opt/browser-platform/sealskin-lifecycle/install.py
LABEL io.browser-platform.sealskin-lifecycle=\"{release}\"

FROM runtime AS testbase
RUN apk add --no-cache build-base
RUN PYTHONPATH=/opt/browser-platform/python-dependencies/{pip_wheel} python3 -m pip install --break-system-packages pytest==9.0.2 pytest-asyncio==1.3.0

FROM testbase AS checks
COPY tests /checks/tests
COPY pytest.ini /checks/pytest.ini
""")
        # The payload release identifies installed application bytes. Include
        # all packaging inputs so dependency/installer/test-only changes cannot
        # silently overwrite an older retained image tag.
        image = "browser-platform/sealskin:" + release + "-pkg-" + packaging_sha[:12]
        (output / "release.json").write_text(json.dumps({"release": release, "image": image,
                                                       "packaging_sha256": packaging_sha}, indent=2) + "\n")
        print(json.dumps({"release": release, "output": str(output), "files": len(files)}))


if __name__ == "__main__":
    main()
