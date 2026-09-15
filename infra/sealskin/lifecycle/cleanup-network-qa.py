#!/usr/bin/env python3
"""Remove an empty, explicitly owned QA deployment and its temporary secrets.

Generation resources must first be stopped through SealSkin/Adapter. This
script refuses to force-remove any remaining Worker, Relay or network lease.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import stat
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "qa_checks", Path(__file__).with_name("check-network-live.py")
)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    assert root.name == "qa" and (root / "live-results.json").is_file(), (
        "Explicit completed QA evidence is required"
    )
    config = json.loads((root / "adapter-config.json").read_text())
    assert (
        config["sealskin"]["username"] == "network-qa"
        and config["sealskin"]["api_base_url"] == "http://127.0.0.1:28110"
    )
    client = checks.SecureClient(root)
    status, sessions = client.call("GET", "/api/sessions")
    assert status == 200 and not sessions, (
        "QA sessions still exist; stop them through the lifecycle API first"
    )
    scope = hashlib.sha256(
        str(root / "config/.config/sealskin/sessions.yml").encode()
    ).hexdigest()
    selector = "label=io.browser-platform.scope=" + scope
    assert not checks.docker("ps", "-aq", "--filter", selector).stdout.strip(), (
        "QA generation containers remain"
    )
    assert not checks.docker(
        "network", "ls", "-q", "--filter", selector
    ).stdout.strip(), "QA generation networks remain"
    reservations = root / "config/.config/sealskin/profile-network-runtime"
    assert not reservations.exists() or not list(reservations.glob("*.json")), (
        "QA reservations remain"
    )
    expected = {
        "sealskin-network-qa": root / "config",
        "network-qa-upstream": root / "upstream",
    }
    known = checks.docker(
        "ps",
        "-a",
        "--filter",
        "label=io.browser-platform.qa=network-20260913",
        "--format",
        "{{.Names}}",
    ).stdout.splitlines()
    assert set(known) == set(expected), "Unrecognized QA containers require inspection"
    container_evidence = {}
    for name, source in expected.items():
        value = json.loads(checks.docker("inspect", name).stdout)[0]
        assert (
            value["Config"]["Labels"].get("io.browser-platform.qa")
            == "network-20260913"
        )
        assert any(m.get("Source") == str(source) for m in value.get("Mounts", [])), (
            "QA mount ownership mismatch"
        )
        container_evidence[name] = value
    checks.write_json(root.parent / "qa-cleanup-container-inspects.json", container_evidence)
    adapter_pid = root / "adapter-pid.json"
    if adapter_pid.exists():
        pid = json.loads(adapter_pid.read_text())["pid"]
        assert (
            Path(os.readlink(f"/proc/{pid}/exe")).resolve()
            == (root / "bin/profile-adapter").resolve()
        )
        os.kill(pid, signal.SIGTERM)
    else:
        # Browser-only QA uses SealSkin directly and may never start Adapter.
        # A missing PID record is safe only if its exact executable is absent.
        expected_adapter = (root / "bin/profile-adapter").resolve()
        for process in Path("/proc").glob("[0-9]*"):
            try:
                executable = Path(os.readlink(process / "exe")).resolve()
            except (FileNotFoundError, ProcessLookupError):
                continue
            except PermissionError:
                # setgid helpers and container processes can share the UID but
                # hide /exe. QA starts with absolute binary/config arguments.
                try:
                    command = process.joinpath("cmdline").read_bytes().split(b"\0")
                except (FileNotFoundError, ProcessLookupError):
                    continue
                assert str(expected_adapter).encode() not in command
                assert str(root / "adapter-config.json").encode() not in command
                continue
            assert executable != expected_adapter, "QA Adapter exists without an owned PID record"
    for name in expected:
        checks.docker("rm", "-f", "-v", container_evidence[name]["Id"])
    network = json.loads(
        checks.docker("network", "inspect", "browser-platform-network-qa").stdout
    )[0]
    assert network.get("Labels", {}).get(
        "io.browser-platform.qa"
    ) == "network-20260913" and not network.get("Containers")
    checks.docker("network", "rm", network["Id"])
    pid = json.loads((root / "proxy-pid.json").read_text())["pid"]
    command = Path(f"/proc/{pid}/cmdline").read_bytes()
    assert (
        b"qa-network-docker-proxy.py" in command
        and str(root).encode() in command
        and os.getpgid(pid) == pid
    )
    os.killpg(pid, signal.SIGTERM)
    time.sleep(0.3)
    for path in (
        Path("/tmp/browser-platform-network-qa-docker.sock"),
        Path("/tmp/browser-platform-network-qa.sock"),
    ):
        if path.exists():
            info = path.lstat()
            assert stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid()
            path.unlink()
    for name in ("config", "storage", "upstream"):
        path = root / name
        assert not path.is_symlink() and path.resolve().is_relative_to(root)
        shutil.rmtree(path)
    for pattern in ("*.pem", "*-pid.json"):
        for path in root.glob(pattern):
            path.unlink()
    for name in (
        "admin.json",
        "adapter-config.json",
        "adapter-state.json",
        "adapter-state.json.lock",
    ):
        path = root / name
        if path.exists():
            path.unlink()
    result = {
        "result": "PASS",
        "generation_resources": 0,
        "qa_containers": 0,
        "qa_networks": 0,
        "qa_controller_and_proxy_stopped": True,
        "temporary_credentials_and_keys_removed": True,
    }
    checks.write_json(root.parent / "qa-cleanup.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
