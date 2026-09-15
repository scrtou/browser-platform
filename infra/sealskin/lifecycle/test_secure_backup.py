"""Encrypted backup failure/restore tests; set BROWSER_PLATFORM_AGE to age v1.2.1."""
import hashlib
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("secure_backup", Path(__file__).with_name("secure-backup.py"))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def file(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


@pytest.fixture
def setup(tmp_path, monkeypatch):
    age = Path(os.environ.get("BROWSER_PLATFORM_AGE") or shutil.which("age") or "")
    if not age.is_file():
        pytest.skip("age v1.2.1 is required")
    tmp_path.chmod(0o700)
    identity = tmp_path / "identity"
    subprocess.run([str(age.with_name("age-keygen")), "-o", str(identity)], capture_output=True, check=True)
    recipient = subprocess.check_output([str(age.with_name("age-keygen")), "-y", str(identity)], text=True).strip()
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    home = root / "home"
    home.mkdir(mode=0o700)
    file(home / "cookies.sqlite", b"qa-browser-storage-content")
    os.link(home / "cookies.sqlite", home / "hardlink-copy")
    (home / "relative-link").symlink_to("cookies.sqlite")
    (home / "container-link").symlink_to("/config/cookies.sqlite")
    store = root / "control/proxy-secret-store"
    (store / "versions").mkdir(parents=True, mode=0o700)
    store.chmod(0o700)
    store.parent.chmod(0o700)
    (store / "revocations").mkdir(mode=0o700)
    key = file(root / "key-material/secret-store.key", os.urandom(32))
    metadata = {"version": 1, "store_id": "a" * 32, "key_sha256": backup.sha(key)}
    file(store / "store.json", backup.canonical(metadata))
    file(store / "versions/test.json", b'{"ciphertext":"encrypted-version"}')
    file(root / "control/keys/private.pem", b"qa-private-key-content")
    for leaf in ("installed_apps.yml", "profile-network-policies.json", "profile-secret-store.json"):
        file(root / "control" / leaf, b"{}")
    artifact = file(root / "environment/artifact.json", b'{"id":"qa-fixed-artifact"}')
    acceptance = file(root / "environment/acceptance.json", b'{"status":"pass"}')
    file(root / "adapter/config.json", b'{"reference":"secret://qa/password/1"}')
    file(root / "adapter/state.json", b'{"operations":[]}')
    for leaf in ("client-private.pem", "server-public.pem"):
        file(root / "adapter" / leaf, b"qa-adapter-identity")
    for leaf in ("server_key.pem", "proxy_key.pem", "proxy_cert.pem"):
        file(root / "control/ssl" / leaf, b"qa-service-identity")
    file(root / "control/admin.json", b"qa-admin-recovery-identity")
    sources = {leaf: root / leaf for leaf in ("home", "adapter", "environment", "key-material", "control")}
    context = {"artifact_sha256": backup.sha(artifact), "acceptance_sha256": backup.sha(acceptance)}
    monkeypatch.setattr(backup, "collect_sources", lambda _: ({}, {"status": "stopped"}, context, sources))
    monkeypatch.setattr(backup.home_backup, "require_stopped", lambda *_: {"status": "stopped"})
    monkeypatch.setattr(backup.home_backup, "docker", lambda *_: "")
    scratch = Path(tempfile.mkdtemp(prefix="browser-platform-backup-test-", dir="/dev/shm"))
    args = SimpleNamespace(age=age, recipient=recipient, output=tmp_path / "bundle.age", profile="qa",
                           archive=tmp_path / "bundle.age", identity=identity, scratch_root=scratch,
                           target=tmp_path / "restored", bundle=tmp_path / "restored", current_store=store)
    try:
        yield args, root
    finally:
        shutil.rmtree(scratch)


def revocation(store, identifier, version=1):
    value = {"version": 1, "store_id": "a" * 32, "secret_id": identifier, "secret_version": version,
             "revoked": True, "operation_id": "b" * 32, "revoked_at": "2026-09-14T00:00:00Z"}
    leaf = hashlib.sha256(backup.canonical([identifier, version])).hexdigest() + ".json"
    return file(store / "revocations" / leaf, backup.canonical(value))


def rewrite_archive(args, change):
    plain = subprocess.check_output([str(args.age), "-d", "-i", str(args.identity), str(args.archive)])
    replacement = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(plain), mode="r:") as old, tarfile.open(fileobj=replacement, mode="w") as new:
        for member in old:
            contents = old.extractfile(member).read() if member.isfile() else None
            member, contents = change(member, contents)
            if contents is not None:
                member.size = len(contents)
            new.addfile(member, io.BytesIO(contents) if contents is not None else None)
    result = subprocess.run([str(args.age), "-r", args.recipient], input=replacement.getvalue(), capture_output=True, check=True)
    args.archive.write_bytes(result.stdout)


