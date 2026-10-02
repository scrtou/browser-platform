#!/usr/bin/env python3
"""Focused managed-DIRECT QA for the production-compatible Work Firefox/Wayland image.

The script only accepts the isolated generation QA prepared by
prepare-network-qa.py and prepare-network-browser.py. It converts that QA app
to an independent DIRECT revision, proves real DNS/TLS/page access, verifies
the Worker cannot bypass its gateway, exercises a gateway failure, and checks
browser storage after a clean stop and new generation. It never targets the
production Work Home or application.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[3]
CHECKS_PATH = PROJECT / "infra/sealskin/lifecycle/check-network-live.py"
BIDI_PATH = PROJECT / "infra/firefox-proxy/check-bidi.py"


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def wait(predicate, message: str, seconds: float = 60) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (OSError, RuntimeError, KeyError, IndexError, json.JSONDecodeError):
            pass
        time.sleep(0.4)
    raise RuntimeError("timeout waiting for " + message)


def bidi_value(network, worker: str, expression: str, navigate: str = ""):
    source = BIDI_PATH.read_text().split("\ndef main()", 1)[0]
    source += (
        '\nb=BiDi(WebSocket("127.0.0.1",9228))\n'
        'b.command("session.new",{"capabilities":{}})\n'
        'try:\n c=b.command("browsingContext.getTree",{})["contexts"][0]["context"]\n'
    )
    if navigate:
        source += (
            ' b.command("browsingContext.navigate",{"context":c,"url":'
            + repr(navigate)
            + ',"wait":"complete"})\n'
        )
    source += (
        " print(json.dumps({\"value\":b.evaluate(c," + repr(expression) + ")}))\n"
        "finally:\n b.command(\"session.end\",{})\n b.websocket.socket.close()\n"
    )
    output = network.docker("exec", worker, "python3", "-c", source).stdout
    return json.loads(output)["value"]


def process_identity(network, worker: str) -> dict[str, object]:
    source = r'''import json
from pathlib import Path
out=[]
for path in Path('/proc').glob('[0-9]*'):
 try:
  args=path.joinpath('cmdline').read_bytes().split(b'\0')
  remote=any(item==b'--remote-debugging-port' or item.startswith(b'--remote-debugging-port=') for item in args)
  if args and args[0].endswith(b'/firefox') and remote:
   status=path.joinpath('status').read_text().splitlines()
   uid=int(next(item for item in status if item.startswith('Uid:')).split()[1])
   out.append({'pid':int(path.name),'uid':uid,
               'start':path.joinpath('stat').read_text().split()[21]})
 except (OSError,IndexError,ValueError): pass
assert len(out)==1
print(json.dumps(out[0]))
'''
    identity = json.loads(network.docker("exec", worker, "python3", "-c", source).stdout)
    detail_source = r'''import json,os
from pathlib import Path
pid=PID
env=dict(item.split(b'=',1) for item in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in item)
fds=[]
for path in Path(f'/proc/{pid}/fd').iterdir():
 try:fds.append(os.readlink(path))
 except OSError:pass
print(json.dumps({'wayland':bool(env.get(b'WAYLAND_DISPLAY')),
                  'native_wayland':any('wayland' in item.lower() for item in fds)}))
'''.replace("PID", str(identity["pid"]))
    details = json.loads(network.docker(
        "exec", "-u", str(identity.pop("uid")), worker, "python3", "-c", detail_source
    ).stdout)
    identity.update(details)
    return identity


def raw_bypass(network, worker: str) -> dict[str, bool]:
    source = Path(__file__).with_name("worker-bypass.py").read_text()
    outcomes = json.loads(network.docker("exec", worker, "python3", "-c", source).stdout)
    if any(not value["blocked"] and value["outcome"] != "connected_or_replied" for value in outcomes.values()):
        raise RuntimeError("Worker bypass rejection is unconfirmed")
    return {name: not value["blocked"] for name, value in outcomes.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resolver-ip", default="1.1.1.1")
    args = parser.parse_args()
    resolver = ipaddress.IPv4Address(args.resolver_ip)
    if not resolver.is_global:
        parser.error("resolver must be a public IPv4 address")
    qa, output = args.root.resolve(), args.output.resolve()
    if qa.name != "qa" or output.exists() or output.parent != qa.parent:
        parser.error("use a new evidence directory beside the isolated qa directory")
    output.mkdir(mode=0o700)

    spec = importlib.util.spec_from_file_location("network_checks", CHECKS_PATH)
    network = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(network)
    checks = network.Checks(qa)
    info = json.loads((qa / "browser-worker.json").read_text())
    if (
        info.get("engine") != "firefox"
        or info.get("source_app") != "firefox-work"
        or not info.get("wayland")
        or not info.get("managed_image")
    ):
        raise RuntimeError("R7B requires a firefox-work Wayland QA fixture")
    if info["home"] == "work" or info["profile"] == "work":
        raise RuntimeError("production Work identity is forbidden")

    results: list[dict[str, object]] = []

    def passed(name: str, **details: object) -> None:
        item = {"check": name, "result": "PASS", **details}
        results.append(item)
        network.write_json(output / "results.json", results)
        print(json.dumps(item, sort_keys=True), flush=True)

    initial_stop = json.loads((qa / "browser-stop.json").read_text())
    status, current = checks.client.call("GET", "/api/profile-runtime/" + info["home"])
    if status != 200:
        raise RuntimeError("could not inspect the initial proxy QA generation")
    if current["records"] or current["workers"] or current["resources"]:
        expected = {
            "app": initial_stop["application_id"],
            "profile": initial_stop["profile_id"],
            "operation": initial_stop["operation_id"],
            "policy": initial_stop["network_policy_id"],
            "revision": initial_stop["network_policy_sha256"],
        }
        observed = []
        for item in current["records"] + current["workers"]:
            observed.append({
                "app": item["app_id"], "profile": item["profile_id"],
                "operation": item["operation_id"], "policy": item["network_policy_id"],
                "revision": item["network_policy_sha256"],
            })
        for item in current["resources"]:
            observed.append({
                "app": item["app_id"], "profile": item["profile_id"],
                "operation": item["operation_id"], "policy": item["policy_id"],
                "revision": item["policy_sha256"],
            })
        if not observed or any(item != expected for item in observed):
            raise RuntimeError("refusing to stop an unexpected QA generation")
        status, _ = checks.client.call(
            "POST", "/api/profile-runtime/" + info["home"] + "/stop", initial_stop
        )
        if status != 204:
            raise RuntimeError("could not stop the initial proxy QA generation")
    status, empty = checks.client.call("GET", "/api/profile-runtime/" + info["home"])
    if status != 200 or empty["records"] or empty["workers"] or empty["resources"]:
        raise RuntimeError("initial QA generation did not reach zero resources")

    admin_data = json.loads((qa / "admin.json").read_text())
    admin = network.SecureClient(
        qa,
        username=admin_data["username"],
        private=admin_data["private_key"].encode(),
        public=admin_data["server_public_key"].encode(),
    )
    status, apps = admin.call("GET", "/api/admin/apps/installed")
    app = next(value for value in apps if value["id"] == "network-qa-firefox-network")
    managed = json.loads(network.docker("image", "inspect", info["managed_image"]).stdout)[0]
    managed_labels = managed.get("Config", {}).get("Labels") or {}
    if (
        managed["Id"] != info["managed_image"]
        or managed_labels.get("io.browser-platform.managed-firefox-network") != "1"
        or app["provider_config"].get("image") != managed["Id"]
    ):
        raise RuntimeError("R7B requires the reviewed managed-network Work image")
    images = json.loads((qa / "images.json").read_text())
    relay_info = json.loads(network.docker("image", "inspect", images["relay"]).stdout)[0]
    if relay_info.get("Config", {}).get("Labels", {}).get("io.browser-platform.direct-egress") != "1":
        raise RuntimeError("QA Relay image lacks DIRECT capability")
    policy = {
        "username": "network-qa",
        "profile_id": info["profile"],
        "home_name": info["home"],
        "application_id": app["id"],
        "mode": "direct",
        "approved_resolver_id": "r7b-public-resolver-v1",
        "approved_resolver_ip": str(resolver),
        "relay_image": images["relay"],
        "probe_image": images["probe"],
        "upstream_host": "",
        "upstream_port": 0,
        "username_file": "",
        "username_sha256": "",
        "password_file": "",
        "password_sha256": "",
        "probe_url": "https://example.com/",
        "probe_ca_file": "",
        "probe_ca_sha256": "",
        "probe_timeout_seconds": 10,
    }
    policy_id = "r7b-work-direct-" + uuid.uuid4().hex[:12]
    revision = digest(policy)
    registry_path = qa / "config/.config/sealskin/profile-network-policies.json"
    registry = json.loads(registry_path.read_text())
    registry["policies"][policy_id] = policy
    network.write_json(registry_path, registry)
    provider = app["provider_config"]
    provider["network_policy_id"], provider["network_policy_sha256"] = policy_id, revision
    status, _ = admin.call(
        "PATCH", "/api/admin/apps/installed/" + app["id"], {"provider_config": provider}
    )
    if status != 200:
        raise RuntimeError("could not bind the QA app to its DIRECT revision")

    def launch() -> tuple[dict[str, object], dict[str, object], str]:
        request = {
            "url": "https://example.com/",
            "application_id": app["id"],
            "home_name": info["home"],
            "profile_id": info["profile"],
            "operation_id": uuid.uuid4().hex,
            "network_policy_id": policy_id,
            "network_policy_sha256": revision,
            "language": "zh_TW.UTF-8",
            "timezone": "Asia/Taipei",
            "wayland_mode": True,
            "launch_in_room_mode": False,
        }
        status, value = checks.client.call("POST", "/api/launch/url", request)
        if status != 200:
            raise RuntimeError("DIRECT Work QA launch failed")
        stop = {key: request[key] for key in (
            "application_id", "profile_id", "operation_id", "network_policy_id", "network_policy_sha256"
        )}
        stop["bootstrap_url"] = request["url"]
        status, snapshot = checks.client.call("GET", "/api/profile-runtime/" + info["home"])
        if status != 200 or len(snapshot["workers"]) != 1:
            raise RuntimeError("DIRECT Work QA worker missing")
        worker = snapshot["workers"][0]["instance_id"]
        wait(lambda: process_identity(network, worker)["wayland"], "Wayland Firefox")
        wait(
            lambda: bidi_value(
                network, worker, "document.readyState", navigate=request["url"]
            ) == "complete",
            "BiDi public navigation",
        )
        return request, stop, worker

    request, stop, worker = launch()
    identity = process_identity(network, worker)
    if not identity["wayland"] or not identity["native_wayland"]:
        raise RuntimeError("Firefox is not using native Wayland")
    wait(lambda: bidi_value(network, worker, "document.readyState") == "complete", "public page")
    page = {
        "hostname": bidi_value(network, worker, "location.hostname"),
        "title": bidi_value(network, worker, "document.title"),
        "ready": bidi_value(network, worker, "document.readyState"),
    }
    if page != {"hostname": "example.com", "title": "Example Domain", "ready": "complete"}:
        raise RuntimeError("unexpected public page result")
    status, health = checks.client.call(
        "GET", "/api/profile-runtime/" + info["home"] + "/health?upstream=true"
    )
    if (
        status != 200
        or health.get("network", {}).get("mode") != "direct"
        or health["network"].get("enforcement_version") != 1
        or health["network"].get("worker_namespace") is not True
        or health["network"].get("upstream", {}).get("status") != "pass"
    ):
        raise RuntimeError("DIRECT health did not prove the managed public path")
    bypass = raw_bypass(network, worker)
    if any(bypass.values()):
        raise RuntimeError("Worker reached a direct bypass target")
    passed(
        "production-compatible Firefox/Wayland reaches public HTTPS only through managed DIRECT",
        image=provider["image"], direct_health="pass", raw_bypass_targets=len(bypass)
    )

    marker = uuid.uuid4().hex
    write_expression = """(async()=>{localStorage.setItem('r7b-marker',MARKER);document.cookie='r7b_marker='+MARKER+'; Path=/; Max-Age=86400; SameSite=Lax; Secure';let db=await new Promise((ok,fail)=>{let q=indexedDB.open('r7b-direct',1);q.onupgradeneeded=()=>q.result.createObjectStore('values');q.onsuccess=()=>ok(q.result);q.onerror=()=>fail(q.error)});await new Promise((ok,fail)=>{let q=db.transaction('values','readwrite').objectStore('values').put(MARKER,'marker');q.onsuccess=ok;q.onerror=()=>fail(q.error)});db.close();return true})()""".replace("MARKER", json.dumps(marker))
    if bidi_value(network, worker, write_expression) is not True:
        raise RuntimeError("could not write browser persistence markers")

    status, snapshot = checks.client.call("GET", "/api/profile-runtime/" + info["home"])
    resources = {item["kind"]: item["id"] for item in snapshot["resources"]}
    network.docker("stop", "-t", "5", resources["relay"])
    wait(
        lambda: checks.client.call("GET", "/api/profile-runtime/" + info["home"] + "/health?upstream=true")[1]
        .get("network", {}).get("relay", {}).get("status") == "fail",
        "DIRECT gateway failure health",
    )
    failed_bypass = raw_bypass(network, worker)
    if any(failed_bypass.values()):
        raise RuntimeError("gateway failure opened a direct bypass")
    passed("DIRECT gateway failure remains fail-closed", raw_bypass_targets=len(failed_bypass))

    status, _ = checks.client.call("POST", "/api/profile-runtime/" + info["home"] + "/stop", stop)
    if status != 204:
        raise RuntimeError("failed generation did not stop cleanly")
    status, empty = checks.client.call("GET", "/api/profile-runtime/" + info["home"])
    if status != 200 or empty["records"] or empty["workers"] or empty["resources"]:
        raise RuntimeError("failed generation left resources")

    request2, stop2, worker2 = launch()
    wait(lambda: bidi_value(network, worker2, "document.readyState") == "complete", "recreated public page")
    read_expression = """(async()=>{let db=await new Promise((ok,fail)=>{let q=indexedDB.open('r7b-direct',1);q.onsuccess=()=>ok(q.result);q.onerror=()=>fail(q.error)});let idb=await new Promise((ok,fail)=>{let q=db.transaction('values').objectStore('values').get('marker');q.onsuccess=()=>ok(q.result);q.onerror=()=>fail(q.error)});db.close();let cookie=(document.cookie.split('; ').find(v=>v.startsWith('r7b_marker='))||'').slice(11);return JSON.stringify({local:localStorage.getItem('r7b-marker'),cookie,idb})})()"""
    restored = json.loads(bidi_value(network, worker2, read_expression))
    if restored != {"local": marker, "cookie": marker, "idb": marker}:
        raise RuntimeError("browser storage did not survive the DIRECT generation change")
    if process_identity(network, worker2)["start"] == identity["start"]:
        raise RuntimeError("test did not create a new browser generation")
    passed("clean stop and new DIRECT generation preserve Work browser storage", stores=3)

    status, _ = checks.client.call("POST", "/api/profile-runtime/" + info["home"] + "/stop", stop2)
    if status != 204:
        raise RuntimeError("final Work QA stop failed")
    status, final = checks.client.call("GET", "/api/profile-runtime/" + info["home"])
    if status != 200 or final["records"] or final["workers"] or final["resources"]:
        raise RuntimeError("final Work QA resources are not empty")
    passed("final Work QA resources are empty", production_mutations=0)
    network.write_json(output / "summary.json", {
        "result": "PASS", "checks": len(results), "engine": "firefox", "display": "wayland",
        "network": "managed-direct", "production_mutations": 0,
    })


if __name__ == "__main__":
    main()
