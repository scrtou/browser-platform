import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("resize_window", ROOT / "resize-window.py")
window = importlib.util.module_from_spec(spec)
spec.loader.exec_module(window)


class WindowRevisionTests(unittest.TestCase):
    def setUp(self):
        spec = json.loads((ROOT / "spec.tw.json").read_text())
        spec.update(id="env-test-r7", revision=7, window={"width": 1600, "height": 900})
        self.artifact = {"id": "env-test-r7-artifact-1", "createdAt": "original", "spec": spec,
            "runtimeImageDigest": "sha256:" + "a" * 64, "runtime": {"fixed": "metadata"},
            "browserforgeFingerprint": {"screen": {"outerWidth": 1600}, "device": [1, 2, 3]},
            "resolvedConfig": {"window.outerWidth": 1600, "window.outerHeight": 900,
                "window.screenX": 160, "window.screenY": 90, "window.devicePixelRatio": 1,
                "screen.width": 1920, "screen.height": 1080, "canvas:seed": 123},
            "firefoxUserPrefs": {"network.proxy.type": 1}}

    def test_full_desktop_revision_preserves_original_device_and_source(self):
        before = copy.deepcopy(self.artifact)
        candidate = window.resize(self.artifact, "env-test-r8", 8, 1920, 1080)
        self.assertEqual(self.artifact, before)
        for key in ("runtime", "runtimeImageDigest", "browserforgeFingerprint", "firefoxUserPrefs"):
            self.assertEqual(candidate[key], before[key])
        self.assertEqual(candidate["spec"]["screen"], before["spec"]["screen"])
        allowed = {"window.outerWidth", "window.outerHeight", "window.screenX", "window.screenY"}
        self.assertEqual({k:v for k,v in candidate["resolvedConfig"].items() if k not in allowed},
                         {k:v for k,v in before["resolvedConfig"].items() if k not in allowed})
        self.assertEqual({k:candidate["resolvedConfig"][k] for k in allowed},
            {"window.outerWidth":1920,"window.outerHeight":1080,"window.screenX":0,"window.screenY":0})
        self.assertEqual(candidate["id"], "env-test-r8-artifact-1")

    def test_invalid_or_conflicting_window_revision_is_rejected(self):
        for environment_id, revision, width, height in [
            ("env-test-r7",8,1920,1080), ("env-test-r8",7,1920,1080),
            ("bad/id",8,1920,1080), ("env-test-r8",True,1920,1080),
            ("env-test-r8",8,1921,1080), ("env-test-r8",8,1920,1081),
            ("env-test-r8",8,639,480), ("env-test-r8",8,640,479),
            ("env-test-r8",8,True,1080)]:
            with self.subTest(environment_id=environment_id, revision=revision, width=width, height=height), self.assertRaises(ValueError):
                window.resize(self.artifact, environment_id, revision, width, height)
        self.artifact["resolvedConfig"]["window.innerWidth"] = 1600
        with self.assertRaises(ValueError):
            window.resize(self.artifact, "env-test-r8", 8, 1920, 1080)

    def test_smaller_window_has_consistent_center_position(self):
        candidate = window.resize(self.artifact, "env-test-r8", 8, 1280, 800)
        self.assertEqual(candidate["resolvedConfig"]["window.screenX"], 320)
        self.assertEqual(candidate["resolvedConfig"]["window.screenY"], 140)


if __name__ == "__main__":
    unittest.main()