def test_encrypted_roundtrip_with_hardlinks_and_browser_links(setup):
    args, root = setup
    result = backup.create(args)
    assert result["encrypted"] and b"qa-private-key-content" not in args.output.read_bytes()
    assert backup.verify(args)["result"] == "BACKUP_VERIFIED"
    receipt = backup.restore(args)
    assert not receipt["ready_to_activate"]
    assert (args.target / "control/proxy-secret-store/.recovery-pending").is_file()
    assert (args.target / "home/cookies.sqlite").read_bytes() == (root / "home/cookies.sqlite").read_bytes()
    assert (args.target / "home/hardlink-copy").stat().st_nlink == 1
    assert os.readlink(args.target / "home/container-link") == "/config/cookies.sqlite"
    assert (args.target / "key-material/secret-store.key").read_bytes() == (root / "key-material/secret-store.key").read_bytes()
    assert not list(args.scratch_root.iterdir())


@pytest.mark.parametrize("damage", ["identity", "ciphertext", "truncated"])
def test_authentication_failure_never_creates_target(setup, damage):
    args, _ = setup
    backup.create(args)
    if damage == "identity":
        args.identity.unlink()
        subprocess.run([str(args.age.with_name("age-keygen")), "-o", str(args.identity)], capture_output=True, check=True)
    else:
        raw = bytearray(args.archive.read_bytes())
        if damage == "ciphertext":
            raw[-10] ^= 1
        else:
            del raw[-20:]
        args.archive.write_bytes(raw)
    with pytest.raises(backup.BackupError, match="BACKUP_AUTHENTICATION_FAILED"):
        backup.restore(args)
    assert not args.target.exists() and not list(args.scratch_root.iterdir())


@pytest.mark.parametrize("damage", ["traversal", "absolute", "link", "hardlink", "digest", "duplicate", "parent_link"])
def test_authenticated_unsafe_content_rejected_before_writes(setup, damage):
    args, _ = setup
    backup.create(args)
    def change(member, raw):
        if member.name == "home/cookies.sqlite":
            if damage == "traversal":
                member.name = "home/../../escaped"
            elif damage == "absolute":
                member.name = str(args.target.parent / "escaped")
            elif damage in {"link", "hardlink"}:
                member.type = tarfile.SYMTYPE if damage == "link" else tarfile.LNKTYPE
                member.linkname, member.size, raw = "../../escaped", 0, None
            elif damage == "digest":
                raw = b"changed-content"
            elif damage == "duplicate":
                member.name = "home/hardlink-copy"
        if damage == "parent_link" and member.name == "home":
            member.type, member.linkname = tarfile.SYMTYPE, "../../escaped"
        return member, raw
    rewrite_archive(args, change)
    with pytest.raises(backup.BackupError):
        backup.restore(args)
    assert not args.target.exists() and not (args.target.parent / "escaped").exists()
    assert not list(args.scratch_root.iterdir())


def test_existing_target_and_archive_preserved(setup):
    args, _ = setup
    backup.create(args)
    digest = backup.sha(args.archive)
    with pytest.raises(backup.BackupError, match="BACKUP_OUTPUT_EXISTS"):
        backup.create(args)
    assert backup.sha(args.archive) == digest
    args.target.mkdir(mode=0o700)
    file(args.target / "keep", b"existing")
    with pytest.raises(backup.BackupError, match="BACKUP_RESTORE_TARGET_EXISTS"):
        backup.restore(args)
    assert (args.target / "keep").read_bytes() == b"existing"


def test_source_changes_discard_ciphertext(setup, monkeypatch):
    args, root = setup
    monkeypatch.setattr(backup.home_backup, "require_stopped", lambda *_: file(root / "home/cookies.sqlite", b"modified-during-backup"))
    with pytest.raises(backup.BackupError, match="BACKUP_SOURCE_CHANGED"):
        backup.create(args)
    assert not args.archive.exists() and not list(args.archive.parent.glob(".encrypted-backup-*"))


