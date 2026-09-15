#!/usr/bin/env python3
"""Create age-encrypted offline bundles and restore into an unused directory.

Creation streams directly into age. Decryption and authentication finish on
tmpfs before any restore target is created. Restored credential stores remain
locked until current revocation tombstones have been merged explicitly.
"""

from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import argparse
import base64
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile

FORMAT = "browser-platform/encrypted-backup/v1"
LEGACY_FORMAT = "browser-platform/encrypted-legacy-backup/v1"
LEGACY_SNAPSHOT = "browser-platform/legacy-runtime-snapshot/v1"
AGE_VERSION = "v1.2.1"
MAX_ARCHIVE = 8 * 1024**3
SESSION_LIMIT = 16 * 1024 * 1024
module = importlib.util.spec_from_file_location("home_backup", Path(__file__).with_name("backup-home.py"))
home_backup = importlib.util.module_from_spec(module)
module.loader.exec_module(home_backup)


class BackupError(Exception):
    pass


def fail(code):
    raise BackupError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def private_directory(path):
    info = path.lstat()
    if (not path.is_absolute() or path.resolve() != path or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid() or info.st_mode & 0o077):
        fail("BACKUP_DIRECTORY_UNSAFE")


def private_file(path):
    private_directory(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_nlink != 1:
        fail("BACKUP_KEY_FILE_UNSAFE")


def public_key_file(path):
    """Public verification keys need integrity, not private read permissions."""
    private_directory(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022 or info.st_nlink != 1:
        fail("BACKUP_KEY_FILE_UNSAFE")


def sha(path):
    return home_backup.sha256_file(path)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, value, *, replace=False):
    private_directory(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".backup-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical(value))
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path, follow_symlinks=False)
        if os.path.exists(temporary):
            os.unlink(temporary)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def store_lock(path):
    """Use the same cross-process lock as FileSecretStore put/revoke/resolve."""
    private_directory(path)
    fd = os.open(path / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "rb") as handle:
        private_file(path / ".lock")
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def age_binary(path):
    result = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10)
    if result.returncode or result.stdout.strip() != AGE_VERSION:
        fail("BACKUP_AGE_VERSION_MISMATCH")
    return str(path)


def safe_name(name):
    path = PurePosixPath(name)
    if not name or name == "." or "\x00" in name or path.is_absolute() or ".." in path.parts or str(path) != name:
        fail("BACKUP_MEMBER_UNSAFE")
    return path


def safe_home_link(name, target):
    if not name.startswith("home/"):
        fail("BACKUP_LINK_UNSAFE")
    # Browser Homes may use /config-relative links inside the container. They
    # are created last and are never followed by this tool on the host.
    if target.startswith("/config/") and ".." not in PurePosixPath(target).parts:
        return
    if target.startswith("/"):
        fail("BACKUP_LINK_UNSAFE")
    normalized = os.path.normpath(str(PurePosixPath(name).parent / target))
    if normalized != "home" and not normalized.startswith("home/"):
        fail("BACKUP_LINK_UNSAFE")


def wayland_runtime_socket(name):
    return isinstance(name, str) and re.fullmatch(r"home/\.XDG/wayland-[0-9]{1,10}", name) is not None


def snapshot(sources):
    """Capture immutable names/types and file hashes; never traverse symlinks."""
    entries, paths, excluded = {}, {}, {}
    for prefix, source in sources.items():
        found = [source]
        if source.is_dir() and not source.is_symlink():
            found += sorted(source.rglob("*"))
        for path in found:
            suffix = path.relative_to(source).as_posix()
            name = prefix if suffix == "." else prefix + "/" + suffix
            if name == "control/proxy-secret-store/.lock":
                continue
            safe_name(name)
            if name in entries:
                fail("BACKUP_DUPLICATE_MEMBER")
            info = path.lstat()
            # A stopped legacy Wayland desktop leaves this endpoint behind.
            # It has no persistent payload and must be recreated by the new
            # compositor. Do not unlink the source or skip any other type/path.
            if stat.S_ISSOCK(info.st_mode) and wayland_runtime_socket(name):
                excluded[name] = "wayland-runtime-socket"
                continue
            item = {"mode": stat.S_IMODE(info.st_mode) & 0o777}
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                safe_home_link(name, target)
                item.update(type="symlink", target=target)
            elif stat.S_ISDIR(info.st_mode):
                item["type"] = "dir"
            elif stat.S_ISREG(info.st_mode):
                item.update(type="file", size=info.st_size, sha256=sha(path))
            else:
                fail("BACKUP_FILE_TYPE_UNSUPPORTED")
            entries[name], paths[name] = item, path
    return entries, paths, excluded


def validate_session_state(raw, key=None):
    """Authenticate the database/key pair before calling a bundle restorable.

    This offline verifier never creates keys, migrates state or logs plaintext.
    Legacy snapshots remain supported only when no sealed-state key exists.
    """
    import yaml
    try:
        if len(raw) > 2 * SESSION_LIMIT:
            fail("BACKUP_SESSION_STATE_INVALID")
        value = yaml.safe_load(raw)
        if isinstance(value, dict) and "session_state_version" in value:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            if (key is None or len(key) != 32 or set(value) != {"session_state_version", "algorithm", "nonce", "ciphertext"}
                    or type(value["session_state_version"]) is not int or value["session_state_version"] != 1
                    or value["algorithm"] != "AES-256-GCM"):
                fail("BACKUP_SESSION_STATE_INVALID")
            nonce = base64.b64decode(value["nonce"], validate=True)
            ciphertext = base64.b64decode(value["ciphertext"], validate=True)
            if len(nonce) != 12 or len(ciphertext) > SESSION_LIMIT + 16:
                fail("BACKUP_SESSION_STATE_INVALID")
            value = json.loads(AESGCM(key).decrypt(nonce, ciphertext, b"browser-platform/sealskin-session-state/v1"))
        elif key is not None:
            fail("BACKUP_SESSION_STATE_INVALID")
        if value is not None and (not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, dict)
                                                                  for k, v in value.items())):
            fail("BACKUP_SESSION_STATE_INVALID")
    except Exception:
        fail("BACKUP_SESSION_STATE_INVALID")


