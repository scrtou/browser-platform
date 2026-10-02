#!/usr/bin/env python3
"""Exercise managed DIRECT in two isolated, normally launched Camoufox Homes.

Requires prepare-network-qa.py --direct-host-evidence and the r6 Camoufox
prepare-network-browser.py fixture. All state and detailed evidence are private.
The public-address website fixture is routed only inside QA namespaces; a
separate real Internet TLS probe must also pass. No host routes are edited.
"""

import argparse
import base64
import copy
import hashlib
import importlib.util
import ipaddress
import json
import os
import signal
import shlex
import socket
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("desktop", Path(__file__).with_name("qa-desktop.py"))
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)
network = desktop.network
PREFIX = "io.browser-platform."
LABEL = PREFIX + "qa=network-20260913"
HOST_SOURCE = "/proc/1/net/fib_trie"
HOST_TARGET = "/run/browser-platform-host/ipv4-fib-trie"
FIXTURE_IP = "93.184.215.14"
DNS_NAME = "network-qa-direct-dns"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def inspect(identifier):
    return json.loads(network.docker("inspect", identifier).stdout)[0]


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class DirectChecks:
    def __init__(self, qa, output, native_engine=None):
        self.qa, self.output = qa.resolve(), output.resolve()
        self.native_engine=native_engine
        self.expected={"locale":"zh-TW","timezone":"Asia/Taipei","screen":"1920x1080","dpr":1}
        if native_engine:
            entry=json.loads((self.qa.parent/"entry.json").read_text());assert entry["browser_engine"]==native_engine
            self.expected.update(locale=entry["locale"],timezone=entry["timezone"],screen=entry["screen"].split("@")[0])
        self.checks = network.Checks(self.qa)
        self.output.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state_path = self.qa / "direct-state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        self.results = json.loads((self.output / "results.json").read_text()) if (self.output / "results.json").exists() else []
        self.observer = self.qa.parent / "observer"
        self.dns = self.qa.parent / "direct-dns"
        self.images = json.loads((self.qa / "images.json").read_text())
        self.refresh()

    def refresh(self):
        self.checks.client = network.SecureClient(self.qa)
        admin = json.loads((self.qa / "admin.json").read_text())
        self.admin = network.SecureClient(self.qa, username=admin["username"],
            private=admin["private_key"].encode(), public=admin["server_public_key"].encode())

    def save(self):
        network.write_json(self.state_path, self.state)

    def passed(self, name, **details):
        value = {"check": name, "result": "PASS", "at": datetime.now(timezone.utc).isoformat(), **details}
        self.results.append(value)
        network.write_json(self.output / "results.json", self.results)
        print(json.dumps(value), flush=True)

    def snapshot(self, key):
        status, value = self.checks.client.call("GET", "/api/profile-runtime/" + self.state[key]["request"]["home_name"])
        assert status == 200 and value["network_direct_version"] == 1
        return value

    def resources(self, key):
        return {item["kind"]: item["id"] for item in self.snapshot(key)["resources"]}

    def journal(self, key):
        request = self.state[key]["request"]
        matches = [path for path in (self.qa / "config/.config/sealskin/profile-network-runtime").glob("*.json")
                   if json.loads(path.read_text())["identity"]["operation"] == request["operation_id"]]
        assert len(matches) == 1
        return matches[0], json.loads(matches[0].read_text())

    def worker(self, key):
        return self.state[key]["worker"]

    def control(self, key):
        if self.native_engine:
            ns=importlib.util.spec_from_file_location("native_direct",Path(__file__).with_name("native-network-client.py"));nm=importlib.util.module_from_spec(ns);ns.loader.exec_module(nm)
            network.wait(lambda: network.docker("exec",self.worker(key),"python3","-c",'import socket;socket.create_connection(("127.0.0.1",9222),1).close()',check=False).returncode==0,"native DIRECT browser readiness",seconds=90)
            return nm.NativeDesktop(self.worker(key),self.native_engine)
        return desktop.Desktop(self.worker(key))

    def stop(self, key):
        value = self.snapshot(key)
        if value["records"] or value["workers"] or value["resources"]:
            status, response = self.checks.client.call("POST", "/api/profile-runtime/" + self.state[key]["request"]["home_name"] + "/stop", self.state[key]["stop"])
            network.write_json(self.case / (key + "-stop.json"), {"status": status, "response": response})
            assert status == 204
        value = self.snapshot(key)
        assert value["records"] == value["workers"] == value["resources"] == []

    def diagnostic(self, instance, *command, cap="NET_ADMIN"):
        value = inspect(instance)
        labels = value["Config"]["Labels"]
        assert labels.get(PREFIX + "owner") == "network-qa" or labels.get(PREFIX + "qa") == "network-20260913"
        assert value["HostConfig"]["NetworkMode"] != "host"
        return network.docker("run", "--rm", "--label", LABEL, "--network", "container:" + value["Id"],
            "--cap-drop", "ALL", "--cap-add", cap, "--read-only", "--security-opt", "no-new-privileges:true",
            "--memory", "64m", "--pids-limit", "24", "--entrypoint", command[0], self.images["relay"], *command[1:]).stdout

    def prepare(self):
        if not self.state.get("configured"):
            original = json.loads((self.qa / "browser-worker.json").read_text())
            assert (original["engine"] == "camoufox" or original["engine"] == self.native_engine) and original["home"] == "network-qa-home-browser"
            body = json.loads((self.qa / "browser-stop.json").read_text())
            status, _ = self.checks.client.call("POST", "/api/profile-runtime/" + original["home"] + "/stop", body)
            assert status == 204
            manifest = json.loads((self.qa.parent / "guard-image.json").read_text())
            self.images["relay"] = manifest["image_id"]
            network.write_json(self.qa / "images.json", self.images)
            allowed = json.loads((self.qa / "allow.json").read_text())
            for field in ("images", "guard_images", "direct_images"):
                allowed[field] = sorted(set(allowed.get(field, []) + [self.images["relay"]]))
            network.write_json(self.qa / "allow.json", allowed)
            config = inspect("sealskin-network-qa")
            assert any(m["Source"] == HOST_SOURCE and m["Destination"] == HOST_TARGET and not m["RW"] for m in config["Mounts"])
            source = "from app.network_direct import parse_host_ipv4;from pathlib import Path;import json;print(json.dumps(parse_host_ipv4(Path(" + repr(HOST_TARGET) + ").read_text())))"
            hosts = json.loads(network.docker("exec", "sealskin-network-qa", "python3", "-c", source).stdout)
            addresses = sorted({row[4][0] for row in socket.getaddrinfo("example.com", 443, socket.AF_INET, socket.SOCK_STREAM)
                                if ipaddress.IPv4Address(row[4][0]).is_global and row[4][0] not in hosts})
            assert addresses and FIXTURE_IP not in addresses + hosts
            self.dns.mkdir(mode=0o700, exist_ok=False)
            network.write_json(self.dns / "config.json", {"fixture_ipv4": FIXTURE_IP, "private_ipv4": original["observer_ip"],
                "host_ipv4": hosts, "public_probe": {"name": "example.com", "addresses": addresses}})
            network.write_json(self.dns / "mode.json", {})
            network.docker("run", "-d", "--name", DNS_NAME, "--label", LABEL, "--network", "browser-platform-network-qa",
                "--user", "1000:1000", "--cap-drop", "ALL", "--read-only", "--security-opt", "no-new-privileges:true",
                "--memory", "64m", "--cpus", ".5", "--pids-limit", "64", "--sysctl", "net.ipv4.ip_unprivileged_port_start=0",
                "-p", self.images["upstream_host"] + ":53:53/udp", "-p", self.images["upstream_host"] + ":53:53/tcp",
                "-v", str(self.dns) + ":/qa-dns", "-v", str(Path(__file__).with_name("direct-network-dns.py")) + ":/run/dns.py:ro",
                "--entrypoint", "python3", self.images["probe"], "/run/dns.py", "--root", "/qa-dns")
            network.wait(lambda: "DIRECT QA DNS ready" in network.docker("logs", DNS_NAME).stdout, "DIRECT DNS fixture")
            registry_path = self.qa / "config/.config/sealskin/profile-network-policies.json"
            registry = json.loads(registry_path.read_text())
            app_template = json.loads((self.qa / "camoufox-app.json").read_text())
            for key, profile, home, app_id in (
                    ("a", "network-qa-browser", "network-qa-home-browser", "camoufox-network-qa-r4"),
                    ("b", "network-qa-b", "network-qa-home-b", "camoufox-network-qa-direct-b")):
                app = copy.deepcopy(app_template)
                app.update(id=app_id, name="Private DIRECT QA " + key, source_app_id=app_id)
                policy = dict(username="network-qa", profile_id=profile, home_name=home, application_id=app_id,
                    mode="direct", approved_resolver_id="qa-pinned-dns", approved_resolver_ip=self.images["upstream_host"],
                    relay_image=self.images["relay"], probe_image=self.images["probe"], upstream_host="", upstream_port=0,
                    username_file="", username_sha256="", password_file="", password_sha256="", probe_url="https://example.com/",
                    probe_ca_file="", probe_ca_sha256="", probe_timeout_seconds=10)
                policy_id = "network-qa-direct-" + key + "-" + uuid.uuid4().hex[:8]
                revision = digest(policy)
                registry["policies"][policy_id] = policy
                network.write_json(registry_path, registry)
                app["provider_config"].update(network_policy_id=policy_id, network_policy_sha256=revision)
                method, path = ("PATCH", "/api/admin/apps/installed/" + app_id) if key == "a" else ("POST", "/api/admin/apps/installed")
                payload = {"provider_config": app["provider_config"]} if key == "a" else app
                status, _ = self.admin.call(method, path, payload)
                assert status == (200 if key == "a" else 201)
                if key == "b":
                    self.install_ca(home)
                request = dict(url="https://example.com/", application_id=app_id, home_name=home, profile_id=profile,
                    operation_id=uuid.uuid4().hex, network_policy_id=policy_id, network_policy_sha256=revision,
                    language=self.expected["locale"].replace("-","_")+".UTF-8", timezone=self.expected["timezone"], wayland_mode=False, launch_in_room_mode=False)
                stop = {name: request[name] for name in ("application_id", "profile_id", "operation_id", "network_policy_id", "network_policy_sha256")}
                stop["bootstrap_url"] = request["url"]
                self.state[key] = {"request": request, "stop": stop, "policy": policy, "app": app, "marker": uuid.uuid4().hex}
                self.save()
            self.state.update(configured=True, observer_ip=original["observer_ip"], host_ipv4=hosts, fixture_ip=FIXTURE_IP)
            self.save()
        for key in ("a", "b"):
            snap = self.snapshot(key)
            if not snap["records"] and not snap["workers"] and not snap["resources"]:
                status, response = self.checks.client.call("POST", "/api/launch/url", self.state[key]["request"])
                network.write_json(self.case / (key + "-launch.json"), {"status": status, "response": response})
                assert status == 200, "DIRECT preflight/launch failed; private evidence retained"
                self.state[key]["stop"]["session_id"] = response["session_id"]
            snap = self.snapshot(key)
            assert len(snap["workers"]) == 1 and len(snap["records"]) == 1
            self.state[key]["worker"] = snap["workers"][0]["instance_id"]
            self.save()
            network.write_json(self.case / (key + "-generation.json"), snap)
            _, journal = self.journal(key)
            assert journal["policy"]["mode"] == journal["allocation"]["mode"] == "direct"
            assert all(not journal["policy"].get(name) for name in ("upstream_host", "username_file", "password_file", "username_secret_ref", "password_secret_ref"))
        network.write_json(self.qa / "browser-worker.json", {"instance_id": self.worker("a"), "home": self.state["a"]["request"]["home_name"],
            "profile": self.state["a"]["request"]["profile_id"], "observer_ip": self.state["observer_ip"], "engine": self.native_engine or "camoufox", "network_mode": "direct", **({"native_engine":self.native_engine,"expected_environment":self.expected} if self.native_engine else {})})
        network.write_json(self.qa / "browser-stop.json", self.state["a"]["stop"])
        network.write_json(self.qa / "browser-launch.json", self.state["a"]["request"])
        self.passed("two explicit DIRECT generations start only after real public TLS and bypass preflight", browsers=2, externalUpstreams=0)

    def install_ca(self, home):
        profile = self.qa / "storage/network-qa" / home / {"camoufox":".camoufox/profile","firefox":".firefox/profile","chromix":".pki/nssdb"}.get(self.native_engine,".camoufox/profile")
        profile.mkdir(mode=0o700, parents=True, exist_ok=True)
        nss = self.qa.parent / "nss-tools/extracted/usr"
        command = ["/lib64/ld-linux-x86-64.so.2", "--library-path", str(nss / "lib/x86_64-linux-gnu"), str(nss / "bin/certutil")]
        if shutil.which("certutil"):command=[shutil.which("certutil")]
        for args in (["-N", "--empty-password", "-d", "sql:" + str(profile)],
                     ["-A", "-d", "sql:" + str(profile), "-n", "Private Network QA CA", "-t", "C,,", "-i", str(self.observer / "ca.pem")]):
            assert subprocess.run(command + args, capture_output=True).returncode == 0

    def attach_fixture(self):
        # One /32 alias lives in the observer namespace. Each DIRECT gateway
        # routes it via a temporary observer endpoint on that QA egress bridge.
        # The gateways' nftables rules and the host routes remain untouched.
        observer = inspect("network-qa-observer")
        addresses = self.diagnostic(observer["Id"], "ip", "-4", "addr", "show", "dev", "lo")
        if FIXTURE_IP + "/32" not in addresses:
            self.diagnostic(observer["Id"], "ip", "addr", "add", FIXTURE_IP + "/32", "dev", "lo")
        for key in ("a", "b"):
            resources = self.resources(key)
            egress = json.loads(network.docker("network", "inspect", resources["egress"]).stdout)[0]
            assert egress["Labels"][PREFIX + "owner"] == "network-qa"
            if observer["Id"] not in egress.get("Containers", {}):
                network.docker("network", "connect", egress["Id"], observer["Id"])
            current = inspect(observer["Id"])
            address = current["NetworkSettings"]["Networks"][egress["Name"]]["IPAddress"]
            self.diagnostic(resources["relay"], "ip", "route", "replace", FIXTURE_IP + "/32", "via", address)
            route = self.diagnostic(resources["relay"], "ip", "route", "get", FIXTURE_IP)
            assert "via " + address in route and " dev lo" not in route
            self.state[key]["fixture_endpoint"] = {"egress": egress["Id"], "via": address}
        self.save()

    def detach_fixture(self):
        observer = inspect("network-qa-observer")
        for key in ("a", "b"):
            endpoint = self.state[key].get("fixture_endpoint")
            if not endpoint:
                continue
            snap = self.snapshot(key)
            resources = {item["kind"]: item["id"] for item in snap["resources"]}
            if resources.get("relay") and inspect(resources["relay"])["State"]["Running"]:
                self.diagnostic(resources["relay"], "ip", "route", "del", FIXTURE_IP + "/32")
            egress = json.loads(network.docker("network", "inspect", endpoint["egress"]).stdout)[0]
            if observer["Id"] in egress.get("Containers", {}):
                network.docker("network", "disconnect", egress["Id"], observer["Id"])
            del self.state[key]["fixture_endpoint"]
        self.save()

    def transports(self):
        self.attach_fixture()
        for key in ("a", "b"):
            control = self.control(key)
            for scheme in ("https", "http"):
                control.navigate(scheme + "://entry.leak.qa.test/test")
                result = control.evaluate("qa.transport()")
                assert result["pageProtocol"] == scheme + ":" and result["fetch"] and result["websocket"]
                network.write_json(self.case / (key + "-" + scheme + ".json"), result)
            control.navigate("https://entry.leak.qa.test/test")
            result = control.evaluate("({webrtc:typeof RTCPeerConnection,locale:navigator.language,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,screen:[screen.width,screen.height],dpr:devicePixelRatio})")
            assert result == dict(webrtc="function" if self.native_engine=="chromix" else "undefined", locale=self.expected["locale"], timezone=self.expected["timezone"], screen=[int(v) for v in self.expected["screen"].split("x")], dpr=1)
            network.write_json(self.case / (key + "-environment.json"), result)
            self.store_marker(key)
        dns_events = events(self.dns / "events.jsonl")
        assert any(e["name"] == "example.com" and e["answers"] > 0 and not e["authoritative"] for e in dns_events)
        observed = events(self.observer / "events.jsonl")
        for key in ("a", "b"):
            _, journal = self.journal(key)
            relay = inspect(journal["allocation"]["relay_id"])
            egress = json.loads(network.docker("network", "inspect", journal["allocation"]["egress_id"]).stdout)[0]
            address = relay["NetworkSettings"]["Networks"][egress["Name"]]["IPAddress"]
            assert all(any(e["event"] == kind and e.get("source") == address for e in observed) for kind in ("http", "https", "websocket"))
        self.passed("both normal browsers use DIRECT for HTTP HTTPS WS WSS", fixture="public /32 routed only inside QA namespaces", environmentUnchanged=True)

    def store_marker(self, key):
        marker = self.state[key]["marker"]
        expression = """(async()=>{const value=MARKER;localStorage.setItem('direct-marker',value);document.cookie='direct_marker='+value+';Path=/;SameSite=Lax;Secure;Max-Age=86400';
const db=await new Promise((ok,fail)=>{const q=indexedDB.open('direct-qa',1);q.onupgradeneeded=()=>q.result.createObjectStore('values');q.onsuccess=()=>ok(q.result);q.onerror=()=>fail(q.error)});
await new Promise((ok,fail)=>{const t=db.transaction('values','readwrite');t.objectStore('values').put(value,'marker');t.oncomplete=ok;t.onerror=()=>fail(t.error)});db.close();return true})()""".replace("MARKER", json.dumps(marker))
        assert self.control(key).evaluate(expression)

    def verify_marker(self, key):
        expression = """(async()=>{const db=await new Promise((ok,fail)=>{const q=indexedDB.open('direct-qa',1);q.onsuccess=()=>ok(q.result);q.onerror=()=>fail(q.error)});
const idb=await new Promise((ok,fail)=>{const q=db.transaction('values').objectStore('values').get('marker');q.onsuccess=()=>ok(q.result);q.onerror=()=>fail(q.error)});db.close();const cookie=document.cookie.split('; ').find(x=>x.startsWith('direct_marker='));return {local:localStorage.getItem('direct-marker'),cookie:cookie?cookie.slice(14):null,idb}})()"""
        value = self.control(key).evaluate(expression)
        assert value == dict(local=self.state[key]["marker"], cookie=self.state[key]["marker"], idb=self.state[key]["marker"])
        return True

    def raw_probes(self, instance, targets):
        source = """import socket,struct,json,os
targets=TARGETS
name='bypass-'+os.urandom(16).hex()+'.leak.qa.test'
query=struct.pack('!HHHHHH',1234,256,1,0,0,0)+b''.join(bytes([len(x)])+x.encode() for x in name.split('.'))+b'\\0'+struct.pack('!HH',1,1)
out=[]
for label,address,port,transport in targets:
 family=socket.AF_INET6 if ':' in address else socket.AF_INET
 kind=socket.SOCK_DGRAM if transport=='udp' else socket.SOCK_STREAM
 with socket.socket(family,kind) as s:
  s.settimeout(.3)
  try:
   s.connect((address,port))
   if transport=='udp':
    payload=query if port==53 else b'\\0\\1\\0\\0\\x21\\x12\\xa4\\x42'+os.urandom(12) if port==3478 else b'\\xc3\\0\\0\\0\\1\\x08'+os.urandom(1194)
    s.send(payload);s.recv(4096)
   reachable=True
  except OSError:reachable=False
  out.append({'target':label,'reachable':reachable})
print(json.dumps({'query':name,'results':out}))
""".replace("TARGETS", repr(targets))
        return json.loads(network.docker("exec", "--user", "1000", instance, "python3", "-c", source).stdout)

    def socks_probes(self, key, targets):
        _, journal = self.journal(key)
        relay_ip = journal["allocation"]["relay_ip"]
        source = """import socket,struct,json,ipaddress,ssl,hashlib
targets=TARGETS
def exact(s,size):
 data=b''
 while len(data)<size:
  chunk=s.recv(size-len(data))
  if not chunk:raise OSError('closed')
  data+=chunk
 return data
out=[]
for item in targets:
 result={'target':item['label'],'reachable':False}
 try:
  with socket.create_connection((RELAY,1080),timeout=12) as s:
   s.sendall(b'\\5\\1\\0');assert exact(s,2)==b'\\5\\0'
   target=item['host']
   try:
    address=ipaddress.ip_address(target);payload=bytes([1 if address.version==4 else 4])+address.packed
   except ValueError:
    value=target.encode('idna');payload=b'\\3'+bytes([len(value)])+value
   s.sendall(b'\\5\\1\\0'+payload+struct.pack('!H',item['port']))
   header=exact(s,4);result['reply']=header[1]
   if header[3]==1:exact(s,6)
   elif header[3]==4:exact(s,18)
   elif header[3]==3:exact(s,exact(s,1)[0]+2)
   if header[1]==0:
    result['reachable']=True
    if item.get('tls_name'):
     context=ssl.create_default_context(cadata=item.get('ca'))
     with context.wrap_socket(s,server_hostname=item['tls_name']) as secure:
      result.update(tls=secure.version(),certificateSHA256=hashlib.sha256(secure.getpeercert(binary_form=True)).hexdigest())
      secure.sendall(('GET /ping HTTP/1.1\\r\\nHost: '+item['tls_name']+'\\r\\nConnection: close\\r\\n\\r\\n').encode())
      result['httpStatus']=secure.recv(4096).split(b'\\r\\n',1)[0].decode('ascii')
 except (OSError,ValueError,AssertionError) as error:result['error']=type(error).__name__
 out.append(result)
print(json.dumps(out))
""".replace("TARGETS", repr(targets)).replace("RELAY", repr(relay_ip))
        return json.loads(network.docker("exec", "--user", "1000", self.worker(key), "python3", "-c", source).stdout)

    def dropped(self, instance):
        value = json.loads(network.docker("exec", instance, "nft", "-j", "list", "table", "inet", "bp_guard").stdout)
        return sum(e.get("counter", {}).get("packets", 0) for item in value["nftables"]
                   if item.get("rule", {}).get("chain") == "output" and any("drop" in e for e in item["rule"]["expr"])
                   for e in item["rule"]["expr"])

    def start_capture(self, key, kind):
        _, journal = self.journal(key)
        allocation = journal["allocation"]
        instance = allocation[kind + "_id"]
        interface, source = "eth0", allocation["guard_ip"]
        if kind == "relay":
            route = self.diagnostic(instance, "ip", "route", "get", FIXTURE_IP)
            interface = route.split(" dev ", 1)[1].split()[0]
            egress = json.loads(network.docker("network", "inspect", allocation["egress_id"]).stdout)[0]
            source = inspect(instance)["NetworkSettings"]["Networks"][egress["Name"]]["IPAddress"]
        path = self.case / (key + "-" + kind + "-wire.jsonl")
        log = path.open("w")
        os.fchmod(log.fileno(), 0o600)
        name = "network-qa-wire-direct-" + key + "-" + kind
        command = ["docker", "run", "--rm", "--name", name, "--label", LABEL, "--network", "container:" + instance,
            "--cap-drop", "ALL", "--cap-add", "NET_RAW", "--read-only", "--security-opt", "no-new-privileges:true",
            "--memory", "64m", "--pids-limit", "16", "-v", str(Path(__file__).with_name("network-wire.py")) + ":/run/wire.py:ro",
            "--entrypoint", "python3", self.images["probe"], "/run/wire.py", "--worker-ip", source, "--interface", interface, "--seconds", "900"]
        process = subprocess.Popen(["sg", "docker", "-c", shlex.join(command)], stdout=log, stderr=subprocess.STDOUT)
        network.wait(lambda: "wire_capture_ready" in path.read_text(), "DIRECT packet observer")
        return {"name": name, "process": process, "log": log, "path": path, "kind": kind, "key": key}

    def finish_capture(self, capture):
        network.docker("stop", "-t", "2", capture["name"], check=False)
        capture["process"].wait(timeout=10)
        capture["log"].close()
        rows = [json.loads(line) for line in capture["path"].read_text().splitlines() if line.startswith("{")]
        value = next(row for row in rows if "outbound" in row)
        assert value["directionSource"] == "AF_PACKET.sll_pkttype == PACKET_OUTGOING"
        return value

    def isolation(self):
        self.attach_fixture()
        captures = [self.start_capture(key, kind) for key in ("a", "b") for kind in ("guard", "relay")]
        metadata = []
        try:
            for key, other in (("a", "b"), ("b", "a")):
                _, journal = self.journal(key)
                _, foreign = self.journal(other)
                allocation = journal["allocation"]
                resources = self.resources(key)
                nonce = uuid.uuid4().hex
                # These real listeners are independently reachable from the
                # trusted controller, before testing rejected Worker traffic.
                positive = "import socket,json\naddresses=" + repr([(self.state["observer_ip"], p) for p in (53, 853, 443)] + [(foreign["allocation"]["guard_ip"], 3000)]) + "\nfor a in addresses:\n s=socket.create_connection(a,timeout=3);s.close()\nprint(json.dumps({'listeners':len(addresses)}))"
                assert json.loads(network.docker("exec", "sealskin-network-qa", "python3", "-c", positive).stdout)["listeners"] == 4
                names = ("private", "host", "metadata", "mixed", "aaaa", "cname-private")
                rejected = [{"label": name, "host": name + "-" + nonce + ".leak.qa.test", "port": 443} for name in names]
                rejected += [{"label": label, "host": host, "port": port} for label, host, port in (
                    ("controller", allocation["controller_ip"], 8000), ("host-private", self.images["upstream_host"], 22),
                    ("metadata-literal", "169.254.169.254", 80), ("other-display", foreign["allocation"]["guard_ip"], 3000),
                    ("other-relay", foreign["allocation"]["relay_ip"], 1080), ("reserved", "240.0.0.1", 443),
                    ("benchmark", "198.18.0.1", 443), ("documentation", "192.0.2.1", 443), ("ipv6", "2606:4700:4700::1111", 443),
                    ("ipv6-loopback", "::1", 443), ("dns-via-socks", self.images["upstream_host"], 53),
                    ("public-dns-via-socks", "1.1.1.1", 53), ("public-dot-via-socks", "1.1.1.1", 853),
                    *(("host-public-" + str(i), host, 443) for i, host in enumerate(self.state["host_ipv4"])))]
                result = self.socks_probes(key, rejected)
                network.write_json(self.case / (key + "-socks-denials.json"), result)
                assert all(not item["reachable"] and item.get("reply", 0) != 0 for item in result)
                allowed = self.socks_probes(key, [
                    {"label": "literal", "host": FIXTURE_IP, "port": 443, "tls_name": "literal-" + nonce + ".leak.qa.test", "ca": (self.observer / "ca.pem").read_text()},
                    {"label": "udp-truncated-tcp-fallback", "host": "truncated-" + nonce + ".leak.qa.test", "port": 443},
                    {"label": "real-public-tls", "host": "example.com", "port": 443, "tls_name": "example.com"}])
                network.write_json(self.case / (key + "-positive-tls.json"), allowed)
                assert all(item["reachable"] for item in allowed)
                assert " 200 " in allowed[0]["httpStatus"] and allowed[2]["tls"] in ("TLSv1.2", "TLSv1.3")
                dns_events = events(self.dns / "events.jsonl")
                assert all(any(e["name"] == "truncated-" + nonce + ".leak.qa.test" and e["transport"] == transport for e in dns_events) for transport in ("udp", "tcp"))
                self.passed("DIRECT validates the complete destination set and accepts public literals and verified public TLS", home=key, rejectedTargets=len(rejected), privateDNS=True)
                targets = [(label, host, port, "tcp") for label, host, port in (
                    ("controller-api", allocation["controller_ip"], 8000), ("host-private", self.images["upstream_host"], 22),
                    ("metadata", "169.254.169.254", 80), ("other-display", foreign["allocation"]["guard_ip"], 3000),
                    ("other-relay", foreign["allocation"]["relay_ip"], 1080), ("fixture-direct-https", FIXTURE_IP, 443),
                    ("public-direct-https", "1.1.1.1", 443), ("ipv6", "2606:4700:4700::1111", 443),
                    *(("host-public-" + str(i), host, 443) for i, host in enumerate(self.state["host_ipv4"])))]
                targets += [(label, address, port, transport) for label, address in (("approved", self.images["upstream_host"]),
                    ("unapproved", self.state["observer_ip"]), ("docker", "127.0.0.11")) for port, transport in ((53,"udp"),(53,"tcp"))]
                targets += [("observer-" + str(port) + "-" + transport, self.state["observer_ip"], port, transport)
                            for port, transport in ((853,"tcp"),(443,"tcp"),(443,"udp"),(3478,"udp"))]
                before = self.dropped(resources["guard"])
                result = self.raw_probes(self.worker(key), targets)
                after = self.dropped(resources["guard"])
                network.write_json(self.case / (key + "-worker-bypass.json"), result)
                assert all(not item["reachable"] for item in result["results"]) and after > before
                assert not any(e.get("name") == result["query"] for e in events(self.dns / "events.jsonl") + events(self.observer / "events.jsonl"))
                relay_targets = [(label, address, port, transport) for label, address, port, transport in targets
                                 if label not in {"fixture-direct-https", "public-direct-https", "approved"}]
                relay_targets += [("public-dot", "1.1.1.1", 853, "tcp"), ("public-dns", "1.1.1.1", 53, "udp"),
                                  ("public-quic", FIXTURE_IP, 443, "udp"), ("public-stun", FIXTURE_IP, 3478, "udp")]
                before_relay = self.dropped(resources["relay"])
                result = self.raw_probes(resources["relay"], relay_targets)
                network.write_json(self.case / (key + "-relay-bypass.json"), result)
                assert all(not item["reachable"] for item in result["results"]) and self.dropped(resources["relay"]) > before_relay
                self.passed("Worker and gateway reject management LAN cross-Profile DNS IPv6 and UDP bypasses", home=key, workerTargets=len(targets), gatewayTargets=len(relay_targets), workerDrops=after-before)
                control = self.control(key)
                control.navigate("https://entry.leak.qa.test/test")
                assert control.evaluate("qa.transport()") == {"pageProtocol":"https:", "fetch":True, "websocket":True, "nonce":control.evaluate("qa.nonce")}
                browser_denials = control.evaluate("(async()=>{const out={};for(const label of ['private','host','metadata','mixed','aaaa']){try{await fetch('https://'+label+'-'+qa.nonce+'.leak.qa.test/ping',{signal:AbortSignal.timeout(2000)});out[label]=true}catch(_){out[label]=false}}return out})()")
                assert all(value is False for value in browser_denials.values())
                assert self.verify_marker(key)
                network.write_json(self.case / (key + "-browser-denials.json"), browser_denials)
            self.check_privileges()
        finally:
            for capture in captures:
                metadata.append((capture, self.finish_capture(capture)))
        for capture, value in metadata:
            _, journal = self.journal(capture["key"])
            allocation = journal["allocation"]
            out = value["outbound"]
            assert out
            if capture["kind"] == "guard":
                assert all(item["family"] == 4 and item["protocol"] == 6 and (
                    item["destination"] == allocation["relay_ip"] and item["destination_port"] == 1080 or
                    item["destination"] == allocation["controller_ip"] and item["source_port"] == 3000) for item in out)
            else:
                assert all(item["family"] == 4 and (
                    item["destination"] == self.images["upstream_host"] and item["destination_port"] == 53 and item["protocol"] in (6,17) or
                    item["protocol"] == 6 and ipaddress.IPv4Address(item["destination"]).is_global and
                    item["destination"] not in self.state["host_ipv4"] and item["destination_port"] not in (53,853)) for item in out)
                assert any(item["destination_port"] == 53 and item["protocol"] == 17 for item in out)
                assert any(item["destination_port"] == 53 and item["protocol"] == 6 for item in out)
            self.passed("outbound packet directions match the frozen DIRECT policy", home=capture["key"], namespace=capture["kind"], flows=len(out))

    def check_privileges(self):
        evidence = {}
        for key in ("a", "b"):
            resources = self.resources(key)
            details = {}
            for kind in ("guard", "relay"):
                value = inspect(resources[kind])
                process = dict(line.split(":", 1) for line in network.docker("exec", value["Id"], "cat", "/proc/1/status").stdout.splitlines())
                caps = {name: int(process[name].strip(), 16) for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")}
                assert all(value == 0 for value in caps.values()) and process["NoNewPrivs"].strip() == "1"
                mounts = [m for m in value["Mounts"] if m["Source"] == HOST_SOURCE]
                assert (len(mounts) == 1 and mounts[0]["RW"] is False and mounts[0]["Destination"] == HOST_TARGET) if kind == "relay" else not mounts
                details[kind] = {"caps": caps, "noNewPrivileges": True, "hostEvidenceMounts": len(mounts)}
            worker = inspect(self.worker(key))
            assert worker["HostConfig"]["NetworkMode"] == "container:" + resources["guard"]
            assert not worker["HostConfig"].get("Privileged") and not any(cap in (worker["HostConfig"].get("CapAdd") or []) for cap in ("NET_ADMIN", "NET_RAW"))
            assert not any(m["Source"] == HOST_SOURCE or m["Destination"] in (HOST_TARGET, "/var/run/docker.sock", "/run/secrets") for m in worker["Mounts"])
            evidence[key] = details
        network.write_json(self.case / "privileges.json", evidence)
        self.passed("DIRECT evidence mount and actual long-lived capabilities remain confined to the trusted gateway", homes=2)

    def browser_identity(self, key):
        source = """import json
from pathlib import Path
out=[]
for path in Path('/proc').glob('[0-9]*'):
 try:
  args=path.joinpath('cmdline').read_bytes().split(b'\\0')
  if args[0].endswith(b'/camoufox') and b'--profile' in args:
   out.append([int(path.name),path.joinpath('stat').read_text().split()[21]])
 except (OSError,IndexError):pass
assert len(out)==1
print(json.dumps(out))
"""
        if self.native_engine:
            source=source.replace("args[0].endswith(b'/camoufox') and b'--profile' in args", "any(a == b'--remote-debugging-port=9222' for a in args)")
        return json.loads(network.docker("exec", self.worker(key), "python3", "-c", source).stdout)

    def dns_faults(self):
        self.attach_fixture()
        nonce = uuid.uuid4().hex
        key = "a"
        original = self.browser_identity(key)
        relay = self.resources(key)["relay"]
        capture = self.start_capture(key, "relay")
        proxy_events = [e for e in events(self.observer / "events.jsonl") if e["event"] in ("socks", "http_connect", "https_connect")]
        try:
            local_name = "localhost"
            hosts_before = network.docker("exec", relay, "cat", "/etc/hosts").stdout
            assert any(line.split()[:2] == ["127.0.0.1", "localhost"] for line in hosts_before.splitlines())
            result = self.socks_probes(key, [{"label":"ignore-system-hosts", "host":local_name, "port":443}])
            assert result[0]["reachable"]
            assert any(e["name"] == local_name for e in events(self.dns / "events.jsonl"))
            assert network.docker("exec", relay, "cat", "/etc/hosts").stdout == hosts_before
            rebind = {"label":"rebinding", "host":"rebind-" + nonce + ".leak.qa.test", "port":443}
            assert self.socks_probes(key, [rebind])[0]["reachable"]
            network.write_json(self.dns / "mode.json", {"rebind_private": True})
            result = self.socks_probes(key, [rebind])
            assert result[0]["reachable"] is False and result[0].get("reply") != 0
            network.write_json(self.case / "dns-rebinding.json", result)
            self.passed("DIRECT ignores system hosts and rejects a changed private DNS answer on the next connection", caching="no application DNS cache")
            for mode in ("servfail", "drop"):
                network.write_json(self.dns / "mode.json", {"mode":mode})
                started = time.monotonic()
                result = self.socks_probes(key, [{"label":mode, "host":"failure-" + uuid.uuid4().hex + ".leak.qa.test", "port":443}])
                elapsed = time.monotonic() - started
                assert not result[0]["reachable"]
                network.write_json(self.case / ("resolver-" + mode + ".json"), {"result":result, "elapsedSeconds":elapsed})
                assert self.socks_probes(key, [{"label":"validated-literal", "host":FIXTURE_IP, "port":443}])[0]["reachable"]
            network.write_json(self.dns / "mode.json", {})
            self.passed("resolver errors and timeouts block new hostname connections without DNS or proxy fallback", numericTargets="remain governed by the address ACL")
            control = self.control(key)
            control.navigate("https://entry.leak.qa.test/test")
            name = "doh-query-" + nonce + ".leak.qa.test"
            query = b"\x04\xd2\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + b"".join(bytes([len(label)]) + label.encode() for label in name.split(".")) + b"\0\0\x01\0\x01"
            url = "https://doh-" + nonce + ".leak.qa.test/dns-query?dns=" + base64.urlsafe_b64encode(query).decode().rstrip("=")
            assert control.evaluate("(async()=>{const r=await fetch(" + json.dumps(url) + ");const b=new Uint8Array(await r.arrayBuffer());return r.ok && !!(b[2]&4)})()")
            assert any(e["event"] == "dns" and e.get("transport") == "doh" and e["name"] == name for e in events(self.observer / "events.jsonl"))
            transport = control.evaluate("(async()=>{try{const t=new WebTransport('https://h3-'+qa.nonce+'.leak.qa.test/');const ok=await Promise.race([t.ready.then(()=>true,()=>false),new Promise(r=>setTimeout(()=>r(false),2500))]);t.close();return ok}catch(_){return false}})()")
            assert transport is False
            if self.native_engine=="chromix":
                assert control.evaluate("typeof RTCPeerConnection")=="function"
                network.write_json(self.case / "webrtc-candidates.json", control.assert_webrtc_confined())
            else:
                assert control.evaluate("typeof RTCPeerConnection")=="undefined"
            self.passed("page DoH stays inside DIRECT HTTPS while WebRTC and HTTP3 do not open a UDP path")
        finally:
            network.write_json(self.dns / "mode.json", {})
            wire = self.finish_capture(capture)
        assert original == self.browser_identity(key)
        assert proxy_events == [e for e in events(self.observer / "events.jsonl") if e["event"] in ("socks", "http_connect", "https_connect")]
        assert all(item["family"] == 4 and (item["protocol"] == 6 or
                   item["protocol"] == 17 and item["destination"] == self.images["upstream_host"] and item["destination_port"] == 53)
                   for item in wire["outbound"])

    def adapter_health(self, key, force=False):
        deadline = time.monotonic() + 15
        while True:
            connection = network.UnixConnection("adapter", timeout=100)
            try:
                connection.request("POST" if force else "GET", "/profiles/" + self.state[key]["request"]["profile_id"] + "/health")
                response = connection.getresponse()
                status, value = response.status, json.loads(response.read())
            finally:
                connection.close()
            if status != 429 or time.monotonic() >= deadline:
                assert status == 200, "DIRECT Adapter health query failed"
                return value["health"]
            time.sleep(.5)

    def entry(self):
        self.attach_fixture()
        for key in ("a", "b"):
            self.control(key).navigate("https://entry.leak.qa.test/test")
            self.state[key]["marker"] = uuid.uuid4().hex
            self.save()
            self.store_marker(key)
            self.neutral(key)
        self.detach_fixture()
        state_path = self.qa / "adapter-state.json"
        bindings = json.loads(state_path.read_text())["bindings"] if state_path.exists() else {}
        if bindings and not (self.qa / "adapter-pid.json").exists():
            self.checks.start_adapter()
        for key in ("a", "b"):
            profile = self.state[key]["request"]["profile_id"]
            binding = bindings.get(profile)
            if binding and binding["status"] not in ("stopped", "failed"):
                assert binding["operation_id"] == self.state[key]["request"]["operation_id"]
                status, value = self.checks.control(profile.removeprefix("network-qa-"), "stop")
                network.write_json(self.case / (key + "-previous-adapter-stop.json"), {"status":status, "response":value})
                assert status == 200 and value["result"]["status"] == "stopped"
            self.stop(key)
        self.stop_adapter()
        config = json.loads((self.qa / "adapter-config.json").read_text())
        # The public entry authority deliberately names the real host address.
        # Its bootstrap is denied by DIRECT. Only the loopback QA API is used
        # by this test; the initial browser page must reach example.com itself.
        config["public_base_url"] = "https://" + self.state["host_ipv4"][0]
        config["profiles"] = [{"id":self.state[key]["request"]["profile_id"],
            "application_id":self.state[key]["request"]["application_id"], "home_name":self.state[key]["request"]["home_name"],
            "start_url":"https://example.com/", "language":self.expected["locale"].replace("-","_")+".UTF-8", "timezone":self.expected["timezone"], "wayland_mode":False,
            "network_policy_id":self.state[key]["request"]["network_policy_id"],
            "network_policy_sha256":self.state[key]["request"]["network_policy_sha256"]} for key in ("a", "b")]
        network.write_json(self.qa / "adapter-config.json", config)
        self.checks.start_adapter()
        for key in ("a", "b"):
            profile = self.state[key]["request"]["profile_id"]
            status, headers, raw = network.request("POST", "/browser/" + profile + "/start", b"", {"Origin":config["public_base_url"]}, port=29110)
            network.write_json(self.case / (key + "-entry-response.json"), {"status":status, "headers":headers, "body":raw.decode()})
            assert status == 303
            binding = json.loads(state_path.read_text())["bindings"][profile]
            assert binding["status"] == "running"
            self.state[key]["request"].update(operation_id=binding["operation_id"], url=binding["bootstrap_url"], initial_url="https://example.com/")
            self.state[key]["stop"].update(operation_id=binding["operation_id"], bootstrap_url=binding["bootstrap_url"], session_id=binding["session_id"])
            snap = self.snapshot(key)
            assert len(snap["workers"]) == 1 and snap["profile_initial_url_version"] == 1
            self.state[key]["worker"] = snap["workers"][0]["instance_id"]
            self.save()
            value = inspect(self.worker(key))
            env = dict(item.split("=",1) for item in value["Config"]["Env"] if "=" in item)
            assert env["SEALSKIN_URL"] == "https://example.com/"
            assert snap["records"][0]["launch_context"] == {"type":"url", "value":binding["bootstrap_url"]}
            control = self.control(key)
            network.wait(lambda: "Example Domain" in control.available_title(), "configured DIRECT initial page", seconds=60)
            before = self.checks.identity(self.worker(key))
            for _ in range(2):
                assert network.request("POST", "/browser/" + profile + "/start", b"", {"Origin":config["public_base_url"]}, port=29110)[0] == 303
            assert before == self.checks.identity(self.worker(key))
            assert json.loads(state_path.read_text())["bindings"][profile]["operation_id"] == binding["operation_id"]
            assert not self.socks_probes(key,[{"label":"bootstrap-host-remains-denied", "host":self.state["host_ipv4"][0], "port":443}])[0]["reachable"]
            network.write_json(self.case / (key + "-entry.json"), {"result":"PASS", "initialPageTitle":control.title(),
                "uniqueLaunchContextPreserved":True, "reusedRequests":2, "hostStillDenied":True})
        network.write_json(self.qa / "browser-worker.json", {"instance_id":self.worker("a"), "home":self.state["a"]["request"]["home_name"],
            "profile":self.state["a"]["request"]["profile_id"], "observer_ip":self.state["observer_ip"], "engine":self.native_engine or "camoufox", "native_engine":self.native_engine, "network_mode":"direct"})
        network.write_json(self.qa / "browser-stop.json", self.state["a"]["stop"])
        network.write_json(self.qa / "browser-launch.json", self.state["a"]["request"])
        self.attach_fixture()
        for key in ("a", "b"):
            self.control(key).navigate("https://entry.leak.qa.test/test")
            assert self.verify_marker(key)
        self.passed("fixed Adapter entry opens the configured public page, preserves unique ownership and reuses both DIRECT sessions", homes=2, hostException=False)

    def health(self):
        assert (self.qa / "adapter-state.json").exists(), "Run the fixed entry stage; health never adopts an unbound session"
        if not (self.qa / "adapter-pid.json").exists():
            self.checks.start_adapter()
        for key in ("a", "b"):
            # Observe read-only health after Adapter startup bootstrap has
            # durably adopted the already-running generation.
            value = self.adapter_health(key)
            binding_path = self.qa / "adapter-state.json"
            before = binding_path.read_bytes()
            workers = {k:self.checks.identity(self.worker(k)) for k in ("a", "b")}
            assert (self.qa / "proxy-events.jsonl").exists()
            events_before = events(self.qa / "proxy-events.jsonl")
            value = self.adapter_health(key, force=True)
            network.write_json(self.case / (key + "-health.json"), value)
            checks = {check["name"]:check for check in value["checks"]}
            assert value["network_mode"] == "direct" and value["overall"] == "healthy"
            assert checks["proxy"]["status"] == "not_applicable" and checks["proxy"]["code"] == "DIRECT_NO_UPSTREAM"
            assert checks["egress"]["status"] == "pass" and checks["egress"]["required"] and checks["egress"]["code"] == "DIRECT_OK"
            assert value["binding"]["operation_id"] == self.state[key]["request"]["operation_id"]
            assert before == binding_path.read_bytes() and workers == {k:self.checks.identity(self.worker(k)) for k in ("a", "b")}
            assert events_before == events(self.qa / "proxy-events.jsonl")
            status, observation = self.checks.client.call("GET", "/api/profile-runtime/" + self.state[key]["request"]["home_name"] + "/health")
            assert status == 200 and observation["network"]["upstream"] is None
            network.write_json(self.case / (key + "-no-probe-observation.json"), observation)
        self.passed("DIRECT health distinguishes no external proxy from required egress and does not mutate lifecycle", homes=2, unrunProbe="absent")

    def lose_evidence(self, instance):
        # Fault injection unmounts only this QA container's private bind. The
        # source procfs file is never written and mount propagation is private.
        value = inspect(instance)
        labels = value["Config"]["Labels"]
        assert labels.get(PREFIX + "owner") == "network-qa" or labels.get(PREFIX + "qa") == "network-20260913"
        assert value["HostConfig"]["NetworkMode"] != "host" and value["HostConfig"].get("PidMode", "") != "host"
        mounts = [m for m in value["Mounts"] if m.get("Destination") == HOST_TARGET]
        assert len(mounts) == 1 and mounts[0]["Source"] == HOST_SOURCE and mounts[0]["RW"] is False and mounts[0]["Propagation"] == "rprivate"
        # The workload's dropped capabilities/AppArmor correctly prevent an
        # exec from unmounting it. Use a short-lived, networkless QA helper
        # sharing only this target's PID namespace, with no host mounts.
        source = """import ctypes,json,os
target=TARGET
namespace=os.readlink('/proc/1/ns/mnt')
assert namespace != os.readlink('/proc/self/ns/mnt')
root=os.open('/proc/1/root',os.O_RDONLY|os.O_DIRECTORY)
mount=os.open('/proc/1/ns/mnt',os.O_RDONLY)
libc=ctypes.CDLL(None,use_errno=True)
if libc.setns(mount,0):raise OSError(ctypes.get_errno(),'QA mount namespace entry failed')
os.close(mount)
os.fchdir(root);os.chroot('.');os.chdir('/');os.close(root)
assert any(line.split()[4]==target for line in open('/proc/self/mountinfo'))
if libc.umount2(target.encode(),0):raise OSError(ctypes.get_errno(),'QA evidence unmount failed')
print(json.dumps({'unmounted':target,'mountNamespace':namespace}))
""".replace("TARGET", repr(HOST_TARGET))
        result = network.docker("run", "--rm", "--label", LABEL, "--network", "none", "--pid", "container:" + value["Id"],
            "--cap-drop", "ALL", "--cap-add", "SYS_ADMIN", "--cap-add", "SYS_PTRACE", "--cap-add", "SYS_CHROOT",
            "--read-only", "--security-opt", "apparmor=unconfined", "--security-opt", "no-new-privileges:true",
            "--memory", "64m", "--pids-limit", "16", "--entrypoint", "python3", self.images["relay"], "-c", source)
        assert json.loads(result.stdout)["unmounted"] == HOST_TARGET

    def gateway_faults(self):
        self.attach_fixture()
        key = "a"
        worker_before, browser_before = self.checks.identity(self.worker(key)), self.browser_identity(key)
        other_before = self.checks.identity(self.worker("b"))
        relay = self.resources(key)["relay"]
        capture = self.start_capture(key, "guard")
        try:
            for fault in ("gateway-stop", "host-evidence-loss"):
                control = self.control(key)
                control.navigate("https://entry.leak.qa.test/test")
                control.evaluate("qa.startTraffic()")
                network.wait(lambda: control.evaluate("qa.download.bytes > 0 && qa.background.filter(x=>x.ok).length >= 2"),
                    "DIRECT active download and background requests", seconds=15)
                started = time.monotonic()
                if fault == "gateway-stop":
                    network.docker("stop", "-t", "3", relay)
                else:
                    self.lose_evidence(relay)
                    network.wait(lambda: not inspect(relay)["State"]["Running"], "DIRECT evidence watcher closes gateway", seconds=5)
                exit_elapsed = time.monotonic() - started
                cutoff = control.evaluate("qa.directFaultAt=Date.now()")
                network.wait(lambda: control.evaluate("qa.download.failed"), "existing DIRECT tunnel closes", seconds=10)
                # A failed fetch may take its six-second timeout to settle.
                # Only requests started after the confirmed gateway exit can
                # prove the fault blocks new traffic; old successful samples
                # must not make an early observation pass or fail.
                network.wait(lambda: control.evaluate("qa.background.filter(x=>x.time>=qa.directFaultAt).length >= 2"),
                    "post-fault DIRECT background requests settle", seconds=15)
                traffic = json.loads(control.evaluate("qa.stopTraffic()"))
                evidence = {"gatewayExitSeconds":exit_elapsed, "confirmedExitAt":cutoff, "traffic":traffic}
                network.write_json(self.case / (fault + ".json"), evidence)
                assert traffic["download"]["failed"] and traffic["download"]["bytes"] > 0 and not traffic["download"]["complete"]
                after = [value for value in traffic["background"] if value["time"] >= cutoff]
                assert len(after) >= 2 and all(not value["ok"] for value in after)
                assert self.socks_probes(key, [{"label":"no-fallback", "host":"failure-" + uuid.uuid4().hex + ".leak.qa.test", "port":443}])[0]["reachable"] is False
                health = self.adapter_health(key, force=True)
                evidence["health"] = health
                network.write_json(self.case / (fault + ".json"), evidence)
                check = next(c for c in health["checks"] if c["name"] == "egress")
                assert health["network_mode"] == "direct" and check["status"] == "fail" and check["code"] == "DIRECT_GATEWAY_UNAVAILABLE"
                assert health["recovery"]["blocking"]
                assert self.control("b").evaluate("fetchCheck('other-profile-alive')")
                network.docker("start", relay)
                self.attach_fixture()
                control.navigate("https://entry.leak.qa.test/test")
                assert control.evaluate("fetchCheck('recovered')")
                assert worker_before == self.checks.identity(self.worker(key)) and browser_before == self.browser_identity(key)
                assert other_before == self.checks.identity(self.worker("b"))
                self.passed("gateway fault closes existing tunnels and blocks new traffic without restarting either browser", fault=fault, gatewayExitSeconds=round(exit_elapsed,3))
            log = network.docker("logs", relay)
            assert "DIRECT_HOST_EVIDENCE_UNAVAILABLE" in log.stdout + log.stderr
        finally:
            wire = self.finish_capture(capture)
        _, journal = self.journal(key)
        allocation = journal["allocation"]
        assert wire["outbound"] and all(item["family"] == 4 and item["protocol"] == 6 and (
            item["destination"] == allocation["relay_ip"] and item["destination_port"] == 1080 or
            item["destination"] == allocation["controller_ip"] and item["source_port"] == 3000) for item in wire["outbound"])
        self.passed("gateway fault packet capture shows no Worker direct fallback", flows=len(wire["outbound"]))

    def neutral(self, key):
        path = "/tmp/browser-platform-direct-neutral.html"
        source = "from pathlib import Path;Path(" + repr(path) + ").write_text('<!doctype html><title>Browser Platform Client QA neutral</title><p>Private recovery fixture</p>')"
        network.docker("exec", "--user", "1000", self.worker(key), "python3", "-c", source)
        self.control(key).navigate("file://" + path)

    def stop_adapter(self):
        path = self.qa / "adapter-pid.json"
        if not path.exists():
            return False
        pid = json.loads(path.read_text())["pid"]
        assert Path(os.readlink(f"/proc/{pid}/exe")).resolve() == (self.qa / "bin/profile-adapter").resolve()
        os.kill(pid, signal.SIGTERM)
        def exited():
            try:
                return Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z"
            except FileNotFoundError:
                return True
        network.wait(exited, "owned QA Adapter stop", seconds=10)
        network.write_json(self.case / "stopped-adapter.json", {"pid":pid, "result":"PASS"})
        path.unlink()
        return True

    def recovery(self):
        adapter_running = self.stop_adapter()
        identities = {key:self.checks.identity(self.worker(key)) for key in ("a", "b")}
        browsers = {key:self.browser_identity(key) for key in ("a", "b")}
        for key in ("a", "b"):
            self.neutral(key)
        self.detach_fixture()
        self.lose_evidence("sealskin-network-qa")
        for key in ("a", "b"):
            status, value = self.checks.client.call("GET", "/api/profile-runtime/" + self.state[key]["request"]["home_name"] + "/health?upstream=true")
            assert status == 200 and value["network"]["code"] == "DIRECT_HOST_EVIDENCE_UNAVAILABLE"
            assert value["network"]["upstream"] is None
            network.write_json(self.case / (key + "-controller-evidence-loss.json"), value)
        command = [sys.executable, str(Path(__file__).with_name("recreate-network-controller.py")), "--root", str(self.qa), "--build", str(self.qa.parent / self.images["build"])]
        with (self.case / "controller-recreate.log").open("w") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        assert result.returncode == 0, "DIRECT controller recreation failed; inspect private log"
        self.refresh()
        assert identities == {key:self.checks.identity(self.worker(key)) for key in ("a", "b")}
        assert browsers == {key:self.browser_identity(key) for key in ("a", "b")}
        self.attach_fixture()
        for key in ("a", "b"):
            self.control(key).navigate("https://entry.leak.qa.test/test")
            assert self.verify_marker(key)
        self.passed("controller evidence loss reports unknown; replacement reconnects both live DIRECT generations without restarting browsers")
        resources = {key:self.resources(key) for key in ("a", "b")}
        for key in ("a", "b"):
            # Write a new value immediately before normal shutdown so an old
            # previously persisted marker cannot make this restoration pass.
            self.state[key]["marker"] = uuid.uuid4().hex
            self.save()
            self.store_marker(key)
            started = time.monotonic()
            network.docker("stop", "-t", "30", self.worker(key))
            value = inspect(self.worker(key))
            assert value["State"]["ExitCode"] == 0 and not value["State"]["OOMKilled"]
            assert "BROWSER_SHUTDOWN_CONFIRMED" in network.docker("logs", self.worker(key)).stdout
            network.write_json(self.case / (key + "-normal-shutdown.json"), {"exitCode":0, "elapsedSeconds":time.monotonic()-started})
        self.detach_fixture()
        for key in ("a", "b"):
            network.docker("stop", "-t", "3", resources[key]["guard"], resources[key]["relay"])
        path, record = self.journal("a")
        config_path = path.parent / (record["identity"]["home_hash"] + "-" + record["identity"]["operation"]) / "relay.json"
        before = config_path.read_bytes()
        try:
            config = json.loads(before)
            config["approved_resolver_id"] = "qa-unapproved-change"
            network.write_json(config_path, config)
            status, value = self.checks.client.call("POST", "/api/profile-runtime/" + self.state["a"]["request"]["home_name"] + "/resume", self.state["a"]["stop"])
            assert status == 503 and value["detail"] == "DIRECT_CONFIG_CHANGED"
            assert all(inspect(resources["a"][kind])["State"]["Status"] == "exited" for kind in ("relay", "guard"))
            assert inspect(self.worker("a"))["State"]["Status"] == "exited"
            network.write_json(self.case / "changed-config-resume.json", {"status":status, "response":value, "workerStarted":False})
        finally:
            config_path.write_bytes(before)
            config_path.chmod(0o600)
        try:
            network.write_json(self.dns / "mode.json", {"mode":"servfail"})
            status, value = self.checks.client.call("POST", "/api/profile-runtime/" + self.state["a"]["request"]["home_name"] + "/resume", self.state["a"]["stop"])
            assert status == 503 and inspect(self.worker("a"))["State"]["Status"] == "exited"
            network.write_json(self.case / "dns-failed-resume.json", {"status":status, "response":value, "workerStarted":False})
        finally:
            network.write_json(self.dns / "mode.json", {})
        for key in ("a", "b"):
            status, value = self.checks.client.call("POST", "/api/profile-runtime/" + self.state[key]["request"]["home_name"] + "/resume", self.state[key]["stop"])
            assert status == 200 and value["resumed"] and value["instance_id"] == self.worker(key)
            assert value["steps"] == ["relay", "guard", "controller", "relay-accepting", "probe", "worker", "display", "committed"]
            assert self.resources(key) == resources[key]
            network.write_json(self.case / (key + "-resume.json"), value)
        self.attach_fixture()
        for key in ("a", "b"):
            self.control(key).navigate("https://entry.leak.qa.test/test")
            assert self.verify_marker(key) and self.control(key).evaluate("fetchCheck('resume')")
        if adapter_running:
            self.checks.start_adapter()
        self.passed("same-generation DIRECT resume validates config and DNS before starting browsers and restores independent Cookie localStorage IndexedDB", homes=2, failedPreflights=2)

    def cleanup_retry(self):
        self.stop_adapter()
        sentinels = {}
        for key in ("a", "b"):
            self.neutral(key)
            path = self.qa / "storage/network-qa" / self.state[key]["request"]["home_name"] / ".direct-qa-preserved"
            path.write_text(self.state[key]["marker"])
            path.chmod(0o600)
            sentinels[key] = (path, path.read_bytes())
        self.detach_fixture()
        internal = self.resources("b")["internal"]
        try:
            network.write_json(self.qa / "policy.json", {"mode":"network-remove-error", "instance":internal})
            status, value = self.checks.client.call("POST", "/api/profile-runtime/" + self.state["b"]["request"]["home_name"] + "/stop", self.state["b"]["stop"])
            assert status != 204
            snapshot = self.snapshot("b")
            assert not snapshot["workers"] and snapshot["resources"]
            _, reservation = self.journal("b")
            assert reservation["identity"]["operation"] == self.state["b"]["request"]["operation_id"]
            request = {**self.state["b"]["request"], "operation_id":uuid.uuid4().hex}
            launch_status, launch = self.checks.client.call("POST", "/api/launch/url", request)
            assert launch_status != 200 and self.snapshot("b")["workers"] == []
            network.write_json(self.case / "interrupted-cleanup.json", {"stopStatus":status, "stop":value, "launchStatus":launch_status,
                "launch":launch, "reservationRetained":True, "newWorkerCreated":False})
        finally:
            network.write_json(self.qa / "policy.json", {})
        self.stop("b")
        self.stop("a")
        assert all(path.read_bytes() == data for path,data in sentinels.values())
        self.passed("interrupted cleanup retains the Home reservation; retry removes all generation resources and preserves QA Home data", homes=2)
        network.write_json(self.qa / "live-results.json", self.results)

    def run(self, stage):
        attempts = list(self.output.glob(stage + "-*"))
        self.case = self.output / (stage + "-" + str(len(attempts) + 1))
        self.case.mkdir(mode=0o700)
        print(json.dumps({"stage": stage, "state": "running"}), flush=True)
        try:
            getattr(self, stage)()
            network.write_json(self.case / "result.json", {"result": "PASS"})
        except Exception as exc:
            network.write_json(self.case / "failure.json", {"result": "FAIL", "type": type(exc).__name__, "message": str(exc), "qaRetained": True})
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    stages = ("prepare", "transports", "isolation", "dns_faults", "entry", "health", "gateway_faults", "recovery", "cleanup_retry")
    parser.add_argument("--stages", nargs="+", choices=stages, default=list(stages))
    parser.add_argument("--native-engine", choices=("camoufox","chromix","firefox"))
    args = parser.parse_args()
    checks = DirectChecks(args.root, args.output, args.native_engine)
    for stage in args.stages:
        checks.run(stage)


if __name__ == "__main__":
    main()
