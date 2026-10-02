#!/usr/bin/env python3
"""Authenticated legacy Work migration QA on a prepared, isolated controller.

Copies an approved source definition into network-qa identities. Never accepts
production Homes. Evidence, generated keys and browser data remain under the
ignored QA root. `prepare` requires the current release snapshot and reviewed
source plan; `run` preserves failed evidence and does not clean up on failure.
"""

import argparse
import base64
import copy
import hashlib
import http.client
import http.cookies
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import subprocess
import tarfile
import time
from urllib.parse import urlencode, urlsplit, parse_qs
import uuid
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[3]
PROFILE = "network-qa-work-migration"
HOME = "network-qa-home-migration"
APP = "network-qa-work-migration-app"
ENTRY = "https://entry.r5d.test:29443"
SESSION = "https://session.r5d.test:29443"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


network = module("migration_network", PROJECT / "infra/sealskin/lifecycle/check-network-live.py")
work = module("migration_work", Path(__file__).with_name("check-work-direct.py"))
write = network.write_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scope(qa):
    assert qa.name == "qa" and "runtime" in qa.parts
    controller = json.loads(network.docker("inspect", network.SERVER).stdout)[0]
    assert controller["Config"]["Labels"]["io.browser-platform.qa"] == "network-20260913"
    for dest, source in (("/config", qa / "config"), ("/storage", qa / "storage")):
        assert any(m["Destination"] == dest and m["Source"] == str(source) for m in controller["Mounts"])
    return controller


def clients(qa):
    value = json.loads((qa / "admin.json").read_text())
    return network.SecureClient(qa), network.SecureClient(
        qa, username=value["username"], private=value["private_key"].encode(),
        public=value["server_public_key"].encode())


def app_read(admin):
    status, values = admin.call("GET", "/api/admin/apps/installed")
    assert status == 200, "QA app read failed"
    value = next(item for item in values if item["id"] == APP)
    return {k: v for k, v in value.items() if k not in ("image_sha", "last_checked_at", "pull_status")}


def backup(qa, name, age_dir):
    """Encrypted QA regular-file snapshot; independent restore, no activation."""
    home = qa / "storage/network-qa" / HOME
    target = qa.parent / name
    target.mkdir(mode=0o700)
    key = target / "identity.txt"
    generated = subprocess.run([str(age_dir / "age-keygen"), "-o", str(key)], capture_output=True)
    assert generated.returncode == 0
    recipient = subprocess.run([str(age_dir / "age-keygen"), "-y", str(key)], capture_output=True, check=True).stdout.strip()
    manifest, excluded = {}, []
    archive = target / "home.tar"
    with tarfile.open(archive, "w") as tf:
        for path in sorted(home.rglob("*")):
            rel = str(path.relative_to(home))
            if path.is_file() and not path.is_symlink():
                manifest[rel] = sha(path)
                tf.add(path, arcname=rel, recursive=False)
            elif not path.is_dir():
                excluded.append(rel)
    encrypted = target / "home.tar.age"
    subprocess.run([str(age_dir / "age"), "-r", recipient.decode(), "-o", str(encrypted), str(archive)], check=True, capture_output=True)
    restored_tar = target / "restored.tar"
    subprocess.run([str(age_dir / "age"), "-d", "-i", str(key), "-o", str(restored_tar), str(encrypted)], check=True, capture_output=True)
    assert sha(restored_tar) == sha(archive)
    restored = target / "restored-home"
    restored.mkdir(mode=0o700)
    with tarfile.open(restored_tar) as tf:
        for member in tf:
            dest = restored / member.name
            assert member.isfile() and dest.resolve().is_relative_to(restored)
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tf.extractfile(member) as src, dest.open("xb") as out:
                out.write(src.read())
    actual = {str(p.relative_to(restored)): sha(p) for p in restored.rglob("*") if p.is_file()}
    assert manifest == actual
    write(target / "restore.json", {"scope": "QA Home regular files only", "files": manifest,
          "excluded_nonregular": excluded, "independent_restore_equal": True, "activated": False})
    archive.unlink()
    restored_tar.unlink()
    return sha(encrypted), sha(target / "restore.json")


