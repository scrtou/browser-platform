#!/usr/bin/env python3
"""Exercise disposable QA Homes; never mount a Personal or Work Home."""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import uuid

from environment import encode, expected_environment

ROOT = Path(__file__).resolve().parent


def docker(arguments, **kwargs):
    command = ["docker", *arguments]
    if not os.access("/var/run/docker.sock", os.W_OK):
        command = ["sg", "docker", "-c", shlex.join(command)]
    return subprocess.run(command, text=True, capture_output=True, **kwargs)


class Acceptance:
    def __init__(self, args):
        self.args = args
        self.artifact_path = args.artifact.resolve()
        self.artifact = json.loads(self.artifact_path.read_bytes())
        self.sha256 = hashlib.sha256(self.artifact_path.read_bytes()).hexdigest()
        self.image = self.artifact["runtimeImageDigest"]
        inspected = docker(["image", "inspect", self.image, "--format", "{{.Id}}"], timeout=15)
        if inspected.returncode or inspected.stdout.strip() != self.image:
            raise RuntimeError("the exact artifact-bound image must already exist locally")
        (ROOT / ".build").mkdir(exist_ok=True)
        self.workspace = Path(tempfile.mkdtemp(prefix="acceptance-", dir=ROOT / ".build"))
        self.report = {
            "schemaVersion": "browser-platform/camoufox-acceptance/v1",
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "phase": args.phase, "artifactId": self.artifact["id"],
            "artifactSHA256": self.sha256, "runtimeImageDigest": self.image,
            "resources": {"memoryMiB": 1536, "cpuQuota": 1.5},
            "network": args.network, "results": {}, "status": "running",
        }
        source_hash = hashlib.sha256()
        for path in [Path(__file__), *sorted((ROOT / "tests").glob("*"))]:
            if path.is_file() and path.suffix in (".py", ".js", ".html"):
                source_hash.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes())
        self.report["testSuiteSHA256"] = source_hash.hexdigest()

    def checkpoint(self):
        self.report["evidenceDirectory"] = str(self.workspace)
        self.args.output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".acceptance-", dir=self.args.output.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encode(self.report))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.args.output)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def container(self, label, command, *, home=None, artifact_path=None, artifact_data=None,
                  sha256=None, override_env=None, entrypoint="/opt/camoufox-python/bin/python", network=None):
        name = "bp-camoufox-qa-" + uuid.uuid4().hex[:12]
        data = artifact_data if artifact_data is not None else self.artifact
        args = ["run", "--rm", "--name", name, "--network", network or self.args.network,
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "--memory", "1536m", "--cpus", "1.5", "--shm-size", "256m",
                "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
                "--user", f"{os.getuid()}:{os.getgid()}",
                "--mount", f"type=bind,src={ROOT}/tests,dst=/tests,readonly"]
        if entrypoint is not None:
            args.extend(["--entrypoint", entrypoint])
        if artifact_path is not False:
            path = artifact_path or self.artifact_path
            args.extend(["--mount", f"type=bind,src={path},dst=/run/browser-platform/environment.json,readonly"])
        if home:
            args.extend(["--mount", f"type=bind,src={home},dst=/config"])
        env = expected_environment(data, sha256 or self.sha256)
        env.update(override_env or {})
        for key, value in env.items():
            args.extend(["-e", f"{key}={value}"])
        args.extend([self.image, *command])
        try:
            result = docker(args, timeout=150)
        except BaseException:
            docker(["rm", "--force", name], timeout=20)
            raise
        (self.workspace / (label + ".log")).write_text(result.stdout + result.stderr)
        return result

    def unit(self):
        # Artifact validation runs in the pinned image. Deployment preparation
        # tests need repository tools and are run separately on the host.
        result = self.container("unit", ["-m", "unittest", "discover", "-s", "/tests", "-p", "test_environment.py", "-v"], network="none")
        if result.returncode:
            raise RuntimeError("artifact tests failed: " + (result.stdout + result.stderr)[-6000:])
        self.report["results"]["artifactTests"] = "pass"
        self.checkpoint()
        print("artifact_tests=pass", flush=True)

    def negative(self):
        results = {}
        cases = [
            ("missing-artifact", "ENVIRONMENT_UNAVAILABLE FileNotFoundError", None, {}, False),
            ("wrong-sha256", "ENVIRONMENT_ARTIFACT_MISMATCH", None, {"BROWSER_PLATFORM_ARTIFACT_SHA256": "0" * 64}, None),
            ("timezone-drift", "ENVIRONMENT_CONFIG_DRIFT", None, {"TZ": "Etc/UTC"}, None),
            ("wayland-drift", "ENVIRONMENT_CONFIG_DRIFT", None, {"PIXELFLUX_WAYLAND": "true"}, None),
            ("version-mismatch", "ENVIRONMENT_VERSION_MISMATCH", lambda a: a["runtime"].update(browserRelease="unapproved"), {}, None),
            ("missing-audio-seed", "ENVIRONMENT_SEED_MISSING", lambda a: a["resolvedConfig"].pop("audio:seed"), {}, None),
            ("direct-proxy", "ENVIRONMENT_PROXY_POLICY_MISMATCH", lambda a: a["firefoxUserPrefs"].update({"network.proxy.type": 0}), {}, None),
            ("unsupported-capability", "UNSUPPORTED_CAPABILITY", lambda a: a["spec"]["requiredCapabilities"].append("unverified"), {}, None),
            ("unvalidated-candidate", "ENVIRONMENT_ACCEPTANCE_REQUIRED", None, {}, None),
            ("baseline-randomization", "ENVIRONMENT_PREFERENCE_MISMATCH", lambda a: a["firefoxUserPrefs"].update({"privacy.baselineFingerprintingProtection": True}), {}, None),
            ("asynchronous-font-fallback", "ENVIRONMENT_PREFERENCE_MISMATCH", lambda a: a["firefoxUserPrefs"].update({"gfx.font_rendering.fallback.async": True}), {}, None),
        ]
        for name, expected, mutate, env, path in cases:
            data = copy.deepcopy(self.artifact)
            sha256 = self.sha256
            if mutate:
                mutate(data)
                raw = encode(data)
                path = self.workspace / (name + ".json")
                path.write_bytes(raw)
                sha256 = hashlib.sha256(raw).hexdigest()
            result = self.container(name, [], artifact_path=path, artifact_data=data, sha256=sha256,
                                    override_env=env, entrypoint=None, network="none")
            output = result.stdout + result.stderr
            if result.returncode != 1 or expected not in output or "ENVIRONMENT_ARTIFACT_OK" in output:
                raise RuntimeError(name + " did not fail before /init: " + output[-2000:])
            results[name] = expected
            print(name + "=rejected_before_init", flush=True)
        self.report["results"]["entrypointRejections"] = results
        self.checkpoint()

    def probe(self, home, role, iteration, *, network=False, label=None):
        command = ["/tests/probe.py", "--role", role, "--iteration", str(iteration)]
        if network:
            command.append("--network")
        result = self.container(label or f"home-{role}-{iteration}", command, home=home)
        if result.returncode:
            raise RuntimeError(f"Home {role} iteration {iteration} failed: " + (result.stdout + result.stderr)[-6500:])
        observed = json.loads(result.stdout.strip().splitlines()[-1])
        print(f"home={role} iteration={iteration} storage=pass config=verified", flush=True)
        return observed

    def replay(self):
        homes = {role: self.workspace / ("home-" + role) for role in ("A", "B")}
        for path in homes.values():
            path.mkdir(mode=0o700)
        observations = []
        differences = []
        self.report["results"]["homeReplay"] = {
            "homes": 2, "recreationsPerHome": self.args.recreations,
            "observations": observations, "differences": differences,
            "storageRestored": False, "observationsStable": False,
            "offlineBackupRestore": "pending",
        }
        baseline = None
        for iteration in range(self.args.recreations + 1):
            for role, home in homes.items():
                result = self.probe(home, role, iteration, network=role == "A" and iteration == 0)
                if baseline is None:
                    baseline = result["observed"]
                elif result["observed"] != baseline:
                    changed = [key for key in baseline if result["observed"].get(key) != baseline[key]]
                    differences.append({"role": role, "iteration": iteration, "fields": changed})
                    print("stability_mismatch=" + ",".join(changed), flush=True)
                observations.append(result)
                self.checkpoint()
        # Every browser and container has exited before the offline snapshot.
        restored = self.workspace / "restored-A"
        shutil.copytree(homes["A"], restored, symlinks=True)
        result = self.probe(restored, "A", self.args.recreations + 1, label="restored-A")
        if result["observed"] != baseline:
            changed = [key for key in baseline if result["observed"].get(key) != baseline[key]]
            differences.append({"role": "restored-A", "fields": changed})
        self.report["results"]["homeReplay"] = {
            "homes": 2, "recreationsPerHome": self.args.recreations,
            "offlineBackupRestore": "pass", "observations": observations,
            "restoredObservation": result, "storageRestored": True,
            "observationsStable": not differences, "differences": differences,
        }
        if differences:
            changed = sorted({field for difference in differences for field in difference["fields"]})
            raise RuntimeError("frozen observations changed: " + ", ".join(changed))

    def run(self):
        try:
            if self.args.phase in ("unit", "all"):
                self.unit()
            if self.args.phase in ("negative", "all"):
                self.negative()
            if self.args.phase in ("replay", "all"):
                self.replay()
            self.report["status"] = "pass"
        except BaseException as error:
            self.report["status"] = "failed"
            self.report["error"] = str(error)
            raise
        finally:
            self.report["completedAt"] = datetime.now(timezone.utc).isoformat()
            self.checkpoint()
            print("evidence=" + str(self.args.output), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=ROOT / "artifacts/env-tw-camoufox-r4.json")
    parser.add_argument("--network", default="browser-platform-personal")
    parser.add_argument("--recreations", type=int, default=10)
    parser.add_argument("--phase", choices=("all", "unit", "negative", "replay"), default="all")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "evidence" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"))
    args = parser.parse_args()
    if not 0 <= args.recreations <= 50:
        parser.error("recreations must be between 0 and 50")
    Acceptance(args).run()


if __name__ == "__main__":
    main()