def validate_access_registry(raw):
    try:
        if len(raw) > 1 << 20:
            raise ValueError()
        value = json.loads(raw)
        if (set(value) != {"version", "users"} or type(value["version"]) is not int or value["version"] != 1
                or not isinstance(value["users"], list) or not 1 <= len(value["users"]) <= 64):
            raise ValueError()
        seen = set()
        for user in value["users"]:
            if (not isinstance(user, dict) or set(user) - {"id", "password_hash", "profiles", "disabled"}
                    or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", user["id"]) or user["id"] in seen
                    or type(user.get("disabled", False)) is not bool
                    or not isinstance(user["profiles"], list) or not 1 <= len(user["profiles"]) <= 128
                    or any(not isinstance(p, str) or not p for p in user["profiles"])
                    or len(set(user["profiles"])) != len(user["profiles"])):
                raise ValueError()
            algorithm, iterations, salt, digest = user["password_hash"].split("$")
            if (algorithm != "pbkdf2-sha256" or iterations != "600000"
                    or len(base64.b64decode(salt + "=" * (-len(salt) % 4), validate=True)) != 16
                    or len(base64.b64decode(digest + "=" * (-len(digest) % 4), validate=True)) != 32):
                raise ValueError()
            seen.add(user["id"])
        return value
    except Exception:
        fail("BACKUP_ACCESS_REGISTRY_INVALID")


