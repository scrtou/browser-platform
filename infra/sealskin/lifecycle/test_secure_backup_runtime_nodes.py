"""Real Unix socket and age regressions for stopped legacy Wayland Homes."""
import json
import os
import socket
import stat

import pytest

from test_secure_backup import backup, file, rewrite_archive, setup
from test_secure_backup_legacy import legacy


def endpoint(path):
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    # bind relative to a directory fd to keep long pytest roots below AF_UNIX's
    # pathname limit, without changing the process working directory.
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with socket.socket(socket.AF_UNIX) as stream:
            stream.bind(f"/proc/self/fd/{fd}/{path.name}")
    finally:
        os.close(fd)


def test_legacy_socket_excluded_without_deleting_or_omitting_browser_data(legacy):
    args, _, _, _, _ = legacy
    home = args.storage / "qa-owner/qa-home"
    sock = home / ".XDG/wayland-1"
    endpoint(sock)
    file(home / ".XDG/wayland-2", b"a regular file must survive")
    file(home / ".XDG/wayland-1.lock", b"lock-file-payload")
    result = backup.create(args)
    assert result["excluded_runtime_nodes"] == {"home/.XDG/wayland-1": "wayland-runtime-socket"}
    assert stat.S_ISSOCK(sock.lstat().st_mode)
    backup.verify(args)
    backup.restore(args)
    assert not os.path.lexists(args.target / "home/.XDG/wayland-1")
    assert (args.target / "home/.XDG/wayland-2").read_bytes() == b"a regular file must survive"
    assert (args.target / "home/.XDG/wayland-1.lock").read_bytes() == b"lock-file-payload"
    assert (args.target / "home/cookies.sqlite").read_bytes() == b"qa-browser-storage-content"


def test_store_format_uses_same_exact_runtime_rule(setup):
    args, root = setup
    endpoint(root / "home/.XDG/wayland-0")
    assert backup.create(args)["excluded_runtime_nodes"]
    backup.verify(args)
    backup.restore(args)
    assert not os.path.lexists(args.target / "home/.XDG/wayland-0")


@pytest.mark.parametrize("location,kind", [
    ("home/unknown", "socket"), ("home/.XDG/custom", "socket"),
    ("home/.XDG/wayland-1-extra", "socket"), ("control/.XDG/wayland-1", "socket"),
    ("home/.XDG/wayland-1", "fifo"), ("home/.XDG/nested/wayland-1", "socket"),
])
def test_unknown_special_node_or_wrong_type_remains_rejected(setup, location, kind):
    args, root = setup
    path = root / location
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if kind == "socket":
        endpoint(path)
    else:
        os.mkfifo(path)
    with pytest.raises(backup.BackupError, match="BACKUP_FILE_TYPE_UNSUPPORTED"):
        backup.create(args)
    assert not args.output.exists() and os.path.lexists(path)


@pytest.mark.parametrize("excluded", [[], {"control/keys/private.pem": "wayland-runtime-socket"},
    {"home/.XDG/wayland-1": "arbitrary"}, {"home/.XDG/wayland-2": "wayland-runtime-socket"},
    {"home/.XDG/../wayland-1": "wayland-runtime-socket"}])
def test_authenticated_but_invalid_exclusion_manifest_is_rejected(setup, excluded):
    args, root = setup
    endpoint(root / "home/.XDG/wayland-1")
    file(root / "home/.XDG/wayland-2", b"must not conflict with a real member")
    backup.create(args)
    def change(member, contents):
        if member.name == "manifest.json":
            manifest = json.loads(contents)
            manifest["excluded_runtime_nodes"] = excluded
            contents = backup.canonical(manifest)
        return member, contents
    rewrite_archive(args, change)
    with pytest.raises(backup.BackupError, match="BACKUP_MANIFEST_INVALID"):
        backup.restore(args)
    assert not args.target.exists() and not list(args.scratch_root.iterdir())


def test_socket_replacement_before_publication_prevents_archive(setup, monkeypatch):
    args, root = setup
    path = root / "home/.XDG/wayland-1"
    endpoint(path)
    def stopped(*_):
        path.unlink()
        file(path, b"persistent data appeared during backup")
        return {"status": "stopped"}
    monkeypatch.setattr(backup.home_backup, "require_stopped", stopped)
    with pytest.raises(backup.BackupError, match="BACKUP_SOURCE_CHANGED"):
        backup.create(args)
    assert not args.output.exists() and not list(args.output.parent.glob(".encrypted-backup-*"))