def test_recovery_merges_new_revocations_and_is_idempotent(setup):
    args, _ = setup
    old = revocation(args.current_store, "older")
    backup.create(args)
    backup.restore(args)
    newer = revocation(args.current_store, "newer")
    assert backup.activate(args)["started_workers"] == 0
    restored = args.bundle / "control/proxy-secret-store"
    for entry in (old, newer):
        assert (restored / "revocations" / entry.name).read_bytes() == entry.read_bytes()
    assert not (restored / ".recovery-pending").exists()
    receipt = (args.bundle / "activation.json").read_bytes()
    assert backup.activate(args)["ready_for_offline_rebinding"]
    assert (args.bundle / "activation.json").read_bytes() == receipt


@pytest.mark.parametrize("stage", ["receipt", "unlock"])
def test_activation_interruption_stays_locked_and_retryable(setup, monkeypatch, stage):
    args, _ = setup
    backup.create(args)
    backup.restore(args)
    entry = revocation(args.current_store, "revoked-after-backup")
    original_write, original_unlink = backup.write_json, Path.unlink
    def write(path, value, **kwargs):
        if stage == "receipt" and path.name == "activation.json":
            raise OSError("simulated process failure")
        return original_write(path, value, **kwargs)
    def unlink(path, *a, **kw):
        if stage == "unlock" and path.name == ".recovery-pending":
            raise OSError("simulated process failure")
        return original_unlink(path, *a, **kw)
    with monkeypatch.context() as patch:
        patch.setattr(backup, "write_json", write)
        patch.setattr(Path, "unlink", unlink)
        with pytest.raises(OSError):
            backup.activate(args)
    store = args.bundle / "control/proxy-secret-store"
    assert (store / ".recovery-pending").exists()
    assert (store / "revocations" / entry.name).exists()
    backup.activate(args)
    assert not (store / ".recovery-pending").exists()


@pytest.mark.parametrize("mount_current", [False, True])
def test_activation_refuses_mounted_source_or_target(setup, monkeypatch, mount_current):
    args, _ = setup
    backup.create(args)
    backup.restore(args)
    path = args.current_store.parent if mount_current else args.bundle
    monkeypatch.setattr(backup.home_backup, "docker", lambda *a: "container" if a[0] == "ps" else json.dumps([{"Mounts": [{"Source": str(path)}]}]))
    with pytest.raises(backup.BackupError, match="BACKUP_RECOVERY_ALREADY_MOUNTED"):
        backup.activate(args)
    assert (args.bundle / "control/proxy-secret-store/.recovery-pending").exists()


def test_activation_refuses_foreign_store(setup):
    args, _ = setup
    backup.create(args)
    backup.restore(args)
    metadata = json.loads((args.current_store / "store.json").read_bytes())
    metadata["store_id"] = "c" * 32
    file(args.current_store / "store.json", backup.canonical(metadata))
    with pytest.raises(backup.BackupError, match="BACKUP_STORE_IDENTITY_MISMATCH"):
        backup.activate(args)


def test_error_output_is_sanitized(setup, monkeypatch, capsys):
    args, _ = setup
    monkeypatch.setattr("sys.argv", ["secure-backup.py", "activate", "--bundle", str(args.bundle), "--current-store", str(args.current_store)])
    monkeypatch.setattr(backup, "activate", lambda _: (_ for _ in ()).throw(RuntimeError("password:QA-SECRET")))
    assert backup.main() == 1
    assert capsys.readouterr().out == '{"result": "FAIL", "code": "BACKUP_OPERATION_FAILED"}\n'


def source_arguments(args, root, monkeypatch):
    config_root = root / "server-config"
    metadata = config_root / ".config/sealskin"
    shutil.copytree(root / "control", metadata)
    shutil.copytree(root / "control/ssl", config_root / "ssl")
    shutil.copyfile(root / "control/admin.json", config_root / "admin.json")
    storage = root / "storage"
    shutil.copytree(root / "home", storage / "qa-owner/qa-home", symlinks=True)
    settings = {"sealskin": {"username": "qa-owner", "client_private_key_file": "client-private.pem",
                            "server_public_key_file": "server-public.pem"},
                "state_file": "state.json", "profiles": [{"id": "qa", "home_name": "qa-home", "application_id": "qa-app"}]}
    file(root / "adapter/config.json", backup.canonical(settings))
    artifact = root / "environment/artifact.json"
    acceptance = file(root / "environment/acceptance.json", backup.canonical({"status": "pass", "phase": "all",
                          "artifactSHA256": backup.sha(artifact), "runtimeImageDigest": "sha256:" + "d" * 64}))
    monkeypatch.setattr(backup.home_backup, "app_context", lambda *_: {"artifact_sha256": backup.sha(artifact),
                        "acceptance_sha256": backup.sha(acceptance), "image_id": "sha256:" + "d" * 64})
    args.config, args.storage, args.sealskin_config = root / "adapter/config.json", storage, metadata
    args.artifact, args.acceptance, args.master_key_file = artifact, acceptance, root / "key-material/secret-store.key"
    return config_root


