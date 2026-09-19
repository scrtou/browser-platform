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


def network_binding(network, policy_id, policy_sha256):
    """Choose exactly one topology; managed resources remain owned by SealSkin."""
    if policy_id or policy_sha256:
        if (network or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", policy_id or "")
                or not re.fullmatch(r"[a-f0-9]{64}", policy_sha256 or "")
                or policy_sha256 == "0" * 64):
            raise ValueError("managed networking requires a policy ID and SHA-256, without --network")
        return {}, {"network_policy_id": policy_id, "network_policy_sha256": policy_sha256}
    network = network or "browser-platform-personal"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", network):
        raise ValueError("invalid static network name")
    return {"network": network}, {}


def clipboard_mounts(directory):
    """Accept only the versioned clipboard code in this checkout, mounted read-only."""
    if directory is None:
        return [], {}
    if directory.is_symlink():
        raise ValueError("clipboard addon directory must not be a symlink")
    directory = directory.resolve(strict=True)
    source = Path(__file__).resolve().parents[1] / "sealskin"
    names = ("enable-screenshot-paste.py", "screenshot-paste.js", "screenshot-paste-init.sh")
    hashes = {}
    for name in names:
        path = directory / name
        if (path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o022
                or path.read_bytes() != (source / name).read_bytes()):
            raise ValueError("clipboard addon must contain the unmodified versioned scripts")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if directory.stat().st_mode & 0o022:
        raise ValueError("clipboard addon directory must not be writable by other users")
    return [
        {"Type": "bind", "Source": str(directory), "Target": "/opt/browser-platform/selkies-paste", "ReadOnly": True},
        {"Type": "bind", "Source": str(directory / names[2]), "Target": "/custom-cont-init.d/95-browser-platform-paste", "ReadOnly": True},
    ], hashes


def verify_in_image(image, mounts, env):
    """Ask the exact bound image to accept the artifact and report before use."""
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


def build_definition(*, app_id, artifact_path, report_path, artifact, env, image, username, store, template,
                     network_overrides, policy_reference, addon_mounts, verify):
    """Assemble the SealSkin application definition for one accepted artifact.

    The same shape serves a directly installed app and the R6 catalog template;
    the template leaves the policy reference and final ID to the Adapter.
    """
    mounts = [
        {"Type": "bind", "Source": str(artifact_path), "Target": "/run/browser-platform/environment.json", "ReadOnly": True},
        {"Type": "bind", "Source": str(report_path), "Target": "/run/browser-platform/acceptance.json", "ReadOnly": True},
    ]
    if verify:
        verify_in_image(image, mounts, env)
    mounts += addon_mounts
    script = '#!/usr/bin/env bash\nset -euo pipefail\nexec /usr/local/bin/browser-platform-camoufox "${SEALSKIN_URL:-about:blank}"\n'
    wayland_script = '#!/usr/bin/env bash\necho "ENVIRONMENT_CONFIG_DRIFT: X11 is required" >&2\nexit 1\n'
    return {
        "id": app_id, "name": "Camoufox Personal (" + artifact["spec"]["id"] + ")",
        "logo": "", "url": "https://camoufox.com/", "provider": "docker",
        "source": store, "source_app_id": "firefox", "app_template": template,
        "users": [username], "groups": [], "home_directories": True, "auto_update": False,
        "is_meta_app": False,
        "provider_config": {
            **policy_reference,
            "image": image, "port": 3000, "type": "browser", "url_support": True,
            "open_support": False, "extensions": [], "nvidia_support": False, "dri3_support": False,
            "autostart": True,
            "custom_autostart_script_b64": base64.b64encode(script.encode()).decode(),
            "custom_autostart_wayland_script_b64": base64.b64encode(wayland_script.encode()).decode(),
            "env": [{"name": key, "value": value} for key, value in sorted(env.items())],
            # The Docker provider shallow-merges these kwargs. Additional mounts
            # preserve the separate Home/shared-files volumes managed by SealSkin.
            "docker_overrides": {
                **network_overrides, "mounts": mounts, "mem_limit": "1536m",
                "nano_cpus": 1500000000, "pids_limit": 512, "shm_size": "256m",
                "security_opt": ["no-new-privileges:true"],
                "labels": {"browser-platform.application": app_id,
                           "browser-platform.environment": artifact["spec"]["id"]},
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--username", default="profile-adapter")
    topology = parser.add_mutually_exclusive_group()
    topology.add_argument("--network", help="legacy static internal network (default: browser-platform-personal)")
    topology.add_argument("--network-policy-id", help="operator-approved generation policy; no static network override")
    parser.add_argument("--network-policy-sha256", help="SHA-256 of the policy with all server defaults resolved")
    parser.add_argument("--clipboard-addon", type=Path, help="immutable directory containing the versioned native clipboard scripts")
    parser.add_argument("--store", default="SealSkin Apps")
    parser.add_argument("--template", default="Default")
    parser.add_argument("--session-origin", required=True, help="trusted HTTPS origin of the SealSkin client")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        network_overrides, policy_reference = network_binding(args.network, args.network_policy_id, args.network_policy_sha256)
        addon_mounts, addon_hashes = clipboard_mounts(args.clipboard_addon)
    except (ValueError, OSError) as error:
        parser.error(str(error))
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
    if addon_mounts:
        env.update(SELKIES_UI_SIDEBAR_SHOW_FILES="true", SELKIES_FILE_TRANSFERS="upload")
    image = artifact["runtimeImageDigest"]
    inspected = docker(["image", "inspect", image, "--format", "{{.Id}}"], timeout=15)
    if inspected.returncode or inspected.stdout.strip() != image:
        raise SystemExit("the exact artifact-bound image is not installed")
    if network_overrides:
        inspected = docker(["network", "inspect", network_overrides["network"], "--format", "{{.Internal}}"], timeout=15)
        if inspected.returncode or inspected.stdout.strip() != "true":
            raise SystemExit("the Worker network must be an existing Docker internal network")
    definition = build_definition(
        app_id=args.app_id, artifact_path=artifact_path, report_path=report_path, artifact=artifact,
        env=env, image=image, username=args.username, store=args.store, template=args.template,
        network_overrides=network_overrides, policy_reference=policy_reference, addon_mounts=addon_mounts,
        verify=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(encode(definition))
    print(json.dumps({"applicationId": args.app_id, "artifactSHA256": artifact_sha,
                      "acceptanceSHA256": report_sha, "definition": str(args.output),
                      "networkMode": "managed" if policy_reference else "static", "clipboardFiles": addon_hashes}))


if __name__ == "__main__":
    main()