def approve(qa, source, revision, name, age_dir):
    backup_hash, restore_hash = backup(qa, name + "-backup", age_dir)
    plan = copy.deepcopy(source)
    plan.update(id=name, status="accepted", source_revision=revision,
                backup_sha256=backup_hash, restore_sha256=restore_hash)
    write(qa / "legacy-network-migrations.json", {"version": 1, "migrations": [plan]})
    write(qa.parent / (name + "-approved.json"), plan)
    return plan


def prepare(qa, args):
    controller = scope(qa)
    assert not (qa / "access").exists(), "preparation is not replayable"
    # The base network fixture only reads its registry. Management appends
    # require a private parent directory as well as private JSON files.
    (qa / "config/.config/sealskin").chmod(0o700)
    baseline = json.loads(args.baseline.read_text())
    assert controller["Image"] == json.loads((qa / "images.json").read_text())["controller"]
    assert sha(qa / "bin/profile-adapter") == baseline["adapter_sha256"]
    source = copy.deepcopy(json.loads(args.source_plan.read_text())["migrations"][0])
    definition = source["source_definition"]
    definition.update(id=PROFILE, application_id=APP, home_name=HOME, disabled=True)
    app = source["source_application"]
    app.update(id=APP, name="Isolated Work migration QA", source_app_id=APP, users=["network-qa"], groups=[], auto_update=False)
    provider = app["provider_config"]
    script = base64.b64encode(b"#!/bin/sh\nexec firefox --no-remote --profile /config/network-qa-profile --remote-debugging-port 9228 --new-window about:blank\n").decode()
    provider.update(custom_autostart_script_b64=script, custom_autostart_wayland_script_b64=script,
                    nvidia_support=False, dri3_support=False,
                    docker_overrides={"mem_limit": "1024m", "nano_cpus": 1500000000, "shm_size": "256m", "pids_limit": 512})
    for item in provider["env"]:
        if item["name"] == "SELKIES_ALLOWED_ORIGINS":
            item["value"] = SESSION
    allow = json.loads((qa / "allow.json").read_text())
    allow["images"] += [provider["image"], source["target_image"]]
    write(qa / "allow.json", allow)
    client, admin = clients(qa)
    assert client.call("POST", "/api/homedirs", {"home_name": HOME})[0] == 201
    assert admin.call("POST", "/api/admin/apps/installed", app)[0] == 201
    source["source_application"] = app_read(admin)
    home = qa / "storage/network-qa" / HOME
    (home / "network-qa-profile").mkdir(mode=0o700)
    (home / "qa-sentinel.txt").write_text(uuid.uuid4().hex + "\n")
    access = qa / "access"
    access.mkdir(mode=0o700)
    auth = module("migration_auth", Path(__file__).with_name("prepare-entry-auth.py"))
    auth.private_tls(qa, access, network)
    cfg = json.loads((qa / "adapter-config.json").read_text())
    cfg.update(public_base_url=ENTRY, profile_directory=str(qa / "profiles.json"),
               environment_catalog=str(qa / "environment-catalog.json"),
               legacy_network_migrations=str(qa / "legacy-network-migrations.json"), profiles=[definition])
    cfg["health"] = {"sample_interval_seconds": 0, "entry_hint": False}
    cfg["sealskin"].update(api_base_url="https://127.0.0.1:28443", public_session_base_url=SESSION, allow_unencrypted_http=False)
    admin_data = json.loads((qa / "admin.json").read_text())
    (access / "admin-private.pem").write_text(admin_data["private_key"])
    (access / "admin-private.pem").chmod(0o600)
    cfg["sealskin_admin"] = {"username": admin_data["username"], "client_private_key_file": str(access / "admin-private.pem")}
    cfg["direct_template"] = copy.deepcopy(baseline["direct"])
    cfg["direct_template"]["owner"] = "network-qa"
    cfg["access"] = {"users_file": str(access / "users.json"), "session_upstream_url": cfg["sealskin"]["api_base_url"],
                      "session_ca_file": str(access / "session-ca.pem"), "session_tls_name": "network.invalid",
                      "session_seconds": 3600, "ticket_seconds": 30}
    write(qa / "environment-catalog.json", {"version": 1, "artifacts": []})
    write(qa / "source.json", source)
    approve(qa, source, 1, "r7f-work-qa-first", args.age_dir)
    write(qa / "adapter-config.json", cfg)
    write(qa / "profiles.json", {"version": 1, "revision": 1, "browsers": [
        {**definition, "revision": 1, "status": "ready", "updated_at": datetime.now(timezone.utc).isoformat()}]})
    account = {"username": "work-qa-admin", "password": uuid.uuid4().hex + uuid.uuid4().hex}
    result = subprocess.run([str(qa / "bin/profile-accounts"), "put", "--config", str(qa / "adapter-config.json"),
                            "--user", account["username"], "--profiles", PROFILE, "--role", "admin"],
                            input=account["password"].encode(), capture_output=True)
    (access / "account-setup.log").write_bytes(result.stderr)
    assert result.returncode == 0, "QA account setup failed"
    write(access / "account.json", account)
    log_check = module("migration_log", Path(__file__).with_name("check-entry-log-boundary.py"))
    cert, key = log_check.identity(access)
    template = (PROJECT / "infra/sealskin/entry-auth/Caddyfile.example").read_text()
    template = template.replace("admin off", "admin off\n    auto_https off", 1)
    template = template.replace("mybrowser.example.com, mysession.example.com {", ENTRY + ", " + SESSION + " {\n    bind 127.0.0.1\n    tls " + str(cert) + " " + str(key))
    template = template.replace("127.0.0.1:8080", cfg["listen_address"])
    (access / "Caddyfile").write_text(template)
    for name, command, env in [
        ("adapter", [str(qa / "bin/profile-adapter"), "--config", str(qa / "adapter-config.json")], None),
        ("front-caddy", ["caddy", "run", "--config", str(access / "Caddyfile"), "--adapter", "caddyfile"],
         dict(os.environ, XDG_CONFIG_HOME=str(access / "caddy-config"), XDG_DATA_HOME=str(access / "caddy-data")))]:
        with (qa / (name + ".log")).open("ab") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
        write(qa / (name + "-pid.json"), {"pid": process.pid})
    network.wait(lambda: network.request("GET", "/readyz", headers={"Host": urlsplit(ENTRY).netloc}, port=29110)[0] == 200, "authenticated QA Adapter")
    write(qa.parent / "prepared.json", {"controller_image": controller["Image"], "adapter_sha256": sha(qa / "bin/profile-adapter"),
          "old_image": provider["image"], "target_image": source["target_image"], "profile": PROFILE,
          "fixture_changes": ["QA identities/origins", "BiDi autostart", "resource limits", "no production clipboard mounts"]})
    print("QA authenticated migration fixture ready", flush=True)