def test_backup_includes_actual_ssl_and_adapter_identity_paths(setup, monkeypatch):
    args, root = setup
    config_root = source_arguments(args, root, monkeypatch)
    original = module_source_collect_sources()
    sources = original(args)[3]
    assert sources["control/ssl"] == config_root / "ssl"
    assert sources["control/admin.json"] == config_root / "admin.json"
    assert sources["adapter/client-private.pem"] == root / "adapter/client-private.pem"
    assert sources["adapter/server-public.pem"] == root / "adapter/server-public.pem"
    monkeypatch.setattr(backup, "collect_sources", original)
    backup.create(args)
    backup.restore(args)
    for leaf in ("server_key.pem", "proxy_key.pem", "proxy_cert.pem"):
        assert (args.target / "control/ssl" / leaf).read_bytes() == (config_root / "ssl" / leaf).read_bytes()


def module_source_collect_sources():
    # Reload only to retain the real source collector beneath setup's fixture.
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    value.home_backup = backup.home_backup
    return value.collect_sources


@pytest.mark.parametrize("leaf", ["ssl/server_key.pem", "ssl/proxy_key.pem", "ssl/proxy_cert.pem", "admin.json"])
def test_required_service_recovery_key_missing_rejects_backup(setup, monkeypatch, leaf):
    args, root = setup
    config_root = source_arguments(args, root, monkeypatch)
    (config_root / leaf).unlink()
    original = module_source_collect_sources()
    # Exception classes belong to the reloaded collector module.
    with pytest.raises(Exception, match="BACKUP_CONTROL_KEY_MISSING"):
        original(args)
    assert not args.archive.exists()


def test_legacy_control_state_uses_actual_ssl_directory(setup, monkeypatch, capsys):
    args, root = setup
    config_root = source_arguments(args, root, monkeypatch)
    args.output, args.include_secrets = root / "legacy-state", True
    backup.home_backup.control_state(args)
    archives = list(args.output.glob("*.tar"))
    assert len(archives) == 1
    with tarfile.open(archives[0]) as archive:
        assert archive.extractfile("ssl/server_key.pem").read() == (config_root / "ssl/server_key.pem").read_bytes()


def test_offline_admin_recovery_file_can_replace_removed_bootstrap_copy(setup, monkeypatch):
    args, root = setup
    config_root = source_arguments(args, root, monkeypatch)
    private = root / "offline-identity"
    private.mkdir(mode=0o700)
    args.admin_recovery_file = private / "admin.json"
    shutil.copy2(config_root / "admin.json", args.admin_recovery_file)
    args.admin_recovery_file.chmod(0o600)
    (config_root / "admin.json").unlink()
    sources = module_source_collect_sources()(args)[3]
    assert sources["control/admin.json"] == args.admin_recovery_file


def test_missing_adapter_journal_is_not_silently_fabricated(setup, monkeypatch):
    args, root = setup
    source_arguments(args, root, monkeypatch)
    (root / "adapter/state.json").unlink()
    with pytest.raises(Exception, match="BACKUP_ADAPTER_STATE_MISSING"):
        module_source_collect_sources()(args)
    assert not (root / "adapter/state.json").exists()


def access_and_session_state(args, root):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import yaml
    key = os.urandom(32)
    nonce = os.urandom(12)
    plaintext = backup.canonical({"test-session": {"access_token": "synthetic-session-capability",
                                                   "lifecycle_phase": "stopping"}})
    envelope = {"session_state_version": 1, "algorithm": "AES-256-GCM", "nonce": base64.b64encode(nonce).decode(),
                "ciphertext": base64.b64encode(AESGCM(key).encrypt(nonce, plaintext,
                                  b"browser-platform/sealskin-session-state/v1")).decode()}
    file(args.sealskin_config / "session-secrets/state.key", key)
    file(args.sealskin_config / "sessions.yml", yaml.safe_dump(envelope).encode())
    registry = {"version": 1, "users": [{"id": "qa", "profiles": ["qa"], "password_hash":
                "pbkdf2-sha256$600000$" + base64.b64encode(os.urandom(16)).decode().rstrip("=") + "$" +
                 base64.b64encode(os.urandom(32)).decode().rstrip("=")}]}
    file(root / "adapter/access-users.json", backup.canonical(registry))
    file(root / "adapter/session-ca.pem", b"synthetic-public-ca")
    config = json.loads(args.config.read_bytes())
    config["access"] = {"users_file": "access-users.json", "session_ca_file": "session-ca.pem"}
    file(args.config, backup.canonical(config))
    return registry, plaintext


