#!/usr/bin/env python3
"""Verify actual incorrect credential revisions fail before a QA Worker starts.

Uses the existing private protocol matrix fixtures. Each wrong password is a
new file/reference; the previous immutable credential files remain untouched.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import uuid

spec = importlib.util.spec_from_file_location("matrix", Path(__file__).with_name("check-proxy-protocols.py"))
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)
network = matrix.network


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runner = matrix.Matrix(args.root, args.output)
    results = []
    for protocol, auth in (("socks5", "username_password"), ("http", "basic"), ("https", "basic")):
        case = runner.output / protocol
        case.mkdir(mode=0o700)
        path = runner.qa / "config/.config/sealskin/network-secrets" / ("r5a-wrong-password-" + uuid.uuid4().hex)
        path.write_text("incorrect-qa-" + uuid.uuid4().hex)
        path.chmod(0o600)
        runner.template["password_file"] = "/config/.config/sealskin/network-secrets/" + path.name
        runner.template["password_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        start = len(runner.events())
        try:
            runner.configure(protocol, auth, case)
        except AssertionError as exc:
            assert str(exc) == "QA protocol preflight/launch failed", "failure occurred outside the intended preflight"
        else:
            raise AssertionError("incorrect credentials started a browser")
        launch = json.loads((case / "launch-result.json").read_text())
        assert launch["status"] == 503
        snapshot = runner.snapshot()
        assert snapshot["workers"] == [], "browser created before valid proxy credentials"
        relay = next(v["id"] for v in snapshot["resources"] if v["kind"] == "relay")
        logs = network.docker("logs", relay).stdout
        assert '"error_code":"UPSTREAM_AUTH_FAILED"' in logs
        assert path.read_text() not in logs and "network-observer-user" not in logs
        events = runner.events()[start:]
        assert any(e["event"] == "auth_rejected" and e["protocol"] == protocol and e["auth"] == auth for e in events)
        assert not any(e["event"] in {"http", "https"} and e.get("host") == "preflight.leak.qa.test" for e in events)
        network.write_json(case / "failed-inventory.json", snapshot)
        (case / "relay.log").write_text(logs)
        (case / "observer-events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        runner.stop()
        result = {"protocol": protocol, "auth": auth, "result": "PASS", "actualWrongCredentialRevision": True,
                  "preflightStatus": launch["status"], "workersCreated": 0, "targetRequests": 0,
                  "safeAuthenticationError": True, "verifiedStopReleasedReservation": True}
        results.append(result)
        network.write_json(runner.output / "credential-failures.json", results)
        print(json.dumps(result), flush=True)
    network.write_json(runner.output / "stopped.json", {"result": "PASS", "generationResources": 0})


if __name__ == "__main__":
    main()
