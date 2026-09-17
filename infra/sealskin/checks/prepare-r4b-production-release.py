#!/usr/bin/env python3
"""Build the complete private R4B production package without changing production."""

from __future__ import annotations

import argparse
import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import sys


PROJECT = Path(__file__).resolve().parents[3]
DEFAULT_RUNTIME = PROJECT / "infra/sealskin/runtime/r4b-production-migration-2026-09-15"
PRODUCTION = PROJECT / "infra/sealskin"
ARTIFACT = PROJECT / "infra/camoufox/artifacts/env-tw-camoufox-r9.json"
ACCEPTANCE = PROJECT / "infra/camoufox/evidence/acceptance-r9-1-2026-09-15.json"
ADDON = PRODUCTION / "runtime/client-addons/native-clipboard-88dfb32aa9f275e1"
PERSONAL_APP = "camoufox-personal-r9-fill-r1"
PERSONAL_HOME = "personal-camoufox-r9"
PERSONAL_POLICY = "personal-camoufox-r9-socks5-r1"
CAPABILITIES = {"browser_shutdown_version": 1, "session_auth_version": 1}


def read(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise RuntimeError("unsafe or unavailable JSON input: " + str(path))
    return json.loads(path.read_bytes())


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path: Path, value) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with path.open("x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(payload)


def run(command: list[str], *, input_bytes: bytes | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    result = subprocess.run(command, input=input_bytes, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("release preparation command failed: " + command[0])
    return result


def docker(*arguments: str) -> str:
    command = ["docker", *arguments]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode and "permission denied" in result.stderr.lower():
        result = subprocess.run(["sg", "docker", "-c", shlex.join(command)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Docker inspection failed")
    return result.stdout


def inspect_image(identifier: str):
    values = json.loads(docker("image", "inspect", identifier))
    if len(values) != 1 or values[0]["Id"] != identifier:
        raise RuntimeError("image identity mismatch")
    return values[0]


def revision(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def container_identity(value):
    return {"id": value["Id"], "image": value["Image"], "started_at": value["State"]["StartedAt"],
            "pid": value["State"]["Pid"], "running": value["State"]["Running"]}


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime_root.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError("output already exists")
    output.mkdir(mode=0o700, parents=True)

    candidate = runtime / "candidate-4"
    controller = runtime / "candidate-3"
    work_release = runtime / "work-compatibility-1/release-candidate-1"
    config_path = PRODUCTION / "adapter-config.json"
    state_path = PRODUCTION / "adapter-state.json"
    policies_path = PRODUCTION / "config/.config/sealskin/profile-network-policies.json"
    caddy_path = Path("/etc/caddy/Caddyfile")
    source_paths = [config_path, state_path, policies_path, caddy_path,
                    PRODUCTION / "compose.yml", PRODUCTION / "compose.proxy.yml"]
    source_hashes = {str(path): sha(path) for path in source_paths}

    config, state, policies = read(config_path), read(state_path), read(policies_path)
    profiles = {value["id"]: value for value in config["profiles"]}
    bindings = state.get("bindings", {})
    personal, work = profiles["personal"], profiles["work"]
    if (personal["home_name"], personal["application_id"], personal["network_policy_id"]) != (
            "personal-camoufox-r7", "camoufox-personal-r7-guard", "personal-camoufox-r7-socks5-r1"):
        raise RuntimeError("production Personal definition drifted")
    if bindings.get("personal", {}).get("status") != "stopped":
        raise RuntimeError("Personal must remain stopped during package preparation")
    if bindings.get("work", {}).get("status") != "running":
        raise RuntimeError("Work running identity is unavailable")
    if any(bindings["personal"].get(key) != personal.get(key) for key in ("home_name", "application_id")):
        raise RuntimeError("Personal binding differs from its configuration")
    if any(bindings["work"].get(key) != work.get(key) for key in ("home_name", "application_id")):
        raise RuntimeError("Work binding differs from its configuration")

    storage = PRODUCTION / "storage/profile-adapter"
    if not (storage / personal["home_name"]).is_dir() or (storage / PERSONAL_HOME).exists():
        raise RuntimeError("Personal source Home must exist and the r9 Home must be absent")
    all_ids = docker("ps", "-aq").split()
    containers = json.loads(docker("inspect", *all_ids)) if all_ids else []
    if any(mount.get("Source") == str(storage / PERSONAL_HOME)
           for value in containers for mount in value.get("Mounts", [])):
        raise RuntimeError("the r9 Home is already mounted")
    work_containers = [value for value in containers
                       if value.get("Config", {}).get("Labels", {}).get("io.browser-platform.profile") == "work"]
    if len(work_containers) != 1 or not work_containers[0]["State"]["Running"]:
        raise RuntimeError("exactly one running Work generation is required")

    source_policy = copy.deepcopy(policies["policies"][personal["network_policy_id"]])
    if revision(source_policy) != personal["network_policy_sha256"]:
        raise RuntimeError("Personal source policy revision drifted")
    if PERSONAL_POLICY in policies["policies"]:
        raise RuntimeError("r9 production policy already exists")
    source_policy.update(home_name=PERSONAL_HOME, application_id=PERSONAL_APP)
    policy_sha = revision(source_policy)
    candidate_policies = copy.deepcopy(policies)
    candidate_policies["policies"][PERSONAL_POLICY] = source_policy
    write(output / "network-policies.candidate.json", candidate_policies)
    write(output / "network-policies.rollback.json", policies)

    app_command = [sys.executable, str(PROJECT / "infra/camoufox/prepare-sealskin.py"),
                   "--artifact", str(ARTIFACT), "--acceptance", str(ACCEPTANCE),
                   "--app-id", PERSONAL_APP, "--username", config["sealskin"]["username"],
                   "--store", "Production", "--network-policy-id", PERSONAL_POLICY,
                   "--network-policy-sha256", policy_sha, "--clipboard-addon", str(ADDON),
                   "--session-origin", config["sealskin"]["public_session_base_url"],
                   "--output", str(output / "application.personal.json")]
    prepared = run(app_command, timeout=180)
    (output / "application.personal.prepare.log").write_bytes(prepared.stdout + prepared.stderr)
    os.chmod(output / "application.personal.prepare.log", 0o600)
    personal_app = read(output / "application.personal.json")
    if personal_app["provider_config"]["network_policy_sha256"] != policy_sha:
        raise RuntimeError("Personal application policy binding mismatch")

    work_app = read(work_release / "application.work.json")
    work_source = read(work_release / "application.work.source.json")
    if work_app["id"] != work_source["id"] or work_app["id"] != "firefox-work":
        raise RuntimeError("Work application identity mismatch")
    shutil.copy2(work_release / "application.work.json", output / "application.work.json")
    shutil.copy2(work_release / "application.work.source.json", output / "application.work.source.json")
    os.chmod(output / "application.work.json", 0o600)
    os.chmod(output / "application.work.source.json", 0o600)

    r9_image = inspect_image(personal_app["provider_config"]["image"])
    work_image = inspect_image(work_app["provider_config"]["image"])
    for image in (r9_image, work_image):
        labels = image["Config"].get("Labels", {})
        if labels.get("io.browser-platform.browser-shutdown") != "1" or labels.get("io.browser-platform.session-auth") != "1":
            raise RuntimeError("release image lacks required runtime capabilities")

    # prepare-release owns Caddy/private TLS/tmpfiles generation. Its candidate
    # input uses candidate-4 binaries and the already accepted controller image.
    release_input = output / "release-input"
    (release_input / "bin").mkdir(mode=0o700, parents=True)
    shutil.copy2(controller / "images.json", release_input / "images.json")
    for name in ("profile-adapter", "profile-accounts"):
        shutil.copy2(candidate / "bin" / name, release_input / "bin" / name)
        os.chmod(release_input / "bin" / name, 0o700)
    release = run([sys.executable, str(PRODUCTION / "entry-auth/prepare-release.py"),
                   "--config", str(config_path), "--candidate", str(release_input),
                   "--system-caddy", str(caddy_path), "--output", str(output / "entry-auth")], timeout=180)
    (output / "entry-auth.prepare.log").write_bytes(release.stdout + release.stderr)
    os.chmod(output / "entry-auth.prepare.log", 0o600)

    candidate_config = read(output / "entry-auth/adapter.candidate.json")
    candidate_profiles = {value["id"]: value for value in candidate_config["profiles"]}
    candidate_profiles["personal"].update(home_name=PERSONAL_HOME, application_id=PERSONAL_APP,
        network_policy_id=PERSONAL_POLICY, network_policy_sha256=policy_sha,
        language="zh_TW.UTF-8", timezone="Asia/Taipei", wayland_mode=False,
        required_runtime_capabilities=CAPABILITIES)
    candidate_profiles["work"]["required_runtime_capabilities"] = CAPABILITIES
    write(output / "adapter.candidate.json", candidate_config)

    application_rollback = copy.deepcopy(candidate_config)
    rollback_profiles = {value["id"]: value for value in application_rollback["profiles"]}
    rollback_profiles["personal"] = copy.deepcopy(personal)
    rollback_profiles["personal"]["required_runtime_capabilities"] = CAPABILITIES
    # Work must keep the accepted image after the shared authenticated gateway
    # is enabled; a full old-stack rollback uses the maintenance backup instead.
    rollback_profiles["work"]["required_runtime_capabilities"] = CAPABILITIES
    application_rollback["profiles"] = [rollback_profiles[value["id"]] for value in application_rollback["profiles"]]
    write(output / "adapter.personal-rollback.json", application_rollback)
    write(output / "adapter.production-before.json", config)

    secrets_dir = output / "secrets"
    secrets_dir.mkdir(mode=0o700)
    account_config = copy.deepcopy(candidate_config)
    account_config["access"]["users_file"] = str(secrets_dir / "entry-users.json")
    write(output / "adapter.account-staging.json", account_config)
    password = secrets.token_urlsafe(32)
    account_result = run([str(candidate / "bin/profile-accounts"), "put", "--config",
                          str(output / "adapter.account-staging.json"), "--user", "owner",
                          "--profiles", "personal,work"], input_bytes=password.encode())
    (output / "account.prepare.log").write_bytes(account_result.stdout + account_result.stderr)
    os.chmod(output / "account.prepare.log", 0o600)
    run([str(candidate / "bin/profile-accounts"), "check", "--config",
         str(output / "adapter.account-staging.json")])
    write(output / "operator-access.txt", "生产入口：" + config["public_base_url"] +
          "/\n账号：owner\n密码：" + password + "\n")
    password = ""

    compose_result = run(["docker", "compose", "-f", str(PRODUCTION / "compose.yml"),
                          "-f", str(PRODUCTION / "compose.proxy.yml"),
                          "-f", str(output / "entry-auth/compose.entry-auth.yml"), "config"], timeout=120)
    (output / "compose-merged.private.yml").write_bytes(compose_result.stdout)
    os.chmod(output / "compose-merged.private.yml", 0o600)

    adapter_build = read(candidate / "adapter-build.json")
    for path, expected in {**adapter_build["sources"], **adapter_build["module_inputs"]}.items():
        if sha(PROJECT / path) != expected:
            raise RuntimeError("candidate-4 source drift: " + path)
    binary_hashes = {name: sha(candidate / "bin" / name) for name in ("profile-adapter", "profile-accounts")}
    if binary_hashes != {name: adapter_build["binaries"][name] for name in binary_hashes}:
        raise RuntimeError("candidate-4 binary drift")

    current_controller = json.loads(docker("inspect", "sealskin"))[0]
    current_relay = json.loads(docker("inspect", "profile-relay-personal"))[0]
    controller_images = read(controller / "images.json")
    if inspect_image(controller_images["runtime"]["id"])["Id"] != controller_images["runtime"]["id"]:
        raise RuntimeError("controller candidate is unavailable")
    backup_dir = runtime.parent / "r2c-production-home-maintenance-2026-09-15"
    backups = {name: {"size": (backup_dir / name).stat().st_size, "sha256": sha(backup_dir / name)}
               for name in ("personal.age", "work.age")}
    expected_backups = {"personal.age": "231c08a0d886d48d47fc264733234fc3956517d3dd2c481f2be6e57ff043c206",
                        "work.age": "c0488ecf99ddf02fe438d53667f6d6ff6d58a4ed6bc7d431ae3cecb3f03976e2"}
    if any(backups[name]["sha256"] != digest for name, digest in expected_backups.items()):
        raise RuntimeError("production Home backup drift")

    plan = {
        "schema": "browser-platform/r4b-maintenance-plan/v1",
        "preconditions": ["recheck every production input hash", "load the exact maintenance Caddy config",
                          "capture a fresh encrypted control/Home backup", "keep current journal authoritative"],
        "forward": ["stop Work through profile.Stop and verify all generation resources are absent",
                    "install tmpfiles and Docker ordering; create the session-secret tmpfs directory",
                    "install private TLS, staged account registry, candidate controller and Adapter",
                    "install Work candidate App and append the r9 Personal App/policy/config",
                    "start Work and Personal; verify image, Home, policy, display auth, proxy and health",
                    "test owner login and both fixed Profile URLs before loading the public Caddy config"],
        "rollback": ["keep both public hosts on the maintenance response",
                     "stop any candidate generations and verify Worker/Guard/Relay/network/display removal",
                     "for Personal-only failure use adapter.personal-rollback.json and the accepted r7 App",
                     "for shared-stack failure restore the maintenance-time encrypted control/config backup",
                     "restore matching old applications and start new old-image generations; never replace the live journal with a preparation snapshot"],
    }
    write(output / "maintenance-plan.json", plan)

    audit = {
        "status": "READY_FOR_MAINTENANCE",
        "ready_for_maintenance": True,
        "production_changes_performed": False,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": source_hashes,
        "profiles": {
            "personal": {"from_home": personal["home_name"], "to_home": PERSONAL_HOME,
                         "application": PERSONAL_APP, "policy": PERSONAL_POLICY,
                         "image": r9_image["Id"], "required_capabilities": CAPABILITIES},
            "work": {"home": work["home_name"], "application": work["application_id"],
                     "image": work_image["Id"], "required_capabilities": CAPABILITIES},
        },
        "target_mac": {"fill_r10_viewport": "pass", "click_mapping": "pass",
                       "r9_buttons_and_image_preview": "pass",
                       "fixed_resolution_narrow_view_distortion": "accepted tradeoff"},
        "accounts": {"staged": True, "users": ["owner"], "profiles": ["personal", "work"],
                     "plaintext_only_in_private_operator_file": True},
        "host_configuration": {"tmpfiles_staged": True, "docker_ordering_staged": True,
                               "caddy_api_resume_staged": True, "compose_merged": True,
                               "private_tls_staged": True},
        "backups": backups,
        "current_runtime_preserved": {"controller": container_identity(current_controller),
                                      "relay": container_identity(current_relay),
                                      "work": container_identity(work_containers[0]),
                                      "personal_status": "stopped"},
        "qa_cleanup": read(runtime / "window-r10/stage-1/cleanup-final.json"),
        "resolved_blockers": ["WORK_NEXT_LAUNCH_IMAGE_UNSUPPORTED", "TARGET_MAC_MATRIX_PENDING",
                              "PRODUCTION_ACCOUNTS_NOT_PROVISIONED_IN_PACKAGE",
                              "R9_PRODUCTION_CONFIGURATION_PACKAGE_PENDING"],
        "remaining_release_gates": ["MAINTENANCE_INSTALL_AND_PRODUCTION_ACCEPTANCE",
                                    "R2_LOGOUT_DOCKER_AND_VPS_RESTART_VERIFICATION"],
    }
    if source_hashes != {str(path): sha(path) for path in source_paths}:
        raise RuntimeError("production inputs changed during preparation")
    fresh = json.loads(docker("inspect", current_controller["Id"], current_relay["Id"], work_containers[0]["Id"]))
    if [container_identity(value) for value in fresh] != [container_identity(value) for value in
            (current_controller, current_relay, work_containers[0])]:
        raise RuntimeError("production runtime identity changed during preparation")
    write(output / "release-audit.json", audit)
    files = {str(path.relative_to(output)): sha(path) for path in sorted(output.rglob("*")) if path.is_file()}
    write(output / "manifest.json", {"status": audit["status"], "ready_for_maintenance": True,
          "production_changes_performed": False, "files": files})
    print(json.dumps({"status": audit["status"], "output": str(output),
                      "production_changes_performed": False, "files": len(files)}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        raise SystemExit("R4B release preparation refused: " + str(error))