def coherence_asset_references(registry):
    """Map only canonical controller asset references into the offline bundle."""
    if not isinstance(registry, dict) or not isinstance(registry.get("policies", {}), dict):
        fail("BACKUP_COHERENCE_POLICY_INVALID")
    references = {}
    for policy in registry.get("policies", {}).values():
        if not isinstance(policy, dict):
            fail("BACKUP_COHERENCE_POLICY_INVALID")
        coherence = policy.get("coherence")
        if coherence is None:
            continue
        if not isinstance(coherence, dict):
            fail("BACKUP_COHERENCE_POLICY_INVALID")
        for kind, limit in (("artifact", 1 << 20), ("acceptance", 1 << 20), ("geoip", 64 << 20)):
            location, digest = coherence.get(kind + "_file", ""), coherence.get(kind + "_sha256", "")
            if kind == "geoip" and location == digest == "":
                continue
            if (not isinstance(location, str) or not 1 <= len(location) <= 512 or "\x00" in location
                    or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
                fail("BACKUP_COHERENCE_POLICY_INVALID")
            path = PurePosixPath(location)
            if path.parent != PurePosixPath("/config/.config/sealskin/coherence-assets") or str(path) != location:
                fail("BACKUP_COHERENCE_POLICY_INVALID")
            name = "control/coherence-assets/" + path.name
            safe_name(name)
            if name in references and references[name]["sha256"] != digest:
                fail("BACKUP_COHERENCE_POLICY_INVALID")
            references[name] = {"sha256": digest, "limit": min(limit, references.get(name, {}).get("limit", limit))}
    return references


def validate_coherence_assets(registry, entries):
    references = coherence_asset_references(registry)
    if references:
        directory = entries.get("control/coherence-assets", {})
        if directory.get("type") != "dir" or directory.get("mode", 0o777) & 0o077:
            fail("BACKUP_COHERENCE_ASSET_INVALID")
    for name, expected in references.items():
        entry = entries.get(name, {})
        if (entry.get("type") != "file" or entry.get("mode", 0o777) & 0o077
                or type(entry.get("size")) is not int or not 0 <= entry["size"] <= expected["limit"]
                or entry.get("sha256") != expected["sha256"]):
            fail("BACKUP_COHERENCE_ASSET_INVALID")
    return references


def validate_source_coherence(entries, paths):
    name = "control/profile-network-policies.json"
    if entries[name].get("type") != "file" or entries[name]["size"] > SESSION_LIMIT:
        fail("BACKUP_COHERENCE_POLICY_INVALID")
    raw = paths[name].read_bytes()
    if hashlib.sha256(raw).hexdigest() != entries[name]["sha256"]:
        fail("BACKUP_SOURCE_CHANGED")
    for name in validate_coherence_assets(json.loads(raw), entries):
        private_file(paths[name])


def collect_sources(args):
    if args.sealskin_config.name != "sealskin" or args.sealskin_config.parent.name != ".config":
        fail("BACKUP_CONTROL_LAYOUT_UNSUPPORTED")
    config = home_backup.load_config(args.config)
    definition = next((p for p in config["profiles"] if p["id"] == args.profile), None)
    if definition is None:
        fail("BACKUP_PROFILE_UNKNOWN")
    before = home_backup.require_stopped(config, args.profile)
    username, name = config["sealskin"]["username"], definition["home_name"]
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", v) for v in (username, name, args.profile)):
        fail("BACKUP_PROFILE_INVALID")
    home = args.storage / username / name
    if home.is_symlink() or not home.is_dir() or home.resolve() != home:
        fail("BACKUP_HOME_UNSAFE")
    context = home_backup.app_context(args.sealskin_config, definition["application_id"])
    if (sha(args.artifact) != context["artifact_sha256"] or sha(args.acceptance) != context["acceptance_sha256"]):
        fail("BACKUP_ENVIRONMENT_MISMATCH")
    report = json.loads(args.acceptance.read_bytes())
    if (report.get("status") != "pass" or report.get("phase") != "all"
            or report.get("artifactSHA256") != context["artifact_sha256"]
            or report.get("runtimeImageDigest") != context["image_id"]):
        fail("BACKUP_ACCEPTANCE_MISMATCH")
    private_file(args.master_key_file)
    store = args.sealskin_config / "proxy-secret-store"
    private_directory(store)
    metadata = json.loads((store / "store.json").read_bytes())
    if args.master_key_file.stat().st_size != 32 or sha(args.master_key_file) != metadata["key_sha256"]:
        fail("BACKUP_MASTER_KEY_MISMATCH")
    if (store / ".recovery-pending").exists():
        fail("BACKUP_STORE_RECOVERY_PENDING")
    if not Path(config["state_file"]).is_file():
        fail("BACKUP_ADAPTER_STATE_MISSING")
    sources = {"home": home, "adapter/config.json": args.config,
        "adapter/state.json": Path(config["state_file"]), "environment/artifact.json": args.artifact,
        "environment/acceptance.json": args.acceptance, "key-material/secret-store.key": args.master_key_file,
        "control/proxy-secret-store": store}
    return config, before, context, collect_control_sources(args, config, sources)


def collect_control_sources(args, config, sources, *, require_store=True):
    """Collect shared identities/state without weakening either archive format."""
    container_config = args.sealskin_config.parent.parent
    for field, leaf in (("client_private_key_file", "client-private.pem"), ("server_public_key_file", "server-public.pem")):
        value = Path(config["sealskin"][field])
        path = value if value.is_absolute() else args.config.parent / value
        (private_file if field == "client_private_key_file" else public_key_file)(path)
        sources["adapter/" + leaf] = path
    if config.get("access") is not None:
        for field, leaf in (("users_file", "access-users.json"), ("session_ca_file", "session-ca.pem")):
            value = Path(config["access"][field])
            path = value if value.is_absolute() else args.config.parent / value
            if field == "users_file":
                private_file(path)
                validate_access_registry(path.read_bytes())
            elif not path.is_file() or path.is_symlink():
                fail("BACKUP_ACCESS_CA_MISSING")
            sources["adapter/" + leaf] = path
    required = ["installed_apps.yml", "profile-network-policies.json", "keys"]
    if require_store:
        required.append("profile-secret-store.json")
    for leaf in required:
        path = args.sealskin_config / leaf
        if not path.exists():
            fail("BACKUP_CONTROL_STATE_MISSING")
        sources["control/" + leaf] = path
    for leaf in ("sessions.yml", "app_stores.yml", "Caddyfile", "network-secrets", "groups", "app_templates",
                 "profile-launch-runtime", "profile-network-runtime", "session-secrets", "coherence-assets"):
        path = args.sealskin_config / leaf
        if path.exists():
            sources["control/" + leaf] = path
    sessions, key_directory = args.sealskin_config / "sessions.yml", args.sealskin_config / "session-secrets"
    key = None
    if os.path.lexists(key_directory):
        private_directory(key_directory)
        if os.path.lexists(key_directory / "migration.pending"):
            fail("BACKUP_SESSION_MIGRATION_PENDING")
        private_file(key_directory / "state.key")
        key = (key_directory / "state.key").read_bytes()
        if not sessions.is_file():
            fail("BACKUP_SESSION_STATE_MISSING")
    if os.path.lexists(sessions):
        if sessions.is_symlink() or not sessions.is_file() or sessions.stat().st_size > 2 * SESSION_LIMIT:
            fail("BACKUP_SESSION_STATE_INVALID")
        validate_session_state(sessions.read_bytes(), key)
    ssl = container_config / "ssl"
    for leaf in ("server_key.pem", "proxy_key.pem", "proxy_cert.pem"):
        if not (ssl / leaf).is_file():
            fail("BACKUP_CONTROL_KEY_MISSING")
    admin_recovery = getattr(args, "admin_recovery_file", None) or container_config / "admin.json"
    if not admin_recovery.is_file():
        fail("BACKUP_CONTROL_KEY_MISSING")
    if getattr(args, "admin_recovery_file", None):
        private_file(admin_recovery)
    sources["control/ssl"] = ssl
    sources["control/admin.json"] = admin_recovery
    return sources


def legacy_metadata_guard(config, registry, sessions=None):
    """Old file credentials have no Store revocation or access-registry semantics."""
    if config.get("access") is not None:
        fail("BACKUP_LEGACY_MODE_FORBIDDEN")

    def references(value):
        if isinstance(value, dict):
            return any(references(item) for item in value.values())
        if isinstance(value, list):
            return any(references(item) for item in value)
        return isinstance(value, str) and value.startswith("secret://")

    if references(registry):
        fail("BACKUP_LEGACY_MODE_FORBIDDEN")
    if sessions is not None:
        import yaml
        validate_session_state(sessions)
        value = yaml.safe_load(sessions) or {}
        if any(item.get("display_secret_version") is not None for item in value.values()):
            fail("BACKUP_LEGACY_MODE_FORBIDDEN")


def legacy_source_guard(config, metadata):
    for name in ("profile-secret-store.json", "proxy-secret-store", "session-secrets"):
        if os.path.lexists(metadata / name):
            fail("BACKUP_LEGACY_MODE_FORBIDDEN")
    registry = metadata / "profile-network-policies.json"
    if registry.is_symlink() or not registry.is_file() or registry.stat().st_size > SESSION_LIMIT:
        fail("BACKUP_CONTROL_STATE_MISSING")
    database = metadata / "sessions.yml"
    sessions = None
    if os.path.lexists(database):
        if database.is_symlink() or not database.is_file() or database.stat().st_size > 2 * SESSION_LIMIT:
            fail("BACKUP_SESSION_STATE_INVALID")
        sessions = database.read_bytes()
    legacy_metadata_guard(config, json.loads(registry.read_bytes()), sessions)


def legacy_definition(args):
    if args.sealskin_config.name != "sealskin" or args.sealskin_config.parent.name != ".config":
        fail("BACKUP_CONTROL_LAYOUT_UNSUPPORTED")
    config = home_backup.load_config(args.config)
    selected = [p for p in config["profiles"] if p["id"] == args.profile]
    if len(selected) != 1:
        fail("BACKUP_PROFILE_UNKNOWN")
    definition = selected[0]
    owner, name = config["sealskin"]["username"], definition["home_name"]
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) for value in (owner, name, args.profile)):
        fail("BACKUP_PROFILE_INVALID")
    home = args.storage / owner / name
    if home.is_symlink() or not home.is_dir() or home.resolve() != home:
        fail("BACKUP_HOME_UNSAFE")
    legacy_source_guard(config, args.sealskin_config)
    return config, definition, home


def legacy_input_hashes(args):
    paths = {"config": args.config, "applications": args.sealskin_config / "installed_apps.yml",
             "policies": args.sealskin_config / "profile-network-policies.json"}
    if any(p.is_symlink() or not p.is_file() or p.stat().st_size > SESSION_LIMIT for p in paths.values()):
        fail("BACKUP_LEGACY_INPUT_INVALID")
    return {key: sha(path) for key, path in paths.items()}


