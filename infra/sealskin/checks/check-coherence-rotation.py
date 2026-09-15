#!/usr/bin/env python3
"""Observe two independent QA Profiles sharing one real rotating proxy.

An upstream outage between JP and HK verifies that UNKNOWN does not erase the
last known exit used by on_exit_change=block. No controller/Worker/proxy policy
is rewritten to claim a country. Only the scoped endpoint's authorized test
mode and peer routing state are changed, and both generations are cleaned up.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import traceback
import uuid
from types import SimpleNamespace


spec = importlib.util.spec_from_file_location("rotation_coherence", Path(__file__).with_name("check-runtime-coherence.py"))
coherence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coherence)
network = coherence.network


class Checks:
    def __init__(self, args):
        self.args = args
        self.qa = coherence.Checks(args.root)
        self.output = args.output.resolve()
        self.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.names = [args.recheck_case, args.block_case]
        entries = [self.qa.state["cases"][name] for name in self.names]
        coherence.require(self.names[0] != self.names[1] and
                          entries[0]["policy"]["upstream_host"] == entries[1]["policy"]["upstream_host"] == "188.253.118.223" and
                          entries[0]["policy"]["upstream_port"] == entries[1]["policy"]["upstream_port"] == 18180 and
                          [e["policy"]["coherence"]["on_exit_change"] for e in entries] == ["recheck", "block"] and
                          all(set(e["policy"]["coherence"]["allowed_countries"]) == {"JP", "HK"} for e in entries),
                          "Two scoped Profiles sharing the authorized JP proxy are required")
        for name in self.names:
            snapshot = self.qa.snapshot(name)
            coherence.require(not any(snapshot[k] for k in ("records", "workers", "resources")), "New empty QA generations required")
        self.started = []
        self.counter = 0

    def write(self, name, value):
        network.write_json(self.output / name, value)

    def endpoint(self, action, value, label):
        command = ["/tmp/browser-platform-lifecycle-venv/bin/python", str(Path(__file__).parent / "public-dns-endpoint/manage.py"),
                   action, "--deployment", str(self.args.deployment), "--ssh-key", str(self.args.ssh_key),
                   "--known-hosts", str(self.args.known_hosts), "--output", str(self.output / label)]
        if action == "rotation":
            command += ["--exit", value]
        elif action == "mode":
            command += ["--mode", value]
        result = subprocess.run(command, capture_output=True, text=True, timeout=40)
        self.write(label + "-command.json", {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        coherence.require(result.returncode == 0, "Scoped endpoint change failed")

    def probe(self, name, label):
        deadline = time.monotonic() + 40
        while time.time() - self.qa.journal(name).get("coherence_attempt_at", 0) < 10:
            coherence.require(time.monotonic() < deadline, "Probe scheduling exceeded bound")
            time.sleep(.2)
        self.counter += 1
        summary = self.qa.run(SimpleNamespace(action="probe", case=name, output=self.output / (label + "-" + name + "-" + str(self.counter))))
        return self.qa.journal(name)["coherence_report"]

    def stable(self, name, address, label):
        for _ in range(4):
            report = self.probe(name, label)
            if report.get("exit", {}).get("browser_ip") == address and report.get("observed", {}).get("timezone") == "America/New_York":
                return report
        raise RuntimeError("Actual browser exit did not reach the expected endpoint")

    def run(self):
        baseline = {}
        result = {"result": "INCOMPLETE"}
        try:
            self.endpoint("rotation", "local", "initial-local")
            self.endpoint("mode", "online", "initial-online")
            for name in self.names:
                self.started.append(name)
                self.qa.run(SimpleNamespace(action="start", case=name, output=self.output / ("start-" + name)))
                report = self.stable(name, "188.253.118.223", "baseline")
                coherence.require(report["allowed"] and report["exit"]["geoip"]["country"] == "JP", "Initial JP observation did not pass")
                baseline[name] = report
            fields = ("profile_id", "home_name", "operation_id", "session_id", "worker_id", "relay_id", "guard_id")
            coherence.require(all(baseline[self.names[0]]["binding"][key] != baseline[self.names[1]]["binding"][key] for key in fields),
                              "Profiles unexpectedly share runtime identity")
            self.write("baseline.json", baseline)
            self.endpoint("mode", "offline", "outage")
            unavailable = {name: self.probe(name, "unavailable") for name in self.names}
            coherence.require(all(not r["allowed"] and r["overall"] == "unknown" for r in unavailable.values()),
                              "Unreachable upstream was not UNKNOWN/blocked")
            self.write("unavailable.json", unavailable)
            histories = {name: self.qa.journal(name).get("coherence_exit_history") for name in self.names}
            self.write("unavailable-history.json", histories)
            history_preserved = all(isinstance(h, dict) and h.get("observation", {}).get("browser_ip") == "188.253.118.223" and
                                    h["observation"].get("checked_at", float("inf")) <= unavailable[name]["checked_at"]
                                    for name, h in histories.items())
            if self.args.require_history:
                coherence.require(history_preserved, "UNKNOWN lost a previous actual exit or its time")
            self.endpoint("rotation", "peer", "rotate-peer")
            self.endpoint("mode", "online", "restore-online")
            rotated = {name: self.stable(name, "202.155.153.31", "rotated") for name in self.names}
            self.write("rotated.json", rotated)
            coherence.require(all(r["exit"]["geoip"]["country"] == "HK" and
                                  r["binding"] == baseline[name]["binding"] and
                                  r["expected"] == baseline[name]["expected"] and r["observed"]["locale"] == "en-US"
                                  for name, r in rotated.items()), "Rotation altered binding, artifact or observed country")
            coherence.require(rotated[self.names[0]]["nonce"] != rotated[self.names[1]]["nonce"] and rotated[self.names[0]]["allowed"],
                              "Reports were shared or the recheck profile failed")
            block = rotated[self.names[1]]
            blocked = not block["allowed"] and block["overall"] == "unhealthy" and block.get("exit_change_blocked") is True
            result.update(result="PASS" if blocked else "CONFIRMED_GAP", same_entry="188.253.118.223:18180",
                          actual_exits=["188.253.118.223", "202.155.153.31"], countries=["JP", "HK"],
                          independent_reports=True, binding_and_environment_unchanged=True, outage_unknown=True,
                          recheck_allowed=True, block_latched_after_unknown=blocked, history_preserved_across_unknown=history_preserved)
            self.endpoint("rotation", "local", "return-local")
            returned = {name: self.stable(name, "188.253.118.223", "returned") for name in self.names}
            self.write("returned.json", returned)
            if blocked:
                coherence.require(returned[self.names[0]]["allowed"] and not returned[self.names[1]]["allowed"] and
                                  returned[self.names[1]].get("exit_change_blocked"), "Returning to the old exit cleared the block latch")
                result["block_retained_on_return"] = True
            if self.args.require_history:
                coherence.require(blocked, "A confirmed exit change was not latched")
                # Reset through a normal stop and a new launch operation on the
                # same QA Home, never by editing the controller reservation.
                name = self.names[1]
                self.qa.run(SimpleNamespace(action="stop", case=name, output=self.output / "reset-old-stop"))
                self.qa.state["cases"][name]["request"]["operation_id"] = uuid.uuid4().hex
                self.qa.save()
                self.qa.run(SimpleNamespace(action="start", case=name, output=self.output / "reset-new-start"))
                reset = self.stable(name, "188.253.118.223", "reset-new")
                self.write("reset-new.json", reset)
                coherence.require(reset["allowed"] and not reset.get("exit_change_blocked") and
                                  reset["binding"]["home_name"] == baseline[name]["binding"]["home_name"] and
                                  all(reset["binding"][key] != baseline[name]["binding"][key] for key in
                                      ("operation_id", "session_id", "worker_id", "relay_id", "guard_id")),
                                  "A normal new generation inherited a previous block or reused runtime identity")
                result["new_generation_resets_history_and_block"] = True
        except Exception:
            (self.output / "error.log").write_text(traceback.format_exc())
            result["result"] = "FAIL"
        finally:
            try:
                self.endpoint("rotation", "local", "cleanup-local")
                self.endpoint("mode", "online", "cleanup-online")
                for name in self.started:
                    self.qa.run(SimpleNamespace(action="stop", case=name, output=self.output / ("stop-" + name)))
                result["cleanup"] = "PASS"
            except Exception:
                (self.output / "cleanup-error.log").write_text(traceback.format_exc())
                result["cleanup"], result["result"] = "FAIL", "FAIL"
            self.write("result.json", result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("root", "output", "deployment", "ssh-key", "known-hosts"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--recheck-case", default="rotate-recheck")
    parser.add_argument("--block-case", default="rotate-block")
    parser.add_argument("--require-history", action="store_true", help="Verify persistent comparison evidence and a normal new-generation reset")
    args = parser.parse_args()
    os.umask(0o077)
    result = Checks(args).run()
    print(json.dumps(result), flush=True)
    if result["result"] == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
