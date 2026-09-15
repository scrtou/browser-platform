#!/usr/bin/env python3
"""Observe persistent browser WebSockets and an actual failed navigation.

Only the named public-DNS QA Worker is used. The local observation page is
opened through the normal address bar; no browser debugging port is enabled.
Network and remote endpoint evidence must be correlated separately.
"""

import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import time
import uuid

spec = importlib.util.spec_from_file_location("public_browser", Path(__file__).with_name("check-public-dns-browser.py"))
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)
network, require = browser.network, browser.require


def clipboard(worker):
    result = network.docker("exec", "--user", "1000", "-e", "DISPLAY=:1", worker,
                            "xclip", "-selection", "clipboard", "-t", "UTF8_STRING", "-o", check=False)
    return result.stdout if result.returncode == 0 else ""


def navigate(control, worker, url):
    network.wait(lambda: bool(control.available_title()), "QA browser window", seconds=60)
    for _ in range(3):
        control.key("ctrl+l")
        control.key("ctrl+a")
        control.type(url)
        control.key("ctrl+a")
        control.key("ctrl+c")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if clipboard(worker) == url:
                control.key("Return")
                return
            time.sleep(.1)
    raise ValueError("QA address bar mismatch")


def body(control, worker):
    window = control.run("xdotool", "getactivewindow").strip()
    control.run("xdotool", "mousemove", "--window", window, "450", "300", "click", "1")
    control.key("ctrl+a")
    control.key("ctrl+c")
    time.sleep(.15)
    return clipboard(worker)


def observe(run, role, output, expected):
    entry = run.state["roles"][role]
    run.owned(role, entry["worker"])
    worker = entry["worker"]
    state = json.loads((run.qa / "public-fault-state.json").read_text())[role]
    control = browser.desktop.Desktop(worker)
    require(state["worker"] == worker, "Fault observation belongs to another Worker")
    deadline = time.monotonic() + 25
    value = None
    while time.monotonic() < deadline:
        if control.available_title().startswith("R5C2 fault "):
            try:
                candidate = json.loads(body(control, worker))
                if candidate.get("nonce") == state["nonce"]:
                    value = candidate
                    if all(value[kind].get("state") == expected and value[kind].get("echo", {}).get("nonce") == state["nonce"]
                           and value[kind]["echo"].get("endpoint") == state["endpoint"] for kind in ("ws", "wss")):
                        break
            except (ValueError, AttributeError, KeyError):
                pass
        time.sleep(.25)
    record = {"role": role, "nonce": state["nonce"], "expected": expected, "observed": value,
              "recorded_at": time.time(), "title": control.available_title(), "plan_sha256": run.state["plan_sha256"]}
    network.write_json(output / (role + "-fault-browser.json"), record)
    browser.screenshot(control, worker, output, role + "-fault-browser")
    require(value is not None and all(value[kind].get("state") == expected and
            value[kind].get("echo", {}).get("nonce") == state["nonce"] and
            value[kind]["echo"].get("endpoint") == state["endpoint"] for kind in ("ws", "wss")),
            "Persistent browser socket observation failed")
    return {"result": "SOCKETS_" + expected, "role": role, "nonce": state["nonce"], "transports": ["ws", "wss"]}