def validate_legacy_snapshot(value):
    fields = {"format", "captured_at", "profile", "owner", "home_name", "application_id", "operation_id",
              "session_id", "binding_identity", "input_sha256", "journal_sha256", "worker", "controller", "configured_image_id"}
    try:
        if not isinstance(value, dict) or set(value) != fields or value["format"] != LEGACY_SNAPSHOT:
            raise ValueError()
        for name in ("profile", "owner", "home_name", "application_id", "operation_id", "session_id"):
            if not isinstance(value[name], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value[name]):
                raise ValueError()
        identity = value["binding_identity"]
        if (not isinstance(identity, dict) or set(identity) - {"home_name", "application_id"}
                or any(v not in ("", value[k]) for k, v in identity.items())):
            raise ValueError()
        if (set(value["input_sha256"]) != {"config", "applications", "policies"}
                or any(not re.fullmatch(r"[a-f0-9]{64}", v) for v in value["input_sha256"].values())
                or not re.fullmatch(r"[a-f0-9]{64}", value["journal_sha256"])
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", value["configured_image_id"])):
            raise ValueError()
        datetime.fromisoformat(value["captured_at"])
        for name in ("worker", "controller"):
            item = value[name]
            expected = {"id", "image_id", "started_at"} | ({"auto_remove", "environment"} if name == "worker" else set())
            if (not isinstance(item, dict) or set(item) != expected
                    or not re.fullmatch(r"[a-f0-9]{64}", item["id"])
                    or not re.fullmatch(r"sha256:[a-f0-9]{64}", item["image_id"])):
                raise ValueError()
            datetime.fromisoformat(item["started_at"].replace("Z", "+00:00"))
        worker = value["worker"]
        allowed = {"LC_ALL", "LANG", "TZ", "PUID", "PGID", "BROWSER_PLATFORM_ENVIRONMENT_ID",
                   "BROWSER_PLATFORM_ARTIFACT_SHA256", "BROWSER_PLATFORM_ACCEPTANCE_SHA256"}
        if (type(worker["auto_remove"]) is not bool or not isinstance(worker["environment"], dict)
                or set(worker["environment"]) - allowed
                or any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_./:+-]{0,256}", v)
                       for v in worker["environment"].values())):
            raise ValueError()
    except (KeyError, ValueError, TypeError, AttributeError):
        fail("BACKUP_LEGACY_SNAPSHOT_INVALID")
    return value


