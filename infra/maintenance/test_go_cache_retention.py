import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("retention", Path(__file__).with_name("go-cache-retention.py"))
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


class CacheRetentionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "runtime"
        self.cache = self.root / "completed-task" / "go-cache"
        self.cache.mkdir(parents=True)
        (self.cache / "README").write_text(retention.MARKER + " from the Go build system.\n")
        (self.cache / "aa").mkdir()
        self.file = self.cache / "aa" / ("a" * 64 + "-d")
        self.file.write_bytes(b"compiled artifact")
        self.idle = patch.object(retention, "ensure_idle")
        self.idle.start()
        self.addCleanup(self.idle.stop)

    def test_plan_and_clear_preserve_adjacent_source(self):
        source = self.cache.parent / "source.go"
        source.write_text("package main\n")
        expected = retention.plan(self.root, self.cache)
        self.assertTrue(self.file.exists())
        result = retention.clear(json.loads(json.dumps(expected)))
        self.assertEqual(result["files_removed"], 2)
        self.assertEqual(list(self.cache.iterdir()), [])
        self.assertEqual(source.read_text(), "package main\n")

    def test_changed_cache_refuses_all_deletion(self):
        expected = retention.plan(self.root, self.cache)
        self.file.write_bytes(b"new build")
        with self.assertRaises(ValueError):
            retention.clear(expected)
        self.assertTrue((self.cache / "README").exists())
        self.assertEqual(self.file.read_bytes(), b"new build")

    def test_symlink_file_is_rejected(self):
        self.file.unlink()
        self.file.symlink_to(self.cache.parent / "outside")
        with self.assertRaises(ValueError):
            retention.plan(self.root, self.cache)

    def test_non_cache_content_is_rejected(self):
        (self.cache / "state.json").write_text("{}")
        with self.assertRaises(ValueError):
            retention.plan(self.root, self.cache)
        self.assertTrue(self.file.exists())

    def test_root_and_ancestor_symlinks_are_rejected(self):
        link = self.root / "linked"
        link.symlink_to(self.cache.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            retention.plan(self.root, link / "go-cache")

    def test_missing_marker_and_outside_scope_are_rejected(self):
        with self.assertRaises(ValueError):
            retention.plan(self.root, self.root)
        (self.cache / "README").write_text("project source")
        with self.assertRaises(ValueError):
            retention.plan(self.root, self.cache)


class CacheActivityTest(unittest.TestCase):
    def test_active_compiler_blocks_cleanup(self):
        with patch.object(retention.subprocess, "check_output", return_value="python3\ncompile\n"):
            with self.assertRaises(ValueError):
                retention.ensure_idle(Path("/project/runtime/qa/go-cache"))

    def test_parent_mount_blocks_cleanup_even_for_stopped_container(self):
        results = ["python3\n", "container-id\n", json.dumps([
            {"State": {"Running": False}, "Mounts": [{"Source": "/project/runtime/qa"}]}
        ])]
        with patch.object(retention.subprocess, "check_output", side_effect=results):
            with self.assertRaises(ValueError):
                retention.ensure_idle(Path("/project/runtime/qa/go-cache"))


if __name__ == "__main__":
    unittest.main()