def open_sockets(run, role, output, endpoint):
    entry = run.state["roles"][role]
    run.owned(role, entry["worker"])
    worker = entry["worker"]
    state_path = run.qa / "public-fault-state.json"
    states = json.loads(state_path.read_text()) if state_path.exists() else {}
    require(role not in states, "Refusing to replace an existing socket observation")
    nonce = uuid.uuid4().hex
    ports = run.state["endpoint_config"]["ports"]
    plan = {"nonce": nonce, "urls": {kind: f"{kind}://{entry['website']}:{ports[port]}/ws?nonce={nonce}"
                                   for kind, port in (("ws", "http"), ("wss", "https"))}}
    page = ("<!doctype html><meta charset=utf-8><title>R5C2 fault starting</title>"
            "<pre id=result>Starting</pre><script>const p=" + json.dumps(plan) + ";"
            "const result={nonce:p.nonce,ws:{state:'STARTING'},wss:{state:'STARTING'}};"
            "function draw(){document.getElementById('result').textContent=JSON.stringify(result,null,2);"
            "document.title='R5C2 fault '+result.ws.state+'/'+result.wss.state;}"
            "for(const [kind,url] of Object.entries(p.urls)){const row=result[kind],w=new WebSocket(url);let timer;"
            "row.url=url;w.onopen=()=>{row.opened_at=Date.now();w.send(p.nonce);"
            "timer=setInterval(()=>{if(w.readyState===WebSocket.OPEN)w.send(p.nonce)},4000);};"
            "w.onmessage=e=>{try{row.echo=JSON.parse(e.data);row.state='OPEN';row.last_echo_at=Date.now()}"
            "catch(e){row.state='INVALID'}draw()};"
            "w.onerror=()=>{row.error_at=Date.now();draw()};"
            "w.onclose=e=>{clearInterval(timer);row.state='CLOSED';row.closed_at=Date.now();row.close_code=e.code;draw()};}draw();"
            "</script>")
    remote = "/tmp/browser-platform-public-fault-" + nonce + ".html"
    source = "import base64,pathlib; p=pathlib.Path(" + repr(remote) + ");assert not p.exists();p.write_bytes(base64.b64decode(" + repr(base64.b64encode(page.encode()).decode()) + "));p.chmod(0o600)"
    network.docker("exec", "--user", "1000", worker, "python3", "-c", source)
    states[role] = {"nonce": nonce, "worker": worker, "endpoint": endpoint, "remote_page": remote, "created_at": time.time()}
    network.write_json(state_path, states)
    (output / (role + "-fault.html")).write_text(page)
    navigate(browser.desktop.Desktop(worker), worker, "file://" + remote)
    return observe(run, role, output, "OPEN")


def blocked_page(run, role, output):
    entry = run.state["roles"][role]
    run.owned(role, entry["worker"])
    worker = entry["worker"]
    control = browser.desktop.Desktop(worker)
    nonce = uuid.uuid4().hex
    url = f"http://{entry['website']}:{run.state['endpoint_config']['ports']['http']}/test?nonce={nonce}"
    started = time.time()
    navigate(control, worker, url)
    patterns = ("proxy server is refusing connections", "unable to connect", "connection was reset", "server not found",
                "代理伺服器拒絕連線", "無法連線", "找不到伺服器", "連線被重設")
    deadline = time.monotonic() + 30
    text = ""
    while time.monotonic() < deadline:
        text = body(control, worker)
        if any(pattern in text.lower() for pattern in patterns) and not control.available_title().startswith("R5C2 "):
            break
        time.sleep(.3)
    control.key("ctrl+l")
    control.key("ctrl+c")
    time.sleep(.2)
    address = clipboard(worker)
    record = {"role": role, "url": url, "nonce": nonce, "observed_address": address, "body": text,
              "title": control.available_title(), "started_at": started, "recorded_at": time.time(),
              "plan_sha256": run.state["plan_sha256"]}
    network.write_json(output / (role + "-blocked-page.json"), record)
    browser.screenshot(control, worker, output, role + "-blocked-page")
    require(address == url and any(pattern in text.lower() for pattern in patterns) and
            not control.available_title().startswith("R5C2 "), "Expected a browser connection error for the unique URL")
    return {"result": "BROWSER_CONNECTION_FAILED", "role": role, "nonce": nonce}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("open", "still-open", "closed", "blocked-page"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--role", choices=("direct", "proxy"), required=True)
    parser.add_argument("--endpoint", choices=("before", "after"), default="after")
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    run = browser.PublicBrowsers(args.root)
    try:
        if args.action == "open":
            result = open_sockets(run, args.role, args.output, args.endpoint)
        elif args.action == "blocked-page":
            result = blocked_page(run, args.role, args.output)
        else:
            result = observe(run, args.role, args.output, "CLOSED" if args.action == "closed" else "OPEN")
        network.write_json(args.output / "result.json", result)
        print(json.dumps(result))
    except Exception as exc:
        network.write_json(args.output / "failure.json", {"error_type": type(exc).__name__, "error": str(exc)})
        raise


if __name__ == "__main__":
    main()