class Browser:
    def __init__(self, qa):
        self.qa, self.cookies = qa, http.cookies.SimpleCookie()
        self.context = ssl.create_default_context(cafile=str(qa / "access/cert.pem"))

    def request(self, method, path, fields=None):
        connection = http.client.HTTPSConnection("entry.r5d.test", 29443, context=self.context, timeout=150)
        connection.sock = self.context.wrap_socket(socket.create_connection(("127.0.0.1", 29443), timeout=150), server_hostname="entry.r5d.test")
        headers = {"Origin": ENTRY}
        if self.cookies:
            headers["Cookie"] = "; ".join(k + "=" + v.value for k, v in self.cookies.items())
        body = None
        if fields is not None:
            body = urlencode(fields)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            raw = response.read()
            for k, v in response.getheaders():
                if k.lower() == "set-cookie":
                    self.cookies.load(v)
            return response.status, response.getheader("Location", ""), raw
        finally:
            connection.close()

    def csrf(self, path="/manage/"):
        status, _, raw = self.request("GET", path)
        assert status == 200, "QA form unavailable"
        return re.search(rb'name="csrf" value="([^"]+)"', raw).group(1).decode()

    def login(self):
        account = json.loads((self.qa / "access/account.json").read_text())
        status, _, _ = self.request("POST", "/auth/login", {**account, "csrf": self.csrf("/auth/login"), "next": "/manage/"})
        assert status == 303, "QA login failed"
        status, _, _ = self.request("POST", "/auth/reauth", {"password": account["password"], "csrf": self.csrf(), "next": "/manage/"})
        assert status == 303, "QA recent authentication failed"

    def action(self, action, **fields):
        fields = {"action": action, "csrf": self.csrf(), **fields}
        status, location, _ = self.request("POST", "/manage/browsers/" + PROFILE, fields)
        notice = parse_qs(urlsplit(location).query).get("notice", [""])[0]
        assert status == 303, "QA management action failed"
        return notice


