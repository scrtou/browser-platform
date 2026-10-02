#!/usr/bin/env python3
"""Restore an explicitly transferred synthetic QA checkpoint on another host.

Requires imported images, separately supplied age identity and reviewed current
QA trust inputs. Never accepts production owners or creates a source fixture.
Failure evidence and partially restored services are retained for diagnosis.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("remote_dr", HERE / "check-disaster-recovery.py")
dr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dr)


class RemoteDrill(dr.Drill):
    def __init__(self, root):
        self.root = root.resolve()
        assert self.root.name.startswith("r6ap-") and "runtime" in self.root.parts
        assert self.root.is_dir() and self.root.stat().st_uid == os.getuid()
        assert self.root.stat().st_mode & 0o077 == 0
        self.inputs = self.root / "inputs"
        self.backup = self.root / "backup"
        self.source = self.root / "source-must-remain-absent"
        assert not self.source.exists()
        self.age = self.inputs / "bin/age"
        self.script = dr.ROOT / "infra/sealskin/lifecycle/secure-backup.py"
        self.storage = dr.module("remote_dr_store", self.inputs / "secret_store.py")
        manifest = dr.read(self.inputs / "MANIFEST.json")
        for name, digest in manifest.items():
            path = self.inputs / name
            assert not path.is_symlink() and path.resolve().is_relative_to(self.inputs)
            assert dr.sha(path) == digest, "recovery input checksum mismatch"
        assert dr.sha(self.backup / "home.age") == dr.read(self.backup / "receipt.json")["archive_sha256"]
        self.target = self.root / "restored"
        self.bundle = self.root / "bundle"

    def restore_bundle(self, bundle, label):
        assert not bundle.exists()
        with tempfile.TemporaryDirectory(prefix="r6ap-auth-", dir="/dev/shm") as scratch:
            args = [sys.executable, self.script, "restore", "--age", self.age,
                    "--archive", self.backup / "home.age", "--identity", self.root / "keys/age-identity.txt",
                    "--scratch-root", scratch, "--target", bundle]
            self.command(args, label + "-decrypt", timeout=600)
            assert not list(Path(scratch).iterdir())
        store = self.storage.FileSecretStore(bundle / "control/proxy-secret-store", bundle / "key-material/secret-store.key")
        grant = {"owner": "network-qa", "profile": dr.PROFILE, "home": dr.HOME, "app": dr.migration.APP}
        refs = self.storage.references("dr-check", 1)
        try:
            store.resolve(grant, refs["username"], refs["password"])
            raise AssertionError("unreviewed restore was usable")
        except self.storage.SecretError as error:
            assert error.code == "SECRET_RECOVERY_LOCKED"
        args = [sys.executable, self.script, "activate", "--bundle", bundle,
                "--current-store", self.inputs / "current-store"]
        self.command(args, label + "-missing-users", expected=1)
        self.command(args + ["--current-access-users", self.inputs / "current-users.json"], label + "-activate")
        store.resolve(grant, refs["username"], refs["password"])
        refs = self.storage.references("dr-check", 2)
        try:
            store.resolve(grant, refs["username"], refs["password"])
            raise AssertionError("revoked secret was restored")
        except self.storage.SecretError as error:
            assert error.code == "SECRET_REVOKED"

    def restore(self):
        start = time.monotonic()
        assert not self.target.exists()
        images = dr.read(self.inputs / "images.json")
        for image in set(images.values()):
            actual = json.loads(dr.network.docker("image", "inspect", image).stdout)[0]
            assert actual["Id"] == image and actual["Architecture"] == "amd64"
        self.restore_bundle(self.bundle, "initial")
        self.target.mkdir(mode=0o700)
        dr.write(self.root / "staged.json", dr.layout.stage(self.bundle, self.target / "qa"))
        self.start_services(self.target / "qa", self.bundle / "key-material/secret-store.key", "r6ap-recovered")
        dr.write(self.root / "restore-timing.json", {"seconds_to_services": round(time.monotonic() - start, 3)})
        print("PASS fresh-root services started using imported image IDs", flush=True)

    def verify(self):
        # Inherited checks cover login, disabled user, three stores, display,
        # current HTTPS, bypass denial, new generation and normal release.
        super().verify()
        result = dr.read(self.root / "recovery-result.json")
        result["scope"] = "independent host; transferred synthetic checkpoint; cold imported image IDs"
        result["adapter_sha256"] = dr.sha(self.target / "qa/bin/profile-adapter")
        dr.write(self.root / "recovery-result.json", result)

    def rollback(self):
        assert dr.read(self.root / "recovery-result.json")["result"] == "PASS"
        self.retire(self.target / "qa")
        bundle = self.root / "rollback-bundle"
        self.restore_bundle(bundle, "rollback")
        target = self.root / "rollback/runtime/qa"
        dr.layout.stage(bundle, target)
        self.start_services(target, bundle / "key-material/secret-store.key", "r6ap-rollback")
        browser, _, _ = self.launch(target, "rollback")
        self.stop(target, browser)
        self.retire(target)
        dr.write(self.root / "rollback-result.json", {
            "result": "PASS", "second_fresh_root": True, "checkpoint_stores_read": True,
            "latest_trust_preserved": True, "normal_stop_and_services_retired": True,
            "reverse_replication": False})
        print("PASS checkpoint rollback into a second root; QA services retired", flush=True)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("restore", "verify", "rollback"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    getattr(RemoteDrill(args.root), args.phase)()


if __name__ == "__main__":
    main()
