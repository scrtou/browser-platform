#!/usr/bin/env python3
"""Execute the reviewed R4B production migration with a private phase journal."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import html
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlencode, urlsplit


PROJECT = Path(__file__).resolve().parents[3]
PRODUCTION = PROJECT / "infra/sealskin"
RUNTIME = PRODUCTION / "runtime/r4b-production-migration-2026-09-15"
SERVICE_BINARY = Path.home() / ".local/lib/browser-platform/profile-adapter"
CANDIDATE_BINARY = RUNTIME / "candidate-4/bin/profile-adapter"


def read(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
        raise RuntimeError("unsafe deployment input")
    return json.loads(path.read_bytes())


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(arguments: list[str], *, input_bytes: bytes | None = None, timeout: int = 180,
            check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(arguments, input=input_bytes, capture_output=True, text=False, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError("command failed: " + Path(arguments[0]).name)
    return result


def docker(*arguments: str, timeout: int = 180) -> str:
    raw = ["docker", *arguments]
    result = subprocess.run(raw, capture_output=True, text=True, timeout=timeout)
    if result.returncode and "permission denied" in result.stderr.lower():
        result = subprocess.run(["sg", "docker", "-c", shlex.join(raw)], capture_output=True,
                                text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Docker command failed")
    return result.stdout


def compose(files: tuple[Path, ...], arguments: tuple[str, ...], timeout: int = 300) -> str:
    raw = ["docker", "compose"]
    for path in files:
        raw.extend(["-f", str(path)])
    raw.extend(arguments)
    result = subprocess.run(raw, capture_output=True, text=True, timeout=timeout)
    if result.returncode and "permission denied" in result.stderr.lower():
        result = subprocess.run(["sg", "docker", "-c", shlex.join(raw)], capture_output=True,
                                text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Compose command failed")
    return result.stdout


def atomic_bytes(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def save(path: Path, value) -> None:
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(), 0o600)


def mark(evidence: Path, phase: str, **extra) -> None:
    save(evidence / "phase.json", {"phase": phase, "time": datetime.now(timezone.utc).isoformat(), **extra})


def http_json(method: str, path: str, value=None, port: int = 2019):
    body = None if value is None else json.dumps(value).encode()
    headers = {} if body is None else {"Content-Type": "application/json"}
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def load_caddy(path: Path) -> None:
    status, _, _ = http_json("POST", "/load", read(path))
    if status != 200:
        raise RuntimeError("Caddy configuration load failed")


def current_caddy():
    status, _, raw = http_json("GET", "/config/")
    if status != 200:
        raise RuntimeError("Caddy configuration read failed")
    return json.loads(raw)


def wait_http(host: str, path: str, expected: set[int], port: int = 9100, seconds: int = 90):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", path, headers={"Host": host})
            response = connection.getresponse()
            body = response.read()
            last = response.status
            if response.status in expected:
                return response.status, body
        except (OSError, http.client.HTTPException):
            pass
        finally:
            connection.close()
        time.sleep(.4)
    raise RuntimeError(f"HTTP wait failed with status {last}")


def profile_snapshot(profile: str, config: Path | None = None):
    result = command([str(SERVICE_BINARY), "-config", str(config or PRODUCTION / "adapter-config.json"),
                      "-inspect-profile", profile], timeout=90)
    return json.loads(result.stdout)


def secure_client():
    path = PRODUCTION / "lifecycle/check-network-live.py"
    spec = importlib.util.spec_from_file_location("r4b_network", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    admin = read(PRODUCTION / "config/admin.json")
    return module.SecureClient(PRODUCTION, username=admin["username"],
        private=admin["private_key"].encode(), public=admin["server_public_key"].encode(), port=8000)


def wait_admin(seconds: int = 120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            client = secure_client()
            status, apps = client.call("GET", "/api/admin/apps/installed")
            if status == 200:
                return client, apps
        except (AssertionError, OSError, ValueError, http.client.HTTPException):
            pass
        time.sleep(.8)
    raise RuntimeError("candidate controller did not become ready")


def local_call(host: str, method: str, path: str, body: bytes | None = None,
               headers: dict[str, str] | None = None, timeout: int = 180):
    request_headers = {"Host": host, **(headers or {})}
    connection = http.client.HTTPConnection("127.0.0.1", 9100, timeout=timeout)
    try:
        connection.request(method, path, body, request_headers)
        response = connection.getresponse()
        return response.status, response.headers, response.read()
    finally:
        connection.close()


def launch_authenticated(profile: str, username: str, password: str):
    entry_host, session_host = "mybrowser.azhen.de", "mysession.azhen.de"
    entry_origin = "https://" + entry_host
    cookies: dict[str, dict[str, str]] = {entry_host: {}, session_host: {}}

    def call(host, method, path, value=None):
        headers = {"Cookie": "; ".join(key + "=" + item for key, item in cookies[host].items())}
        body = None
        if value is not None:
            headers.update({"Origin": entry_origin, "Content-Type": "application/x-www-form-urlencoded"})
            body = urlencode(value).encode()
        status, response_headers, raw = local_call(host, method, path, body, headers)
        # http.client collapses only through dict conversion for non-cookie fields;
        # collect Set-Cookie from the raw response is not available here, so make
        # one-cookie-per-response behavior explicit through the returned header.
        for key, item in response_headers.items():
            if key.lower() == "set-cookie":
                parsed = SimpleCookie(); parsed.load(item)
                cookies[host].update({name: part.value for name, part in parsed.items()})
        return status, response_headers, raw

    fixed = "/browser/" + profile + "/"
    status, _, body = call(entry_host, "GET", "/auth/login?" + urlencode({"next": fixed}))
    if status != 200:
        raise RuntimeError("production login page unavailable")
    match = re.search(rb'name="csrf" value="([^"]+)"', body)
    if not match:
        raise RuntimeError("production login CSRF missing")
    status, _, _ = call(entry_host, "POST", "/auth/login",
                        {"csrf": html.unescape(match.group(1).decode()), "username": username,
                         "password": password, "next": fixed})
    if status != 303:
        raise RuntimeError("production login rejected")
    status, _, body = call(entry_host, "GET", fixed)
    if status != 200:
        raise RuntimeError("production Profile page unavailable")
    match = re.search(rb'name="csrf" value="([^"]+)"', body)
    if not match:
        raise RuntimeError("Profile start CSRF missing")
    status, headers, _ = call(entry_host, "POST", fixed + "start",
                              {"csrf": html.unescape(match.group(1).decode())})
    location = headers.get("Location") or headers.get("location")
    if status != 303 or not location:
        raise RuntimeError("Profile start did not return a handoff")
    handoff = urlsplit(location)
    if handoff.netloc != session_host or handoff.path != "/auth/accept":
        raise RuntimeError("unexpected Session handoff host")
    status, headers, _ = call(session_host, "GET", handoff.path + ("?" + handoff.query if handoff.query else ""))
    location = headers.get("Location") or headers.get("location")
    if status != 303 or not location:
        raise RuntimeError("Session handoff rejected")
    clean = urlsplit(location)
    clean_query = parse_qs(clean.query, keep_blank_values=True)
    if clean.netloc not in ("", session_host) or set(clean_query) - {"embedded"}:
        raise RuntimeError("Session handoff retained a capability query")
    status, _, body = call(session_host, "GET", clean.path + ("?" + clean.query if clean.query else ""))
    if status != 200 or b"access_token" in body:
        raise RuntimeError("authenticated Session page failed")
    return {"profile": profile, "start_status": 303, "handoff_status": 303,
            "session_status": 200, "session_path": clean.path, "embedded": "embedded" in clean_query}


def backup(evidence: Path) -> tuple[dict[str, Path], dict[str, dict]]:
    targets = {
        "adapter-config.json": PRODUCTION / "adapter-config.json",
        "adapter-state.json": PRODUCTION / "adapter-state.json",
        "profile-network-policies.json": PRODUCTION / "config/.config/sealskin/profile-network-policies.json",
        "installed_apps.yml": PRODUCTION / "config/.config/sealskin/installed_apps.yml",
        "sessions.yml": PRODUCTION / "config/.config/sealskin/sessions.yml",
        "compose.yml": PRODUCTION / "compose.yml",
        "compose.proxy.yml": PRODUCTION / "compose.proxy.yml",
        "profile-adapter": SERVICE_BINARY,
        "proxy_cert.pem": PRODUCTION / "config/ssl/proxy_cert.pem",
        "proxy_key.pem": PRODUCTION / "config/ssl/proxy_key.pem",
    }
    destination = evidence / "before"
    destination.mkdir(mode=0o700)
    metadata = {}
    for name, source in targets.items():
        target = destination / name
        shutil.copy2(source, target, follow_symlinks=False)
        original_mode = source.stat().st_mode & 0o777
        os.chmod(target, 0o600)
        metadata[name] = {"source": str(source), "sha256": sha(source), "mode": oct(original_mode)}
    session_secrets = PRODUCTION / "config/.config/sealskin/session-secrets"
    if session_secrets.is_dir():
        shutil.copytree(session_secrets, destination / "session-secrets", symlinks=True)
    save(destination / "manifest.json", metadata)
    return targets, metadata


def public_status(host: str, path: str) -> int:
    result = command(["curl", "-k", "-sS", "--resolve", host + ":443:127.0.0.1",
                      "-o", "/dev/null", "-w", "%{http_code}", "https://" + host + path], timeout=30)
    return int(result.stdout.decode())


def activate_candidate(package: Path, evidence: Path) -> dict:
    admin, apps = wait_admin()
    mark(evidence, "controller_ready")

    personal_app = read(package / "application.personal.json")
    existing_personal = next((value for value in apps if value.get("id") == personal_app["id"]), None)
    if existing_personal is None:
        personal_status, _ = admin.call("POST", "/api/admin/apps/installed", personal_app)
        if personal_status != 201:
            raise RuntimeError("r9 Personal application installation failed")
    else:
        if existing_personal.get("provider_config") != personal_app["provider_config"]:
            raise RuntimeError("existing r9 Personal application differs from the package")
        personal_status = "already_installed_exact"
    work_app = read(package / "application.work.json")
    existing_work = next((value for value in apps if value.get("id") == work_app["id"]), None)
    current_work = copy.deepcopy(existing_work.get("provider_config", {})) if existing_work else {}
    for key in ("network_policy_id", "network_policy_sha256"):
        if current_work.get(key) is None:
            current_work.pop(key, None)
    if current_work == work_app["provider_config"]:
        work_status = "already_installed_exact"
    else:
        status, _ = admin.call("PATCH", "/api/admin/apps/installed/firefox-work",
                               {"provider_config": work_app["provider_config"]})
        if status != 200:
            raise RuntimeError("Work compatibility application update failed")
        work_status = 200
    save(evidence / "apps-installed.json", {"personal_status": personal_status, "work_patch_status": work_status,
                                             "personal_app": personal_app["id"], "work_app": work_app["id"]})

    command(["systemctl", "--user", "start", "profile-adapter.service"], timeout=60)
    wait_http("mybrowser.azhen.de", "/readyz", {200})
    unauthenticated = {
        "login": local_call("mybrowser.azhen.de", "GET", "/auth/login")[0],
        "work": local_call("mybrowser.azhen.de", "GET", "/browser/work/")[0],
        "session": local_call("mysession.azhen.de", "GET", "/")[0],
    }
    if unauthenticated != {"login": 200, "work": 303, "session": 404}:
        raise RuntimeError("local unauthenticated access boundary failed")

    access = (package / "operator-access.txt").read_text()
    username_match = re.search(r"账号：([^\n]+)", access)
    password_match = re.search(r"密码：([^\n]+)", access)
    if not username_match or not password_match:
        raise RuntimeError("private operator account material is incomplete")
    username, password = username_match.group(1), password_match.group(1)
    sessions = {profile: launch_authenticated(profile, username, password) for profile in ("work", "personal")}
    password = ""
    snapshots = {profile: profile_snapshot(profile) for profile in ("work", "personal")}
    expected_counts = {
        "work": {"resources": 0, "relays": 0, "guards": 0, "networks": 0},
        "personal": {"resources": 5, "relays": 1, "guards": 1, "networks": 2},
    }
    for profile, snapshot in snapshots.items():
        if (snapshot["status"] != "running" or snapshot["records"] != 1
                or snapshot["workers"] != 1 or snapshot["orphans"] != 0):
            raise RuntimeError(profile + " generation did not start cleanly")
        if any(snapshot[key] != value for key, value in expected_counts[profile].items()):
            raise RuntimeError(profile + " managed network count mismatch")
        if (snapshot["capabilities"].get("browser_shutdown_version") != 1
                or snapshot["capabilities"].get("session_auth_version") != 1):
            raise RuntimeError(profile + " runtime capabilities are incomplete")
    save(evidence / "sessions.private.json", sessions)
    save(evidence / "runtime-after.json", snapshots)
    mark(evidence, "local_acceptance_passed")

    current = json.loads(docker("inspect", "sealskin", "profile-relay-personal", timeout=60))
    candidate_image = read(RUNTIME / "candidate-3/images.json")["runtime"]["id"]
    if current[0]["Image"] != candidate_image or not current[0]["State"]["Running"]:
        raise RuntimeError("candidate controller image is not active")
    if current[1]["Id"] != read(package / "release-audit.json")["current_runtime_preserved"]["relay"]["id"]:
        raise RuntimeError("static production relay identity changed")

    load_caddy(package / "entry-auth/caddy.candidate.json")
    public = {
        "login": public_status("mybrowser.azhen.de", "/auth/login"),
        "work": public_status("mybrowser.azhen.de", "/browser/work/"),
        "session": public_status("mysession.azhen.de", "/"),
    }
    if public != {"login": 200, "work": 303, "session": 404}:
        raise RuntimeError("public access boundary failed")
    if current_caddy() != read(package / "entry-auth/caddy.candidate.json"):
        raise RuntimeError("Caddy candidate did not remain active")
    mark(evidence, "candidate_public")

    result = {
        "status": "PASS", "phase": "candidate_public",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "production_changes_performed": True,
        "runtime": {profile: {key: snapshots[profile][key] for key in
                    ("status", "records", "workers", "orphans", "resources", "relays", "guards", "networks")}
                    for profile in snapshots},
        "public": public, "controller_image": candidate_image,
        "target_personal_home_created": (PRODUCTION / "storage/profile-adapter/personal-camoufox-r9").is_dir(),
        "work_old_generation_stopped": True,
        "caddy_api_resume_active": True,
        "rollback": "maintenance-time backup and post-stop control journal retained",
        "next_required": ["target Mac production display/input check", "logout persistence",
                          "Caddy and Docker restart, then VPS reboot recovery"],
    }
    if not result["target_personal_home_created"]:
        raise RuntimeError("target Personal Home was not created")
    save(evidence / "deployment-result.json", result)
    return result


def deployment(package: Path, evidence: Path) -> dict:
    audit = read(package / "release-audit.json")
    if audit.get("status") != "READY_FOR_MAINTENANCE" or audit.get("production_changes_performed"):
        raise RuntimeError("package is not a reviewed candidate")
    verify_dir = evidence / "package-verification"
    command([sys.executable, str(PRODUCTION / "checks/verify-r4b-production-release.py"),
             "--package", str(package), "--output", str(verify_dir)], timeout=240)
    host = json.loads(command([sys.executable, str(PRODUCTION / "entry-auth/install-host-prerequisites.py"),
                               "--package", str(package)]).stdout)
    if host.get("status") != "installed" or not host.get("caddy_api_resume_active"):
        raise RuntimeError("host prerequisites are incomplete")
    mark(evidence, "preflight_passed")

    targets, metadata = backup(evidence)
    save(evidence / "caddy-before.json", current_caddy())
    containers_before = json.loads(docker("inspect", "sealskin", "profile-relay-personal", timeout=60))
    linger_before = command(["loginctl", "show-user", str(os.getuid()), "-p", "Linger", "--value"]).stdout.decode().strip()

    load_caddy(package / "entry-auth/caddy.maintenance.json")
    mark(evidence, "maintenance_loaded")
    if public_status("mybrowser.azhen.de", "/browser/work/") != 503 or public_status("mysession.azhen.de", "/") != 503:
        raise RuntimeError("maintenance edge did not close both hosts")

    # The legacy Adapter points at the public Session origin, which is now 503,
    # and control commands must match the running process' config fingerprint.
    # Restart it briefly with a same-path loopback config, stop Work normally,
    # then restore the original bytes while the Adapter remains stopped.
    legacy_config = (PRODUCTION / "adapter-config.json").read_bytes()
    stop_config = copy.deepcopy(read(PRODUCTION / "adapter-config.json"))
    stop_config["sealskin"].update(api_base_url="http://127.0.0.1:8000",
                                   allow_unencrypted_http=True, lifecycle_enabled=True)
    stop_path = evidence / "legacy-loopback-stop.json"
    save(stop_path, stop_config)
    stop_complete = False
    try:
        command(["systemctl", "--user", "stop", "profile-adapter.service"], timeout=60)
        atomic_bytes(PRODUCTION / "adapter-config.json",
                     (json.dumps(stop_config, ensure_ascii=False, indent=2) + "\n").encode(), 0o600)
        command(["systemctl", "--user", "start", "profile-adapter.service"], timeout=60)
        wait_http("mybrowser.azhen.de", "/readyz", {200})
        profiles_before = {name: profile_snapshot(name) for name in ("personal", "work")}
        if (profiles_before["personal"]["status"] != "stopped"
                or profiles_before["work"]["status"] != "running"):
            raise RuntimeError("legacy Profile state changed before stop")
        save(evidence / "production-before.json", {
            "inputs": metadata, "profiles": profiles_before,
            "containers": containers_before, "linger": linger_before,
        })
        stop = command([str(SERVICE_BINARY), "-config", str(PRODUCTION / "adapter-config.json"),
                        "-stop-profile", "work"], timeout=300, check=False)
        (evidence / "work-stop.json").write_bytes(stop.stdout)
        (evidence / "work-stop.log").write_bytes(stop.stderr)
        os.chmod(evidence / "work-stop.json", 0o600); os.chmod(evidence / "work-stop.log", 0o600)
        if stop.returncode:
            raise RuntimeError("Work lifecycle stop failed")
        snapshots = {name: profile_snapshot(name) for name in ("personal", "work")}
        for name, value in snapshots.items():
            if value["status"] != "stopped" or any(value[key] for key in
                    ("records", "workers", "orphans", "resources", "relays", "guards", "networks")):
                raise RuntimeError(name + " resources were not fully released")
        save(evidence / "post-stop.json", snapshots)
        stop_complete = True
    finally:
        command(["systemctl", "--user", "stop", "profile-adapter.service"], timeout=60, check=False)
        atomic_bytes(PRODUCTION / "adapter-config.json", legacy_config, 0o600)
        if not stop_complete:
            command(["systemctl", "--user", "start", "profile-adapter.service"], timeout=60, check=False)
    if not stop_complete:
        raise RuntimeError("legacy Work stop was not confirmed")
    mark(evidence, "profiles_stopped")
    if command(["systemctl", "--user", "is-active", "profile-adapter.service"], check=False).returncode == 0:
        raise RuntimeError("Adapter did not stop")
    post = evidence / "post-stop-control"
    post.mkdir(mode=0o700)
    for source in (PRODUCTION / "adapter-config.json", PRODUCTION / "adapter-state.json",
                   PRODUCTION / "config/.config/sealskin/sessions.yml"):
        shutil.copy2(source, post / source.name, follow_symlinks=False)
        os.chmod(post / source.name, 0o600)
    mark(evidence, "adapter_stopped")

    atomic_bytes(PRODUCTION / "config/.config/sealskin/profile-network-policies.json",
                 (package / "network-policies.candidate.json").read_bytes(), 0o600)
    atomic_bytes(PRODUCTION / "adapter-config.json", (package / "adapter.candidate.json").read_bytes(), 0o600)
    atomic_bytes(SERVICE_BINARY, CANDIDATE_BINARY.read_bytes(), 0o755)
    secrets = PRODUCTION / "secrets"
    secrets.mkdir(mode=0o700, exist_ok=True); os.chmod(secrets, 0o700)
    atomic_bytes(secrets / "entry-users.json", (package / "secrets/entry-users.json").read_bytes(), 0o600)
    atomic_bytes(secrets / "private-session-ca.pem", (package / "entry-auth/private-tls/cert.pem").read_bytes(), 0o600)
    atomic_bytes(PRODUCTION / "config/ssl/proxy_cert.pem",
                 (package / "entry-auth/private-tls/cert.pem").read_bytes(), 0o644)
    atomic_bytes(PRODUCTION / "config/ssl/proxy_key.pem",
                 (package / "entry-auth/private-tls/key.pem").read_bytes(), 0o600)
    mark(evidence, "files_staged")

    compose((PRODUCTION / "compose.yml", PRODUCTION / "compose.proxy.yml",
             package / "entry-auth/compose.entry-auth.yml"), ("up", "-d", "sealskin"))
    return activate_candidate(package, evidence)


def resume_files_staged(package: Path, evidence: Path) -> dict:
    phase = read(evidence / "phase.json")
    failure = read(evidence / "deployment-failure.json")
    if phase.get("phase") not in {"files_staged", "controller_ready"} or failure.get("error_class") not in {"InvalidSignature", "RuntimeError"}:
        raise RuntimeError("evidence is not the reviewed files-staged recovery point")
    if not (evidence / "before/manifest.json").is_file() or not (evidence / "post-stop.json").is_file():
        raise RuntimeError("maintenance rollback or stop evidence is missing")
    host = json.loads(command([sys.executable, str(PRODUCTION / "entry-auth/install-host-prerequisites.py"),
                               "--package", str(package)]).stdout)
    if host.get("status") != "installed" or not host.get("caddy_api_resume_active"):
        raise RuntimeError("host prerequisites are incomplete")
    if public_status("mybrowser.azhen.de", "/browser/work/") != 503 or public_status("mysession.azhen.de", "/") != 503:
        raise RuntimeError("maintenance edge is not retained")
    expected = {
        PRODUCTION / "adapter-config.json": package / "adapter.candidate.json",
        PRODUCTION / "config/.config/sealskin/profile-network-policies.json": package / "network-policies.candidate.json",
        SERVICE_BINARY: CANDIDATE_BINARY,
        PRODUCTION / "secrets/entry-users.json": package / "secrets/entry-users.json",
        PRODUCTION / "secrets/private-session-ca.pem": package / "entry-auth/private-tls/cert.pem",
        PRODUCTION / "config/ssl/proxy_cert.pem": package / "entry-auth/private-tls/cert.pem",
        PRODUCTION / "config/ssl/proxy_key.pem": package / "entry-auth/private-tls/key.pem",
    }
    for current, source in expected.items():
        if not current.is_file() or sha(current) != sha(source):
            raise RuntimeError("staged production file drift")
    state = read(PRODUCTION / "adapter-state.json")
    profile_states = {name: state.get("bindings", {}).get(name, {}).get("status") for name in ("personal", "work")}
    if set(profile_states.values()) not in ({"stopped"}, {"running"}):
        raise RuntimeError("Profile journals are not at one coherent recovery point")
    adapter_active = command(["systemctl", "--user", "is-active", "profile-adapter.service"], check=False).returncode == 0
    profile_containers = set()
    for name in ("personal", "work"):
        profile_containers.update(docker("ps", "-aq", "--filter", "label=io.browser-platform.profile=" + name).split())
    if set(profile_states.values()) == {"stopped"} and (profile_containers or adapter_active):
        raise RuntimeError("stopped recovery point still has a Profile container or Adapter")
    if set(profile_states.values()) == {"running"}:
        if not adapter_active or len(profile_containers) != 4:
            raise RuntimeError("running recovery point lacks its Adapter or managed containers")
        snapshots = {name: profile_snapshot(name) for name in ("personal", "work")}
        if (snapshots["work"]["records"], snapshots["work"]["workers"], snapshots["work"]["resources"],
                snapshots["personal"]["records"], snapshots["personal"]["workers"], snapshots["personal"]["resources"],
                snapshots["personal"]["relays"], snapshots["personal"]["guards"], snapshots["personal"]["networks"]) != (1, 1, 0, 1, 1, 5, 1, 1, 2):
            raise RuntimeError("running recovery point resource counts drifted")
    controller = json.loads(docker("inspect", "sealskin", timeout=60))[0]
    candidate_image = read(RUNTIME / "candidate-3/images.json")["runtime"]["id"]
    if not controller["State"]["Running"] or controller["Image"] != candidate_image:
        raise RuntimeError("candidate controller recovery point is unavailable")
    mark(evidence, phase["phase"], resumed_after="production_admin_port_and_root_status_correction")
    return activate_candidate(package, evidence)


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--resume-files-staged", action="store_true")
    args = parser.parse_args()
    package, evidence = args.package.resolve(strict=True), args.evidence.resolve()
    if args.resume_files_staged:
        if not evidence.is_dir():
            raise RuntimeError("resume evidence directory is unavailable")
    else:
        if evidence.exists():
            raise RuntimeError("evidence directory already exists")
        evidence.mkdir(mode=0o700, parents=True)
    try:
        result = resume_files_staged(package, evidence) if args.resume_files_staged else deployment(package, evidence)
    except Exception as error:
        phase = "not_started"
        try:
            phase = read(evidence / "phase.json").get("phase", phase)
        except (OSError, ValueError, RuntimeError):
            pass
        maintenance_attempted = phase not in {"not_started", "preflight_passed"}
        maintenance_retained = False
        if maintenance_attempted:
            try:
                load_caddy(package / "entry-auth/caddy.maintenance.json")
                maintenance_retained = True
            except Exception:
                maintenance_retained = False
        save(evidence / "deployment-failure.json", {
            "status": "FAILED_MAINTENANCE" if maintenance_attempted else "REFUSED_BEFORE_MAINTENANCE",
            "failed_at": datetime.now(timezone.utc).isoformat(), "phase": phase,
            "error_class": type(error).__name__, "maintenance_retained": maintenance_retained,
            "rollback_materials": (evidence / "before/manifest.json").is_file(),
            "production_result_written": False,
        })
        raise RuntimeError("deployment failed at " + phase) from error
    print(json.dumps({"status": result["status"], "phase": result["phase"],
                      "evidence": str(evidence), "target_mac_check": "pending",
                      "production_changes_performed": True}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        raise SystemExit("R4B deployment refused: " + str(error))
