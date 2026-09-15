#!/usr/bin/env python3
"""R2B real old-Firefox checks; only the explicitly named private QA roots.

Prepare the source with lifecycle/prepare-network-qa.py and the retained
lifecycle-v2 build. Use secure-backup.py for the encrypted offline transfer.
This observer does not operate on production Homes or implement activation.
"""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
import uuid


CHECKS = Path(__file__).resolve().parent
PROJECT = CHECKS.parents[2]
WORK = PROJECT / "infra/sealskin/runtime/r2b-legacy-browser-recovery-2026-09-15"
IMAGE = "sha256:7e3dbebd9e730952648b8c902ce90fa72c0e2be3e786ab17026c38e0909b47f7"
PROFILE, HOME, APP = "network-qa-legacy", "network-qa-home-legacy", "network-qa-app-legacy"
URL = "http://localhost:28998/"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


boot = module("r2b_boot", CHECKS / "check-boot-recovery.py")
network, docker = boot.mod, boot.docker


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def root_checked(path):
    root = path.resolve()
    require(root.name == "qa" and root.parent.parent == WORK
            and root.parent.name in {"source", "recovered"}, "EXACT_R2B_ROOT_REQUIRED")
    controller = json.loads(docker("inspect", network.SERVER).stdout)[0]
    require(controller["Config"]["Labels"].get("io.browser-platform.qa") == "network-20260913"
            and any(m.get("Source") == str(root / "config") and m["Destination"] == "/config"
                    for m in controller["Mounts"]), "QA_CONTROLLER_OWNERSHIP_REQUIRED")
    return root


def configure(root):
    require(root.parent.name == "source", "ONLY_FRESH_SOURCE_CAN_BE_CONFIGURED")
    app = json.loads((root / "app-a.json").read_text())
    app.update(id=APP, source_app_id=APP, name="R2B Legacy Firefox QA")
    provider = app["provider_config"]
    provider.pop("network_policy_id", None)
    provider.pop("network_policy_sha256", None)
    provider["image"] = IMAGE
    provider["docker_overrides"] = {"mem_limit": "1024m", "nano_cpus": 1500000000,
                                    "shm_size": "256m", "pids_limit": 512}
    script = ("#!/bin/sh\nexec firefox --no-remote --profile /config/r2b-profile "
              "--remote-debugging-port 9228 --new-window about:blank\n")
    for key in ("custom_autostart_script_b64", "custom_autostart_wayland_script_b64"):
        provider[key] = base64.b64encode(script.encode()).decode()
    allow = json.loads((root / "allow.json").read_text())
    require(docker("image", "inspect", IMAGE, "--format", "{{.Id}}").stdout.strip() == IMAGE,
            "OLD_FIREFOX_IMAGE_MISSING")
    allow["images"] = sorted(set(allow["images"] + [IMAGE]))
    network.write_json(root / "allow.json", allow)
    d = boot.Drill(root)
    require(d.admin_client().call("POST", "/api/admin/apps/installed", app)[0] == 201,
            "QA_APP_INSTALL_FAILED")
    require(d.checks.client.call("POST", "/api/homedirs", {"home_name": HOME})[0] == 201,
            "QA_HOME_CREATE_FAILED")
    (root / "storage/network-qa" / HOME / "r2b-profile").mkdir(mode=0o700)
    config = json.loads((root / "adapter-config.json").read_text())
    config["profiles"] = [{"id": PROFILE, "application_id": APP, "home_name": HOME,
                           "start_url": URL, "wayland_mode": True}]
    config["health"] = {"sample_interval_seconds": 0}
    network.write_json(root / "adapter-config.json", config)
    network.write_json(root / "legacy-app.json", app)
    return {"old_firefox_image": IMAGE, "wayland_requested": True,
            "network_policy": "legacy-unmanaged-QA-bridge", "production_mutations": 0}


