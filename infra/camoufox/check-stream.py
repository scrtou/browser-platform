#!/usr/bin/env python3
"""Run the Selkies test client separately from the proxy-restricted Worker."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import uuid

from acceptance import docker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--session-file", type=Path, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--client-browsers", type=Path,
                        default=Path(__file__).resolve().parent / ".build/playwright-client-browsers")
    args = parser.parse_args()
    session = args.session_file.resolve(strict=True)
    info = session.stat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise SystemExit("Session file must be a private regular file")
    artifact = json.loads(args.artifact.read_bytes())
    browsers = args.client_browsers.resolve(strict=True)
    output = args.output_dir.resolve()
    if (output / "stream.json").exists():
        raise SystemExit("stream evidence already exists; choose a new output directory")
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    name = "bp-camoufox-stream-client-" + uuid.uuid4().hex[:12]
    command = ["run", "--rm", "--name", name, "--network", "host", "--user", f"{os.getuid()}:{os.getgid()}",
               "--memory", "1536m", "--cpus", "1.5", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges:true", "--read-only",
               "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m", "--shm-size", "256m",
               "-e", "PLAYWRIGHT_BROWSERS_PATH=/client-browsers",
               "--entrypoint", "/opt/camoufox-python/bin/python"]
    for source, destination, readonly in (
        (Path(__file__).resolve().with_name("stream-client.py"), "/checks/stream-client.py", True),
        (session, "/run/session.json", True), (output, "/evidence", False),
        (browsers, "/client-browsers", True),
    ):
        command += ["--mount", f"type=bind,src={source},dst={destination}" + (",readonly" if readonly else "")]
    command += [artifact["runtimeImageDigest"], "/checks/stream-client.py", "--session-file", "/run/session.json",
                "--origin", args.origin, "--output-dir", "/evidence"]
    try:
        result = docker(command, timeout=150)
        print(result.stdout, end="")
        path = output / "stream.json"
        if path.exists():
            report = json.loads(path.read_bytes())
            report.update(artifactSHA256=hashlib.sha256(args.artifact.read_bytes()).hexdigest(),
                          runtimeImageDigest=artifact["runtimeImageDigest"])
            path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
        return result.returncode
    except subprocess.TimeoutExpired:
        print("stream_client_timeout=true")
        return 1
    finally:
        docker(["rm", "--force", name], timeout=20)


if __name__ == "__main__":
    raise SystemExit(main())
