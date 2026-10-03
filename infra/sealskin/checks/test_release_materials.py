import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("release_materials", Path(__file__).with_name("check-release-materials.py"))
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ReleaseMaterialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = self.root / "binary"
        self.payload.write_bytes(b"accepted build")
        self.payload.chmod(0o600)
        self.item = {"path": "binary", "sha256": hashlib.sha256(self.payload.read_bytes()).hexdigest(),
                     "size": self.payload.stat().st_size, "role": "binary"}

    def manifest(self, entries=None):
        manifest = {"schema": "browser-platform-materials-v1", "purpose": "audit-only",
                    "files": entries if entries is not None else [self.item]}
        raw = json.dumps(manifest).encode()
        p = self.root / "manifest.json"
        p.write_bytes(raw)
        p.chmod(0o600)
        return hashlib.sha256(raw).hexdigest()

    def test_valid_then_tampered_payload_and_manifest(self):
        pin = self.manifest()
        self.assertEqual(checker.verify(self.root, pin)["result"], "VERIFIED")
        self.payload.write_bytes(b"tampered build")
        with self.assertRaisesRegex(checker.Rejected, "MEMBER_DIGEST_MISMATCH"):
            checker.verify(self.root, pin)
        self.item["sha256"] = hashlib.sha256(self.payload.read_bytes()).hexdigest()
        self.manifest()
        with self.assertRaisesRegex(checker.Rejected, "MANIFEST_DIGEST_MISMATCH"):
            checker.verify(self.root, pin)

    def test_unlisted_file_and_public_permissions(self):
        pin = self.manifest()
        extra = self.root / "unreviewed"
        extra.write_bytes(b"unreviewed")
        with self.assertRaisesRegex(checker.Rejected, "UNLISTED_PAYLOAD"):
            checker.verify(self.root, pin)
        extra.unlink()
        self.payload.chmod(0o644)
        with self.assertRaisesRegex(checker.Rejected, "UNSAFE_FILE_OR_PERMISSIONS"):
            checker.verify(self.root, pin)

    def test_paths_and_symlink_cannot_escape(self):
        for name in ("../binary", "/binary", "dir//binary", "./binary", "dir/../binary"):
            with self.subTest(path=name):
                pin = self.manifest([{**self.item, "path": name}])
                with self.assertRaisesRegex(checker.Rejected, "INVALID_PATH"):
                    checker.verify(self.root, pin)
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        pin = self.manifest([{**self.item, "path": "alias/binary"}])
        with self.assertRaises(OSError):
            checker.verify(self.root, pin)

    def test_duplicate_paths_rejected(self):
        pin = self.manifest([self.item, self.item])
        with self.assertRaisesRegex(checker.Rejected, "DUPLICATE_PATH"):
            checker.verify(self.root, pin)

    def test_fifo_is_rejected_without_blocking(self):
        self.payload.unlink()
        os.mkfifo(self.payload, 0o600)
        pin = self.manifest()
        with self.assertRaisesRegex(checker.Rejected, "UNSAFE_FILE_OR_PERMISSIONS"):
            checker.verify(self.root, pin)


if __name__ == "__main__":
    unittest.main()
