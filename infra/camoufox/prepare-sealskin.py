#!/usr/bin/env python3
"""Prepare a separate SealSkin app after the pinned image accepts its evidence."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from acceptance import docker
from environment import encode, expected_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--username", default="profile-adapter")
    parser.add_argument("--network", default="browser-platform-personal")
    parser.add_argument("--store", default="SealSkin Apps")
    parser.add_argument("--template", default="Default")
    parser.add_argument("--session-origin", required=True, help="trusted HTTPS origin of the SealSkin client")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"camoufox-[a-z0-9-]+", args.app_id):
        parser.error("use a separate camoufox-* application ID")
    if args.output.exists():
        parser.error("output already exists; refusing to replace a deployment definition")
    origin = urlsplit(args.session_origin)
    if (origin.scheme != "https" or not origin.hostname or origin.username is not None
            or origin.password is not None or origin.path not in ("", "/") or origin.query or origin.fragment):
        parser.error("session-origin must be an HTTPS origin without credentials, query or path")
    artifact_path, report_path = args.artifact.resolve(strict=True), args.acceptance.resolve(strict=True)
    artifact = json.loads(artifact_path.read_bytes())
    artifact_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()
    env = expected_environment(artifact, artifact_sha)
    env["BROWSER_PLATFORM_ACCEPTANCE_SHA256"] = report_sha
    env.update(SELKIES_ALLOWED_ORIGINS=args.session_origin.rstrip("/"), SELKIES_UI_TITLE="Camoufox", TITLE="Camoufox")
    image = artifact["runtimeImageDigest"]
    inspected = docker(["image", "inspect", image, "--format", "{{.Id}}"], timeout=15)
    if inspected.returncode or inspected.stdout.strip() != image:
        raise SystemExit("the exact artifact-bound image is not installed")
    inspected = docker(["network", "inspect", args.network, "--format", "{{.Internal}}"], timeout=15)
    if inspected.returncode or inspected.stdout.strip() != "true":
        raise SystemExit("the Worker network must be an existing Docker internal network")
    mounts = [
        {"Type": "bind", "Source": str(artifact_path), "Target": "/run/browser-platform/environment.json", "ReadOnly": True},
        {"Type": "bind", "Source": str(report_path), "Target": "/run/browser-platform/acceptance.json", "ReadOnly": True},
    ]
    command = ["run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges:true", "--user", f"{os.getuid()}:{os.getgid()}",
               "--entrypoint", "/opt/camoufox-python/bin/python"]
    for mount in mounts:
        command += ["--mount", f'type=bind,src={mount["Source"]},dst={mount["Target"]},readonly']
    for key, value in env.items():
        command += ["-e", key + "=" + value]
    command += [image, "/usr/local/lib/browser-platform/environment.py", "verify"]
    verified = docker(command, timeout=60)
    if verified.returncode or "ENVIRONMENT_ARTIFACT_OK" not in verified.stdout:
        raise SystemExit("image rejected the artifact or acceptance report: " + verified.stderr.strip())
    script = '#!/usr/bin/env bash\nset -euo pipefail\nexec /usr/local/bin/browser-platform-camoufox "${SEALSKIN_URL:-about:blank}"\n'
    wayland_script = '#!/usr/bin/env bash\necho "ENVIRONMENT_CONFIG_DRIFT: X11 is required" >&2\nexit 1\n'
    definition = {
        "id": args.app_id, "name": "Camoufox Personal (" + artifact["spec"]["id"] + ")",
        "logo": "", "url": "https://camoufox.com/", "provider": "docker",
        "source": args.store, "source_app_id": "firefox", "app_template": args.template,
        "users": [args.username], "groups": [], "home_directories": True, "auto_update": False,
        "is_meta_app": False,
        "provider_config": {
            "image": image, "port": 3000, "type": "browser", "url_support": True,
            "open_support": False, "extensions": [], "nvidia_support": False, "dri3_support": False,
            "autostart": True,
            "custom_autostart_script_b64": base64.b64encode(script.encode()).decode(),
            "custom_autostart_wayland_script_b64": base64.b64encode(wayland_script.encode()).decode(),
            "env": [{"name": key, "value": value} for key, value in sorted(env.items())],
            # The Docker provider shallow-merges these kwargs. Additional mounts
            # preserve the separate Home/shared-files volumes managed by SealSkin.
            "docker_overrides": {
                "network": args.network, "mounts": mounts, "mem_limit": "1536m",
                "nano_cpus": 1500000000, "pids_limit": 512, "shm_size": "256m",
                "security_opt": ["no-new-privileges:true"],
                "labels": {"browser-platform.application": args.app_id,
                           "browser-platform.environment": artifact["spec"]["id"]},
            },
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(encode(definition))
    print(json.dumps({"applicationId": args.app_id, "artifactSHA256": artifact_sha,
                      "acceptanceSHA256": report_sha, "definition": str(args.output)}))


if __name__ == "__main__":
    main()