def worker(d):
    snapshot = d.snapshot(HOME)
    require(len(snapshot["workers"]) == len(snapshot["records"]) == 1, "ONE_QA_WORKER_REQUIRED")
    # The Home bind, current scope and actual image are all checked before exec.
    identifiers = docker("ps", "-aq", "--filter", "label=io.browser-platform.scope=" +
                         hashlib.sha256(str(d.root / "config/.config/sealskin/sessions.yml").encode()).hexdigest()).stdout.split()
    values = json.loads(docker("inspect", *identifiers).stdout) if identifiers else []
    matches = [v for v in values if any(m.get("Source") == str(d.root / "storage/network-qa" / HOME)
                                       and m["Destination"] == "/config" for m in v["Mounts"])]
    require(len(matches) == 1 and matches[0]["Image"] == IMAGE and matches[0]["State"]["Running"],
            "QA_WORKER_IDENTITY_MISMATCH")
    return matches[0]


def bidi(instance, expression=None, close=False):
    source = (PROJECT / "infra/firefox-proxy/check-bidi.py").read_text().split("def main()", 1)[0]
    source += "\nb = BiDi(WebSocket('127.0.0.1', 9228))\nb.command('session.new', {'capabilities': {}})\n"
    if close:
        source += "b.command('browser.close', {})\nprint(json.dumps({'close_command_acknowledged':True}))\n"
    else:
        source += "c = b.command('browsingContext.getTree', {})['contexts'][0]['context']\n"
        source += "b.command('browsingContext.navigate', {'context':c, 'url':" + repr(URL) + ", 'wait':'complete'})\n"
        source += "print(b.evaluate(c, " + repr(expression) + "))\nb.command('session.end', {})\n"
    result = docker("exec", "--user", "abc", instance, "python3", "-c", source, check=False)
    require(result.returncode == 0, "QA_BIDI_COMMAND_FAILED: " + result.stderr[-300:])
    return json.loads(result.stdout)


READ = """async function readR2B() {
 const db = await new Promise((resolve,reject) => { const r=indexedDB.open('r2b-persist',1);
   r.onupgradeneeded=()=>r.result.createObjectStore('values'); r.onerror=()=>reject(r.error); r.onsuccess=()=>resolve(r.result); });
 const value = await new Promise((resolve,reject) => { const r=db.transaction('values').objectStore('values').get('nonce');
   r.onsuccess=()=>resolve(r.result); r.onerror=()=>reject(r.error); }); db.close();
 return {cookie:document.cookie.split('; ').find(x=>x.startsWith('r2b='))?.slice(4),
   localStorage:localStorage.getItem('r2b'), indexedDB:value,
   origin:location.origin, userAgent:navigator.userAgent};
} """