def snapshot_legacy(args):
    """Record actual old image/binding while it still exists; never read Home files."""
    private_directory(args.output.parent)
    if os.path.lexists(args.output):
        fail("BACKUP_OUTPUT_EXISTS")
    config, definition, home = legacy_definition(args)
    inputs = legacy_input_hashes(args)
    state_path = Path(config["state_file"])
    with Path(str(state_path) + ".lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        state = json.loads(state_path.read_bytes())
        journal_sha = sha(state_path)
    binding = state.get("bindings", {}).get(args.profile, {})
    status, response = home_backup.control(config["control_socket"], args.profile)
    current = response.get("result", {})
    if (state.get("version") != 1 or status != 200 or response.get("error")
            or binding.get("status") != "running" or current.get("status") != "running"
            or binding.get("profile_id") != args.profile or current.get("profile_id") != args.profile
            or current.get("workers") != 1 or current.get("records") != 1 or current.get("orphans") != 0
            or current.get("session_id") != binding.get("session_id")
            or any(k in binding and binding[k] not in ("", definition[k]) for k in ("home_name", "application_id"))
            or binding.get("stop_operation_id") or binding.get("resume_idempotency_key")):
        fail("BACKUP_LEGACY_RUNNING_BINDING_REQUIRED")
    identifiers = home_backup.docker("ps", "-aq").split()
    containers = json.loads(home_backup.docker("inspect", *identifiers)) if identifiers else []
    workers = [c for c in containers if any(m.get("Source") == str(home) and m.get("Destination") == "/config"
                                          for m in c.get("Mounts", []))]
    control_root = args.sealskin_config.parent.parent
    controllers = [c for c in containers if any(m.get("Source") == str(control_root) and m.get("Destination") == "/config"
                                              for m in c.get("Mounts", []))]
    if (len(workers) != 1 or len(controllers) != 1
            or any(not c["State"]["Running"] or c["State"].get("Paused") for c in [*workers, *controllers])):
        fail("BACKUP_LEGACY_INVENTORY_MISMATCH")
    worker, controller = workers[0], controllers[0]
    def identity(container):
        return {"id": container["Id"], "image_id": container["Image"], "started_at": container["State"]["StartedAt"]}
    environment = dict(item.split("=", 1) for item in worker["Config"].get("Env", []) if "=" in item)
    environment = {k: v for k, v in environment.items() if k in {"LC_ALL", "LANG", "TZ", "PUID", "PGID",
                   "BROWSER_PLATFORM_ENVIRONMENT_ID", "BROWSER_PLATFORM_ARTIFACT_SHA256", "BROWSER_PLATFORM_ACCEPTANCE_SHA256"}}
    value = {"format": LEGACY_SNAPSHOT, "captured_at": datetime.now(timezone.utc).isoformat(),
             "profile": args.profile, "owner": config["sealskin"]["username"], "home_name": definition["home_name"],
             "application_id": definition["application_id"], "operation_id": binding["operation_id"],
             "session_id": binding["session_id"],
             # Older journals omit these fields. Ownership is still verified by
             # Adapter inspect against the Session/bootstrap and exact Home.
             # Preserve absence instead of rewriting the production journal.
             "binding_identity": {k: binding[k] for k in ("home_name", "application_id") if k in binding},
             "input_sha256": inputs, "journal_sha256": journal_sha,
             "worker": {**identity(worker), "auto_remove": worker["HostConfig"]["AutoRemove"], "environment": environment},
             "controller": identity(controller),
             "configured_image_id": home_backup.app_context(args.sealskin_config, definition["application_id"])["image_id"]}
    validate_legacy_snapshot(value)
    if legacy_input_hashes(args) != inputs or sha(state_path) != journal_sha:
        fail("BACKUP_SOURCE_CHANGED")
    after = {c["Id"]: c for c in json.loads(home_backup.docker("inspect", worker["Id"], controller["Id"]))}
    for previous in (worker, controller):
        current_container = after.get(previous["Id"])
        if (current_container is None or not current_container["State"]["Running"]
                or current_container["State"].get("Paused") or identity(current_container) != identity(previous)):
            fail("BACKUP_SOURCE_CHANGED")
    write_json(args.output, value)
    return {"result": "BACKUP_LEGACY_SNAPSHOT_PREPARED", "production_mutations": 0,
            "home_contents_read": False, "runtime_differs_from_configured_image": worker["Image"] != value["configured_image_id"]}


def validate_legacy_stopped_binding(state, recorded):
    binding = state.get("bindings", {}).get(recorded["profile"], {})
    if (state.get("version") != 1 or binding.get("status") != "stopped" or binding.get("session_id")
            or binding.get("profile_id") != recorded["profile"]
            or binding.get("operation_id") != recorded["operation_id"]
            or {k: binding[k] for k in ("home_name", "application_id") if k in binding} != recorded["binding_identity"]):
        fail("BACKUP_LEGACY_GENERATION_CHANGED")


def collect_legacy_sources(args):
    config, definition, home = legacy_definition(args)
    before = home_backup.require_stopped(config, args.profile)
    private_file(args.legacy_snapshot)
    if args.legacy_snapshot.stat().st_size > 64 * 1024:
        fail("BACKUP_LEGACY_SNAPSHOT_INVALID")
    recorded = validate_legacy_snapshot(json.loads(args.legacy_snapshot.read_bytes()))
    if ((recorded["profile"], recorded["owner"], recorded["home_name"], recorded["application_id"]) !=
            (args.profile, config["sealskin"]["username"], definition["home_name"], definition["application_id"])
            or recorded["input_sha256"] != legacy_input_hashes(args)):
        fail("BACKUP_LEGACY_SNAPSHOT_MISMATCH")
    state_path = Path(config["state_file"])
    if not state_path.is_file():
        fail("BACKUP_ADAPTER_STATE_MISSING")
    state = json.loads(state_path.read_bytes())
    validate_legacy_stopped_binding(state, recorded)
    image_id = recorded["worker"]["image_id"]
    if home_backup.docker("image", "inspect", image_id, "--format", "{{.Id}}").strip() != image_id:
        fail("BACKUP_LEGACY_IMAGE_MISSING")
    sources = {"home": home, "adapter/config.json": args.config, "adapter/state.json": Path(config["state_file"]),
               "runtime/snapshot.json": args.legacy_snapshot}
    sources = collect_control_sources(args, config, sources, require_store=False)
    context = {"application_id": definition["application_id"], "image_id": image_id,
               "runtime_snapshot_sha256": sha(args.legacy_snapshot), "environment_evidence": "observed-legacy-runtime"}
    return config, before, context, sources


def create(args):
    binary = age_binary(args.age)
    if not re.fullmatch(r"age1[023456789acdefghjklmnpqrstuvwxyz]{58}", args.recipient):
        fail("BACKUP_RECIPIENT_INVALID")
    private_directory(args.output.parent)
    if os.path.lexists(args.output):
        fail("BACKUP_OUTPUT_EXISTS")
    legacy = getattr(args, "legacy_snapshot", None) is not None
    config, before, context, sources = collect_legacy_sources(args) if legacy else collect_sources(args)
    entries, paths, excluded = snapshot(sources)
    validate_source_coherence(entries, paths)
    manifest = {"format": LEGACY_FORMAT if legacy else FORMAT,
                "created_at": datetime.now(timezone.utc).isoformat(), "profile": args.profile,
                "context": context, "stopped_before": before, "entries": entries}
    if excluded:
        manifest["excluded_runtime_nodes"] = excluded
    fd, name = tempfile.mkstemp(prefix=".encrypted-backup-", dir=args.output.parent)
    try:
        with os.fdopen(fd, "wb") as destination:
            process = subprocess.Popen([binary, "--encrypt", "--recipient", args.recipient],
                                       stdin=subprocess.PIPE, stdout=destination, stderr=subprocess.PIPE)
            try:
                with tarfile.open(fileobj=process.stdin, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                    for name_in_archive, source in paths.items():
                        entry = entries[name_in_archive]
                        member = tarfile.TarInfo(name_in_archive)
                        member.mode = entry["mode"]
                        if entry["type"] == "dir":
                            member.type = tarfile.DIRTYPE
                            archive.addfile(member)
                        elif entry["type"] == "symlink":
                            member.type, member.linkname = tarfile.SYMTYPE, entry["target"]
                            archive.addfile(member)
                        else:
                            # Store hard-linked files as independent contents. Never
                            # follow a source that became a symlink after snapshot.
                            source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                            with os.fdopen(source_fd, "rb") as contents:
                                info = os.fstat(contents.fileno())
                                if not stat.S_ISREG(info.st_mode) or info.st_size != entry["size"]:
                                    fail("BACKUP_SOURCE_CHANGED")
                                member.size = entry["size"]
                                archive.addfile(member, contents)
                    raw = canonical(manifest)
                    member = tarfile.TarInfo("manifest.json")
                    member.size, member.mode = len(raw), 0o600
                    archive.addfile(member, io.BytesIO(raw))
                process.stdin.close()
                if process.wait(timeout=120) != 0:
                    fail("BACKUP_ENCRYPTION_FAILED")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stderr.close()
            destination.flush()
            os.fsync(destination.fileno())
        home_backup.require_stopped(config, args.profile)
        if legacy:
            legacy_source_guard(home_backup.load_config(args.config), args.sealskin_config)
        final_entries, _, final_excluded = snapshot(sources)
        if final_entries != entries or final_excluded != excluded:
            fail("BACKUP_SOURCE_CHANGED")
        os.link(name, args.output, follow_symlinks=False)
        sync_directory(args.output.parent)
        return {"result": "BACKUP_CREATED", "encrypted": True, "archive_sha256": sha(args.output),
                "archive_format": manifest["format"], "entries": len(entries),
                "excluded_runtime_nodes": excluded}
    finally:
        if os.path.exists(name):
            os.unlink(name)


def tmpfs_directory(path):
    private_directory(path)
    match = None
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        mount = Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4]))
        if path == mount or path.is_relative_to(mount):
            if match is None or len(mount.parts) > match[0]:
                match = len(mount.parts), fields[fields.index("-") + 1]
    if match is None or match[1] != "tmpfs":
        fail("BACKUP_TMPFS_REQUIRED")


