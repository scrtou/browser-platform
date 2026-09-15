#!/usr/bin/env python3
"""Bounded continuity, expiry, GeoIP and resume checks for an owned QA case."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import traceback
from urllib.parse import urlsplit


spec = importlib.util.spec_from_file_location("recovery_coherence", Path(__file__).with_name("check-runtime-coherence.py"))
coherence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coherence)
network = coherence.network

WEBSOCKET = r'''
import socket,struct,base64,json,os,time,sys
relay,target,port,nonce,seconds=sys.argv[1],sys.argv[2],int(sys.argv[3]),sys.argv[4],float(sys.argv[5])
def exact(s,n):
 b=b''
 while len(b)<n:
  v=s.recv(n-len(b))
  if not v:raise EOFError('closed')
  b+=v
 return b
s=socket.create_connection((relay,1080),timeout=8);s.sendall(b'\x05\x01\x00');assert exact(s,2)==b'\x05\x00'
h=target.encode();s.sendall(b'\x05\x01\x00\x03'+bytes([len(h)])+h+struct.pack('!H',port));assert exact(s,10)[:2]==b'\x05\x00'
key=base64.b64encode(os.urandom(16)).decode()
s.sendall((f'GET /ws?nonce={nonce} HTTP/1.1\r\nHost: {target}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n').encode())
head=b''
while not head.endswith(b'\r\n\r\n'):head+=exact(s,1)
assert head.startswith(b'HTTP/1.1 101')
start=time.monotonic();count=0
print(json.dumps({'event':'ready','at':time.time()}),flush=True)
try:
 while time.monotonic()-start<seconds:
  mask=os.urandom(4);body=nonce.encode()
  s.sendall(bytes([129,128+len(body)])+mask+bytes(c^mask[i%4] for i,c in enumerate(body)))
  code,length=exact(s,2);assert code==129
  reply=json.loads(exact(s,length));assert reply['nonce']==nonce
  count+=1;time.sleep(1)
 result='OPEN'
except (EOFError,OSError):
 result='CLOSED'
finally:s.close()
print(json.dumps({'result':result,'echoes':count,'seconds':time.monotonic()-start,'finished_at':time.time()}),flush=True)
'''


class Checks:
    def __init__(self, args):
        self.args = args
        self.qa = coherence.Checks(args.root)
        self.root = self.qa.qa
        self.output = args.output.resolve()
        self.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.case = args.case
        self.entry = self.qa.state["cases"][self.case]
        self.before = self.qa.snapshot(self.case)
        self.journal = self.qa.journal(self.case)
        coherence.require(len(self.before["workers"]) == 1 and len(self.before["records"]) == 1, "One owned QA generation required")
        self.ids = {"worker": self.before["workers"][0]["instance_id"], "guard": self.journal["allocation"]["guard_id"],
                    "relay": self.journal["allocation"]["relay_id"]}
        self.controller = self.qa.controller["Id"]
        self.identity = self.journal["identity"]
        self.resources = self.inspect()
        for value in self.resources.values():
            coherence.require(value["State"]["Running"] and not value["State"]["Paused"] and
                              all(value["Config"]["Labels"].get(network.PREFIX + k) == v for k, v in self.identity.items() if k != "home_source"),
                              "Exact running QA resources required")
        self.write("before.json", {"snapshot": self.before, "journal": self.journal, "containers": self.resources})

    def write(self, name, value):
        network.write_json(self.output / name, value)

    def inspect(self):
        return {role: json.loads(network.docker("inspect", identifier).stdout)[0] for role, identifier in self.ids.items()}

    def command(self, action, label):
        result = subprocess.run([str(self.root / "bin/profile-adapter"), "-config", str(self.root / "adapter-config.json"),
                                 "-" + action + "-profile", self.entry["request"]["profile_id"]],
                                capture_output=True, text=True, timeout=110)
        self.write(label + ".json", {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "at": time.time()})
        coherence.require(result.returncode == 0, "Explicit QA Adapter operation failed")
        return json.loads(result.stdout)

    def resume_until_ready(self):
        # Resume can restore all containers before a new browser observation
        # is ready. A 503 retains the operation; normal retries must eventually
        # succeed on this exact generation before the check can pass.
        for attempt in range(4):
            if attempt:
                time.sleep(10.2)
            result = subprocess.run([str(self.root / "bin/profile-adapter"), "-config", str(self.root / "adapter-config.json"),
                                     "-resume-profile", self.entry["request"]["profile_id"]],
                                    capture_output=True, text=True, timeout=110)
            self.write("adapter-resume-" + str(attempt + 1) + ".json",
                       {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "at": time.time()})
            if result.returncode == 0:
                return attempt + 1
            coherence.require("control command returned HTTP 503:" in result.stdout,
                              "Resume failed outside the retryable readiness response")
        raise RuntimeError("QA resume did not become verified ready within four attempts")

    def probe(self, label):
        while time.time() - self.qa.journal(self.case).get("coherence_attempt_at", 0) < 10:
            time.sleep(.2)
        return self.command("coherence", label)

    def permitted(self, label):
        for attempt in range(4):
            result = self.probe(label + "-" + str(attempt + 1))
            if result.get("allowed"):
                return result
        raise RuntimeError("QA generation did not recover a permitted report")

    def websocket(self, seconds):
        endpoint = json.loads((self.args.bundle / "before/config.json").read_text())
        command = ["docker", "exec", self.ids["worker"], "python3", "-u", "-c", WEBSOCKET,
                   self.journal["allocation"]["relay_ip"], endpoint["website_names"][0],
                   str(endpoint["ports"]["http"]), os.urandom(16).hex(), str(seconds)]
        log = self.output / "client.log"
        with log.open("w") as handle:
            process = subprocess.Popen(["sg", "docker", "-c", shlex.join(command)], stdout=handle, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            lines = log.read_text().splitlines()
            if any(line.startswith('{"event": "ready"') for line in lines):
                return process
            coherence.require(process.poll() is None, "QA WebSocket did not establish")
            time.sleep(.2)
        raise RuntimeError("QA WebSocket readiness timeout")

    def finish_client(self, process, seconds):
        deadline = time.monotonic() + seconds
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(.2)
        coherence.require(process.poll() == 0, "Bounded QA WebSocket did not complete")
        return json.loads((self.output / "client.log").read_text().splitlines()[-1])

    def continuity(self):
        self.permitted("preflight")
        process = self.websocket(95)
        samples = []
        while process.poll() is None:
            report = self.qa.journal(self.case)["coherence_report"]
            samples.append({"at": time.time(), "nonce": report.get("nonce"), "checked_at": report["checked_at"],
                            "expires_at": report["expires_at"], "allowed": report["allowed"], "overall": report["overall"]})
            time.sleep(.5)
        self.write("samples.json", samples)
        client = self.finish_client(process, 1)
        fresh = all(s["allowed"] and s["checked_at"] <= s["at"] < s["expires_at"] for s in samples)
        nonces = len({s["nonce"] for s in samples})
        coherence.require(client["result"] == "OPEN" and client["seconds"] >= 95 and client["echoes"] >= 70 and fresh and nonces >= 4,
                          "Continuous access or timely report renewal failed")
        return {"result": "PASS", "client": client, "fresh_samples": fresh, "distinct_nonces": nonces}

    def expiry(self):
        self.permitted("preflight")
        process = self.websocket(100)
        stopped = False
        try:
            network.docker("stop", "--time", "30", self.controller)
            stopped = True
            actual = self.inspect()
            coherence.require(all(v["State"]["Running"] and v["State"]["StartedAt"] == self.resources[k]["State"]["StartedAt"]
                                  for k, v in actual.items()), "Stopping QA controller affected generation processes")
            journal = self.qa.journal(self.case)
            gate_path = self.root / "config/.config/sealskin/profile-network-runtime" / (self.identity["home_hash"] + "-" + self.identity["operation"]) / "coherence/gate.json"
            gate = json.loads(gate_path.read_text())
            self.write("stopped.json", {"containers": actual, "journal": journal, "gate": gate})
            client = self.finish_client(process, 80)
            delay = client["finished_at"] - gate["expires_ms"] / 1000
            coherence.require(client["result"] == "CLOSED" and client["echoes"] >= 1 and -.5 <= delay <= 3,
                              "Existing website tunnel did not close at actual gate expiry")
        finally:
            if stopped:
                network.docker("start", self.controller)
                network.wait(lambda: network.request("POST", "/api/handshake/initiate")[0] == 200, "owned QA controller", 40)
                self.qa = coherence.Checks(self.root)
        recovered = self.permitted("recovery")
        return {"result": "PASS", "client": client, "delay_after_expiry_seconds": delay,
                "controller_restarted": True, "same_binding": recovered["report"]["binding"] == self.journal["coherence_report"]["binding"]}

    def exchange(self, label):
        record = json.loads(self.args.entry_record.read_text())
        target = urlsplit(record["headers"]["Location"])
        coherence.require(target.scheme == "https" and target.netloc == "network.invalid", "Only the QA Session origin is allowed")
        status, headers, body = network.request("GET", target.path + ("?" + target.query if target.query else ""))
        self.write(label + ".json", {"status": status, "headers": headers, "body": body.decode(errors="replace")})
        return status, headers

    def geoip(self):
        before = self.permitted("preflight")
        status, _ = self.exchange("exchange-before")
        coherence.require(status == 303, "Initial token exchange unavailable")
        ref = self.journal["policy"]["coherence"]["geoip_file"]
        database = self.root / "config" / ref.removeprefix("/config/")
        coherence.require(database.resolve().is_relative_to(self.root / "config/coherence-assets") or
                          database.resolve().is_relative_to(self.root / "config/.config/sealskin/coherence-assets"),
                          "Only QA GeoIP asset may be moved")
        original_sha = hashlib.sha256(database.read_bytes()).hexdigest()
        withheld = self.output / "temporarily-unavailable.csv"
        try:
            database.rename(withheld)
            missing = self.probe("missing-database")
            status, headers = self.exchange("exchange-unavailable")
            coherence.require(not missing["allowed"] and missing["report"]["overall"] == "unknown" and
                              status == 503 and not headers.get("Set-Cookie"), "Unknown GeoIP incorrectly passed strict token exchange")
        finally:
            if withheld.exists():
                coherence.require(not database.exists(), "QA database target unexpectedly changed")
                withheld.rename(database)
        after = self.permitted("recovery")
        recovered_status, _ = self.exchange("exchange-restored")
        coherence.require(after["report"]["binding"] == before["report"]["binding"] and recovered_status == 303 and
                          hashlib.sha256(database.read_bytes()).hexdigest() == original_sha, "GeoIP restore changed binding or data")
        return {"result": "PASS", "token_exchange_statuses": [303, status, recovered_status], "missing_overall": "unknown",
                "same_binding": True, "same_database_sha256": original_sha}

    def resume(self):
        before = self.permitted("preflight")
        marker = self.root / "storage/network-qa" / self.entry["request"]["home_name"] / ".r5c3-recovery-marker"
        marker.write_text("qa-recovery-" + self.identity["operation"])
        marker_sha = hashlib.sha256(marker.read_bytes()).hexdigest()
        for role in ("worker", "guard", "relay"):
            network.docker("stop", "--time", "30", self.ids[role])
        self.write("dormant.json", self.inspect())
        attempts = self.resume_until_ready()
        after = self.permitted("recovery")
        actual = self.inspect()
        stable = ("application_id", "profile_id", "home_name", "operation_id", "session_id", "policy_id", "policy_sha256",
                  "artifact_sha256", "acceptance_sha256", "environment_id", "worker_id", "relay_id", "guard_id")
        coherence.require(all(before["report"]["binding"][k] == after["report"]["binding"][k] for k in stable) and
                          all(v["State"]["Running"] and v["State"]["StartedAt"] != self.resources[k]["State"]["StartedAt"]
                              for k, v in actual.items()) and hashlib.sha256(marker.read_bytes()).hexdigest() == marker_sha,
                          "Same-generation resume changed identity or lost QA Home data")
        self.write("after.json", {"containers": actual, "snapshot": self.qa.snapshot(self.case), "report": after})
        return {"result": "PASS", "same_generation": True, "all_three_processes_restarted": True,
                "home_marker_preserved": True, "new_nonce": before["report"]["nonce"] != after["report"]["nonce"],
                "resume_attempts": attempts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("continuity", "expiry", "geoip", "resume"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--entry-record", type=Path)
    args = parser.parse_args()
    coherence.require(args.action not in {"continuity", "expiry"} or args.bundle, "Endpoint bundle required")
    coherence.require(args.action != "geoip" or args.entry_record, "Private entry response required")
    os.umask(0o077)
    checks = Checks(args)
    try:
        result = getattr(checks, args.action)()
        result.update(action=args.action, case=args.case)
        checks.write("result.json", result)
    except Exception:
        (checks.output / "error.log").write_text(traceback.format_exc())
        checks.write("result.json", {"result": "FAIL", "action": args.action, "case": args.case})
        raise RuntimeError("QA recovery check failed; inspect private evidence") from None
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
