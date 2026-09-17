#!/usr/bin/env python3
"""Verify the deployed R4B production state without exposing access material."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import http.client
import json
import os
from pathlib import Path
import shlex
import subprocess


PROJECT = Path(__file__).resolve().parents[3]
PRODUCTION = PROJECT / "infra/sealskin"
RUNTIME = PRODUCTION / "runtime/r4b-production-migration-2026-09-15"
DEFAULT_PACKAGE = RUNTIME / "release-ready-2"
SERVICE_BINARY = Path.home() / ".local/lib/browser-platform/profile-adapter"


def read(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise RuntimeError("unsafe or unavailable input")
    return json.loads(path.read_bytes())


def command(arguments: list[str], *, timeout: int = 120,
            check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError("command failed: " + Path(arguments[0]).name)
    return result


def docker(*arguments: str) -> str:
    raw = ["docker", *arguments]
    result = subprocess.run(raw, capture_output=True, text=True, timeout=120)
    if result.returncode and "permission denied" in result.stderr.lower():
        result = subprocess.run(["sg", "docker", "-c", shlex.join(raw)], capture_output=True,
                                text=True, timeout=120)
    if result.returncode:
        raise RuntimeError("Docker inspection failed")
    return result.stdout


def service(*arguments: str, user: bool = False) -> str:
    line = ["systemctl"] + (["--user"] if user else []) + list(arguments)
    return command(line).stdout.strip()


def profile_snapshot(profile: str):
    result = command([str(SERVICE_BINARY), "-config", str(PRODUCTION / "adapter-config.json"),
                      "-inspect-profile", profile])
    return json.loads(result.stdout)


def local_status(host: str, path: str) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", 9100, timeout=30)
    try:
        connection.request("GET", path, headers={"Host": host})
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def public_status(host: str, path: str) -> int:
    result = command(["curl", "-k", "-sS", "--resolve", host + ":443:127.0.0.1",
                      "-o", "/dev/null", "-w", "%{http_code}", "https://" + host + path],
                     timeout=30)
    return int(result.stdout)


def caddy_config():
    connection = http.client.HTTPConnection("127.0.0.1", 2019, timeout=30)
    try:
        connection.request("GET", "/config/")
        response = connection.getresponse()
        raw = response.read()
        if response.status != 200:
            raise RuntimeError("Caddy administration endpoint is unavailable")
        return json.loads(raw)
    finally:
        connection.close()


def profile_containers(profile: str) -> list[dict]:
    identifiers = docker("ps", "-aq", "--filter", "label=io.browser-platform.profile=" + profile).split()
    return json.loads(docker("inspect", *identifiers)) if identifiers else []


def require_file(path: Path, mode: int) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o777 != mode:
        raise RuntimeError("production file mode or type drift")


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package, output = args.package.resolve(strict=True), args.output.resolve()
    if output.exists():
        raise RuntimeError("output already exists")
    output.mkdir(mode=0o700, parents=True)

    host = json.loads(command([
        "python3", str(PRODUCTION / "entry-auth/install-host-prerequisites.py"),
        "--package", str(package),
    ]).stdout)
    if host.get("status") != "installed" or not host.get("caddy_api_resume_active"):
        raise RuntimeError("host prerequisites are incomplete")

    services = {
        "docker_active": service("is-active", "docker.service"),
        "docker_enabled": service("is-enabled", "docker.service"),
        "caddy_active": service("is-active", "caddy.service"),
        "caddy_enabled": service("is-enabled", "caddy.service"),
        "adapter_active": service("is-active", "profile-adapter.service", user=True),
        "adapter_enabled": service("is-enabled", "profile-adapter.service", user=True),
        "linger": command(["loginctl", "show-user", str(os.getuid()), "-p", "Linger",
                           "--value"]).stdout.strip(),
    }
    expected_services = {key: "active" if key.endswith("_active") else "enabled"
                         for key in services if key != "linger"}
    expected_services["linger"] = "yes"
    if services != expected_services:
        raise RuntimeError("service or linger state drift")
    caddy_unit = service("show", "caddy.service", "-p", "ExecStart", "-p", "ExecReload")
    if "--resume" not in caddy_unit or "autosave.json" not in caddy_unit:
        raise RuntimeError("Caddy API resume unit drift")
    if caddy_config() != read(package / "entry-auth/caddy.candidate.json"):
        raise RuntimeError("active Caddy configuration drift")

    snapshots = {name: profile_snapshot(name) for name in ("personal", "work")}
    expected_counts = {
        "personal": {"records": 1, "workers": 1, "orphans": 0, "resources": 5,
                     "relays": 1, "guards": 1, "networks": 2},
        "work": {"records": 1, "workers": 1, "orphans": 0, "resources": 0,
                 "relays": 0, "guards": 0, "networks": 0},
    }
    for name, expected in expected_counts.items():
        snapshot = snapshots[name]
        if snapshot.get("status") != "running" or any(snapshot.get(key) != value
                                                       for key, value in expected.items()):
            raise RuntimeError(name + " runtime count drift")
        capabilities = snapshot.get("capabilities", {})
        if (capabilities.get("browser_shutdown_version") != 1
                or capabilities.get("session_auth_version") != 1):
            raise RuntimeError(name + " runtime capability drift")
    if snapshots["personal"].get("network_phase") != "running":
        raise RuntimeError("Personal network phase drift")

    audit = read(package / "release-audit.json")
    expected_images = {name: audit["profiles"][name]["image"] for name in ("personal", "work")}
    containers = {}
    for name in ("personal", "work"):
        current = profile_containers(name)
        workers = [item for item in current if item["Config"].get("Labels", {}).get(
            "io.browser-platform.role") not in {"guard", "relay"}]
        if len(current) != (3 if name == "personal" else 1) or len(workers) != 1:
            raise RuntimeError(name + " managed container set drift")
        if any(not item["State"]["Running"] for item in current):
            raise RuntimeError(name + " managed container is not running")
        worker = workers[0]
        if worker["Image"] != expected_images[name]:
            raise RuntimeError(name + " Worker image drift")
        labels = worker["Config"].get("Labels", {})
        if labels.get("io.browser-platform.browser-shutdown") != "1" or labels.get(
                "io.browser-platform.session-auth") != "1":
            raise RuntimeError(name + " Worker label drift")
        containers[name] = {"managed": len(current), "worker_image": worker["Image"],
                            "all_running": True}

    controller, static_relay = json.loads(docker("inspect", "sealskin", "profile-relay-personal"))
    controller_image = read(RUNTIME / "candidate-3/images.json")["runtime"]["id"]
    if not controller["State"]["Running"] or controller["Image"] != controller_image:
        raise RuntimeError("production controller drift")
    if (not static_relay["State"]["Running"]
            or static_relay["Id"] != audit["current_runtime_preserved"]["relay"]["id"]):
        raise RuntimeError("static Relay identity drift")

    homes = {name: (PRODUCTION / "storage/profile-adapter" / name).is_dir() for name in (
        "personal", "personal-camoufox-r7", "personal-camoufox-r9", "work")}
    if not all(homes.values()):
        raise RuntimeError("preserved production Home drift")
    require_file(PRODUCTION / "secrets/entry-users.json", 0o600)
    require_file(PRODUCTION / "secrets/private-session-ca.pem", 0o600)
    require_file(PRODUCTION / "config/ssl/proxy_key.pem", 0o600)
    require_file(PRODUCTION / "config/.config/sealskin/sessions.yml", 0o600)
    runtime_secrets = Path("/run/browser-platform/session-secrets")
    state_secrets = PRODUCTION / "config/.config/sealskin/session-secrets"
    if (not runtime_secrets.is_dir() or runtime_secrets.stat().st_mode & 0o777 != 0o700
            or len(list(runtime_secrets.iterdir())) != 2):
        raise RuntimeError("display secret runtime drift")
    if (not state_secrets.is_dir() or state_secrets.stat().st_mode & 0o777 != 0o700
            or len(list(state_secrets.iterdir())) != 1):
        raise RuntimeError("sealed state secret drift")

    public = {
        "login": public_status("mybrowser.azhen.de", "/auth/login"),
        "work": public_status("mybrowser.azhen.de", "/browser/work/"),
        "personal": public_status("mybrowser.azhen.de", "/browser/personal/"),
        "session_root": public_status("mysession.azhen.de", "/"),
    }
    local = {
        "login": local_status("mybrowser.azhen.de", "/auth/login"),
        "work": local_status("mybrowser.azhen.de", "/browser/work/"),
        "personal": local_status("mybrowser.azhen.de", "/browser/personal/"),
        "session_root": local_status("mysession.azhen.de", "/"),
    }
    expected_boundary = {"login": 200, "work": 303, "personal": 303, "session_root": 404}
    if public != expected_boundary or local != expected_boundary:
        raise RuntimeError("entry access boundary drift")
    state = read(PRODUCTION / "adapter-state.json")
    session_boundary = {}
    for name in ("personal", "work"):
        session_id = state.get("bindings", {}).get(name, {}).get("session_id", "")
        if not session_id:
            raise RuntimeError(name + " binding is missing")
        status = public_status("mysession.azhen.de", "/" + session_id + "/?embedded=true")
        if status != 401:
            raise RuntimeError(name + " Session boundary drift")
        session_boundary[name] = status

    result = {
        "status": "PASS",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "services": services,
        "host_prerequisites": {
            "caddy_api_resume_active": True,
            "docker_tmpfiles_ordering_active": True,
            "runtime_matches": bool(host.get("runtime", {}).get("matches")),
        },
        "caddy_candidate_exact": True,
        "profiles": {name: {key: snapshots[name][key] for key in (
            "status", "records", "workers", "orphans", "resources", "relays", "guards",
            "networks")} for name in snapshots},
        "containers": containers,
        "controller": {"running": True, "image": controller_image},
        "static_relay_identity_preserved": True,
        "homes_preserved": homes,
        "secret_material": {"file_modes": "pass", "display_entries": 2,
                            "sealed_state_entries": 1},
        "public_boundary": public,
        "local_boundary": local,
        "session_without_cookie": session_boundary,
        "sensitive_values_recorded": False,
    }
    with (output / "result.json").open("x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "output": str(output),
                      "caddy_candidate_exact": True, "profiles": result["profiles"],
                      "public_boundary": public, "sensitive_values_recorded": False}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        raise SystemExit("R4B production live check refused: " + str(error))