def validate_legacy_bundle(archive, members, manifest):
    forbidden = ("control/proxy-secret-store", "control/profile-secret-store.json", "control/session-secrets",
                 "adapter/access-users.json", "adapter/session-ca.pem")
    if any(name == prefix or name.startswith(prefix + "/") for name in members for prefix in forbidden):
        fail("BACKUP_LEGACY_MODE_FORBIDDEN")
    record = members["runtime/snapshot.json"]
    if record.mode & 0o077 or record.size > 64 * 1024:
        fail("BACKUP_LEGACY_SNAPSHOT_INVALID")
    recorded = validate_legacy_snapshot(json.load(archive.extractfile(record)))
    expected = {"application_id": recorded["application_id"], "image_id": recorded["worker"]["image_id"],
                "runtime_snapshot_sha256": manifest["entries"]["runtime/snapshot.json"]["sha256"],
                "environment_evidence": "observed-legacy-runtime"}
    if manifest.get("context") != expected or manifest["profile"] != recorded["profile"]:
        fail("BACKUP_LEGACY_SNAPSHOT_MISMATCH")
    paths = {"config": "adapter/config.json", "applications": "control/installed_apps.yml",
             "policies": "control/profile-network-policies.json"}
    if any(manifest["entries"][name]["sha256"] != recorded["input_sha256"][key] for key, name in paths.items()):
        fail("BACKUP_LEGACY_SNAPSHOT_MISMATCH")
    if any(members[name].size > SESSION_LIMIT for name in paths.values()):
        fail("BACKUP_LEGACY_INPUT_INVALID")
    config = json.load(archive.extractfile(members["adapter/config.json"]))
    registry = json.load(archive.extractfile(members["control/profile-network-policies.json"]))
    state_member = members["adapter/state.json"]
    if state_member.size > SESSION_LIMIT:
        fail("BACKUP_LEGACY_INPUT_INVALID")
    validate_legacy_stopped_binding(json.load(archive.extractfile(state_member)), recorded)
    stopped = manifest.get("stopped_before", {})
    if stopped.get("status") != "stopped" or any(stopped.get(key) != 0 for key in ("records", "workers", "resources")):
        fail("BACKUP_LEGACY_GENERATION_CHANGED")
    definitions = [p for p in config.get("profiles", []) if p.get("id") == recorded["profile"]]
    if (len(definitions) != 1 or config.get("sealskin", {}).get("username") != recorded["owner"]
            or any(definitions[0].get(key) != recorded[key] for key in ("home_name", "application_id"))):
        fail("BACKUP_LEGACY_SNAPSHOT_MISMATCH")
    database = members.get("control/sessions.yml")
    if database and (not database.isfile() or database.size > 2 * SESSION_LIMIT):
        fail("BACKUP_SESSION_STATE_INVALID")
    legacy_metadata_guard(config, registry, archive.extractfile(database).read() if database else None)


