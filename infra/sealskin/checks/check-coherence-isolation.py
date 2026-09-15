#!/usr/bin/env python3
"""Inject a narrowly scoped isolation fault into one owned coherence QA case.

The sole added permit is to the configured public QA observer over HTTPS.
Restore the original ACL and topology while the Worker is paused, then stop
through the lifecycle API. Detailed Session evidence stays in a private folder.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import traceback
from types import SimpleNamespace


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


coherence = module("coherence_checks", Path(__file__).with_name("check-runtime-coherence.py"))
network = coherence.network
guard_code = module("isolation_guard", Path(__file__).resolve().parents[3] / "relay/network-guard.py")


def docker_input(args, data):
    result = subprocess.run(["sg", "docker", "-c", shlex.join(["docker", *args])],
                            input=data, text=True, capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError("Scoped QA rules operation failed")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kind", choices=("topology", "rules"), default="topology")
    args = parser.parse_args()
    os.umask(0o077)
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    qa = coherence.Checks(args.root)
    write = lambda name, value: network.write_json(output / name, value)
    inspect = lambda identifier: json.loads(network.docker("inspect", identifier).stdout)[0]
    journal = qa.journal(args.case)
    identity, allocation = journal["identity"], journal["allocation"]
    before = qa.snapshot(args.case)
    coherence.require(len(before["workers"]) == len(before["records"]) == 1, "One owned running QA generation required")
    ids = {"worker": before["workers"][0]["instance_id"], "guard": allocation["guard_id"], "relay": allocation["relay_id"]}
    resources = {key: inspect(identifier) for key, identifier in ids.items()}
    for value in resources.values():
        labels = value["Config"]["Labels"]
        coherence.require(value["State"]["Running"] and not value["State"]["Paused"] and
                          all(labels.get(network.PREFIX + key) == wanted for key, wanted in identity.items() if key != "home_source"),
                          "Exact running QA ownership required")
    controller = qa.controller["Id"]
    controller_start = qa.controller["State"]["StartedAt"]
    guard_networks = resources["guard"]["NetworkSettings"]["Networks"]
    coherence.require(len(guard_networks) == 1 and
                      next(iter(guard_networks.values()))["NetworkID"] == allocation["internal_id"],
                      "Original guard topology required")
    egress = json.loads(network.docker("network", "inspect", allocation["egress_id"]).stdout)[0]
    coherence.require(egress["Labels"].get(network.PREFIX + "operation") == identity["operation"] and
                      set(egress["Containers"]) == {ids["relay"]}, "Exclusive generation egress required")
    mount = [m for m in resources["guard"]["Mounts"] if m["Destination"] == "/run/config/network.json"]
    coherence.require(len(mount) == 1 and Path(mount[0]["Source"]).resolve().is_relative_to(qa.qa), "Owned guard policy required")
    config = guard_code.load(Path(mount[0]["Source"]))
    coherence.require(coherence.digest(config) == allocation["guard_config_sha256"], "Frozen guard configuration required")
    original_rules = guard_code.rules(config)
    observer = journal["policy"]["coherence"]
    address, port = observer["observer_ipv4"][0], observer["observer_port"]
    coherence.require(address in {"188.253.118.223", "202.155.153.31"} and port == 18443, "Only authorized QA observer target allowed")
    ca_path = qa.qa / "config" / journal["policy"]["probe_ca_file"].removeprefix("/config/")
    tls_config = {"ipv4": address, "port": port, "domain": observer["observer_domain"], "ca": ca_path.read_text()}
    command = (
        "import json,socket,ssl\n"
        "c=json.loads(" + repr(json.dumps(tls_config)) + ")\n"
        "ctx=ssl.create_default_context(cadata=c['ca'])\n"
        "with socket.create_connection((c['ipv4'],c['port']),5) as raw:\n"
        " with ctx.wrap_socket(raw,server_hostname=c['domain']) as s:\n"
        "  s.sendall(('GET /health HTTP/1.1\\r\\nHost: '+c['domain']+':'+str(c['port'])+'\\r\\nConnection: close\\r\\n\\r\\n').encode())\n"
        "  line=s.recv(4096).split(b'\\r\\n',1)[0].decode()\n"
        "  print(json.dumps({'status_line':line,'peer':s.getpeername(),'local':s.getsockname(),'tls_verified':True,'via':'literal-native-socket'}))\n"
    )
    write("before.json", {"journal": journal, "snapshot": before, "containers": resources, "egress": egress})
    result = {"kind": args.kind, "result": "INCOMPLETE", "started_at": time.time()}
    changed, controller_paused, restored = False, False, False
    try:
        preflight = qa.run(SimpleNamespace(action="access", case=args.case, output=output / "preflight"))
        coherence.require(preflight.get("allowed"), "Fresh permitted baseline required")
        network.docker("pause", controller)
        controller_paused = True
        denied = network.docker("exec", ids["worker"], "python3", "-c", command, check=False)
        write("native-before.json", {"returncode": denied.returncode, "stdout": denied.stdout, "stderr": denied.stderr})
        coherence.require(denied.returncode != 0, "Original native bypass must be denied")
        changed = True
        if args.kind == "topology":
            network.docker("network", "connect", allocation["egress_id"], ids["guard"])
        network.docker("exec", "--user", "0", ids["guard"], "nft", "insert", "rule", "inet", "bp_guard", "output",
                       "ip", "daddr", address, "tcp", "dport", str(port), "counter", "accept")
        reached = network.docker("exec", ids["worker"], "python3", "-c", command, check=False)
        write("native-after.json", {"returncode": reached.returncode, "stdout": reached.stdout, "stderr": reached.stderr})
        write("injected.json", {"worker": inspect(ids["worker"]), "guard": inspect(ids["guard"])})
        result["native_bypass_confirmed"] = reached.returncode == 0 and json.loads(reached.stdout)["status_line"].startswith("HTTP/1.1 200")
        if args.kind == "topology":
            coherence.require(result["native_bypass_confirmed"], "Actual HTTPS bypass was not demonstrated")
        else:
            coherence.require(not result["native_bypass_confirmed"], "Rules-only fault should still lack a public route")
        network.docker("unpause", controller)
        controller_paused = False
        deadline = time.monotonic() + 12
        while time.time() - qa.journal(args.case).get("coherence_attempt_at", 0) < 10:
            if time.monotonic() > deadline:
                break
            time.sleep(.2)
        probe = qa.run(SimpleNamespace(action="probe", case=args.case, output=output / "probe"))
        worker = inspect(ids["worker"])
        updated = qa.journal(args.case)
        report = updated.get("coherence_report") or {}
        result.update(system_paused=worker["State"]["Paused"], overall=report.get("overall"),
                      allowed=report.get("allowed"), codes=[c["code"] for c in report.get("checks", [])],
                      paused_for_isolation=report.get("paused_for_isolation", False))
        write("observed.json", {"probe": probe, "worker": worker, "journal": updated})
        if result["system_paused"] and report.get("paused_for_isolation") and report.get("overall") == "unhealthy" and not report.get("allowed"):
            # A second explicit request sees the paused instance as unavailable.
            # It must preserve the confirmed failure and blocked gate.
            time.sleep(10.1)
            followup = qa.run(SimpleNamespace(action="probe", case=args.case, output=output / "followup"))
            retained = qa.journal(args.case)["coherence_report"]
            result["failure_retained"] = retained.get("paused_for_isolation") and retained.get("overall") == "unhealthy" and not retained.get("allowed")
            coherence.require(result["failure_retained"], "Unavailable followup erased confirmed failure")
            result["result"] = "PASS"
        else:
            result["result"] = "CONFIRMED_GAP"
    except Exception:
        (output / "error.log").write_text(traceback.format_exc())
        result["result"] = "FAILED"
    finally:
        try:
            if changed:
                worker = inspect(ids["worker"])
                if not worker["State"]["Paused"]:
                    network.docker("pause", ids["worker"])
                    result["manual_containment"] = True
                attached = inspect(ids["guard"])["NetworkSettings"]["Networks"]
                if any(v["NetworkID"] == allocation["egress_id"] for v in attached.values()):
                    network.docker("network", "disconnect", allocation["egress_id"], ids["guard"])
                docker_input(["exec", "--user", "0", "-i", ids["guard"], "nft", "-f", "-"], original_rules)
                after = inspect(ids["guard"])
                coherence.require(after["NetworkSettings"]["Networks"] == guard_networks, "Original QA topology restoration unconfirmed")
                result["restrictions_restored_before_stop"] = True
                restored = True
            if controller_paused:
                network.docker("unpause", controller)
                controller_paused = False
            control = inspect(controller)
            coherence.require(control["State"]["StartedAt"] == controller_start and not control["State"]["Paused"], "QA controller state changed")
            if changed and restored:
                qa.run(SimpleNamespace(action="stop", case=args.case, output=output / "stop"))
                result["lifecycle_cleanup"] = "PASS"
        except Exception:
            (output / "cleanup-error.log").write_text(traceback.format_exc())
            result["cleanup"] = "FAILED"
            result["result"] = "FAILED"
        result["finished_at"] = time.time()
        write("result.json", result)
    print(json.dumps(result), flush=True)
    if result["result"] == "FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
