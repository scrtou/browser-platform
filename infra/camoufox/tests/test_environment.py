"""Adversarial checks against the actual frozen artifact and pinned runtime."""

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, "/usr/local/lib/browser-platform")
import environment as engine


class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path(os.environ["BROWSER_PLATFORM_ARTIFACT_FILE"])
        cls.raw = cls.path.read_bytes()
        cls.sha256 = hashlib.sha256(cls.raw).hexdigest()
        cls.artifact = engine.load_artifact(cls.path, cls.sha256)
        cls.metadata = engine.runtime_metadata()

    def altered(self, change, code):
        artifact = copy.deepcopy(self.artifact)
        change(artifact)
        raw = engine.encode(artifact)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            path.write_bytes(raw)
            with patch.object(engine, "runtime_metadata", return_value=self.metadata):
                with self.assertRaisesRegex(engine.ArtifactError, "^" + code + "$"):
                    engine.load_artifact(path, hashlib.sha256(raw).hexdigest(), check_environment=False)

    def test_exact_bytes_not_reserialized_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            path.write_bytes(self.raw + b" ")
            with patch.object(engine, "runtime_metadata", side_effect=AssertionError("late validation")):
                with self.assertRaisesRegex(engine.ArtifactError, "ENVIRONMENT_ARTIFACT_MISMATCH"):
                    engine.load_artifact(path, self.sha256)

    def test_missing_hash(self):
        with self.assertRaisesRegex(engine.ArtifactError, "ENVIRONMENT_HASH_REQUIRED"):
            engine.load_artifact(self.path, "")

    def test_wrong_version_even_with_new_hash(self):
        self.altered(lambda artifact: artifact["runtime"].update(browserRelease="unapproved"), "ENVIRONMENT_VERSION_MISMATCH")

    def test_missing_seeds_not_regenerated(self):
        for key in engine.SEEDS:
            with self.subTest(seed=key):
                self.altered(lambda artifact: artifact["resolvedConfig"].pop(key), "ENVIRONMENT_SEED_MISSING")

    def test_seed_only_is_not_a_complete_result(self):
        self.altered(lambda artifact: artifact.update(browserforgeFingerprint={}), "BROWSERFORGE_RESULT_INCOMPLETE")

    def test_incomplete_browserforge_navigator_rejected(self):
        self.altered(lambda artifact: artifact["browserforgeFingerprint"].update(navigator={}), "BROWSERFORGE_RESULT_INCOMPLETE")

    def test_unknown_property_is_not_silently_skipped(self):
        self.altered(lambda artifact: artifact["resolvedConfig"].update({"unsupported:property": 1}), "UNSUPPORTED_CAPABILITY")

    def test_direct_proxy_setting_rejected(self):
        self.altered(lambda artifact: artifact["firefoxUserPrefs"].update({"network.proxy.type": 0}), "ENVIRONMENT_PROXY_POLICY_MISMATCH")

    def test_rendering_randomization_cannot_be_reenabled(self):
        for name in ("privacy.baselineFingerprintingProtection", "gfx.font_rendering.fallback.async"):
            with self.subTest(preference=name):
                self.altered(lambda artifact: artifact["firefoxUserPrefs"].update({name: True}), "ENVIRONMENT_PREFERENCE_MISMATCH")

    def test_spec_drift_rejected(self):
        self.altered(lambda artifact: artifact["resolvedConfig"].update(timezone="Etc/UTC"), "ENVIRONMENT_SPEC_MISMATCH")

    def test_unknown_capability_rejected(self):
        self.altered(lambda artifact: artifact["spec"]["requiredCapabilities"].append("unverified-capability"), "UNSUPPORTED_CAPABILITY")

    def test_environment_and_wayland_drift(self):
        for key, value in (("TZ", "Etc/UTC"), ("PIXELFLUX_WAYLAND", "true"), ("CAMOU_CONFIG_1", "{}")):
            with self.subTest(variable=key), patch.dict(os.environ, {key: value}), \
                    patch.object(engine, "runtime_metadata", return_value=self.metadata):
                with self.assertRaisesRegex(engine.ArtifactError, "ENVIRONMENT_CONFIG_DRIFT"):
                    engine.load_artifact(self.path, self.sha256)

    def test_replay_preserves_complete_config_without_generator(self):
        with patch.object(engine, "generate", side_effect=AssertionError("generator called")):
            first = engine.replay_environment(self.artifact)
            second = engine.replay_environment(self.artifact)
        chunks = sorted((key for key in first if key.startswith("CAMOU_CONFIG_")), key=lambda key: int(key.rsplit("_", 1)[1]))
        self.assertEqual(json.loads("".join(first[key] for key in chunks)), self.artifact["resolvedConfig"])
        self.assertEqual(first, second)

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        for raw in (b'{"seed":1,"seed":2}', b'{"seed":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(engine.ArtifactError):
                engine.decode(raw)

    def test_published_revision_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            engine.publish(path, self.artifact)
            with self.assertRaises(FileExistsError):
                engine.publish(path, {"replaced": True})
            self.assertEqual(path.read_bytes(), engine.encode(self.artifact))

    def test_unvalidated_candidate_cannot_be_activated(self):
        with patch.dict(os.environ, {"BROWSER_PLATFORM_ACCEPTANCE_SHA256": ""}):
            with self.assertRaisesRegex(engine.ArtifactError, "ENVIRONMENT_ACCEPTANCE_REQUIRED"):
                engine.verify_acceptance(self.artifact, self.sha256)

    def test_failed_or_unrelated_acceptance_cannot_be_reused(self):
        complete = {
            "schemaVersion": "browser-platform/camoufox-acceptance/v1",
            "phase": "all", "status": "pass", "artifactSHA256": self.sha256,
            "runtimeImageDigest": self.artifact["runtimeImageDigest"],
            "results": {"artifactTests": "pass", "entrypointRejections": dict.fromkeys(engine.REJECTIONS, "rejected"),
                        "homeReplay": {"homes": 2, "recreationsPerHome": 10, "observationsStable": True,
                                       "storageRestored": True, "offlineBackupRestore": "pass"}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acceptance.json"
            for name, change, expected in (
                ("valid", lambda r: None, None),
                ("failed", lambda r: r.update(status="failed"), "ENVIRONMENT_ACCEPTANCE_FAILED"),
                ("other-artifact", lambda r: r.update(artifactSHA256="0" * 64), "ENVIRONMENT_ACCEPTANCE_MISMATCH"),
                ("other-image", lambda r: r.update(runtimeImageDigest="sha256:" + "0" * 64), "ENVIRONMENT_ACCEPTANCE_MISMATCH"),
                ("unit-only", lambda r: r.update(phase="unit"), "ENVIRONMENT_ACCEPTANCE_FAILED"),
                ("short-run", lambda r: r["results"]["homeReplay"].update(recreationsPerHome=1), "ENVIRONMENT_ACCEPTANCE_INCOMPLETE"),
                ("unstable", lambda r: r["results"]["homeReplay"].update(observationsStable=False), "ENVIRONMENT_ACCEPTANCE_INCOMPLETE"),
            ):
                report = copy.deepcopy(complete)
                change(report)
                raw = engine.encode(report)
                path.write_bytes(raw)
                with self.subTest(name=name), patch.dict(os.environ, {
                    "BROWSER_PLATFORM_ACCEPTANCE_FILE": str(path),
                    "BROWSER_PLATFORM_ACCEPTANCE_SHA256": hashlib.sha256(raw).hexdigest(),
                }):
                    if expected:
                        with self.assertRaisesRegex(engine.ArtifactError, expected):
                            engine.verify_acceptance(self.artifact, self.sha256)
                    else:
                        engine.verify_acceptance(self.artifact, self.sha256)


if __name__ == "__main__":
    unittest.main()