def test_session_keys_and_access_material_restore_with_current_login_policy(setup, monkeypatch):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import yaml
    args, root = setup
    source_arguments(args, root, monkeypatch)
    registry, plaintext = access_and_session_state(args, root)
    collector = module_source_collect_sources()
    sources = collector(args)[3]
    assert sources["control/session-secrets"] == args.sealskin_config / "session-secrets"
    assert sources["adapter/access-users.json"] == root / "adapter/access-users.json"
    assert sources["adapter/session-ca.pem"] == root / "adapter/session-ca.pem"
    monkeypatch.setattr(backup, "collect_sources", collector)
    backup.create(args)
    assert b"synthetic-session-capability" not in args.archive.read_bytes()
    assert backup.verify(args)["result"] == "BACKUP_VERIFIED"
    receipt = backup.restore(args)
    assert receipt["access_review_required"]
    restored_key = (args.target / "control/session-secrets/state.key").read_bytes()
    envelope = yaml.safe_load((args.target / "control/sessions.yml").read_bytes())
    assert AESGCM(restored_key).decrypt(base64.b64decode(envelope["nonce"]), base64.b64decode(envelope["ciphertext"]),
                                      b"browser-platform/sealskin-session-state/v1") == plaintext
    with pytest.raises(backup.BackupError, match="BACKUP_CURRENT_ACCESS_REQUIRED"):
        backup.activate(args)
    assert (args.bundle / "control/proxy-secret-store/.recovery-pending").exists()
    registry["users"][0]["disabled"] = True
    args.current_access_users = file(root / "adapter/access-users.json", backup.canonical(registry))
    backup.activate(args)
    assert json.loads((args.bundle / "adapter/access-users.json").read_bytes()) == registry
    assert not list(args.scratch_root.iterdir())


@pytest.mark.parametrize("damage", ["missing_key", "wrong_key", "missing_database", "downgrade", "pending"])
def test_backup_rejects_unrecoverable_session_material(setup, monkeypatch, damage):
    args, root = setup
    source_arguments(args, root, monkeypatch)
    access_and_session_state(args, root)
    key = args.sealskin_config / "session-secrets/state.key"
    if damage == "missing_key":
        key.unlink()
    elif damage == "wrong_key":
        key.write_bytes(os.urandom(32))
    elif damage == "missing_database":
        (args.sealskin_config / "sessions.yml").unlink()
    elif damage == "downgrade":
        (args.sealskin_config / "sessions.yml").write_text("{}")
    else:
        file(key.with_name("migration.pending"), b"a" * 64)
    monkeypatch.setattr(backup, "collect_sources", module_source_collect_sources())
    with pytest.raises((Exception, SystemExit)):
        backup.create(args)
    assert not args.archive.exists()


def test_authenticated_archive_with_wrong_session_key_is_rejected_before_restore(setup, monkeypatch):
    args, root = setup
    source_arguments(args, root, monkeypatch)
    access_and_session_state(args, root)
    monkeypatch.setattr(backup, "collect_sources", module_source_collect_sources())
    backup.create(args)
    replacement = os.urandom(32)
    def change(member, raw):
        if member.name == "control/session-secrets/state.key":
            raw = replacement
        if member.name == "manifest.json":
            manifest = json.loads(raw)
            manifest["entries"]["control/session-secrets/state.key"]["sha256"] = hashlib.sha256(replacement).hexdigest()
            raw = backup.canonical(manifest)
        return member, raw
    rewrite_archive(args, change)
    with pytest.raises(backup.BackupError, match="BACKUP_SESSION_STATE_INVALID"):
        backup.restore(args)
    assert not args.target.exists()


@pytest.mark.parametrize("material", ["session", "accounts"])
def test_legacy_plaintext_control_archive_refuses_session_and_login_state(setup, monkeypatch, material):
    args, root = setup
    source_arguments(args, root, monkeypatch)
    if material == "session":
        file(args.sealskin_config / "sessions.yml", b"{}")
    else:
        config = json.loads(args.config.read_bytes())
        config["access"] = {"users_file": "accounts.json"}
        file(args.config, backup.canonical(config))
    args.output, args.include_secrets = root / "legacy-refused", True
    with pytest.raises(SystemExit, match="secure-backup.py"):
        backup.home_backup.control_state(args)
    assert not args.output.exists()
