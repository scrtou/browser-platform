#!/usr/bin/env python3
"""Add two local-login Profiles to an existing, private Camoufox network QA."""

import argparse
import base64
import copy
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def private_tls(qa, access, network):
    project = Path(__file__).resolve().parents[3]
    tls = module("entry_private_tls", project / "infra/sealskin/entry-auth/prepare-tls.py")
    identity = tls.create(access / "private-tls", "network.invalid", 2)
    old = access / "previous-private-tls"
    old.mkdir(mode=0o700)
    for name, target in (("cert.pem", "proxy_cert.pem"), ("key.pem", "proxy_key.pem")):
        path = qa / "config/ssl" / target
        shutil.copy2(path, old / target)
        shutil.copy2(access / "private-tls" / name, path)
        path.chmod(0o600)
    shutil.copy2(access / "private-tls/cert.pem", access / "session-ca.pem")
    # Caddy is a child of this isolated controller's service; an explicit
    # reload swaps its certificate without restarting the API or any Worker.
    result = network.docker("exec", network.SERVER, "caddy", "reload", "--config", "/config/.config/sealskin/Caddyfile",
                            "--adapter", "caddyfile", "--force", check=False)
    if result.returncode:
        raise RuntimeError("QA_PRIVATE_TLS_RELOAD_FAILED")
    network.write_json(access / "private-tls-installed.json", identity)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--entry-origin", default="https://entry.r5d.test:29443")
    parser.add_argument("--session-origin", default="https://session.r5d.test:29443")
    parser.add_argument("--backend-port", type=int, default=28443)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[3]
    network = module("entry_network", project / "infra/sealskin/lifecycle/check-network-live.py")
    log_check = module("entry_log_check", Path(__file__).with_name("check-entry-log-boundary.py"))
    qa = args.root.resolve()
    assert qa.name == "qa" and not (qa / "access").exists()
    entry, session = urlsplit(args.entry_origin), urlsplit(args.session_origin)
    assert entry.scheme == session.scheme == "https" and entry.port == session.port
    assert entry.hostname == "entry.r5d.test" and session.hostname == "session.r5d.test"
    controller = json.loads(network.docker("inspect", network.SERVER).stdout)[0]
    assert controller["Config"]["Labels"]["io.browser-platform.qa"] == "network-20260913"
    assert any(m["Source"] == str(qa / "config") and m["Destination"] == "/config" for m in controller["Mounts"])
    access = qa / "access"
    access.mkdir(mode=0o700)
    client = network.SecureClient(qa)
    original = json.loads((qa / "browser-launch.json").read_text())
    stop = json.loads((qa / "browser-stop.json").read_text())
    status, _ = client.call("POST", "/api/profile-runtime/" + original["home_name"] + "/stop", stop)
    assert status == 204, "initial QA browser stop failed"
    status, inventory = client.call("GET", "/api/profile-runtime/" + original["home_name"])
    assert status == 200 and not inventory["records"] and not inventory["workers"] and not inventory["resources"]
    network.write_json(access / "initial-stop.json", {"status": status, "empty": True})

    admin = json.loads((qa / "admin.json").read_text())
    admin_client = network.SecureClient(qa, username=admin["username"], private=admin["private_key"].encode(),
                                         public=admin["server_public_key"].encode())
    app_a = json.loads((qa / "camoufox-app.json").read_text())
    for value in app_a["provider_config"]["env"]:
        if value["name"] == "SELKIES_ALLOWED_ORIGINS":
            value["value"] = args.session_origin
    status, _ = admin_client.call("PATCH", "/api/admin/apps/installed/" + app_a["id"],
                                   {"provider_config": app_a["provider_config"]})
    assert status == 200, "QA Session origin update failed"
    policies_path = qa / "config/.config/sealskin/profile-network-policies.json"
    policies = json.loads(policies_path.read_text())
    policy_b = copy.deepcopy(policies["policies"][original["network_policy_id"]])
    policy_b.update(profile_id="network-qa-browser-b", home_name="network-qa-home-browser-b", application_id="r5d-camoufox-b")
    revision = hashlib.sha256(json.dumps(policy_b, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    policy_id = "r5d-browser-b-r1"
    policies["policies"][policy_id] = policy_b
    network.write_json(policies_path, policies)
    status, _ = client.call("POST", "/api/homedirs", {"home_name": policy_b["home_name"]})
    assert status == 201
    profile = qa / "storage/network-qa" / policy_b["home_name"] / ".camoufox/profile"
    profile.mkdir(mode=0o700, parents=True)
    nss = qa.parent / "nss-tools/extracted/usr"
    command = ["/lib64/ld-linux-x86-64.so.2", "--library-path", str(nss / "lib/x86_64-linux-gnu"), str(nss / "bin/certutil")]
    for extra in (["-N", "--empty-password", "-d", "sql:" + str(profile)],
                  ["-A", "-d", "sql:" + str(profile), "-n", "Private Network QA CA", "-t", "C,,", "-i", str(qa.parent / "observer/ca.pem")]):
        assert subprocess.run(command + extra, capture_output=True).returncode == 0
    app_b = copy.deepcopy(app_a)
    app_b.update(id=policy_b["application_id"], name="R5D isolated browser B")
    app_b["provider_config"].update(network_policy_id=policy_id, network_policy_sha256=revision)
    app_b["provider_config"]["docker_overrides"]["labels"]["browser-platform.application"] = app_b["id"]
    status, _ = admin_client.call("POST", "/api/admin/apps/installed", app_b)
    assert status == 201

    config = json.loads((qa / "adapter-config.json").read_text())
    config["public_base_url"] = args.entry_origin
    config["sealskin"].update(api_base_url=f"https://127.0.0.1:{args.backend_port}",
                               public_session_base_url=args.session_origin, allow_unencrypted_http=False)
    config["access"] = {"users_file": str(access / "users.json"),
                         "session_upstream_url": config["sealskin"]["api_base_url"],
                         "session_ca_file": str(access / "session-ca.pem"), "session_tls_name": "network.invalid",
                         "session_seconds": 1800, "ticket_seconds": 30}
    private_tls(qa, access, network)
    config["profiles"] = [{"id": original["profile_id"], "application_id": original["application_id"],
        "home_name": original["home_name"], "start_url": "https://entry.leak.qa.test/test", "language": original["language"],
        "timezone": original["timezone"], "wayland_mode": False, "network_policy_id": original["network_policy_id"],
        "network_policy_sha256": original["network_policy_sha256"]},
        {"id": policy_b["profile_id"], "application_id": app_b["id"], "home_name": policy_b["home_name"],
         "start_url": "https://entry.leak.qa.test/test", "language": original["language"], "timezone": original["timezone"],
         "wayland_mode": False, "network_policy_id": policy_id, "network_policy_sha256": revision}]
    config["limits"] = {"max_active_profiles": 2, "max_concurrent_launches": 1}
    network.write_json(qa / "adapter-config.json", config)
    accounts = []
    for actor, definition in zip(("alice", "bob"), config["profiles"]):
        password = base64.urlsafe_b64encode(os.urandom(24)).decode()
        result = subprocess.run([str(qa / "bin/profile-accounts"), "put", "--config", str(qa / "adapter-config.json"),
                                 "--user", actor, "--profiles", definition["id"]], input=password.encode(), capture_output=True)
        assert result.returncode == 0, "QA account creation failed"
        accounts.append({"username": actor, "password": password, "profile": definition["id"], "home": definition["home_name"]})
    network.write_json(access / "test-accounts.json", {"entry_origin": args.entry_origin, "session_origin": args.session_origin, "accounts": accounts})
    cert, private_key = log_check.identity(access)
    template = (project / "infra/sealskin/entry-auth/Caddyfile.example").read_text()
    template = template.replace("admin off", "admin off\n    auto_https off", 1)
    template = template.replace("mybrowser.example.com, mysession.example.com {",
                                args.entry_origin + ", " + args.session_origin + " {\n    bind 127.0.0.1\n    tls " + str(cert) + " " + str(private_key))
    template = template.replace("127.0.0.1:8080", config["listen_address"])
    (access / "Caddyfile").write_text(template)
    environment = dict(os.environ, XDG_CONFIG_HOME=str(access / "caddy-config"), XDG_DATA_HOME=str(access / "caddy-data"))
    check = subprocess.run(["caddy", "adapt", "--config", str(access / "Caddyfile"), "--adapter", "caddyfile", "--validate"],
                           env=environment, capture_output=True)
    (access / "caddy-validation.log").write_bytes(check.stderr)
    assert check.returncode == 0, "QA frontend Caddy configuration rejected"
    for name, command, env in [
            ("adapter", [str(qa / "bin/profile-adapter"), "--config", str(qa / "adapter-config.json")], None),
            ("front-caddy", ["caddy", "run", "--config", str(access / "Caddyfile"), "--adapter", "caddyfile"], environment)]:
        with (qa / (name + ".log")).open("ab") as output:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, start_new_session=True, env=env)
        network.write_json(qa / (name + "-pid.json"), {"pid": process.pid})

    def ready():
        connection = http.client.HTTPConnection("127.0.0.1", 29110, timeout=3)
        try:
            connection.request("GET", "/readyz", headers={"Host": entry.netloc})
            response = connection.getresponse()
            response.read()
            return response.status == 200
        finally:
            connection.close()
    network.wait(ready, "private TLS control and authenticated entry", seconds=45)
    result = {"result": "PASS", "profiles": [p["id"] for p in config["profiles"]], "entry_origin": args.entry_origin,
              "session_origin": args.session_origin, "controller_image": controller["Image"], "production_mutations": 0}
    network.write_json(access / "prepared.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
