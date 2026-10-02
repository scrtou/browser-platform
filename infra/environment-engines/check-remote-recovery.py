#!/usr/bin/env python3
"""Replay encrypted, transferred synthetic native-browser checkpoints.

Inputs must include the exact accepted artifact/report and a native-home-A QA
Home. This does not activate real production identities or proxy credentials.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(HERE))
native_spec = importlib.util.spec_from_file_location("remote_native_acceptance", HERE / "acceptance.py")
native = importlib.util.module_from_spec(native_spec)
native_spec.loader.exec_module(native)


def extract(archive, root):
    with tarfile.open(archive) as source:
        members = source.getmembers()
        for member in members:
            path = Path(member.name)
            assert not path.is_absolute() and ".." not in path.parts
            assert member.isfile() or member.isdir() or member.issym() or member.islnk()
        for member in members:
            target = root / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with source.extractfile(member) as stream, target.open("xb") as output:
                    shutil.copyfileobj(stream, output)
                target.chmod(member.mode & 0o777)
        # Install links only after every regular file; never write through one.
        for member in members:
            target = root / member.name
            if member.issym():
                target.symlink_to(member.linkname)
            elif member.islnk():
                link = root / member.linkname
                assert link.resolve().is_relative_to(root) and link.is_file() and not link.is_symlink()
                os.link(link, target)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--age", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    assert "runtime" in root.parts and not root.exists()
    root.mkdir(mode=0o700)
    sys.path.insert(0, str(PROJECT / "infra/camoufox"))
    spec = importlib.util.spec_from_file_location("remote_native_runner", PROJECT / "infra/camoufox/environment-job.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    results = []
    for engine, row in json.loads((args.inputs / "manifest.json").read_text()).items():
        assert engine in ("camoufox", "chromix", "firefox") and row["source_storage_marker"] == "native-home-A"
        archive = args.inputs / row["archive"]
        assert archive.parent.resolve() == args.inputs.resolve()
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == row["sha256"]
        work = root / engine
        work.mkdir(mode=0o700)
        # age must authenticate the whole stream before any Home is created.
        raw = work / "authenticated.tar.gz"
        subprocess.run([str(args.age), "-d", "-i", str(args.identity), "-o", str(raw), str(archive)], check=True, capture_output=True)
        original = work / "checkpoint"
        original.mkdir(mode=0o700)
        extract(raw, original)
        assert hashlib.sha256((original / "environment.json").read_bytes()).hexdigest() == row["source_artifact_sha256"]
        assert hashlib.sha256((original / "acceptance.json").read_bytes()).hexdigest() == row["source_report_sha256"]
        artifact = original / "environment.json"
        value = native.normalize(json.loads(artifact.read_bytes()))
        assert value["runtimeImageDigest"] == row["image"]
        prior = json.loads((original / "acceptance.json").read_bytes())
        assert prior["status"] == "pass"
        baseline = native.invariant(prior["observations"][0]["observed"], value["screen"].get("mode") == "auto")
        source = work / "qa-source"
        source.mkdir()
        for leaf in ("probe.py", "qa-browser.py", "qa-entrypoint.py", "browser_client.py", "check-dynamic-client.py"):
            shutil.copy2(HERE / leaf, source / leaf)
        shutil.copy2(PROJECT / "infra/firefox-proxy/check-bidi.py", source / "check_bidi.py")
        for leaf in ("storage.js", "observe.js"):
            shutil.copy2(PROJECT / "infra/camoufox/tests" / leaf, source / leaf)
        (work / "autostart").write_text("#!/bin/sh\nexec /opt/camoufox-python/bin/python /qa/qa-browser.py\n")
        (work / "autostart").chmod(0o755)
        sid, user, password = [str(uuid.uuid4()) for _ in range(3)]
        material = Path(tempfile.mkdtemp(prefix="r6ap-native-display-", dir="/dev/shm"))
        native.write(material / "binding.json", {"version": 1, "session_id": sid, "uid": os.getuid()})
        salt = os.urandom(16)
        (material / "basic.htpasswd").write_text(user + ":{SSHA}" + base64.b64encode(hashlib.sha1(password.encode() + salt).digest() + salt).decode() + "\n")
        (material / "master-token").write_text("")
        home = work / "restored-home"
        shutil.copytree(original / "home", home, symlinks=True)
        with runner.Fixture("job-" + uuid.uuid4().hex[:16], row["image"]) as fixture:
            for iteration in (11, 12):
                observed = native.run_one(value, artifact, home, work, fixture.networks["internal"], "A", iteration,
                                          (sid, user, password), material, verify_input=True, accepted_entrypoint=True)
                assert native.invariant(observed["observed"], value["screen"].get("mode") == "auto") == baseline
                native.write(work / ("readback-" + str(iteration) + ".json"), observed)
            rollback = work / "rollback-checkpoint"
            shutil.copytree(original / "home", rollback, symlinks=True)
            observed = native.run_one(value, artifact, rollback, work, fixture.networks["internal"], "A", 13,
                                      (sid, user, password), material, verify_input=True, accepted_entrypoint=True)
            assert native.invariant(observed["observed"], value["screen"].get("mode") == "auto") == baseline
        shutil.rmtree(material)
        raw.unlink()
        results.append({"engine": engine, "result": "PASS", "image": row["image"], "three_store_readback": True,
                        "reopen": True, "checkpoint_rollback": True, "fingerprint_matches_source": True,
                        "authenticated_display_and_input": True, "https_and_raw_bypass_denial": True})
        native.write(root / "result.json", {"result": "RUNNING", "cases": results})
        print("PASS remote", engine, "checkpoint, reopen, rollback and source fingerprint", flush=True)
    native.write(root / "result.json", {"result": "PASS", "cases": results})


if __name__ == "__main__":
    main()