def sample(root, write=False):
    d = boot.Drill(root)
    if not d.qa_adapter_pids():
        d.start_adapter()
    d.launch(PROFILE, HOME)
    value = worker(d)
    instance = value["Id"]
    d.wait_bidi(instance)
    server = """from http.server import BaseHTTPRequestHandler,HTTPServer
class H(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def do_GET(self):
  page=b'<!doctype html><title>R2B local storage QA</title><p>Private recovery fixture</p>'
  self.send_response(200); self.send_header('Content-Type','text/html'); self.send_header('Content-Length',str(len(page)))
  self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(page)
HTTPServer(('127.0.0.1',28998),H).serve_forever()
"""
    probe = "import socket; s=socket.socket(); print(s.connect_ex(('127.0.0.1',28998)))"
    if docker("exec", instance, "python3", "-c", probe).stdout.strip() != "0":
        docker("exec", "-d", "--user", "abc", instance, "python3", "-c", server)
        network.wait(lambda: docker("exec", instance, "python3", "-c", probe).stdout.strip() == "0", "local QA page")
    if write:
        require(root.parent.name == "source" and not (WORK / "nonce.json").exists(), "FRESH_SOURCE_WRITE_REQUIRED")
        nonce = uuid.uuid4().hex
        network.write_json(WORK / "nonce.json", {"nonce": nonce})
        statement = """const nonce=NONCE; document.cookie='r2b='+nonce+'; Max-Age=604800; SameSite=Strict; Path=/';
localStorage.setItem('r2b',nonce);
const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('r2b-persist',1);
r.onupgradeneeded=()=>r.result.createObjectStore('values');r.onerror=()=>reject(r.error);r.onsuccess=()=>resolve(r.result);});
await new Promise((resolve,reject)=>{const tx=db.transaction('values','readwrite');
tx.objectStore('values').put(nonce,'nonce');tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error);});db.close();
""".replace("NONCE", json.dumps(nonce))
    else:
        nonce = json.loads((WORK / "nonce.json").read_text())["nonce"]
        statement = ""
    observed = bidi(instance, "(async()=>{" + READ + statement + "return JSON.stringify(await readR2B());})()")
    require(all(observed.get(k) == nonce for k in ("cookie", "localStorage", "indexedDB")), "THREE_STORES_MISMATCH")
    process = docker("exec", "--user", "abc", instance, "python3", "-c", """import json
from pathlib import Path
out=[]
for p in Path('/proc').glob('[0-9]*'):
 try:
  args=p.joinpath('cmdline').read_bytes().split(b'\\0')
  if b'--remote-debugging-port' in args and b'9228' in args:
   e=dict(x.split(b'=',1) for x in p.joinpath('environ').read_bytes().split(b'\\0') if b'=' in x)
   out.append({'pid':int(p.name),'wayland_display':e.get(b'WAYLAND_DISPLAY',b'').decode(),
     'moz_enable_wayland':e.get(b'MOZ_ENABLE_WAYLAND',b'').decode()})
 except OSError: pass
print(json.dumps(out))
""").stdout
    processes = json.loads(process)
    require(len(processes) == 1 and processes[0]["wayland_display"], "WAYLAND_BROWSER_REQUIRED")
    network.write_json(root / "browser-observed-private.json", observed)
    network.write_json(root / "browser-identity.json", {"worker_id": instance, "image_id": value["Image"],
                       "started_at": value["State"]["StartedAt"], "auto_remove": value["HostConfig"]["AutoRemove"],
                       "processes": processes})
    return {"three_stores_match": True, "browser": observed["userAgent"], "wayland_process": True,
            "worker_id": instance, "image_id": value["Image"], "mode": "write" if write else "read"}


def close(root):
    d = boot.Drill(root)
    value = worker(d)
    before = d.firefox_pid(value["Id"])
    require(len(before) == 1, "ONE_FIREFOX_PROCESS_REQUIRED")
    started = time.monotonic()
    acknowledgement = bidi(value["Id"], close=True)
    network.wait(lambda: not d.firefox_pid(value["Id"]), "normal Firefox close", seconds=30)
    require(docker("inspect", value["Id"], "--format", "{{.State.Running}}").stdout.strip() == "true",
            "WORKER_MUST_SURVIVE_NORMAL_BROWSER_CLOSE")
    status, response = d.control(PROFILE, "stop")
    network.write_json(root / "stop-private.json", response)
    require(status == 200 and all(not d.snapshot(HOME)[k] for k in ("records", "workers", "resources")),
            "LIFECYCLE_STOP_INCOMPLETE")
    return {**acknowledgement, "browser_exited_before_container_stop": True,
            "elapsed_seconds": round(time.monotonic()-started, 3), "lifecycle_inventory_empty": True,
            "shutdown_scope": "explicit-BiDi-close-then-legacy-lifecycle-stop"}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("action", choices=("configure", "write", "read", "close"))
    args = parser.parse_args()
    root = root_checked(args.root)
    output = args.output.resolve()
    require(output.is_relative_to(WORK) and not output.exists(), "FRESH_PRIVATE_EVIDENCE_REQUIRED")
    result = configure(root) if args.action == "configure" else close(root) if args.action == "close" else sample(root, args.action == "write")
    result.update(status="pass", action=args.action)
    network.write_json(output, result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
