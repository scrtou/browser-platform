"""Keep the policy's private runtime inputs usable after encrypted recovery."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from test_secure_backup import backup, file, rewrite_archive, setup, source_arguments
from test_secure_backup_legacy import legacy

real_collect_sources = backup.collect_sources


def add_assets(args):
    assets = args.sealskin_config / "coherence-assets"
    values = {"artifact": args.artifact.read_bytes(), "acceptance": args.acceptance.read_bytes(),
              "geoip": b"8.8.8.0,8.8.8.255,US\n"}
    references = {}
    for name, raw in values.items():
        path = file(assets / (name + ".data"), raw)
        references.update({name + "_file": "/config/.config/sealskin/coherence-assets/" + path.name,
                           name + "_sha256": hashlib.sha256(raw).hexdigest()})
    registry = {"version": 1, "policies": {"qa-r1": {"coherence": {"mode": "strict", **references}}}}
    file(args.sealskin_config / "profile-network-policies.json", backup.canonical(registry))
    return assets, values, registry


@pytest.fixture
def coherent(setup, monkeypatch):
    args, root = setup
    source_arguments(args, root, monkeypatch)
    assets, values, registry = add_assets(args)
    monkeypatch.setattr(backup, "collect_sources", real_collect_sources)
    return args, root, assets, values, registry


def test_policy_assets_survive_encrypted_restore(coherent):
    args, _, _, values, _ = coherent
    backup.create(args)
    assert backup.verify(args)["archive_format"] == backup.FORMAT
    backup.restore(args)
    for name, expected in values.items():
        restored = args.target / "control/coherence-assets" / (name + ".data")
        assert restored.read_bytes() == expected
        assert restored.stat().st_mode & 0o777 == 0o600


def test_legacy_format_also_preserves_referenced_assets(legacy):
    args, root, set_status, _, _ = legacy
    _, values, _ = add_assets(args)
    set_status("running")
    args.output = root / "coherence-snapshot.json"
    backup.snapshot_legacy(args)
    args.legacy_snapshot, args.output = args.output, args.archive
    set_status("stopped")
    backup.create(args)
    assert backup.restore(args)["offline_only"]
    assert (args.target / "control/coherence-assets/geoip.data").read_bytes() == values["geoip"]


@pytest.mark.parametrize("missing", ["directory", "artifact", "acceptance", "geoip"])
def test_required_asset_missing_rejects_before_archive(coherent, missing):
    args, _, assets, _, _ = coherent
    if missing == "directory": shutil.rmtree(assets)
    else: (assets / (missing + ".data")).unlink()
    with pytest.raises(backup.BackupError, match="BACKUP_COHERENCE_ASSET_INVALID"):
        backup.create(args)
    assert not args.archive.exists()


@pytest.mark.parametrize("damage", ["digest", "directory_mode", "file_mode", "hardlink", "symlink", "oversized"])
def test_unsafe_or_changed_assets_reject_before_archive(coherent, damage):
    args, root, assets, _, _ = coherent
    path = assets / "artifact.data"
    if damage == "digest": path.write_bytes(b"different artifact")
    if damage == "directory_mode": assets.chmod(0o755)
    if damage == "file_mode": path.chmod(0o644)
    if damage == "hardlink": os.link(path, root / "second-link")
    if damage == "symlink":
        path.unlink()
        path.symlink_to(args.artifact)
    if damage == "oversized": path.write_bytes(b"x" * ((1 << 20) + 1))
    with pytest.raises(backup.BackupError):
        backup.create(args)
    assert not args.archive.exists()


@pytest.mark.parametrize("damage", ["outside", "traversal", "missing_hash", "conflicting_hash", "wrong_type"])
def test_policy_cannot_reference_other_paths_or_inconsistent_assets(coherent, damage):
    args, _, _, _, registry = coherent
    value = registry["policies"]["qa-r1"]["coherence"]
    if damage == "outside": value["artifact_file"] = "/etc/passwd"
    if damage == "traversal": value["artifact_file"] = "/config/.config/sealskin/coherence-assets/../admin.json"
    if damage == "missing_hash": value.pop("artifact_sha256")
    if damage == "wrong_type": registry["policies"]["qa-r1"]["coherence"] = []
    if damage == "conflicting_hash":
        registry["policies"]["qa-r2"] = copy.deepcopy(registry["policies"]["qa-r1"])
        registry["policies"]["qa-r2"]["coherence"]["artifact_sha256"] = "0" * 64
    file(args.sealskin_config / "profile-network-policies.json", backup.canonical(registry))
    with pytest.raises(backup.BackupError):
        backup.create(args)
    assert not args.archive.exists()


@pytest.mark.parametrize("damage", ["asset", "policy", "permissions"])
def test_authenticated_archive_must_still_match_policy_assets(coherent, damage):
    args, _, _, _, _ = coherent
    backup.create(args)
    updated = {}
    def change(member, raw):
        if member.name == "control/coherence-assets/artifact.data":
            if damage == "asset":
                raw = b"changed but authenticated artifact"
                updated[member.name] = {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            if damage == "permissions":
                member.mode = 0o644
                updated[member.name] = {"mode": 0o644}
        if member.name == "control/profile-network-policies.json" and damage == "policy":
            value = json.loads(raw)
            value["policies"]["qa-r1"]["coherence"]["artifact_sha256"] = "0" * 64
            raw = backup.canonical(value)
            updated[member.name] = {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if member.name == "manifest.json":
            value = json.loads(raw)
            for name, changes in updated.items(): value["entries"][name].update(changes)
            raw = backup.canonical(value)
        return member, raw
    rewrite_archive(args, change)
    with pytest.raises(backup.BackupError, match="BACKUP_COHERENCE_ASSET_INVALID"):
        backup.restore(args)
    assert not args.target.exists() and not list(args.scratch_root.iterdir())


def test_policy_without_optional_geoip_can_be_backed_up(coherent):
    args, _, assets, _, registry = coherent
    value = registry["policies"]["qa-r1"]["coherence"]
    value["geoip_file"] = value["geoip_sha256"] = ""
    (assets / "geoip.data").unlink()
    file(args.sealskin_config / "profile-network-policies.json", backup.canonical(registry))
    backup.create(args)
    backup.restore(args)
    assert not (args.target / "control/coherence-assets/geoip.data").exists()
