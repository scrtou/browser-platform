#!/usr/bin/env python3
"""Prepare fresh R5E Profiles on the empty, scoped network QA controller.

Keeps Store, display tmpfs and DIRECT mounts installed by prepare-network-qa.
No production paths, original Home, or existing application are replaced.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
from urllib.parse import urlsplit

CHECKS = Path(__file__).resolve().parent
PROJECT = CHECKS.parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


entry = module("combination_entry_prepare", CHECKS / "prepare-entry-auth.py")
network = module("combination_network", CHECKS.parent / "lifecycle/check-network-live.py")


def require(value, code):
    if not value:
        raise RuntimeError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def owned_directory(path):
    info = path.lstat()
    require(path.resolve() == path and stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, "QA_PRIVATE_DIRECTORY_REQUIRED")


def normalize(policy):
    code = ("from app.network_runtime import NetworkPolicy;import json;"
            "print(json.dumps(NetworkPolicy.model_validate(json.loads(" + repr(json.dumps(policy)) + ")).model_dump()))")
    return json.loads(network.docker("exec", "-w", "/app", network.SERVER, "python3", "-c", code).stdout)


def setup(args):
    qa, candidate = args.root.resolve(), args.candidate.resolve()
    require(qa == candidate / "qa" and candidate.parent.name == "r5e-release-combination-2026-09-15",
            "FRESH_R5E_ROOT_REQUIRED")
    resources = json.loads((candidate.parent / "resources.json").read_text())
    require(resources["candidate"] == str(candidate) and resources["qa"] == str(qa), "QA_RESOURCE_REGISTRY_MISMATCH")
    display, runtime, key_dir = (Path(resources[k]) for k in ("display", "credentials", "key_directory"))
    for path in (display, runtime, key_dir):
        owned_directory(path)
    require(display.parent == runtime.parent == Path("/dev/shm") and key_dir == candidate / "master-key",
            "QA_MOUNT_SCOPE_MISMATCH")
    controller = json.loads(network.docker("inspect", network.SERVER).stdout)[0]
    mounts = {m["Destination"]: m for m in controller["Mounts"] if m["Type"] == "bind"}
    images = json.loads((candidate / "images.json").read_text())
    require(controller["Config"]["Labels"].get(network.PREFIX + "qa") == "network-20260913"
            and controller["Image"] == images["runtime"]["id"], "QA_CONTROLLER_IDENTITY_MISMATCH")
    expected = {"/config": qa / "config", "/storage": qa / "storage", "/run/browser-platform-key": key_dir,
                "/run/browser-platform-secrets": runtime, "/run/browser-platform-session-secrets": display,
                "/run/browser-platform-host/ipv4-fib-trie": Path("/proc/1/net/fib_trie")}
    require(all(mounts[k]["Source"] == str(v) for k, v in expected.items()), "QA_CONTROLLER_MOUNTS_MISMATCH")
    require(not mounts["/run/browser-platform-key"]["RW"] and not mounts["/run/browser-platform-host/ipv4-fib-trie"]["RW"],
            "QA_READONLY_MOUNTS_REQUIRED")
    config = json.loads((qa / "adapter-config.json").read_text())
    require(config["sealskin"]["username"] == "network-qa" and config["listen_address"] == "127.0.0.1:29110",
            "QA_ADAPTER_SCOPE_MISMATCH")
    require(not any((qa / p).exists() for p in ("access", "adapter-pid.json", "front-caddy-pid.json")), "QA_ALREADY_PREPARED")
    client = network.SecureClient(qa)
    for profile in config["profiles"]:
        status, inventory = client.call("GET", "/api/profile-runtime/" + profile["home_name"])
        require(status == 200 and not any(inventory[k] for k in ("records", "workers", "resources")), "QA_NOT_EMPTY")
    admin = json.loads((qa / "admin.json").read_text())
    administrator = network.SecureClient(qa, username=admin["username"], private=admin["private_key"].encode(),
                                         public=admin["server_public_key"].encode())
    access, stage = qa / "access", candidate / "stage"
    access.mkdir(mode=0o700)
    stage.mkdir(mode=0o700)
    for name in ("adapter-config.json", "allow.json"):
        shutil.copy2(qa / name, stage / (name + ".before"))
    network.write_json(stage / "controller-before.json", controller)
    endpoint = json.loads((args.bundle / "before/config.json").read_text())
    require(endpoint["client_ipv4"] == ["23.19.231.152"] and endpoint["peer_ipv4"] == ["188.253.118.223", "202.155.153.31"]
            and endpoint.get("rotation_enabled") and endpoint.get("coherence_domain"), "QA_ENDPOINT_SCOPE_MISMATCH")
    credentials = json.loads((args.bundle / "before/credentials.json").read_text())
    metadata = qa / "config/.config/sealskin"
    metadata.chmod(0o700)
    assets = metadata / "coherence-assets"
    assets.mkdir(mode=0o700)

    def asset(source):
        raw = source.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        path = assets / (sha + source.suffix)
        require(not path.exists(), "DUPLICATE_QA_ASSET")
        path.write_bytes(raw)
        path.chmod(0o600)
        return path, "/config/.config/sealskin/coherence-assets/" + path.name, sha

    artifact_path, artifact_ref, artifact_sha = asset(args.artifact.resolve())
    acceptance_path, acceptance_ref, acceptance_sha = asset(args.acceptance.resolve())
    _, geoip_ref, geoip_sha = asset(args.geoip.resolve())
    artifact = json.loads(artifact_path.read_text())
    ca = metadata / "network-secrets/r5e-probe-ca.pem"
    require(not ca.exists(), "QA_CA_ALREADY_EXISTS")
    shutil.copyfile(args.bundle / "before/ca.pem", ca)
    ca.chmod(0o600)
    storage = module("combination_secret_store", candidate / "build/payload/app/secret_store.py")
    # The empty base fixture may reserve a random key before Store creation.
    # Preserve that unused file; let the Store initialize its own fresh key.
    require(not (metadata / "proxy-secret-store").exists(), "FRESH_QA_STORE_REQUIRED")
    if (key_dir / "master.key").exists():
        info = (key_dir / "master.key").lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size == 32, "UNUSED_QA_KEY_INVALID")
        (key_dir / "master.key").rename(stage / "unused-base-master.key")
    secret_store = storage.FileSecretStore.initialize(metadata / "proxy-secret-store", key_dir / "master.key")
    principals = [{"owner": "network-qa", "profile": "network-qa-entry-" + suffix,
                   "home": "network-qa-home-entry-" + suffix, "app": "camoufox-r5e-" + suffix} for suffix in ("a", "b")]
    secret_id = "r5e-proxy-" + endpoint["run_id"]
    secret_store.put(secret_id, 1, principals, username=credentials["username"], password=credentials["password"])
    references = storage.references(secret_id, 1)
    network.write_json(metadata / "profile-secret-store.json", {
        "version": 1, "key_file": "/run/browser-platform-key/master.key", "runtime_dir": "/run/browser-platform-secrets"})
    entry_origin, session_origin = "https://entry.r5d.test:29443", "https://session.r5d.test:29443"
    config["public_base_url"] = entry_origin
    config["sealskin"].update(api_base_url="https://127.0.0.1:28443", public_session_base_url=session_origin,
                              allow_unencrypted_http=False)
    config["access"] = {"users_file": str(access / "users.json"), "session_upstream_url": "https://127.0.0.1:28443",
                         "session_ca_file": str(access / "session-ca.pem"), "session_tls_name": "network.invalid",
                         "session_seconds": 1800, "ticket_seconds": 5}
    entry.private_tls(qa, access, network)
    qa_images = json.loads((qa / "images.json").read_text())
    allow = json.loads((qa / "allow.json").read_text())
    registry_path = metadata / "profile-network-policies.json"
    registry = json.loads(registry_path.read_text())
    profiles, policies, applications, accounts = [], {}, {}, []
    website = f"https://{endpoint['website_names'][0]}:{endpoint['ports']['https']}"
    for suffix, principal, actor in zip(("a", "b"), principals, ("alice", "bob")):
        home, profile_id, app_id = principal["home"], principal["profile"], principal["app"]
        policy_id = "r5e-entry-" + suffix + "-r1"
        policy = {"username": "network-qa", "profile_id": profile_id, "home_name": home, "application_id": app_id,
                  "relay_image": qa_images["relay"], "probe_image": qa_images["probe"],
                  "mode": "proxy_required" if suffix == "a" else "direct",
                  "probe_url": f"https://{endpoint['coherence_domain']}:{endpoint['ports']['https']}/health",
                  "probe_ca_file": "/config/.config/sealskin/network-secrets/" + ca.name,
                  "probe_ca_sha256": hashlib.sha256(ca.read_bytes()).hexdigest(), "probe_timeout_seconds": 10,
                  "coherence": {"mode": "strict", "allowed_countries": ["JP"] if suffix == "a" else ["US"],
                                "allowed_timezones": [artifact["spec"]["timezone"]], "on_exit_change": "recheck",
                                "observer_domain": endpoint["coherence_domain"], "observer_port": endpoint["ports"]["https"],
                                "observer_ipv4": endpoint["peer_ipv4"], "artifact_file": artifact_ref,
                                "artifact_sha256": artifact_sha, "acceptance_file": acceptance_ref, "acceptance_sha256": acceptance_sha,
                                "geoip_file": geoip_ref, "geoip_sha256": geoip_sha,
                                "geoip_source": "https://download.db-ip.com/free/dbip-country-lite-2026-09.csv.gz",
                                "geoip_version": "DB-IP Lite Country 2026-09", "geoip_published_at": "2026-09-01T06:26:58Z",
                                "geoip_max_age_days": 62}}
        if suffix == "a":
            policy.update(upstream_host=endpoint["peer_ipv4"][0], upstream_port=endpoint["ports"]["socks5"],
                          upstream_protocol="socks5", upstream_auth="username_password",
                          username_secret_ref=references["username"], password_secret_ref=references["password"])
        else:
            policy.update(approved_resolver_id="cloudflare-r5e", approved_resolver_ip="1.1.1.1")
        policy = normalize(policy)
        require(policy_id not in registry["policies"], "QA_POLICY_ALREADY_EXISTS")
        registry["policies"][policy_id] = policy
        policies[profile_id] = policy
        network.write_json(registry_path, registry)
        status, _ = client.call("POST", "/api/homedirs", {"home_name": home})
        require(status == 201, "NEW_QA_HOME_REQUIRED")
        browser_profile = qa / "storage/network-qa" / home / ".camoufox/profile"
        browser_profile.mkdir(mode=0o700, parents=True)
        nss = candidate / "nss-tools/extracted/usr"
        command = ["/lib64/ld-linux-x86-64.so.2", "--library-path", str(nss / "lib/x86_64-linux-gnu"), str(nss / "bin/certutil")]
        for extra in (["-N", "--empty-password", "-d", "sql:" + str(browser_profile)],
                      ["-A", "-d", "sql:" + str(browser_profile), "-n", "R5E temporary QA CA", "-t", "C,,", "-i", str(ca)]):
            require(subprocess.run(command + extra, capture_output=True).returncode == 0, "QA_CA_IMPORT_FAILED")
        command = [sys.executable, str(PROJECT / "infra/camoufox/prepare-sealskin.py"), "--artifact", str(artifact_path),
                   "--acceptance", str(acceptance_path), "--app-id", app_id, "--username", "network-qa", "--store", "QA",
                   "--network-policy-id", policy_id, "--network-policy-sha256", digest(policy),
                   "--session-origin", session_origin, "--output", str(stage / (app_id + ".json"))]
        result = subprocess.run(command, capture_output=True)
        (stage / (app_id + ".log")).write_bytes(result.stdout + result.stderr)
        require(result.returncode == 0, "QA_R7_APPLICATION_PREPARE_FAILED")
        app = json.loads((stage / (app_id + ".json")).read_text())
        status, _ = administrator.call("POST", "/api/admin/apps/installed", app)
        require(status == 201, "QA_APPLICATION_REGISTRATION_FAILED")
        applications[profile_id] = app
        allow["images"] = sorted(set(allow["images"] + [app["provider_config"]["image"]]))
        allow["readonly_sources"] = sorted(set(allow["readonly_sources"] +
            [m["Source"] for m in app["provider_config"]["docker_overrides"]["mounts"]]))
        profiles.append({"id": profile_id, "home_name": home, "application_id": app_id, "start_url": website + "/probe",
                         "language": artifact["spec"]["locale"].replace("-", "_") + ".UTF-8",
                         "timezone": artifact["spec"]["timezone"], "wayland_mode": False,
                         "network_policy_id": policy_id, "network_policy_sha256": digest(policy)})
        accounts.append({"username": actor, "password": secrets.token_urlsafe(24), "profile": profile_id, "home": home})
    allow["coherence_guard_images"] = [qa_images["relay"]]
    allow["coherence_observer_sha256"] = [hashlib.sha256((candidate / "build/payload/app/browser_observe.py").read_bytes()).hexdigest()]
    network.write_json(qa / "allow.json", allow)
    config["profiles"] = profiles
    config["limits"] = {"max_active_profiles": 2, "max_concurrent_launches": 1}
    network.write_json(qa / "adapter-config.json", config)
    for account in accounts:
        result = subprocess.run([str(candidate / "bin/profile-accounts"), "put", "--config", str(qa / "adapter-config.json"),
                                 "--user", account["username"], "--profiles", account["profile"]],
                                input=account["password"].encode(), capture_output=True)
        require(result.returncode == 0, "QA_ACCOUNT_CREATION_FAILED")
    network.write_json(access / "test-accounts.json", {"entry_origin": entry_origin, "session_origin": session_origin, "accounts": accounts})
    log_check = module("combination_log_check", CHECKS / "check-entry-log-boundary.py")
    certificate, key = log_check.identity(access)
    template = (CHECKS.parent / "entry-auth/Caddyfile.example").read_text()
    template = template.replace("admin off", "admin off\n    auto_https off", 1)
    template = template.replace("mybrowser.example.com, mysession.example.com {", entry_origin + ", " + session_origin +
                                " {\n    bind 127.0.0.1\n    tls " + str(certificate) + " " + str(key))
    template = template.replace("127.0.0.1:8080", config["listen_address"])
    (access / "Caddyfile").write_text(template)
    environment = dict(os.environ, XDG_CONFIG_HOME=str(access / "caddy-config"), XDG_DATA_HOME=str(access / "caddy-data"))
    result = subprocess.run(["caddy", "adapt", "--config", str(access / "Caddyfile"), "--adapter", "caddyfile", "--validate"],
                            env=environment, capture_output=True)
    (access / "caddy-validation.log").write_bytes(result.stdout + result.stderr)
    require(result.returncode == 0, "QA_FRONTEND_CONFIG_REJECTED")
    for name, command, env in (
            ("adapter", [str(candidate / "bin/profile-adapter"), "--config", str(qa / "adapter-config.json")], None),
            ("front-caddy", ["caddy", "run", "--config", str(access / "Caddyfile"), "--adapter", "caddyfile"], environment)):
        with (qa / (name + ".log")).open("ab") as output:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, start_new_session=True, env=env)
        network.write_json(qa / (name + "-pid.json"), {"pid": process.pid})
    network.wait(lambda: network.request("GET", "/readyz", headers={"Host": urlsplit(entry_origin).netloc}, port=29110)[0] == 200,
                 "R5E authenticated QA entry", seconds=45)
    active = {"candidate": str(candidate), "controller": controller["Id"], "display_runtime_root": str(display),
              "credential_runtime_root": str(runtime), "key_directory": str(key_dir), "profiles": [p["id"] for p in profiles],
              "website_origin": website, "endpoint_bundle": str(args.bundle.resolve()), "secret_id": secret_id,
              "policies": policies, "applications": applications, "artifact": str(artifact_path), "acceptance": str(acceptance_path)}
    network.write_json(access / "active-candidate.json", active)
    result = {"result": "PREPARED", "controller_image": controller["Image"], "profiles": active["profiles"],
              "artifact_sha256": artifact_sha, "acceptance_sha256": acceptance_sha, "secret_store_version": 1,
              "login_and_coherence_enabled": True, "production_mutations": 0}
    network.write_json(stage / "prepared.json", result)
    return result


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "candidate", "bundle", "artifact", "acceptance", "geoip"):
        parser.add_argument("--" + name, type=Path, required=True)
    print(json.dumps(setup(parser.parse_args())), flush=True)


if __name__ == "__main__":
    main()