def run(qa, args):
    scope(qa)
    client, admin = clients(qa)
    browser = Browser(qa)
    browser.login()
    results = []

    def passed(name, **details):
        results.append({"check": name, "result": "PASS", **details})
        write(qa.parent / "results.json", results)
        print(name + ": PASS", flush=True)

    def record():
        return next(p for p in json.loads((qa / "profiles.json").read_text())["browsers"] if p["id"] == PROFILE)

    def inventory():
        status, value = client.call("GET", "/api/profile-runtime/" + HOME)
        assert status == 200
        return value

    def stop():
        assert browser.action("stop") == "stopped", "QA normal stop unconfirmed"
        value = inventory()
        assert all(not value[k] for k in ("records", "workers", "resources"))
        return value

    def launch(name):
        status, _, raw = browser.request("GET", "/browser/" + PROFILE + "/")
        assert status == 200, "QA fixed entry form failed"
        fields = dict((k.decode(), v.decode()) for k, v in re.findall(rb'name="(csrf|launch_plan)" value="([^"]+)"', raw))
        assert set(fields) == {"csrf", "launch_plan"}
        status, _, _ = browser.request("POST", "/browser/" + PROFILE + "/start", fields)
        assert status in (302, 303), "QA fixed entry failed"
        value = inventory()
        assert len(value["workers"]) == len(value["records"]) == 1 and len(value["resources"]) == 5
        worker = value["workers"][0]["instance_id"]
        work.wait(lambda: work.process_identity(network, worker)["native_wayland"], "native Wayland Firefox", seconds=90)
        work.wait(lambda: work.bidi_value(network, worker, "document.title", navigate="https://example.com/") == "Example Domain", "public browser page", seconds=90)
        identity = work.process_identity(network, worker)
        inspect = json.loads(network.docker("inspect", worker).stdout)[0]
        source = json.loads((qa / "source.json").read_text())
        assert inspect["Image"] == source["target_image"]
        write(qa.parent / (name + "-runtime.json"), {"inventory": value, "browser": identity, "container_id": inspect["Id"]})
        return worker, value, identity

    source = json.loads((qa / "source.json").read_text())
    plan = json.loads((qa / "legacy-network-migrations.json").read_text())["migrations"][0]
    assert plan["source_revision"] == 1
    assert record()["revision"] == 1 or any(record().get(k, {}).get("base_revision") == 1 for k in ("pending_migration", "last_migration"))
    assert browser.action("legacy_network_migrate", migration_id=plan["id"], revision=1,
                          idempotency_key="r7f-work-qa-migrate-1") == "network_applied"
    migrated = app_read(admin)
    expected = copy.deepcopy(source["source_application"])
    expected["provider_config"].update(image=source["target_image"], network_policy_id=record()["network_policy_id"],
                                        network_policy_sha256=record()["network_policy_sha256"])
    assert expected == migrated
    passed("authenticated migration preserves full app except approved image and policy")
    assert browser.action("enable", revision=record()["revision"]) in ("enabled", "unchanged")
    worker, first, identity = launch("first")
    assert not any(work.raw_bypass(network, worker).values())
    passed("native Wayland public HTTPS and four explicit bypass rejections")
    marker = uuid.uuid4().hex
    write(qa.parent / "marker.json", {"value": marker})
    expression = """(async()=>{localStorage.setItem('r7f-marker',MARKER);document.cookie='r7f_marker='+MARKER+'; Path=/; Max-Age=31536000; SameSite=Lax; Secure';let db=await new Promise((ok,fail)=>{let q=indexedDB.open('r7f-work',1);q.onupgradeneeded=()=>q.result.createObjectStore('values');q.onsuccess=()=>ok(q.result);q.onerror=()=>fail(q.error)});await new Promise((ok,fail)=>{let t=db.transaction('values','readwrite');t.objectStore('values').put(MARKER,'marker');t.oncomplete=ok;t.onerror=()=>fail(t.error);t.onabort=()=>fail(t.error)});db.close();return true})()""".replace("MARKER", json.dumps(marker))
    assert work.bidi_value(network, worker, expression) is True
    read_expression = """(async()=>{let db=await new Promise((ok,fail)=>{let q=indexedDB.open('r7f-work',1);q.onsuccess=()=>ok(q.result);q.onerror=()=>fail(q.error)});let idb=await new Promise((ok,fail)=>{let q=db.transaction('values').objectStore('values').get('marker');q.onsuccess=()=>ok(q.result);q.onerror=()=>fail(q.error)});db.close();let cookie=(document.cookie.split('; ').find(v=>v.startsWith('r7f_marker='))||'').slice(11);return JSON.stringify({local:localStorage.getItem('r7f-marker'),cookie,idb})})()"""

    def stores(worker):
        assert json.loads(work.bidi_value(network, worker, read_expression)) == {"local": marker, "cookie": marker, "idb": marker}

    stores(worker)
    stop()
    worker2, second, identity2 = launch("rebuilt")
    assert first["records"][0]["operation_id"] != second["records"][0]["operation_id"]
    assert identity["start"] != identity2["start"]
    stores(worker2)
    passed("normal stop releases all resources and new generation preserves three stores")
    resources = {r["kind"]: r["id"] for r in second["resources"]}
    relay = json.loads(network.docker("inspect", resources["relay"]).stdout)[0]
    labels = relay["Config"]["Labels"]
    assert labels["io.browser-platform.owner"] == "network-qa" and labels["io.browser-platform.home"] == HOME
    network.docker("stop", "-t", "5", resources["relay"])
    work.wait(lambda: client.call("GET", "/api/profile-runtime/" + HOME + "/health?upstream=true")[1]
              .get("network", {}).get("relay", {}).get("status") == "fail", "gateway failure health")
    assert not any(work.raw_bypass(network, worker2).values())
    passed("isolated gateway failure remains fail closed")
    stop()
    assert browser.action("disable", revision=record()["revision"]) == "disabled"
    home = qa / "storage/network-qa" / HOME
    before_files = {str(p.relative_to(home)): sha(p) for p in home.rglob("*") if p.is_file() and not p.is_symlink()}
    stable_paths = [qa / "access/users.json", qa / "adapter-state.json", qa / "config/.config/sealskin/profile-network-policies.json"]
    stable = {str(p): sha(p) for p in stable_paths}
    assert browser.action("legacy_network_rollback", migration_id=plan["id"], revision=record()["revision"],
                          idempotency_key="r7f-work-qa-rollback-1") == "network_applied"
    assert app_read(admin) == source["source_application"]
    restored = record()
    metadata = {"revision", "updated_at", "updated_by", "status", "last_migration"}
    assert {k: v for k, v in restored.items() if k not in metadata} == source["source_definition"]
    assert before_files == {str(p.relative_to(home)): sha(p) for p in home.rglob("*") if p.is_file() and not p.is_symlink()}
    assert stable == {str(p): sha(p) for p in stable_paths}
    assert all(not inventory()[k] for k in ("records", "workers", "resources"))
    passed("actual rollback restores exact source app and definition and preserves Home journal accounts policies", files=len(before_files))
    plan2 = approve(qa, source, restored["revision"], "r7f-work-qa-second", args.age_dir)
    passed("fresh QA encrypted regular-file snapshot independently restores", files=len(before_files))
    assert browser.action("legacy_network_migrate", migration_id=plan2["id"], revision=record()["revision"],
                          idempotency_key="r7f-work-qa-migrate-2") == "network_applied"
    assert browser.action("enable", revision=record()["revision"]) == "enabled"
    worker3, third, _ = launch("after-rollback")
    stores(worker3)
    assert second["records"][0]["operation_id"] != third["records"][0]["operation_id"]
    passed("reapproved migration after rollback retains all three browser stores")
    stop()
    passed("final QA normal stop confirms zero runtime resources")


