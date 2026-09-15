#!/usr/bin/env python3
"""Verify the real QA Adapter's fixed entry and private coherence command.

The case must be prepared by check-runtime-coherence.py and configured in the
QA Adapter. Start owns the operation ID: the QA recorder follows the resulting
journal rather than injecting a synthetic Adapter binding. Private responses,
redirects and Session capabilities are written only below the new output root.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import traceback
import http.client


spec = importlib.util.spec_from_file_location("entry_coherence", Path(__file__).with_name("check-runtime-coherence.py"))
coherence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coherence)
network = coherence.network


class Checks:
    def __init__(self, root, case, output):
        self.qa = coherence.Checks(root)
        self.case, self.output = case, output.resolve()
        self.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.entry = self.qa.state["cases"][case]
        self.profile = self.entry["request"]["profile_id"]
        self.config = self.qa.qa / "adapter-config.json"
        config = json.loads(self.config.read_text())
        coherence.require(config["listen_address"] == "127.0.0.1:29110" and config["sealskin"]["username"] == "network-qa" and
                          config["public_base_url"] == "https://network.invalid" and
                          any(p["id"] == self.profile and p["home_name"] == self.entry["request"]["home_name"] for p in config["profiles"]),
                          "This case is not configured in the QA Adapter")
        pid = json.loads((self.qa.qa / "adapter-pid.json").read_text())["pid"]
        coherence.require(Path(os.readlink(f"/proc/{pid}/exe")).resolve() == self.qa.qa / "bin/profile-adapter",
                          "Owned QA Adapter process required")

    def write(self, name, value):
        network.write_json(self.output / name, value)

    def http(self, method, suffix, label):
        status, headers, body = network.request(method, "/browser/" + self.profile + suffix,
                                                headers={"Origin": "https://network.invalid"} if method == "POST" else {}, port=29110)
        value = {"status": status, "headers": headers, "body": body.decode(errors="replace"), "at": time.time()}
        self.write(label + ".json", value)
        return value

    def command(self, action, label):
        result = subprocess.run([str(self.qa.qa / "bin/profile-adapter"), "-config", str(self.config),
                                 "-" + action + "-profile", self.profile], capture_output=True, text=True, timeout=110)
        value = {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "at": time.time()}
        self.write(label + ".json", value)
        return value

    def follow_binding(self):
        """Only the recorder changes. SealSkin and Adapter state remain owned."""
        bindings = json.loads((self.qa.qa / "adapter-state.json").read_text())["bindings"]
        binding = bindings[self.profile]
        request = self.entry["request"]
        for key in ("profile_id", "application_id", "home_name", "network_policy_id", "network_policy_sha256"):
            coherence.require(binding[key] == request[key], "Adapter adopted another case")
        request["operation_id"], request["url"] = binding["operation_id"], binding["bootstrap_url"]
        self.qa.save()
        snapshot = self.qa.snapshot(self.case)
        journal = self.qa.journal(self.case)
        coherence.require(len(snapshot["workers"]) == 1 and len(snapshot["records"]) == 1 and
                          snapshot["records"][0]["session_id"] == binding["session_id"] and
                          journal["identity"]["operation"] == binding["operation_id"], "Adapter and controller binding differ")
        self.write("binding.json", binding)
        return binding, snapshot, journal

    def current_health(self, binding):
        """Wait for an explicit, rate-limited observation of this generation.

        The ordinary private health command is a cache read. A sampler which
        ran during launch can legitimately leave BINDING_CHANGED in that cache;
        its absence of coherence evidence must not be treated as a product
        failure or worked around by changing the binding.
        """
        deadline = time.monotonic() + 120
        for attempt in range(8):
            if attempt:
                coherence.require(time.monotonic() < deadline, "Current health observation exceeded its bound")
                time.sleep(10.2)
            health = self.command("probe" if attempt else "health", "private-health-" + str(attempt + 1))
            if health["exit_code"] != 0:
                coherence.require("HTTP 429" in health["stderr"], "Private health observation failed")
                continue
            value = json.loads(health["stdout"])
            report = value.get("coherence") or {}
            if (report.get("binding", {}).get("session_id") == binding["session_id"] and
                    report.get("binding", {}).get("operation_id") == binding["operation_id"] and
                    not value.get("stale") and report.get("expires_at", 0) > time.time()):
                return value
        raise RuntimeError("Current generation health report unavailable")

    def start(self, expected, existing=False):
        before = self.qa.snapshot(self.case)
        if existing:
            self.follow_binding()
        else:
            coherence.require(not any(before[k] for k in ("records", "workers", "resources")), "A new empty case is required")
            # Even an explicitly requested private probe must not create a Worker.
            empty = self.command("coherence", "empty-private-probe")
            coherence.require(empty["exit_code"] != 0, "Empty Home probe was unexpectedly accepted")
            self.http("GET", "/", "empty-entry-get")
            self.http("GET", "/health", "empty-health-get")
            after_get = self.qa.snapshot(self.case)
            coherence.require(not any(after_get[k] for k in ("records", "workers", "resources")), "Read or probe created a generation")
        replies = []
        for attempt in range(6):
            if attempt:
                time.sleep(10.2)
            response = self.http("POST", "/start", "start-" + str(attempt + 1))
            replies.append(response)
            binding, snapshot, journal = self.follow_binding()
            report = journal.get("coherence_report") or {}
            if expected == "allowed" and response["status"] == 303 and report.get("allowed"):
                break
            # A frozen timezone outside the allowed list is already a known
            # failure before Marionette is ready. This matrix also requires
            # actual page values, so do not mistake missing values for drift.
            if (expected == "blocked" and report.get("overall") == "unhealthy" and
                    report.get("observed", {}).get("timezone") is not None and report.get("observed", {}).get("locale") is not None):
                break
        else:
            raise RuntimeError("Fixed entry did not reach the required state")
        expected_allowed = expected == "allowed"
        coherence.require(bool(report.get("allowed")) == expected_allowed, "Unexpected coherence decision")
        coherence.require(report.get("expected", {}).get("timezone") == "America/New_York" and
                          report.get("observed", {}).get("timezone") == "America/New_York" and
                          report.get("observed", {}).get("locale") == "en-US",
                          "Frozen environment changed to match a proxy region")
        if expected_allowed:
            with ThreadPoolExecutor(max_workers=4) as pool:
                reused = list(pool.map(lambda i: self.http("POST", "/start", "reuse-" + str(i)), range(8)))
            coherence.require(all(r["status"] == 303 and r["headers"].get("Location") == response["headers"].get("Location") for r in reused),
                              "Concurrent reuse changed the Session or failed its gate")
        else:
            response = self.http("POST", "/start", "blocked-repeat")
            coherence.require(response["status"] == 503 and not response["headers"].get("Location") and
                              not response["headers"].get("Set-Cookie") and response["headers"].get("Retry-After") == "10" and
                              "一致性检查" in response["body"], "Blocked fixed entry published a capability or wrong error")
            coherence.require(any(row["code"] == "COHERENCE_TIMEZONE_MISMATCH" and row["required"] and row["status"] == "fail"
                                  for row in report["checks"]), "Explicit timezone rejection missing")
        current_binding, current_snapshot, _ = self.follow_binding()
        coherence.require(current_binding["operation_id"] == binding["operation_id"] and
                          current_snapshot["workers"][0]["instance_id"] == snapshot["workers"][0]["instance_id"],
                          "Entry retries created another Worker")
        private = self.command("coherence", "private-coherence")
        coherence.require(private["exit_code"] == 0, "Private coherence command failed")
        access = json.loads(private["stdout"])
        coherence.require(access["allowed"] == expected_allowed and access["report"]["binding"]["session_id"] == binding["session_id"] and
                          access["report"].get("network_evidence") and access["report"].get("locale_evidence"),
                          "Private report omitted evidence or binding")
        self.current_health(binding)
        public = self.http("GET", "/health", "public-health")
        coherence.require(public["status"] == 200, "Public health cache unavailable")
        public_report = json.loads(public["body"])
        coherence.require(public_report["coherence"]["allowed"] == expected_allowed and
                          not public_report["coherence"]["binding"].get("operation_id") and
                          not public_report["coherence"]["binding"].get("session_id") and
                          binding["operation_id"] not in public["body"] and binding["session_id"] not in public["body"],
                          "Public health leaked operation or Session capability")
        # Freeze only the owned QA controller to remove background sampler races.
        # Cached public GET and unsupported private GET must still work without
        # initiating encrypted controller calls or changing the journal.
        controller = self.qa.controller["Id"]
        network.docker("pause", controller)
        try:
            journal_before = self.qa.journal(self.case)
            self.http("GET", "/", "cached-entry-get")
            self.http("GET", "/health", "cached-health-get")
            connection = http.client.HTTPConnection("localhost", timeout=5)
            connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.sock.settimeout(5)
            connection.sock.connect("/tmp/browser-platform-network-qa.sock")
            connection.request("GET", "/profiles/" + self.profile + "/coherence")
            reply = connection.getresponse()
            rejected = {"status": reply.status, "body": reply.read().decode(errors="replace")}
            connection.close()
            self.write("private-get.json", rejected)
            coherence.require(rejected["status"] == 405 and self.qa.journal(self.case) == journal_before,
                              "GET triggered a coherence probe")
        finally:
            network.docker("unpause", controller)
        result = {"result": "PASS", "case": self.case, "expected": expected, "entry_status": response["status"],
                  "first_entry_status": replies[0]["status"], "same_generation": True,
                  "empty_probe_did_not_create": None if existing else True, "existing_generation": existing,
                  "public_get_read_only": True, "private_get_status": 405, "public_capabilities_removed": True,
                  "coherence_overall": access["report"]["overall"], "country": access["report"].get("exit", {}).get("geoip", {}).get("country"),
                  "browser_ip": access["report"].get("exit", {}).get("browser_ip"),
                  "frozen_timezone": "America/New_York", "language": "en-US"}
        self.write("result.json", result)
        return result

    def stop(self):
        before = self.qa.snapshot(self.case)
        self.write("before.json", before)
        stopped = self.command("stop", "private-stop")
        after = self.qa.snapshot(self.case)
        self.write("after.json", after)
        coherence.require(stopped["exit_code"] == 0 and not any(after[k] for k in ("records", "workers", "resources")),
                          "Adapter stop did not clean the exact generation")
        result = {"result": "PASS", "case": self.case, "action": "stop", "resources": 0}
        self.write("result.json", result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "verify", "stop"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected", choices=("allowed", "blocked"), default="allowed")
    args = parser.parse_args()
    os.umask(0o077)
    checks = Checks(args.root, args.case, args.output)
    try:
        result = checks.start(args.expected, existing=args.action == "verify") if args.action != "stop" else checks.stop()
    except Exception:
        (checks.output / "error.log").write_text(traceback.format_exc())
        checks.write("result.json", {"result": "FAIL", "case": args.case})
        raise RuntimeError("QA entry check failed; inspect the private evidence") from None
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
