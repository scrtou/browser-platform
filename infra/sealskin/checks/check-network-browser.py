#!/usr/bin/env python3
"""Verify a guarded browser path using private DNS and packet observations."""

import argparse
import base64
import importlib.util
import json
import os
import shlex
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="new evidence directory; default retains the legacy ROOT.parent paths")
    args = parser.parse_args()
    qa = args.root.resolve()
    output = args.output.resolve() if args.output else qa.parent
    if args.output:
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
    project = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "checks", project / "infra/sealskin/lifecycle/check-network-live.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    checks = mod.Checks(qa)
    info = json.loads((qa / "browser-worker.json").read_text())
    engine = info.get("native_engine", info.get("engine", "firefox"))
    upstream_protocol = info.get("upstream_protocol", "socks5")
    upstream_auth = info.get("upstream_auth", "username_password")
    upstream_event = {"socks5": "socks", "http": "http_connect", "https": "https_connect"}[upstream_protocol]
    worker = info["instance_id"]
    status, snapshot = checks.client.call("GET", "/api/profile-runtime/" + info["home"])
    assert status == 200 and snapshot["workers"][0]["instance_id"] == worker
    resources = {item["kind"]: item["id"] for item in snapshot["resources"]}
    guard, relay = resources["guard"], resources["relay"]
    internal = json.loads(
        mod.docker("network", "inspect", resources["internal"]).stdout
    )[0]
    network_name = internal["Name"]
    guard_info = json.loads(mod.docker("inspect", guard).stdout)[0]
    worker_ip = guard_info["NetworkSettings"]["Networks"][network_name]["IPAddress"]
    relay_info = json.loads(mod.docker("inspect", relay).stdout)[0]
    relay_ip = relay_info["NetworkSettings"]["Networks"][network_name]["IPAddress"]
    controller = json.loads(mod.docker("inspect", "sealskin-network-qa").stdout)[0]
    controller_ip = controller["NetworkSettings"]["Networks"][network_name]["IPAddress"]
    observer = qa.parent / "observer"
    results = []
    desktop = None
    if info.get("native_engine"):
        native_spec=importlib.util.spec_from_file_location("native_network",Path(__file__).with_name("native-network-client.py"))
        native_module=importlib.util.module_from_spec(native_spec);native_spec.loader.exec_module(native_module)
        desktop=native_module.NativeDesktop(worker,info["native_engine"])
    elif engine == "camoufox":
        desktop_spec = importlib.util.spec_from_file_location("qa_desktop", Path(__file__).with_name("qa-desktop.py"))
        desktop_module = importlib.util.module_from_spec(desktop_spec)
        desktop_spec.loader.exec_module(desktop_module)
        desktop = desktop_module.Desktop(worker)

    def passed(name, **details):
        value = dict(check=name, result="PASS", engine=engine, upstream_protocol=upstream_protocol,
                     upstream_auth=upstream_auth, **details)
        results.append(value)
        mod.write_json(output / "browser-network-results.json", results)
        print(json.dumps(value), flush=True)

    def events():
        return [
            json.loads(line)
            for line in (observer / "events.jsonl").read_text().splitlines()
        ]

    def browser_identity():
        source = """import json
from pathlib import Path
out=[]
for p in Path('/proc').glob('[0-9]*'):
 try:
  args=p.joinpath('cmdline').read_bytes().split(b'\\0')
  if ((b'--remote-debugging-port' in args and b'9228' in args) or
      (args[0].endswith(b'/camoufox') and b'--profile' in args)):
   out.append([int(p.name),p.joinpath('stat').read_text().split()[21]])
 except (OSError,IndexError):pass
assert len(out)==1
print(json.dumps(out))
"""
        if info.get("native_engine"):
            source=native_module.process_identity_source(info["native_engine"])
        return json.loads(mod.docker("exec", worker, "python3", "-c", source).stdout)

    def evaluate(expression, navigate=False):
        if desktop:
            if navigate:
                desktop.navigate("https://entry.leak.qa.test/test")
            return desktop.evaluate(expression)
        source = (
            (project / "infra/firefox-proxy/check-bidi.py")
            .read_text()
            .split("\ndef main()", 1)[0]
        )
        source += '\nb=BiDi(WebSocket("127.0.0.1",9228))\nb.command("session.new",{"capabilities":{}})\ntry:\n c=b.command("browsingContext.getTree",{})["contexts"][0]["context"]\n'
        if navigate:
            source += ' b.command("browsingContext.navigate",{"context":c,"url":"https://entry.leak.qa.test/test","wait":"complete"})\n'
        source += (
            ' print(json.dumps({"value":b.evaluate(c,'
            + repr(expression)
            + ')}))\nfinally:\n b.command("session.end",{})\n b.websocket.socket.close()\n'
        )
        return json.loads(mod.docker("exec", worker, "python3", "-c", source).stdout)[
            "value"
        ]

    def drop_counters(container):
        value = json.loads(
            mod.docker(
                "exec", container, "nft", "-j", "list", "table", "inet", "bp_guard"
            ).stdout
        )
        total = 0
        for item in value["nftables"]:
            rule = item.get("rule", {})
            expr = rule.get("expr", [])
            if rule.get("chain") == "output" and any("drop" in e for e in expr):
                total += sum(e.get("counter", {}).get("packets", 0) for e in expr)
        return total

    def raw_probes(container, targets):
        # Every packet is a test nonce or protocol handshake, never user content.
        source = """import socket,struct,json,ssl,base64,os
targets=TARGETS
out=[]
name="bypass-"+os.urandom(16).hex()+".leak.qa.test"
query=struct.pack("!HHHHHH",1234,256,1,0,0,0)+b"".join(bytes([len(x)])+x.encode() for x in name.split("."))+b"\\0"+struct.pack("!HH",1,1)
for label,address,port,transport in targets:
 family=socket.AF_INET6 if ":" in address else socket.AF_INET
 kind=socket.SOCK_DGRAM if transport=="udp" else socket.SOCK_STREAM
 with socket.socket(family,kind) as s:
  s.settimeout(.35)
  try:
   s.connect((address,port))
   if transport=="udp":
    payload=query if port==53 else b"\\0\\1\\0\\0\\x21\\x12\\xa4\\x42"+os.urandom(12) if port==3478 else b"\\xc3\\0\\0\\0\\1\\x08"+os.urandom(1194)
    s.send(payload);s.recv(4096)
   reachable=True
  except OSError:reachable=False
  out.append({"target":label,"reachable":reachable})
print(json.dumps({"queries":name,"results":out}))
""".replace("TARGETS", repr(targets))
        return json.loads(mod.docker("exec", container, "python3", "-c", source).stdout)

    # Positive controls establish that every observation endpoint is listening.
    ca = (observer / "ca.pem").read_text()
    positive = """import socket,struct,json,ssl,os
host=HOST
ca=CA
name="control-"+os.urandom(16).hex()+".leak.qa.test"
query=struct.pack("!HHHHHH",1234,256,1,0,0,0)+b"".join(bytes([len(x)])+x.encode() for x in name.split("."))+b"\\0"+struct.pack("!HH",1,1)
out={}
for port,kind in [(53,"udp"),(53,"tcp"),(853,"dot"),(443,"https"),(3478,"stun"),(443,"quic")]:
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM if kind in ["udp","stun","quic"] else socket.SOCK_STREAM);s.settimeout(3);s.connect((host,port))
 if kind in ["dot","https"]:s=ssl.create_default_context(cadata=ca).wrap_socket(s,server_hostname="control.leak.qa.test")
 if kind in ["udp","tcp","dot"]:
  s.sendall(query if kind=="udp" else struct.pack("!H",len(query))+query);data=s.recv(4096);data=data if kind=="udp" else data[2:];out[kind]=bool(int.from_bytes(data[2:4],"big") & 1024)
 elif kind=="https":s.sendall(b"GET /ping HTTP/1.1\\r\\nHost: control.leak.qa.test\\r\\nConnection: close\\r\\n\\r\\n");out[kind]=b"200" in s.recv(4096).split(b"\\r\\n",1)[0]
 elif kind=="stun":s.sendall(b"\\0\\1\\0\\0\\x21\\x12\\xa4\\x42"+os.urandom(12));out[kind]=s.recv(4096)[:2]==b"\\1\\1"
 else:s.sendall(b"\\xc3\\0\\0\\0\\1\\x08"+os.urandom(1194));out[kind]=s.recv(4096)==b"qa-udp-received"
 s.close()
print(json.dumps(out))
""".replace("HOST", repr(info["observer_ip"])).replace("CA", repr(ca))
    positive_result = json.loads(
        mod.docker("exec", "sealskin-network-qa", "python3", "-c", positive).stdout
    )
    assert all(positive_result.values())
    passed(
        "DNS UDP/TCP, DoT, HTTPS, STUN and UDP443 listeners pass independent positive controls",
        **positive_result,
    )

    capture_path = output / "browser-wire.jsonl"
    capture_log = capture_path.open("w")
    os.fchmod(capture_log.fileno(), 0o600)
    capture_args = [
        "docker",
        "run",
        "--rm",
        "--name",
        "network-qa-wire",
        "--label",
        "io.browser-platform.qa=network-20260913",
        "--network",
        "container:" + guard,
        "--cap-drop",
        "ALL",
        "--cap-add",
        "NET_RAW",
        "--read-only",
        "--memory",
        "64m",
        "--pids-limit",
        "16",
        "--security-opt",
        "no-new-privileges:true",
        "-v",
        str(Path(__file__).with_name("network-wire.py")) + ":/run/network-wire.py:ro",
        "--entrypoint",
        "python3",
        json.loads((qa / "images.json").read_text())["probe"],
        "/run/network-wire.py",
        "--worker-ip",
        worker_ip,
        "--seconds",
        "300",
    ]
    original = checks.identity(worker)
    original_browser = browser_identity()
    capture = subprocess.Popen(
        ["sg", "docker", "-c", shlex.join(capture_args)],
        stdout=capture_log,
        stderr=subprocess.STDOUT,
    )
    mod.wait(
        lambda: "wire_capture_ready" in capture_path.read_text(),
        "outbound metadata observer",
    )
    try:
        start = len(events())
        initial = json.loads(evaluate("qa.run()", navigate=True))
        nonce = evaluate("qa.nonce")
        assert (
            initial["fetch"]
            and initial["aaaa"]
            and initial["websocket"]
            and initial["webrtc"] == ("function" if info.get("native_engine")=="chromix" else "undefined")
        )
        if info.get("native_engine")=="chromix":
            mod.write_json(output / "webrtc-candidates.json", desktop.assert_webrtc_confined())
        environment = json.loads(
            evaluate(
                "JSON.stringify({locale:navigator.language,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,screen:screen.width+'x'+screen.height,dpr:devicePixelRatio})"
            )
        )
        assert environment == info.get("expected_environment", dict(
            locale="zh-TW", timezone="Asia/Taipei", screen="1920x1080", dpr=1
        ))
        selected = [
            e
            for e in events()[start:]
            if nonce in e.get("name", "") or nonce in e.get("target", "")
        ]
        for label in ("fetch", "aaaa", "ws", "h3"):
            domain = label + "-" + nonce + ".leak.qa.test"
            assert any(
                e["event"] == upstream_event and e["target"] == domain and e["atyp"] == 3
                and e.get("auth") == upstream_auth
                for e in selected
            )
            assert any(
                e["event"] == "dns"
                and e["name"] == domain
                and e["source"] == "127.0.0.1"
                for e in selected
            )
        assert any(
            e["event"] == "dns"
            and e.get("qtype") == 28
            and e["name"].startswith("aaaa-")
            for e in selected
        )
        passed(
            "browser HTTPS/WebSocket and AAAA-only hostname use the selected upstream protocol and authoritative DNS",
            environment=environment,
        )

        query_name = "doh-query-" + nonce + ".leak.qa.test"
        wire = (
            b"\x04\xd2\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
            + b"".join(bytes([len(x)]) + x.encode() for x in query_name.split("."))
            + b"\0\0\x01\0\x01"
        )
        url = (
            "https://doh-"
            + nonce
            + ".leak.qa.test/dns-query?dns="
            + base64.urlsafe_b64encode(wire).decode().rstrip("=")
        )
        assert evaluate(
            "(async()=>{const r=await fetch("
            + json.dumps(url)
            + ");const b=new Uint8Array(await r.arrayBuffer());return r.ok && !!(b[2]&4)})()"
        )
        assert any(
            e["event"] == "dns"
            and e.get("transport") == "doh"
            and e["name"] == query_name
            for e in events()
        )
        passed("page-initiated DoH remains inside the verified HTTPS proxy path")

        transport = evaluate(
            "(async()=>{try{const t=new WebTransport('https://h3-'+qa.nonce+'.leak.qa.test/');const result=await Promise.race([t.ready.then(()=>true,()=>false),new Promise(r=>setTimeout(()=>r(false),3000))]);t.close();return result}catch(_){return false}})()"
        )
        literal = evaluate(
            "(async()=>{try{await fetch('https://[2606:4700:4700::1111]/',{signal:AbortSignal.timeout(2000)});return true}catch(_){return false}})()"
        )
        assert transport is False and literal is False
        assert not any(
            e["event"] in ("stun", "udp443") and e.get("source") == worker_ip
            for e in events()
        )
        passed(
            "WebRTC is unavailable; browser WebTransport and IPv6 literal requests do not establish a direct connection"
        )

        before = drop_counters(guard)
        targets = [
            ("controller-api", controller_ip, 8000, "tcp"),
            ("controller-session", controller_ip, 8443, "tcp"),
            ("host-ssh", internal["IPAM"]["Config"][0]["Gateway"], 22, "tcp"),
            ("metadata", "169.254.169.254", 80, "tcp"),
            ("public-ipv4", "1.1.1.1", 443, "tcp"),
            ("public-ipv6", "2606:4700:4700::1111", 443, "tcp"),
            ("docker-dns-udp", "127.0.0.11", 53, "udp"),
            ("docker-dns-tcp", "127.0.0.11", 53, "tcp"),
        ]
        targets += [
            (
                "observer-" + str(port) + "-" + protocol,
                info["observer_ip"],
                port,
                protocol,
            )
            for port, protocol in (
                (53, "udp"),
                (53, "tcp"),
                (853, "tcp"),
                (443, "tcp"),
                (443, "udp"),
                (3478, "udp"),
            )
        ]
        blocked = raw_probes(worker, targets)
        assert all(not item["reachable"] for item in blocked["results"])
        after = drop_counters(guard)
        assert after > before
        assert not any(e.get("name") == blocked["queries"] for e in events())
        passed(
            "Worker direct DNS/DoT/HTTPS/STUN/UDP443, Docker DNS, controller, host and metadata paths are blocked",
            targets=len(targets),
            dropped_packets=after - before,
        )

        relay_before = drop_counters(relay)
        relay_blocked = raw_probes(
            relay,
            [
                ("unapproved-https", info["observer_ip"], 443, "tcp"),
                ("dns", info["observer_ip"], 53, "udp"),
                ("controller", controller_ip, 8000, "tcp"),
                ("public", "1.1.1.1", 443, "tcp"),
            ],
        )
        assert all(not item["reachable"] for item in relay_blocked["results"])
        assert drop_counters(relay) > relay_before
        for container in (guard, relay):
            process = dict(
                line.split(":", 1)
                for line in mod.docker(
                    "exec", container, "cat", "/proc/1/status"
                ).stdout.splitlines()
            )
            assert all(
                int(process[key].strip(), 16) == 0
                for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
            )
        permission = mod.docker(
            "run",
            "--rm",
            "--network",
            "container:" + guard,
            "--cap-drop",
            "ALL",
            "--read-only",
            "--entrypoint",
            "nft",
            json.loads((qa / "images.json").read_text())["relay"],
            "--check",
            "flush",
            "table",
            "inet",
            "bp_guard",
            check=False,
        )
        assert (
            permission.returncode != 0
            and "Operation not permitted" in permission.stderr
        )
        passed(
            "Relay permits only its fixed upstream endpoint; unprivileged namespace users cannot change nftables"
        )

        for fault in ("offline", "bad-auth", "relay-stop"):
            # Close existing proxy keep-alives for authentication-failure testing.
            if fault == "bad-auth":
                mod.write_json(observer / "mode.json", {"mode": "offline"})
                time.sleep(0.5)
                mod.write_json(observer / "mode.json", {})
            evaluate("qa.startTraffic()")
            time.sleep(1)
            if fault == "relay-stop":
                mod.docker("stop", "-t", "2", relay)
            else:
                if fault == "bad-auth":
                    mod.write_json(observer / "mode.json", {"mode": "offline"})
                    time.sleep(0.5)
                mod.write_json(observer / "mode.json", {"mode": fault})
            boundary = time.time()
            time.sleep(7)
            state = json.loads(evaluate("qa.stopTraffic()"))
            assert any(not e["ok"] for e in state["background"])
            assert not any(
                e["ok"]
                for e in state["background"]
                if e["time"] / 1000 > boundary + 0.5
            )
            assert not state["download"]["complete"] and state["download"]["failed"]
            assert original == checks.identity(worker)
            assert original_browser == browser_identity()
            if fault == "relay-stop":
                mod.docker("start", relay)
            mod.write_json(observer / "mode.json", {})
            mod.wait(
                lambda: evaluate("fetchCheck('recovery').catch(()=>false)"),
                "browser proxy recovery",
                seconds=25,
            )
            passed(
                "browser background requests and streaming download fail closed during "
                + fault,
                worker_preserved=True,
            )

        if upstream_protocol == "https":
            for fault in ("wrong-name", "untrusted"):
                # Close existing tunnels so each attempt must validate TLS again.
                mod.write_json(observer / "mode.json", {"mode": "offline"})
                time.sleep(0.5)
                mod.write_json(observer / "proxy-tls-mode.json", {"mode": fault})
                mod.write_json(observer / "mode.json", {})
                start = len(events())
                assert not evaluate("fetchCheck(" + json.dumps("tls-" + fault) + ").catch(()=>false)")
                observed = events()[start:]
                assert any(e["event"] == "proxy_tls_attempt" and e["tls_mode"] == fault and e["expected_name"]
                           for e in observed)
                assert not any(e["event"] in {"http", "https"} and e.get("host", "").startswith("tls-" + fault + "-")
                               for e in observed)
                logs = mod.docker("logs", "--since", "20s", relay).stdout
                assert '"error_code":"UPSTREAM_TLS_INVALID"' in logs
                assert original == checks.identity(worker) and original_browser == browser_identity()
                mod.write_json(observer / "proxy-tls-mode.json", {})
                mod.wait(lambda: evaluate("fetchCheck(" + json.dumps("tls-recovery-" + fault) + ").catch(()=>false)"),
                         "browser TLS proxy recovery", seconds=25)
                passed("browser rejects HTTPS upstream " + fault + " certificate without direct fallback",
                       worker_preserved=True)

        checks.restart_controller()
        assert original == checks.identity(worker)
        assert original_browser == browser_identity()
        assert evaluate("fetchCheck('controller-restart')")
        passed(
            "SealSkin API restart preserves the real browser process and its guarded proxy path"
        )
    finally:
        mod.write_json(observer / "mode.json", {})
        mod.write_json(observer / "proxy-tls-mode.json", {})
        mod.docker("start", relay, check=False)
        mod.docker("stop", "-t", "2", "network-qa-wire", check=False)
        capture.wait(timeout=10)
        capture_log.close()
    wire = [
        json.loads(line)
        for line in capture_path.read_text().splitlines()
        if line.startswith("{")
    ]
    outgoing = next(value["outbound"] for value in wire if "outbound" in value)
    assert outgoing and any(
        item["destination"] == relay_ip and item["destination_port"] == 1080
        for item in outgoing
    )
    assert all(
        item["family"] == 4
        and item["protocol"] == 6
        and (
            item["destination"] == relay_ip
            and item["destination_port"] == 1080
            or item["destination"] == controller_ip
            and item["source_port"] == 3000
        )
        for item in outgoing
    )
    passed(
        "outbound packet metadata contains only Relay TCP and display replies; no direct DNS, UDP, STUN or IPv6",
        flows=len(outgoing),
    )
    assert original == checks.identity(worker)
    assert original_browser == browser_identity()


if __name__ == "__main__":
    main()