def cleanup(qa):
    """Retire only the verified, stopped QA scope, retaining disk evidence."""
    scope(qa)
    results = json.loads((qa.parent / "results.json").read_text())
    assert results[-1]["check"] == "final QA normal stop confirms zero runtime resources"
    client, _ = clients(qa)
    status, sessions = client.call("GET", "/api/sessions")
    assert status == 200 and not sessions
    scope_id = hashlib.sha256(str(qa / "config/.config/sealskin/sessions.yml").encode()).hexdigest()
    selector = "label=io.browser-platform.scope=" + scope_id
    assert not network.docker("ps", "-aq", "--filter", selector).stdout.strip()
    assert not network.docker("network", "ls", "-q", "--filter", selector).stdout.strip()
    assert not list((qa / "config/.config/sealskin/profile-network-runtime").glob("*.json"))
    display = Path(json.loads((qa / "allow.json").read_text())["display_runtime_root"])
    assert display.parent == Path("/dev/shm") and not display.is_symlink()
    assert not list(display.iterdir())
    fixtures = {network.SERVER: (qa / "config", "/config"), "network-qa-upstream": (qa / "upstream", "/qa")}
    names = network.docker("ps", "-a", "--filter", "label=io.browser-platform.qa=network-20260913", "--format", "{{.Names}}").stdout.splitlines()
    assert set(names) == set(fixtures)
    inspected = json.loads(network.docker("inspect", *fixtures).stdout)
    ids = {v["Id"] for v in inspected}
    volumes = []
    for value in inspected:
        source, target = fixtures[value["Name"].lstrip("/")]
        assert value["Config"]["Labels"]["io.browser-platform.qa"] == "network-20260913"
        assert any(m["Source"] == str(source) and m["Destination"] == target for m in value["Mounts"])
        for mount in value["Mounts"]:
            if mount["Type"] == "volume":
                name = mount["Name"]
                assert re.fullmatch(r"[a-f0-9]{64}", name)
                refs = network.docker("ps", "-aq", "--no-trunc", "--filter", "volume=" + name).stdout.split()
                assert set(refs) <= ids
                volumes.append(name)
    bridge = json.loads(network.docker("network", "inspect", "browser-platform-network-qa").stdout)[0]
    assert bridge["Labels"]["io.browser-platform.qa"] == "network-20260913" and set(bridge["Containers"]) == ids
    write(qa.parent / "cleanup-fixtures.json", inspected)
    stage = module("migration_stage", Path(__file__).with_name("stage-entry-auth.py"))
    stage.stop_process(qa, "front-caddy", "caddy")
    stage.stop_process(qa, "adapter", qa / "bin/profile-adapter")
    for value in inspected:
        network.docker("stop", "-t", "10", value["Id"])
        network.docker("rm", "-v", value["Id"])
    network.docker("network", "rm", bridge["Id"])
    stage.stop_process(qa, "proxy", PROJECT / "infra/sealskin/lifecycle/qa-network-docker-proxy.py")
    for path in (Path(network.SOCKET), Path("/tmp/browser-platform-network-qa-docker.sock")):
        if path.exists():
            assert stat.S_ISSOCK(path.lstat().st_mode) and path.stat().st_uid == os.getuid()
            with socket.socket(socket.AF_UNIX) as probe:
                probe.settimeout(.5)
                assert probe.connect_ex(str(path)) != 0
            path.unlink()
    assert display.stat().st_uid == os.getuid() and stat.S_IMODE(display.stat().st_mode) == 0o700
    display.rmdir()
    assert all(network.docker("volume", "inspect", name, check=False).returncode != 0 for name in volumes)
    for port in (28110, 28443, 29110, 29443):
        with socket.socket() as probe:
            probe.settimeout(.5)
            assert probe.connect_ex(("127.0.0.1", port)) != 0
    write(qa.parent / "cleanup.json", {"result": "PASS", "runtime_resources": 0,
          "fixtures_removed": sorted(fixtures), "fixture_network_removed": True,
          "anonymous_volumes_removed": len(volumes), "processes_stopped": ["adapter", "front-caddy", "proxy"],
          "display_tmpfs_removed": True, "qa_ports_closed": True, "private_evidence_retained": True})
    print("isolated QA cleanup: PASS", flush=True)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run", "cleanup"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-plan", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--age-dir", type=Path)
    args = parser.parse_args()
    qa = args.root.resolve()
    if args.phase == "prepare":
        assert args.source_plan and args.baseline and args.age_dir
        prepare(qa, args)
    elif args.phase == "run":
        assert args.age_dir
        assert not (qa.parent / "results.json").exists(), "preserve prior run evidence"
        run(qa, args)
    else:
        cleanup(qa)


if __name__ == "__main__":
    main()
