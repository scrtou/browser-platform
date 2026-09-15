"""Legacy production backup boundaries with real age, isolated files and API fixtures."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from test_secure_backup import backup, file, rewrite_archive, setup, source_arguments

real_require_stopped = backup.home_backup.require_stopped


@pytest.fixture
def legacy(setup, monkeypatch):
    args, root = setup
    control_root = source_arguments(args, root, monkeypatch)
    shutil.rmtree(args.sealskin_config / "proxy-secret-store")
    (args.sealskin_config / "profile-secret-store.json").unlink()
    file(args.sealskin_config / "network-secrets/username", b"qa-legacy-user")
    file(args.sealskin_config / "network-secrets/password", b"qa-legacy-password")
    worker_id, controller_id = "b" * 64, "c" * 64
    worker_image = "sha256:" + "e" * 64
    session = "11111111-2222-4333-8444-555555555555"
    operation = "a" * 32
    calls = []

    def set_status(status, *, op=operation, identity=True):
        value = {"version": 1, "bindings": {"qa": {"profile_id": "qa", "home_name": "qa-home",
            "application_id": "qa-app", "status": status, "operation_id": op,
            "session_id": session if status == "running" else ""}}}
        if not identity:
            for key in ("home_name", "application_id"):
                value["bindings"]["qa"].pop(key)
        file(root / "adapter/state.json", backup.canonical(value))
        return value

    def current():
        return json.loads((root / "adapter/state.json").read_bytes())["bindings"]["qa"]

    def control(_socket, profile, action="inspect"):
        assert profile == "qa" and action == "inspect"
        calls.append(("control", action))
        state = current()
        return 200, {"result": {"profile_id": "qa", "status": state["status"], "session_id": state["session_id"], "orphans": 0,
            "workers": 1 if state["status"] == "running" else 0,
            "records": 1 if state["status"] == "running" else 0, "resources": 0}}

    containers = [
        {"Id": worker_id, "Image": worker_image, "State": {"Running": True, "Paused": False,
            "StartedAt": "2026-09-15T01:00:00Z"}, "HostConfig": {"AutoRemove": True},
         "Config": {"Env": ["PUID=1000", "TZ=Asia/Taipei", "PASSWORD=qa-secret-never-in-snapshot",
                            "SELKIES_MASTER_TOKEN=qa-master-never-in-snapshot"]},
         "Mounts": [{"Source": str(args.storage / "qa-owner/qa-home"), "Destination": "/config"}]},
        {"Id": controller_id, "Image": "sha256:" + "f" * 64,
         "State": {"Running": True, "Paused": False, "StartedAt": "2026-09-15T00:00:00Z"},
         "Mounts": [{"Source": str(control_root), "Destination": "/config"}]}]

    def docker(*command):
        calls.append(("docker", *command))
        if command == ("ps", "-aq"):
            return "\n".join(c["Id"] for c in containers)
        if command[0] == "inspect":
            return json.dumps([c for identifier in command[1:] for c in containers if c["Id"] == identifier])
        if command[:2] == ("image", "inspect"):
            return worker_image if command[2] == worker_image else ""
        raise AssertionError("unexpected Docker mutation")

    monkeypatch.setattr(backup.home_backup, "control", control)
    monkeypatch.setattr(backup.home_backup, "docker", docker)
    monkeypatch.setattr(backup.home_backup, "require_stopped", real_require_stopped)
    file(root / "adapter/state.json.lock", b"")
    set_status("running")
    snapshot_args = SimpleNamespace(**{**vars(args), "output": root / "legacy-snapshot.json"})
    result = backup.snapshot_legacy(snapshot_args)
    assert result["runtime_differs_from_configured_image"] and not result["home_contents_read"]
    args.legacy_snapshot = snapshot_args.output
    set_status("stopped")
    return args, root, set_status, containers, calls


def test_legacy_age_roundtrip_keeps_data_keys_and_actual_old_image(legacy):
    args, root, _, _, calls = legacy
    created = backup.create(args)
    assert created["archive_format"] == backup.LEGACY_FORMAT
    assert b"qa-browser-storage-content" not in args.archive.read_bytes()
    assert b"qa-service-identity" not in args.archive.read_bytes()
    assert b"qa-legacy-password" not in args.archive.read_bytes()
    assert backup.verify(args)["archive_format"] == backup.LEGACY_FORMAT
    result = backup.restore(args)
    assert result["offline_only"] and not result["ready_to_activate"]
    assert (args.target / ".legacy-recovery-pending.json").is_file()
    assert not (args.target / "control/proxy-secret-store").exists()
    assert not (args.target / "environment").exists()
    for name in ("cookies.sqlite", "hardlink-copy"):
        assert (args.target / "home" / name).read_bytes() == b"qa-browser-storage-content"
    assert (args.target / "control/ssl/server_key.pem").read_bytes() == b"qa-service-identity"
    assert (args.target / "adapter/client-private.pem").read_bytes() == b"qa-adapter-identity"
    assert (args.target / "control/network-secrets/password").read_bytes() == b"qa-legacy-password"
    recorded = json.loads((args.target / "runtime/snapshot.json").read_bytes())
    assert recorded["worker"]["image_id"] == "sha256:" + "e" * 64
    assert recorded["configured_image_id"] == "sha256:" + "d" * 64
    assert all(command[1] in {"inspect", "ps", "image"} for command in calls)
    with pytest.raises(backup.BackupError, match="BACKUP_LEGACY_OFFLINE_REBIND_REQUIRED"):
        backup.activate(args)
    assert not list(args.scratch_root.iterdir())


def test_snapshot_omits_display_secrets_and_never_hashes_home(legacy, monkeypatch):
    args, root, set_status, _, _ = legacy
    set_status("running")
    original_sha = backup.sha
    def checked_sha(path):
        assert not path.is_relative_to(args.storage)
        return original_sha(path)
    monkeypatch.setattr(backup, "sha", checked_sha)
    args.output = root / "second-snapshot.json"
    backup.snapshot_legacy(args)
    raw = args.output.read_bytes()
    assert b"qa-secret-never-in-snapshot" not in raw and b"qa-master-never-in-snapshot" not in raw
    assert b"PASSWORD" not in raw and b"MASTER_TOKEN" not in raw
    assert args.output.stat().st_mode & 0o777 == 0o600


def test_running_legacy_home_is_not_archived(legacy):
    args, _, set_status, _, _ = legacy
    set_status("running")
    with pytest.raises(SystemExit):
        backup.create(args)
    assert not args.archive.exists()


def test_readable_public_key_keeps_mode_and_private_key_stays_private(legacy):
    args, root, _, _, _ = legacy
    (root / "adapter/server-public.pem").chmod(0o644)
    backup.create(args)
    backup.restore(args)
    assert (args.target / "adapter/server-public.pem").stat().st_mode & 0o777 == 0o644
    assert (args.target / "adapter/client-private.pem").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("name,mode", [("server-public.pem", 0o666), ("client-private.pem", 0o644)])
def test_writable_public_or_readable_private_key_is_rejected(legacy, name, mode):
    args, root, _, _, _ = legacy
    (root / "adapter" / name).chmod(mode)
    with pytest.raises(backup.BackupError, match="BACKUP_KEY_FILE_UNSAFE"):
        backup.create(args)
    assert not args.archive.exists()


@pytest.mark.parametrize("source", ["config", "applications", "policies"])
def test_snapshot_input_drift_refuses_before_encryption(legacy, source):
    args, _, _, _, _ = legacy
    path = {"config": args.config, "applications": args.sealskin_config / "installed_apps.yml",
            "policies": args.sealskin_config / "profile-network-policies.json"}[source]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(backup.BackupError, match="BACKUP_LEGACY_SNAPSHOT_MISMATCH"):
        backup.create(args)
    assert not args.archive.exists()


def test_later_stopped_generation_cannot_reuse_earlier_runtime_snapshot(legacy):
    args, _, set_status, _, _ = legacy
    set_status("stopped", op="d" * 32)
    with pytest.raises(backup.BackupError, match="BACKUP_LEGACY_GENERATION_CHANGED"):
        backup.create(args)
    assert not args.archive.exists()


def test_old_journal_without_optional_home_app_fields_can_roundtrip(legacy):
    args, root, set_status, _, _ = legacy
    set_status("running", identity=False)
    args.output = root / "original-journal-snapshot.json"
    original_journal = (root / "adapter/state.json").read_bytes()
    backup.snapshot_legacy(args)
    assert (root / "adapter/state.json").read_bytes() == original_journal
    assert json.loads(args.output.read_bytes())["binding_identity"] == {}
    args.legacy_snapshot, args.output = args.output, args.archive
    set_status("stopped", identity=False)
    backup.create(args)
    assert backup.restore(args)["offline_only"]
    restored = json.loads((args.target / "adapter/state.json").read_bytes())["bindings"]["qa"]
    assert "home_name" not in restored and "application_id" not in restored


@pytest.mark.parametrize("field", ["home_name", "application_id", "profile_id"])
def test_nonempty_journal_identity_conflict_blocks_snapshot(legacy, field):
    args, root, set_status, _, _ = legacy
    state = set_status("running")
    state["bindings"]["qa"][field] = "other"
    file(root / "adapter/state.json", backup.canonical(state))
    args.output = root / "conflicting-snapshot.json"
    with pytest.raises(backup.BackupError, match="BACKUP_LEGACY_RUNNING_BINDING_REQUIRED"):
        backup.snapshot_legacy(args)
    assert not args.output.exists()


def test_stopped_journal_cannot_drop_snapshotted_identity(legacy):
    args, _, set_status, _, _ = legacy
    set_status("stopped", identity=False)
    with pytest.raises(backup.BackupError, match="BACKUP_LEGACY_GENERATION_CHANGED"):
        backup.create(args)
    assert not args.archive.exists()


@pytest.mark.parametrize("field,value", [("profile_id", "other"), ("records", 0), ("orphans", 1)])
def test_snapshot_requires_verified_adapter_ownership(legacy, monkeypatch, field, value):
    args, root, set_status, _, _ = legacy
    set_status("running")
    original = backup.home_backup.control
    def control(*arguments):
        status, result = original(*arguments)
        result["result"][field] = value
        return status, result
    monkeypatch.setattr(backup.home_backup, "control", control)
    args.output = root / "unverified-snapshot.json"
    with pytest.raises(backup.BackupError, match="BACKUP_LEGACY_RUNNING_BINDING_REQUIRED"):
        backup.snapshot_legacy(args)
    assert not args.output.exists()


@pytest.mark.parametrize("damage", ["profile", "worker_image", "secret_environment", "permissions", "symlink"])
def test_wrong_or_unsafe_runtime_snapshot_refused(legacy, damage):
    args, root, _, _, _ = legacy
    value = json.loads(args.legacy_snapshot.read_bytes())
    if damage == "profile": value["profile"] = "other"
    if damage == "worker_image": value["worker"]["image_id"] = "tag:latest"
    if damage == "secret_environment": value["worker"]["environment"]["PASSWORD"] = "injected-password"
    file(args.legacy_snapshot, backup.canonical(value))
    if damage == "permissions": args.legacy_snapshot.chmod(0o644)
    if damage == "symlink":
        alternate = root / "linked-snapshot.json"
        alternate.symlink_to(args.legacy_snapshot)
        args.legacy_snapshot = alternate
    with pytest.raises(backup.BackupError):
        backup.create(args)
    assert not args.archive.exists()


@pytest.mark.parametrize("modern", ["store", "store_config", "session_key", "access", "secret_ref", "sealed", "display_version"])
def test_modern_secret_paths_cannot_downgrade_to_legacy(legacy, modern):
    args, _, _, _, _ = legacy
    if modern == "store": (args.sealskin_config / "proxy-secret-store").mkdir(mode=0o700)
    if modern == "store_config": file(args.sealskin_config / "profile-secret-store.json", b"{}")
    if modern == "session_key": (args.sealskin_config / "session-secrets").mkdir(mode=0o700)
    if modern == "access":
        config = json.loads(args.config.read_bytes()); config["access"] = {"users_file": "current-users.json"}
        file(args.config, backup.canonical(config))
    if modern == "secret_ref":
        file(args.sealskin_config / "profile-network-policies.json", b'{"password_secret_ref":"secret://qa/password/1"}')
    if modern == "sealed": file(args.sealskin_config / "sessions.yml", b"session_state_version: 1\n")
    if modern == "display_version": file(args.sealskin_config / "sessions.yml", b"qa-session:\n  display_secret_version: 1\n")
    with pytest.raises(backup.BackupError, match="BACKUP_(LEGACY_MODE_FORBIDDEN|SESSION_STATE_INVALID)"):
        backup.create(args)
    assert not args.archive.exists()


def test_modern_store_created_during_encryption_prevents_publication(legacy, monkeypatch):
    args, _, _, _, _ = legacy
    calls = 0
    def stopped(*arguments):
        nonlocal calls
        calls += 1
        result = real_require_stopped(*arguments)
        if calls == 2:
            (args.sealskin_config / "proxy-secret-store").mkdir(mode=0o700)
        return result
    monkeypatch.setattr(backup.home_backup, "require_stopped", stopped)
    with pytest.raises(backup.BackupError, match="BACKUP_LEGACY_MODE_FORBIDDEN"):
        backup.create(args)
    assert not args.archive.exists() and not list(args.archive.parent.glob(".encrypted-backup-*"))


@pytest.mark.parametrize("damage", ["ciphertext", "truncated", "identity"])
def test_legacy_authentication_failure_creates_no_restore_target(legacy, damage):
    args, root, _, _, _ = legacy
    backup.create(args)
    if damage == "identity":
        import subprocess
        args.identity = root / "wrong-identity"
        subprocess.run([str(args.age.with_name("age-keygen")), "-o", str(args.identity)], capture_output=True, check=True)
    else:
        raw = bytearray(args.archive.read_bytes())
        if damage == "ciphertext": raw[len(raw) // 2] ^= 1
        else: raw = raw[:-32]
        args.archive.write_bytes(raw)
    with pytest.raises(backup.BackupError, match="BACKUP_AUTHENTICATION_FAILED"):
        backup.restore(args)
    assert not args.target.exists() and not list(args.scratch_root.iterdir())


@pytest.mark.parametrize("damage", ["content", "link", "format", "store_member", "journal"])
def test_legacy_authenticated_but_invalid_members_rejected_before_restore(legacy, damage):
    args, _, _, _, _ = legacy
    backup.create(args)
    replacement = {}
    def change(member, raw):
        if damage == "content" and member.name == "home/cookies.sqlite": raw = b"changed"
        if damage == "link" and member.name == "home/relative-link": member.linkname = "../../outside"
        if damage == "store_member" and member.name == "control/keys/private.pem":
            member.name = "control/proxy-secret-store/store.json"
        if damage == "journal" and member.name == "adapter/state.json":
            value = json.loads(raw); value["bindings"]["qa"]["operation_id"] = "d" * 32
            raw = backup.canonical(value)
            replacement.update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        if member.name == "manifest.json":
            value = json.loads(raw)
            if damage == "format": value["format"] = backup.FORMAT
            if damage == "store_member":
                value["entries"]["control/proxy-secret-store/store.json"] = value["entries"].pop("control/keys/private.pem")
            if damage == "journal": value["entries"]["adapter/state.json"].update(replacement)
            raw = backup.canonical(value)
        return member, raw
    rewrite_archive(args, change)
    with pytest.raises(backup.BackupError):
        backup.restore(args)
    assert not args.target.exists()


def test_legacy_existing_archive_and_restore_directory_preserved(legacy):
    args, _, _, _, _ = legacy
    backup.create(args)
    original = args.archive.read_bytes()
    with pytest.raises(backup.BackupError, match="BACKUP_OUTPUT_EXISTS"):
        backup.create(args)
    assert args.archive.read_bytes() == original
    args.target.mkdir(mode=0o700)
    file(args.target / "keep", b"existing recovery")
    with pytest.raises(backup.BackupError, match="BACKUP_RESTORE_TARGET_EXISTS"):
        backup.restore(args)
    assert (args.target / "keep").read_bytes() == b"existing recovery"


@pytest.mark.parametrize("damage", ["extra_worker", "restart"])
def test_snapshot_requires_one_stable_worker_and_controller(legacy, monkeypatch, damage):
    args, root, set_status, containers, _ = legacy
    set_status("running")
    args.output = root / "rejected-snapshot.json"
    if damage == "extra_worker":
        extra = copy.deepcopy(containers[0]); extra["Id"] = "d" * 64; containers.append(extra)
    else:
        original = backup.home_backup.docker
        inspections = 0
        def docker(*command):
            nonlocal inspections
            value = original(*command)
            if command[0] == "inspect":
                inspections += 1
            if command[0] == "inspect" and inspections == 2:
                decoded = json.loads(value); decoded[0]["State"]["StartedAt"] = "2026-09-15T02:00:00Z"
                value = json.dumps(decoded)
            return value
        monkeypatch.setattr(backup.home_backup, "docker", docker)
    with pytest.raises(backup.BackupError):
        backup.snapshot_legacy(args)
    assert not args.output.exists()


def test_legacy_cli_uses_real_socket_age_and_offline_restore(legacy):
    """Exercise subprocess entry points; only Docker inventory is a fixture."""
    from http.server import BaseHTTPRequestHandler
    from socketserver import UnixStreamServer
    import threading

    args, root, set_status, containers, _ = legacy
    socket_path = args.scratch_root / "adapter.sock"
    config = json.loads(args.config.read_bytes())
    config["control_socket"] = str(socket_path)
    file(args.config, backup.canonical(config))
    file(args.sealskin_config / "installed_apps.yml", backup.canonical([
        {"id": "qa-app", "overrides": {"provider_config": {"image": "sha256:" + "d" * 64}}}]))
    (root / "adapter/server-public.pem").chmod(0o644)
    inventory = file(root / "docker-inventory.json", backup.canonical(containers))
    binary = file(root / "tools/docker", ("#!/usr/bin/python3\n"
        "import json,sys\n"
        f"containers=json.load(open({str(inventory)!r}))\n"
        "args=sys.argv[1:]\n"
        "if args == ['ps','-aq']: print('\\n'.join(c['Id'] for c in containers))\n"
        "elif args[0] == 'inspect': print(json.dumps([c for k in args[1:] for c in containers if c['Id']==k]))\n"
        "elif args[:2] == ['image','inspect']: print(args[2])\n"
        "else: raise SystemExit(1)\n").encode())
    binary.chmod(0o700)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/profiles/qa":
                self.send_error(404)
                return
            state = json.loads((root / "adapter/state.json").read_bytes())["bindings"]["qa"]
            running = state["status"] == "running"
            raw = backup.canonical({"result": {"profile_id": "qa", "status": state["status"],
                "session_id": state["session_id"], "workers": int(running), "records": int(running),
                "orphans": 0, "resources": 0}})
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_):
            pass

    server = UnixStreamServer(str(socket_path), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    command = [sys.executable, str(Path(backup.__file__)), "--help"]
    environment = {**os.environ, "PATH": str(binary.parent) + os.pathsep + os.environ["PATH"]}
    responses = []
    def cli(action, *options, success=True):
        result = subprocess.run([*command[:2], action, *map(str, options)], capture_output=True,
                                env=environment, timeout=20)
        assert result.returncode == (0 if success else 1), result.stderr.decode()
        assert result.stderr == b""
        responses.append(result.stdout)
        return json.loads(result.stdout)
    try:
        source = ["--config", args.config, "--storage", args.storage,
                  "--sealskin-config", args.sealskin_config, "--profile", "qa"]
        recorded = root / "cli-snapshot.json"
        set_status("running", identity=False)
        assert cli("snapshot-legacy", *source, "--output", recorded)["production_mutations"] == 0
        create = [*source, "--legacy-snapshot", recorded, "--age", args.age,
                  "--recipient", args.recipient, "--output", args.archive]
        assert cli("create-legacy", *create, success=False)["result"] == "FAIL"
        assert not args.archive.exists()
        set_status("stopped", identity=False)
        assert cli("create-legacy", *create)["archive_format"] == backup.LEGACY_FORMAT
        recovery = ["--age", args.age, "--archive", args.archive, "--identity", args.identity,
                    "--scratch-root", args.scratch_root]
        assert cli("verify", *recovery)["result"] == "BACKUP_VERIFIED"
        assert cli("restore", *recovery, "--target", args.target)["offline_only"]
        assert (args.target / "home/cookies.sqlite").read_bytes() == b"qa-browser-storage-content"
        assert (args.target / "control/network-secrets/password").read_bytes() == b"qa-legacy-password"
        for secret in (b"qa-legacy-password", b"qa-private-key-content", b"qa-service-identity", b"qa-secret-never-in-snapshot"):
            assert all(secret not in raw for raw in responses)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        socket_path.unlink()
