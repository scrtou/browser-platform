"""Deployment choices must not bypass the managed network or addon revision."""

import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("prepare_sealskin", ROOT / "prepare-sealskin.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PreparationTests(unittest.TestCase):
    def test_managed_policy_cannot_add_a_static_network(self):
        overrides, reference = prepare.network_binding(None, "camoufox-r1", "a" * 64)
        self.assertFalse(overrides)
        self.assertEqual(reference, {"network_policy_id": "camoufox-r1", "network_policy_sha256": "a" * 64})
        for args in [("bridge", "camoufox-r1", "a" * 64), (None, "camoufox-r1", None),
                     (None, None, "a" * 64), (None, "../escape", "a" * 64),
                     (None, "camoufox-r1", "0" * 64), (None, "camoufox-r1", "A" * 64)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                prepare.network_binding(*args)

    def test_existing_static_default_is_explicit(self):
        self.assertEqual(prepare.network_binding(None, None, None), ({"network": "browser-platform-personal"}, {}))

    def test_clipboard_revision_and_permissions(self):
        names = ("enable-screenshot-paste.py", "screenshot-paste.js", "screenshot-paste-init.sh")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in names:
                shutil.copyfile(ROOT.parent / "sealskin" / name, directory / name)
                (directory / name).chmod(0o644)
            mounts, hashes = prepare.clipboard_mounts(directory)
            self.assertEqual(set(hashes), set(names))
            self.assertTrue(all(mount["ReadOnly"] for mount in mounts))
            self.assertNotIn("/config", [mount["Target"] for mount in mounts])
            alias = directory / 'alias'
            alias.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(ValueError):
                prepare.clipboard_mounts(alias)
            alias.unlink()
            path = directory / names[0]
            original = path.read_bytes()
            path.write_bytes(original + b"\n# drift")
            with self.assertRaises(ValueError):
                prepare.clipboard_mounts(directory)
            path.write_bytes(original)
            path.chmod(0o666)
            with self.assertRaises(ValueError):
                prepare.clipboard_mounts(directory)
            path.unlink()
            path.symlink_to(ROOT.parent / "sealskin" / names[0])
            with self.assertRaises(ValueError):
                prepare.clipboard_mounts(directory)


if __name__ == "__main__":
    unittest.main()
