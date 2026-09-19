"""The job runner publishes only complete, accepted results and never loses evidence."""

import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("environment_job", ROOT / "environment-job.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
from environment import encode  # noqa: E402

IMAGE = "sha256:" + "1" * 64
JOB = "job-0123456789abcdef"


def job_spec(**overrides):
    value = {"id": "env-custom-0123456789abcdef", "revision": 1, "osFamily": "linux", "locale": "en-US",
             "languages": ["en-US", "en"], "timezone": "America/New_York",
             "screen": {"width": 1920, "height": 1080, "deviceScaleFactor": 1}, "window": {"width": 1920, "height": 1080},
             "webrtcPolicy": "disabled", "geolocationPolicy": "disabled",
             "requiredCapabilities": ["locale", "languages", "timezone", "fixed-screen", "fixed-dpr",
                                      "frozen-device-config", "webrtc-disabled", "proxy-only"]}
    value.update(overrides)
    return value


def request(job_id=JOB, **overrides):
    value = {"version": 1, "job_id": job_id, "actor": "root", "requested_at": "2026-09-18T20:00:00+00:00", "spec": job_spec()}
    value.update(overrides)
    return value


class FakeFixture:
    def __init__(self, job_id, image):
        self.networks = {"internal": "fake-internal-" + job_id, "egress": "fake-egress"}
        FakeFixture.entered.append(job_id)

    entered = []
    exited = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        FakeFixture.exited.append(self.networks["internal"])
        return False


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        os.chmod(base, 0o700)
        self.spool = runner.Spool(base / "spool")
        self.catalog = base / "catalog" / "environment-catalog.json"
        self.args = SimpleNamespace(image=IMAGE, recreations=10, min_free_mib=2048, catalog=self.catalog,
                                    session_origin="https://sessions.example/", username="profile-adapter", clipboard_addon=None,
                                    store="SealSkin Apps", template="Default", verify_in_image=False)
        self.prepare = runner.load_prepare()
        self.accept_calls = []
        FakeFixture.entered.clear()
        FakeFixture.exited.clear()

    def tearDown(self):
        self.temporary.cleanup()

    def enqueue(self, value, job_id=JOB):
        path = self.spool.root / "queue" / (job_id + ".json")
        runner.write_private(path, encode(value))
        return path

    def fake_generate(self, spec, image, artifact_dir, evidence_dir):
        artifact = {"schemaVersion": "browser-platform/camoufox-environment/v1", "id": spec["id"] + "-artifact-1",
                    "createdAt": "2026-09-18T20:01:00+00:00", "spec": spec, "runtime": {}, "runtimeImageDigest": image,
                    "browserforgeFingerprint": {}, "resolvedConfig": {"audio:seed": 1}, "firefoxUserPrefs": {}}
        runner.write_private(artifact_dir / "environment.json", encode(artifact))
        return 2

    def fake_accept(self, artifact_path, network, report_path, recreations, log_path, *, status="pass"):
        self.accept_calls.append((network, recreations))
        raw = artifact_path.read_bytes()
        report = {"schemaVersion": "browser-platform/camoufox-acceptance/v1", "status": status, "phase": "all",
                  "artifactSHA256": hashlib.sha256(raw).hexdigest(), "runtimeImageDigest": IMAGE,
                  "results": {"artifactTests": "pass", "homeReplay": {"homes": 2, "recreationsPerHome": recreations,
                                                                       "observationsStable": True, "storageRestored": True,
                                                                       "offlineBackupRestore": "pass"}}}
        runner.write_private(report_path, encode(report))
        log_path.write_text("fake acceptance\n")
        return 0 if status == "pass" else 1

    def hooks(self, **overrides):
        hooks = dict(generator=self.fake_generate, fixture=FakeFixture, accept=self.fake_accept,
                     capabilities=lambda image: {"browser_shutdown_version": 1, "session_auth_version": 1},
                     memory=lambda: 4096, resolve_image=lambda image: image)
        hooks.update(overrides)
        return hooks

    def test_accepted_job_publishes_a_complete_catalog_entry(self):
        self.enqueue(request())
        self.assertEqual(runner.run_next(self.spool, self.args, self.prepare, **self.hooks()), "accepted")
        status = self.spool.status(JOB)
        self.assertEqual((status["status"], status["phase"], status["attempts"], status["environment_id"]),
                         ("accepted", "done", 2, "env-custom-0123456789abcdef"))
        self.assertEqual(self.accept_calls, [("fake-internal-" + JOB, 10)])
        self.assertEqual(FakeFixture.exited, ["fake-internal-" + JOB])
        catalog = json.loads(self.catalog.read_bytes())
        self.assertEqual(self.catalog.stat().st_mode & 0o077, 0)
        entry = catalog["artifacts"][0]
        artifact_dir = self.spool.root / "artifacts" / "env-custom-0123456789abcdef"
        self.assertEqual(entry["id"], "env-custom-0123456789abcdef")
        self.assertEqual(entry["sha256"], hashlib.sha256((artifact_dir / "environment.json").read_bytes()).hexdigest())
        self.assertEqual(entry["acceptance_sha256"], hashlib.sha256((artifact_dir / "acceptance.json").read_bytes()).hexdigest())
        self.assertEqual((entry["source"], entry["status"], entry["image"], entry["job_id"]), ("custom", "accepted", IMAGE, JOB))
        self.assertEqual((entry["locale"], entry["timezone"], entry["screen"]), ("en-US", "America/New_York", "1920x1080@1"))
        self.assertEqual(entry["required_runtime_capabilities"], {"browser_shutdown_version": 1, "session_auth_version": 1})
        provider = entry["application"]["provider_config"]
        self.assertEqual(provider["image"], IMAGE)
        self.assertNotIn("network_policy_id", provider)
        self.assertNotIn("network", provider["docker_overrides"])
        sources = {mount["Target"]: mount["Source"] for mount in provider["docker_overrides"]["mounts"]}
        self.assertEqual(sources["/run/browser-platform/environment.json"], str(artifact_dir / "environment.json"))
        self.assertEqual(sources["/run/browser-platform/acceptance.json"], str(artifact_dir / "acceptance.json"))
        self.assertTrue(all(mount["ReadOnly"] for mount in provider["docker_overrides"]["mounts"]))
        env = {item["name"]: item["value"] for item in provider["env"]}
        self.assertEqual(env["BROWSER_PLATFORM_ACCEPTANCE_SHA256"], entry["acceptance_sha256"])
        self.assertEqual(env["BROWSER_PLATFORM_ARTIFACT_SHA256"], entry["sha256"])
        self.assertEqual(env["TZ"], "America/New_York")
        self.assertEqual(provider["docker_overrides"]["labels"]["browser-platform.environment"], "env-custom-0123456789abcdef")
        # A finished job is not picked up again; the request stays as the audit copy.
        self.assertIsNone(runner.run_next(self.spool, self.args, self.prepare, **self.hooks()))
        self.assertTrue((self.spool.root / "queue" / (JOB + ".json")).exists())

    def test_invalid_requests_fail_before_any_generation(self):
        cases = {
            "job-ffffffffffffffff": request(job_id="job-ffffffffffffffff"),  # spec id does not match job id
            "job-0000000000000001": request(job_id="job-0000000000000001", spec=job_spec(id="env-custom-0000000000000001",
                                                                                          screen={"width": 1920, "height": 1080, "deviceScaleFactor": 2})),
            "job-0000000000000002": {**request(job_id="job-0000000000000002", spec=job_spec(id="env-custom-0000000000000002")), "extra": 1},
            "job-0000000000000003": request(job_id="job-0000000000000003", spec=job_spec(id="env-custom-0000000000000003", locale="en-GB")),
            "job-0000000000000004": request(job_id="job-0000000000000004", actor="../root", spec=job_spec(id="env-custom-0000000000000004")),
        }
        expected = {"job-ffffffffffffffff": "ENVIRONMENT_JOB_INVALID", "job-0000000000000001": "UNSUPPORTED_CAPABILITY",
                    "job-0000000000000002": "ENVIRONMENT_JOB_INVALID", "job-0000000000000003": "ENVIRONMENT_JOB_INVALID",
                    "job-0000000000000004": "ENVIRONMENT_JOB_INVALID"}
        generated = []
        for job_id, value in cases.items():
            self.enqueue(value, job_id)
            time.sleep(0.01)
        for _ in cases:
            self.assertEqual(runner.run_next(self.spool, self.args, self.prepare, **self.hooks(generator=lambda *a: generated.append(a))), "failed")
        for job_id, code in expected.items():
            status = self.spool.status(job_id)
            self.assertEqual((status["status"], status["phase"], status["code"]), ("failed", "validate", code), job_id)
        self.assertEqual(generated, [])
        self.assertFalse(self.catalog.exists())

    def test_low_memory_keeps_the_job_queued_with_a_hint(self):
        self.enqueue(request())
        self.assertEqual(runner.run_next(self.spool, self.args, self.prepare, **self.hooks(memory=lambda: 512)), "queued")
        status = self.spool.status(JOB)
        self.assertEqual((status["status"], status["code"]), ("queued", "HOST_MEMORY_LOW"))
        self.assertIn("512 MiB", status["message"])
        self.assertEqual(runner.run_next(self.spool, self.args, self.prepare, **self.hooks()), "accepted")

    def test_generation_retries_only_spec_mismatch_and_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            os.chmod(base, 0o700)
            artifact_dir, evidence_dir = runner.private_directory(base / "a"), runner.private_directory(base / "e")
            outcomes = [SimpleNamespace(returncode=1, stdout="ENVIRONMENT_SPEC_MISMATCH\n", stderr=""),
                        SimpleNamespace(returncode=1, stdout="", stderr="ENVIRONMENT_SPEC_MISMATCH"),
                        SimpleNamespace(returncode=0, stdout='{"status":"candidate"}', stderr="")]
            calls = []

            def once(spec_path, home, output_dir, output_name, image):
                calls.append(output_name)
                result = outcomes[len(calls) - 1]
                if result.returncode == 0:
                    (output_dir / output_name).write_bytes(b"{}")
                return result

            original = runner.generate_once
            runner.generate_once = once
            try:
                self.assertEqual(runner.generate(job_spec(), IMAGE, artifact_dir, evidence_dir), 3)
                self.assertEqual(len(calls), 3)
                self.assertIn("attempt 3 exit=0", (evidence_dir / "generation.log").read_text())
                calls.clear()
                (artifact_dir / "environment.json").unlink()
                outcomes[:] = [SimpleNamespace(returncode=1, stdout="ENVIRONMENT_SPEC_MISMATCH", stderr="")] * 3
                with self.assertRaises(runner.JobError) as failure:
                    runner.generate(job_spec(), IMAGE, artifact_dir, evidence_dir)
                self.assertEqual((failure.exception.code, len(calls)), ("ENVIRONMENT_SPEC_MISMATCH", 3))
                calls.clear()
                outcomes[:] = [SimpleNamespace(returncode=1, stdout="", stderr="ENVIRONMENT_VERSION_MISMATCH")]
                with self.assertRaises(runner.JobError) as failure:
                    runner.generate(job_spec(), IMAGE, artifact_dir, evidence_dir)
                self.assertEqual((failure.exception.code, len(calls)), ("ENVIRONMENT_GENERATION_FAILED", 1))
            finally:
                runner.generate_once = original

    def test_failed_acceptance_keeps_evidence_and_never_publishes(self):
        self.enqueue(request())
        failing = lambda *args, **kwargs: self.fake_accept(*args, status="failed", **kwargs)
        self.assertEqual(runner.run_next(self.spool, self.args, self.prepare, **self.hooks(accept=failing)), "failed")
        status = self.spool.status(JOB)
        self.assertEqual((status["status"], status["code"]), ("failed", "ENVIRONMENT_ACCEPTANCE_FAILED"))
        self.assertEqual(len(status["artifact_sha256"]), 64)
        artifact_dir = self.spool.root / "artifacts" / "env-custom-0123456789abcdef"
        self.assertTrue((artifact_dir / "environment.json").exists() and (artifact_dir / "acceptance.json").exists())
        self.assertTrue((self.spool.root / "evidence" / JOB / "acceptance.log").exists())
        self.assertFalse(self.catalog.exists())
        self.assertEqual(FakeFixture.exited, ["fake-internal-" + JOB])
        # A fixture that cannot be created fails the job the same way and leaves no catalog entry.
        self.enqueue(request(job_id="job-0000000000000009", spec=job_spec(id="env-custom-0000000000000009")), "job-0000000000000009")

        class Broken(FakeFixture):
            def __enter__(self):
                raise runner.JobError("QA_FIXTURE_UNAVAILABLE")

        self.assertEqual(runner.run_next(self.spool, self.args, self.prepare, **self.hooks(fixture=Broken)), "failed")
        self.assertEqual(self.spool.status("job-0000000000000009")["code"], "QA_FIXTURE_UNAVAILABLE")

    def test_catalog_ids_are_never_replaced(self):
        self.catalog.parent.mkdir(mode=0o700)
        runner.write_private(self.catalog, encode({"version": 1, "artifacts": [{"id": "env-custom-0123456789abcdef", "sha256": "x"}]}))
        original = self.catalog.read_bytes()
        self.enqueue(request())
        self.assertEqual(runner.run_next(self.spool, self.args, self.prepare, **self.hooks()), "failed")
        self.assertEqual(self.spool.status(JOB)["code"], "CATALOG_ID_EXISTS")
        self.assertEqual(self.catalog.read_bytes(), original)
        with self.assertRaises(runner.JobError):
            runner.append_catalog(self.catalog, {"id": "env-custom-0123456789abcdef"})
        runner.write_private(self.catalog, b'{"version": 2, "artifacts": []}')
        with self.assertRaises(runner.JobError) as failure:
            runner.append_catalog(self.catalog, {"id": "other"})
        self.assertEqual(failure.exception.code, "CATALOG_INVALID")

    def test_one_runner_at_a_time_and_oldest_first(self):
        self.enqueue(request(job_id="job-000000000000000a", spec=job_spec(id="env-custom-000000000000000a")), "job-000000000000000a")
        time.sleep(0.02)
        self.enqueue(request(job_id="job-000000000000000b", spec=job_spec(id="env-custom-000000000000000b")), "job-000000000000000b")
        self.assertEqual([path.stem for path in self.spool.queued()], ["job-000000000000000a", "job-000000000000000b"])
        with open(self.spool.root / ".lock", "a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertEqual(runner.run_next(self.spool, self.args, self.prepare, **self.hooks()), "locked")
        self.assertEqual(runner.run_next(self.spool, self.args, self.prepare, **self.hooks()), "accepted")
        self.assertEqual(self.spool.status("job-000000000000000a")["status"], "accepted")
        self.assertIsNone(self.spool.status("job-000000000000000b"))
        self.assertEqual([path.stem for path in self.spool.queued()], ["job-000000000000000b"])

    def test_spool_rejects_group_readable_files(self):
        path = self.enqueue(request())
        path.chmod(0o640)
        self.assertEqual(runner.run_next(self.spool, self.args, self.prepare, **self.hooks()), "failed")
        self.assertEqual(self.spool.status(JOB)["code"], "SPOOL_UNSAFE")


if __name__ == "__main__":
    unittest.main()