@contextmanager
def decrypted(args):
    binary = age_binary(args.age)
    private_file(args.identity)
    tmpfs_directory(args.scratch_root)
    info = args.archive.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARCHIVE:
        fail("BACKUP_ARCHIVE_INVALID")
    available = shutil.disk_usage(args.scratch_root).free
    if available < info.st_size + 1024 * 1024:
        fail("BACKUP_TMPFS_CAPACITY")
    with args.archive.open("rb") as source, tempfile.TemporaryFile(dir=args.scratch_root) as plain:
        result = subprocess.run([binary, "--decrypt", "--identity", str(args.identity)],
                                stdin=source, stdout=plain, stderr=subprocess.PIPE, timeout=300)
        if result.returncode:
            fail("BACKUP_AUTHENTICATION_FAILED")
        plain.seek(0)
        with tarfile.open(fileobj=plain, mode="r:") as archive:
            members = {}
            for member in archive.getmembers():
                safe_name(member.name)
                if (member.name in members or member.size < 0 or member.size > MAX_ARCHIVE or member.sparse is not None
                        or not (member.isdir() or member.isfile() or member.issym())):
                    fail("BACKUP_MEMBER_UNSAFE")
                members[member.name] = member
            manifest_member = members.pop("manifest.json", None)
            if manifest_member is None or not manifest_member.isfile() or manifest_member.size > 32 * 1024 * 1024:
                fail("BACKUP_MANIFEST_INVALID")
            manifest = json.load(archive.extractfile(manifest_member))
            if (not isinstance(manifest, dict) or manifest.get("format") not in {FORMAT, LEGACY_FORMAT}
                    or not isinstance(manifest.get("entries"), dict) or set(manifest["entries"]) != set(members)
                    or not isinstance(manifest.get("profile"), str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", manifest["profile"])):
                fail("BACKUP_MANIFEST_INVALID")
            excluded = manifest.get("excluded_runtime_nodes", {})
            if (not isinstance(excluded, dict) or any(
                    not wayland_runtime_socket(name) or reason != "wayland-runtime-socket" or name in members
                    or "home/.XDG" not in members or not members["home/.XDG"].isdir()
                    for name, reason in excluded.items())):
                fail("BACKUP_MANIFEST_INVALID")
            for name, member in members.items():
                entry = manifest["entries"][name]
                if member.issym():
                    safe_home_link(name, member.linkname)
                    if entry["type"] != "symlink" or member.linkname != entry["target"]:
                        fail("BACKUP_CONTENT_MISMATCH")
                elif member.isdir():
                    if entry["type"] != "dir":
                        fail("BACKUP_CONTENT_MISMATCH")
                else:
                    digest = hashlib.sha256()
                    with archive.extractfile(member) as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                    if entry["type"] != "file" or member.size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                        fail("BACKUP_CONTENT_MISMATCH")
                if stat.S_IMODE(member.mode) & 0o777 != entry["mode"]:
                    fail("BACKUP_CONTENT_MISMATCH")
                for parent in PurePosixPath(name).parents:
                    if str(parent) in members and not members[str(parent)].isdir():
                        fail("BACKUP_MEMBER_UNSAFE")
            legacy = manifest["format"] == LEGACY_FORMAT
            required = {"home": "dir", "adapter/config.json": "file", "adapter/state.json": "file",
                        "adapter/client-private.pem": "file", "adapter/server-public.pem": "file",
                        "control/keys": "dir", "control/installed_apps.yml": "file",
                        "control/profile-network-policies.json": "file"}
            if legacy:
                required["runtime/snapshot.json"] = "file"
            else:
                required.update({"environment/artifact.json": "file", "environment/acceptance.json": "file",
                                 "key-material/secret-store.key": "file", "control/proxy-secret-store": "dir",
                                 "control/proxy-secret-store/store.json": "file", "control/proxy-secret-store/versions": "dir",
                                 "control/proxy-secret-store/revocations": "dir", "control/profile-secret-store.json": "file"})
            required.update({"control/ssl/" + leaf: "file" for leaf in ("server_key.pem", "proxy_key.pem", "proxy_cert.pem")})
            required["control/admin.json"] = "file"
            allowed = {"home", "adapter", "control", "runtime"} if legacy else {"home", "adapter", "environment", "key-material", "control"}
            if (any(manifest["entries"].get(name, {}).get("type") != kind for name, kind in required.items())
                    or any(PurePosixPath(name).parts[0] not in allowed for name in members)
                    or "control/proxy-secret-store/.recovery-pending" in members):
                fail("BACKUP_MANIFEST_INVALID")
            if legacy:
                validate_legacy_bundle(archive, members, manifest)
            else:
                context = manifest.get("context", {})
                if (manifest["entries"]["environment/artifact.json"]["sha256"] != context.get("artifact_sha256")
                        or manifest["entries"]["environment/acceptance.json"]["sha256"] != context.get("acceptance_sha256")):
                    fail("BACKUP_ENVIRONMENT_MISMATCH")
                store_metadata = json.load(archive.extractfile(members["control/proxy-secret-store/store.json"]))
                key = manifest["entries"]["key-material/secret-store.key"]
                if key["size"] != 32 or key["sha256"] != store_metadata.get("key_sha256"):
                    fail("BACKUP_MASTER_KEY_MISMATCH")
            policy_registry = members["control/profile-network-policies.json"]
            if policy_registry.size > SESSION_LIMIT:
                fail("BACKUP_COHERENCE_POLICY_INVALID")
            validate_coherence_assets(json.load(archive.extractfile(policy_registry)), manifest["entries"])
            session_key = members.get("control/session-secrets/state.key")
            session_database = members.get("control/sessions.yml")
            if ("control/session-secrets/migration.pending" in members
                    or ("control/session-secrets" in members and (session_key is None or session_database is None))):
                fail("BACKUP_SESSION_STATE_INVALID")
            if session_database is not None:
                if (not session_database.isfile() or session_database.size > 2 * SESSION_LIMIT
                        or (session_key is not None and (not session_key.isfile() or session_key.size != 32
                                                        or session_key.mode != 0o600))):
                    fail("BACKUP_SESSION_STATE_INVALID")
                validate_session_state(archive.extractfile(session_database).read(),
                                       archive.extractfile(session_key).read() if session_key else None)
            adapter_config = json.load(archive.extractfile(members["adapter/config.json"]))
            if adapter_config.get("access") is not None:
                users, ca = members.get("adapter/access-users.json"), members.get("adapter/session-ca.pem")
                if (users is None or not users.isfile() or users.size > 1 << 20 or users.mode & 0o077
                        or ca is None or not ca.isfile()):
                    fail("BACKUP_ACCESS_MATERIAL_MISSING")
                validate_access_registry(archive.extractfile(users).read())
            yield archive, members, manifest


def verify(args):
    with decrypted(args) as (_, members, manifest):
        return {"result": "BACKUP_VERIFIED", "entries": len(members), "profile": manifest["profile"],
                "encrypted": True, "archive_format": manifest["format"]}


def restore(args):
    private_directory(args.target.parent)
    if os.path.lexists(args.target):
        fail("BACKUP_RESTORE_TARGET_EXISTS")
    with decrypted(args) as (archive, members, manifest):
        args.target.mkdir(mode=0o700)
        try:
            for name, member in members.items():
                destination = args.target / name
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if member.isdir():
                    destination.mkdir(mode=0o700, exist_ok=True)
                elif member.isfile():
                    with archive.extractfile(member) as source, destination.open("xb") as output:
                        os.fchmod(output.fileno(), manifest["entries"][name]["mode"])
                        shutil.copyfileobj(source, output)
                        output.flush()
                        os.fsync(output.fileno())
            for name, member in members.items():
                if member.issym():
                    (args.target / name).symlink_to(member.linkname)
            for name, member in sorted(members.items(), key=lambda item: len(item[0]), reverse=True):
                if member.isdir():
                    (args.target / name).chmod(manifest["entries"][name]["mode"])
                    sync_directory(args.target / name)
            legacy = manifest["format"] == LEGACY_FORMAT
            if legacy:
                write_json(args.target / ".legacy-recovery-pending.json",
                           {"version": 1, "reason": "offline-profile-recovery-review-required"})
            else:
                store = args.target / "control/proxy-secret-store"
                private_directory(store)
                write_json(store / ".recovery-pending", {"version": 1, "reason": "merge-current-revocations"})
            receipt = {"result": "BACKUP_RESTORED", "archive_sha256": sha(args.archive),
                       "profile": manifest["profile"], "ready_to_activate": False,
                       "archive_format": manifest["format"], "offline_only": legacy,
                       "access_review_required": "adapter/access-users.json" in members}
            write_json(args.target / "recovery.json", receipt)
            sync_directory(args.target.parent)
        except BaseException:
            shutil.rmtree(args.target)
            raise
    return receipt


def activate(args):
    """An offline rebind step; never overwrite a live store or its newer tombstones."""
    private_directory(args.bundle)
    private_file(args.bundle / "recovery.json")
    receipt = json.loads((args.bundle / "recovery.json").read_bytes())
    if receipt.get("archive_format") == LEGACY_FORMAT:
        fail("BACKUP_LEGACY_OFFLINE_REBIND_REQUIRED")
    store = args.bundle / "control/proxy-secret-store"
    private_directory(store)
    private_directory(args.current_store)
    if (args.current_store == store or args.current_store.is_relative_to(args.bundle)
            or args.bundle.is_relative_to(args.current_store)):
        fail("BACKUP_CURRENT_REVOCATIONS_REQUIRED")
    if receipt.get("result") != "BACKUP_RESTORED":
        fail("BACKUP_RECOVERY_STATE_INVALID")
    for directory in (store, args.current_store):
        private_file(directory / "store.json")
    original, current = (json.loads((p / "store.json").read_bytes()) for p in (store, args.current_store))
    if original != current:
        fail("BACKUP_STORE_IDENTITY_MISMATCH")
    current_access = None
    if receipt.get("access_review_required"):
        # Restoring an old password/grant set must not revive a disabled user.
        # Rebind to the operator-supplied current registry before unlocking.
        path = getattr(args, "current_access_users", None)
        if path is None or path.is_relative_to(args.bundle):
            fail("BACKUP_CURRENT_ACCESS_REQUIRED")
        private_file(path)
        current_access = path.read_bytes()
        validate_access_registry(current_access)
    ids = home_backup.docker("ps", "-aq").split()
    containers = json.loads(home_backup.docker("inspect", *ids)) if ids else []
    for container in containers:
        for mount in container.get("Mounts", []):
            source = Path(mount.get("Source", "/"))
            for protected in (args.bundle, args.current_store):
                if source == protected or source.is_relative_to(protected) or protected.is_relative_to(source):
                    fail("BACKUP_RECOVERY_ALREADY_MOUNTED")
    pending, activation = store / ".recovery-pending", args.bundle / "activation.json"
    if not os.path.lexists(pending):
        private_file(activation)
        previous = json.loads(activation.read_bytes())
        if (previous.get("result") != "BACKUP_REVOCATIONS_MERGED"
                or previous.get("archive_sha256") != receipt["archive_sha256"]
                or previous.get("current_store_id") != current["store_id"]):
            fail("BACKUP_RECOVERY_STATE_INVALID")
    else:
        private_file(pending)
    with ExitStack() as locks:
        for directory in sorted((store, args.current_store)):
            locks.enter_context(store_lock(directory))
        if not os.path.lexists(pending):
            write_json(pending, {"version": 1, "reason": "merge-current-revocations"})
        if os.path.lexists(args.current_store / ".recovery-pending"):
            fail("BACKUP_CURRENT_REVOCATIONS_REQUIRED")
        before, paths, _ = snapshot({"revocations": args.current_store / "revocations"})
        # Check both sets. A tombstone is terminal even when its operation ID
        # differs, so restored revocations are retained rather than replaced.
        restored = snapshot({"revocations": store / "revocations"})[1]
        for path in list(restored.values()) + list(paths.values()):
            if path in {store / "revocations", args.current_store / "revocations"}:
                private_directory(path)
                continue
            private_file(path)
            value = json.loads(path.read_bytes())
            identifier, version = value.get("secret_id"), value.get("secret_version")
            expected = hashlib.sha256(canonical([identifier, version])).hexdigest() + ".json"
            if (path.parent.name != "revocations" or path.name != expected
                    or not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier)
                    or type(version) is not int or not 1 <= version <= 999999999
                    or value.get("store_id") != current["store_id"] or value.get("revoked") is not True):
                fail("BACKUP_REVOCATION_INVALID")
            destination = store / "revocations" / path.name
            if not os.path.lexists(destination):
                write_json(destination, value)
        if snapshot({"revocations": args.current_store / "revocations"})[0] != before:
            fail("BACKUP_REVOCATIONS_CHANGED")
        if current_access is not None:
            private_file(args.current_access_users)
            if args.current_access_users.read_bytes() != current_access:
                fail("BACKUP_ACCESS_CHANGED")
            write_json(args.bundle / "adapter/access-users.json", json.loads(current_access), replace=True)
        # Commit evidence durably before unlocking resolution. If interrupted
        # at any earlier point, retrying merges the same terminal tombstones.
        write_json(activation, {"result": "BACKUP_REVOCATIONS_MERGED", "current_store_id": current["store_id"],
                               "archive_sha256": receipt["archive_sha256"],
                               "revocations_sha256": hashlib.sha256(canonical(before)).hexdigest()}, replace=True)
        pending.unlink()
        sync_directory(store)
    return {"result": "BACKUP_REVOCATIONS_MERGED", "ready_for_offline_rebinding": True, "started_workers": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create")
    for field in ("config", "storage", "sealskin-config", "artifact", "acceptance", "master-key-file", "output"):
        create_parser.add_argument("--" + field, type=Path, required=True)
    create_parser.add_argument("--profile", required=True)
    create_parser.add_argument("--admin-recovery-file", type=Path,
                               help="Private admin recovery JSON if removed from the controller after provisioning")
    create_parser.add_argument("--recipient", required=True, help="age X25519 public recipient, never a private identity")
    create_parser.add_argument("--age", type=Path, default=Path("age"))
    create_parser.set_defaults(run=create)
    snapshot_parser = commands.add_parser("snapshot-legacy", help="Read-only inventory before stopping an old Worker")
    legacy_parser = commands.add_parser("create-legacy", help="Encrypt a stopped old deployment with no Store or entry access")
    for child in (snapshot_parser, legacy_parser):
        for field in ("config", "storage", "sealskin-config", "output"):
            child.add_argument("--" + field, type=Path, required=True)
        child.add_argument("--profile", required=True)
    snapshot_parser.set_defaults(run=snapshot_legacy)
    legacy_parser.add_argument("--legacy-snapshot", type=Path, required=True)
    legacy_parser.add_argument("--admin-recovery-file", type=Path)
    legacy_parser.add_argument("--recipient", required=True, help="age X25519 public recipient")
    legacy_parser.add_argument("--age", type=Path, default=Path("age"))
    legacy_parser.set_defaults(run=create)
    for command, function in (("verify", verify), ("restore", restore)):
        child = commands.add_parser(command)
        for field in ("archive", "identity", "scratch-root"):
            child.add_argument("--" + field, type=Path, required=True)
        child.add_argument("--age", type=Path, default=Path("age"))
        if command == "restore":
            child.add_argument("--target", type=Path, required=True)
        child.set_defaults(run=function)
    activation = commands.add_parser("activate")
    activation.add_argument("--bundle", type=Path, required=True)
    activation.add_argument("--current-store", type=Path, required=True)
    activation.add_argument("--current-access-users", type=Path,
                            help="Current trusted login registry; required when the archive enables entry access")
    activation.set_defaults(run=activate)
    args = parser.parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path) and key != "age":
            setattr(args, key, value.absolute())
    try:
        print(json.dumps(args.run(args)))
    except (Exception, SystemExit) as exc:
        print(json.dumps({"result": "FAIL", "code": str(exc) if isinstance(exc, BackupError) else "BACKUP_OPERATION_FAILED"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
