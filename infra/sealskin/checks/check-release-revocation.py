#!/usr/bin/env python3
"""Bounded Store revocation checks on a Coordinator-validated R5E Worker."""

import base64
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import time
import uuid


def run(coordinator, network, desktop, profile):
    c = coordinator
    worker, binding, _ = c.worker(profile)
    journal = c.network_journal(profile)
    relay, guard = journal["allocation"]["relay_id"], journal["allocation"]["guard_id"]
    assert journal["policy"]["mode"] == "proxy_required"
    before = c.report(profile, True)
    control = desktop.Desktop(worker["Id"])
    nonce = uuid.uuid4().hex
    plan = {"nonce": nonce, "urls": {kind: f"{kind}://{c.endpoint['website_names'][0]}:{c.endpoint['ports'][port]}/ws?nonce={nonce}"
                                      for kind, port in (("ws", "http"), ("wss", "https"))}}
    fixture = """<!doctype html><meta charset=utf-8><title>Browser Platform Client QA Revocation Ready</title>
<p>Temporary revocation fixture. Click to require confirmation before closing.</p><textarea id="report"></textarea>
<script>const plan=PLAN;
const result={nonce:plan.nonce,hold:false,ws:{state:'CONNECTING'},wss:{state:'CONNECTING'}};
document.addEventListener('click',()=>{result.hold=true;window.onbeforeunload=e=>{e.preventDefault();e.returnValue='';}},{once:true});
for(const [kind,url] of Object.entries(plan.urls)){
 const row=result[kind],ws=new WebSocket(url);let timer;
 ws.onopen=()=>{row.opened=Date.now();ws.send(plan.nonce);timer=setInterval(()=>{if(ws.readyState===1)ws.send(plan.nonce)},1000)};
 ws.onmessage=e=>{row.echo=JSON.parse(e.data);row.state='OPEN'};
 ws.onclose=e=>{clearInterval(timer);row.state='CLOSED';row.closed=Date.now();row.code=e.code};
 ws.onerror=()=>{row.error=Date.now()};
}
window.addEventListener('keydown',e=>{
 if(e.key==='F8'){e.preventDefault();window.onbeforeunload=null;result.hold=false;}
 if(e.key==='F9'){e.preventDefault();const t=document.querySelector('#report');t.value='BP_R5E_REVOKE:'+JSON.stringify(result);t.focus();t.select();document.execCommand('copy');}
});</script>""".replace("PLAN", json.dumps(plan))
    remote = "/tmp/browser-platform-r5e-revocation-" + nonce + ".html"
    write = ("import pathlib,base64; p=pathlib.Path(" + repr(remote) + ");assert not p.exists();"
             "p.write_bytes(base64.b64decode(" + repr(base64.b64encode(fixture.encode()).decode()) + "));p.chmod(0o600)")
    network.docker("exec", "--user", "1000", worker["Id"], "python3", "-c", write)
    capture = "bp-r5e-revoke-wire-" + nonce[:12]
    image = json.loads((c.qa / "images.json").read_text())["probe"]
    capture_id = network.docker("run", "-d", "--name", capture, "--label", "io.browser-platform.qa=r5e-revocation-wire",
        "--network", "container:" + guard, "--read-only", "--cap-drop", "ALL", "--cap-add", "NET_RAW",
        "--security-opt", "no-new-privileges:true", "--memory", "64m", "--pids-limit", "32", "--entrypoint", "python3",
        "--mount", "type=bind,src=" + str(Path(__file__).with_name("network-wire.py")) + ",dst=/wire.py,readonly",
        image, "-B", "/wire.py", "--worker-ip", journal["allocation"]["guard_ip"], "--seconds", "180").stdout.strip()
    c.record("revocation-wire-resource", json.loads(network.docker("inspect", capture_id).stdout)[0])
    network.wait(lambda: '"wire_capture_ready": true' in network.docker("logs", capture_id).stdout,
                 "R5E revocation network metadata", seconds=10)
    spec = importlib.util.spec_from_file_location("r5e_fault_desktop", Path(__file__).with_name("check-public-dns-fault.py"))
    fault = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fault)

    def observe(expected):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            control.key("F9")
            selection = network.docker("exec", "--user", "1000", "-e", "DISPLAY=:1", worker["Id"],
                                       "xclip", "-selection", "clipboard", "-o", check=False)
            if selection.returncode == 0 and selection.stdout.startswith("BP_R5E_REVOKE:"):
                value = json.loads(selection.stdout.removeprefix("BP_R5E_REVOKE:"))
                if value["nonce"] == nonce and all(value[kind]["state"] == expected and
                        value[kind].get("echo", {}).get("nonce") == nonce for kind in ("ws", "wss")):
                    c.record("revocation-browser-" + expected.lower(), value)
                    return value
            time.sleep(.25)
        raise RuntimeError("QA_REVOCATION_BROWSER_REPORT_TIMEOUT")

    capture_removed = False
    try:
        control.navigate("file://" + remote)
        window = control.run("xdotool", "getactivewindow").strip()
        control.run("xdotool", "mousemove", "--window", window, "350", "250", "click", "1")
        opened = observe("OPEN")
        assert opened["hold"]
        request = {"secret_ref": journal["policy"]["password_secret_ref"], "operation_id": uuid.uuid4().hex}
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(c.admin.call, "POST", "/api/admin/profile-secrets/revoke", request)
            network.wait(lambda: not json.loads(network.docker("inspect", relay).stdout)[0]["State"]["Running"],
                         "R5E revoked Relay exit", seconds=8)
            blocked_after = time.monotonic() - started
            status, result = pending.result(timeout=35)
        c.record("revocation-first-response", {"status": status, "result": result, "blocked_after_seconds": blocked_after})
        assert status == 503 and result["detail"] == "SECRET_REVOKED_CLEANUP_PENDING"
        assert c.worker(profile)[0]["Id"] == worker["Id"] and c.worker(profile)[0]["State"]["Running"]
        control.key("Escape")
        closed = observe("CLOSED")
        control.key("F8")
        failed_nonce = uuid.uuid4().hex
        url = c.website_origin + "/client?nonce=" + failed_nonce
        fault.navigate(control, worker["Id"], url)
        patterns = ("proxy server is refusing connections", "unable to connect", "connection was reset", "server not found",
                    "代理伺服器拒絕連線", "無法連線", "找不到伺服器", "連線被重設")
        # A stopped Relay leaves a filtered TCP destination. The browser can
        # retain the previous document while its normal connection timeout
        # runs; do not mistake that document for the eventual error page.
        navigation_started = time.monotonic()
        deadline = navigation_started + 90
        text = ""
        while time.monotonic() < deadline:
            text = fault.body(control, worker["Id"])
            if any(pattern in text.lower() for pattern in patterns):
                break
            time.sleep(.3)
        control.key("ctrl+l")
        control.key("ctrl+c")
        time.sleep(.2)
        address = fault.clipboard(worker["Id"])
        c.record("revoked-browser-request", {"url": url, "observed_address": address, "nonce": failed_nonce,
                                             "body": text, "title": control.available_title(),
                                             "navigation_seconds": time.monotonic() - navigation_started})
        assert address == url and any(pattern in text.lower() for pattern in patterns)
        targets = [(ip, port) for ip in c.endpoint["peer_ipv4"] for port in (18080, 18443)] + [("23.19.231.152", 53)]
        probe = """import socket,json,sys
rows=[]
for address,port in json.loads(sys.argv[1]):
 s=socket.socket();s.settimeout(.7)
 try:s.connect((address,port));row={'address':address,'port':port,'connected':True}
 except OSError as e:row={'address':address,'port':port,'connected':False,'errno':e.errno}
 finally:s.close()
 rows.append(row)
print(json.dumps(rows))
"""
        probes = json.loads(network.docker("exec", "--user", "1000", worker["Id"], "python3", "-c", probe, json.dumps(targets)).stdout)
        assert all(not row["connected"] for row in probes)
        c.record("revoked-native-bypass-probes", probes)
        network.docker("stop", "-t", "5", capture_id)
        raw = network.docker("logs", capture_id).stdout
        (c.output / "revocation-wire.log").write_text(raw)
        wire = json.loads(raw.splitlines()[-1])
        assert wire["outbound"] and any(p["destination"] == journal["allocation"]["relay_ip"] and
                                       p["destination_port"] == 1080 for p in wire["outbound"])
        assert not any(p["family"] == 6 or p["destination"] in c.endpoint["peer_ipv4"] + ["23.19.231.152"] for p in wire["outbound"])
        network.docker("rm", "-v", capture_id)
        capture_removed = True
        status, result = c.admin.call("POST", "/api/admin/profile-secrets/revoke", request)
        c.record("revocation-retry-response", {"status": status, "result": result})
        assert status == 200 and result["cleanup_complete"] and result["egress_blocked"]
        c.stop_profile(profile)
        assert not any(c.inventory(profile)[k] for k in ("records", "workers", "resources"))
        return c.record("revocation-result", {"revoked": True, "relay_exit_seconds": blocked_after,
            "browser_ws_and_wss_closed": True, "new_browser_request_failed": True, "native_bypass_failures": len(probes),
            "worker_wire_has_no_direct_fallback": True, "normal_cleanup_retry": True, "home_preserved": True,
            "failed_request_nonce": failed_nonce, "previous_report_nonce": before["nonce"]})
    finally:
        if not capture_removed:
            network.docker("stop", "-t", "5", capture_id, check=False)
            logs = network.docker("logs", capture_id, check=False)
            (c.output / "revocation-wire-failure.log").write_text(logs.stdout)
            network.docker("rm", "-v", capture_id, check=False)
        current = network.docker("inspect", worker["Id"], check=False)
        if current.returncode == 0 and json.loads(current.stdout)[0]["State"]["Running"]:
            # Cancel only this QA page's deliberately armed close confirmation.
            control.key("Escape")
            control.key("F8")
