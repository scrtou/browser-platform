#!/usr/bin/env python3
"""Scan R5B QA artifacts and candidate images without printing credential values."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile


def scan(paths, needles, excludes=()):
    count = size = 0
    matches, unavailable = [], []
    overlap = max(map(len, needles)) - 1
    for base in paths:
        base = Path(base)
        candidates = [base] if base.is_file() else None
        if candidates is None:
            candidates = []
            for directory, directories, files in os.walk(base, followlinks=False):
                directories[:] = [name for name in directories if not (Path(directory) / name).is_symlink()
                                  and not any((Path(directory) / name).is_relative_to(excluded) for excluded in excludes)]
                candidates.extend(Path(directory) / name for name in files)
        for path in candidates:
            if any(path.is_relative_to(excluded) for excluded in excludes):
                continue
            try:
                if not stat.S_ISREG(path.lstat().st_mode):
                    continue
                count += 1
                found = False
                previous = b""
                with path.open("rb") as handle:
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk: break
                        size += len(chunk)
                        window = previous + chunk
                        found = found or any(needle in window for needle in needles)
                        previous = window[-overlap:]
                if found: matches.append(str(path))
            except (OSError, ValueError):
                unavailable.append(str(path))
    return {"files": count, "bytes": size, "matchingFiles": matches, "unavailableFiles": unavailable}


def docker(*args):
    return subprocess.run(["sg", "docker", "-c", shlex.join(["docker", *args])], capture_output=True, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inside = sub.add_parser("scan")
    inside.add_argument("--patterns", type=Path, required=True)
    inside.add_argument("--base", type=Path, nargs="+", required=True)
    inside.add_argument("--exclude", type=Path, nargs="*", default=[])
    audit = sub.add_parser("audit")
    audit.add_argument("--root", type=Path, required=True)
    audit.add_argument("--restored-root", type=Path)
    audit.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "scan":
        values = [base64.b64decode(v) for v in json.loads(args.patterns.read_text())]
        print(json.dumps(scan(args.base, values, args.exclude)))
        return 0
    qa, output = args.root.resolve(), args.output.resolve()
    assert qa.name == "qa"
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    fixture = json.loads((qa.parent / "secret-fixture.json").read_text())
    values = [value.encode() for pair in fixture.values() for value in pair.values()]
    values += [base64.b64encode((pair["username"] + ":" + pair["password"]).encode()) for pair in fixture.values()]
    master = (qa.parent / "master-key/master.key").read_bytes()
    values += [master, base64.b64encode(master), master.hex().encode()]
    roots = [qa] + ([args.restored_root.resolve()] if args.restored_root else [])
    paths = []
    for root in roots:
        assert root.name == "qa"
        paths += [root / "config", root / "storage", root / "adapter-config.json", root / "adapter-state.json"]
        paths += [p for p in root.glob("*.log")]
    paths = [p for p in paths if p.exists()]
    build = qa.parent / json.loads((qa / "images.json").read_text())["build"]
    paths += [build / "payload", Path("infra/camoufox/artifacts").resolve(), Path("infra/camoufox/evidence").resolve()]
    for directory in qa.parent.glob("live-v*"):
        if directory.is_dir(): paths.append(directory)
    # Only the exact QA containers are queried; raw logs are retained privately.
    logs = output / "container-logs"
    logs.mkdir(mode=0o700)
    for name in ("sealskin-network-qa", "network-qa-observer", "network-qa-upstream"):
        details = json.loads(docker("inspect", name).stdout)[0]
        assert details["Config"]["Labels"].get("io.browser-platform.qa") == "network-20260913"
        content = docker("logs", name)
        path = logs / (name + ".log")
        path.write_bytes(content.stdout + content.stderr)
        path.chmod(0o600)
        paths.append(path)
    results = {"host": scan(paths, values)}
    with tempfile.TemporaryDirectory(prefix="browser-platform-r5b-audit-", dir="/dev/shm") as directory:
        private = Path(directory)
        patterns = private / "patterns.json"
        patterns.write_text(json.dumps([base64.b64encode(v).decode() for v in values])); patterns.chmod(0o600)
        positive = private / "positive.txt"
        positive.write_bytes(values[0]); positive.chmod(0o600)
        control = scan([positive], values)
        assert control["matchingFiles"] == [str(positive)]
        candidates = json.loads((qa.parent / "candidate-images.json").read_text())
        guard = json.loads((qa.parent / "guard-image.json").read_text())
        images = {"controller": candidates["controller"]["id"], "relay": guard["image_id"]}
        for role, image in images.items():
            result = docker("run", "--rm", "--name", "r5b-audit-" + role, "--label", "io.browser-platform.qa=secret-artifact-audit",
                "--network", "none", "--read-only", "--cap-drop", "ALL", "--cap-add", "DAC_READ_SEARCH",
                "--security-opt", "no-new-privileges:true",
                "--cpus", ".5", "--memory", "128m", "--pids-limit", "32", "--user", "0:0", "--entrypoint", "python3",
                "-v", str(Path(__file__).resolve()) + ":/run/check-secret-artifacts.py:ro", "-v", str(private) + ":/run/qa:ro",
                image, "-B", "/run/check-secret-artifacts.py", "scan", "--patterns", "/run/qa/patterns.json", "--base", "/",
                "--exclude", "/proc", "/sys", "/dev", "/run/qa")
            results[role + "Image"] = {"image": image, **json.loads(result.stdout)}
    results["positiveControl"] = True
    results["result"] = "PASS" if all(not v["matchingFiles"] and not v["unavailableFiles"] for v in results.values() if isinstance(v, dict)) else "FAIL"
    (output / "artifact-scan.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({"result": results["result"], "scopes": {k:{"files":v["files"], "matches":len(v["matchingFiles"]),
        "unavailable":len(v["unavailableFiles"])} for k,v in results.items() if isinstance(v,dict)}}))
    return 0 if results["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
