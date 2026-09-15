#!/usr/bin/env python3
"""Drive only the two explicitly owned QA Homes in a public DNS experiment.

DNS publication, cache sampling and remote log correlation are separate steps.
A successful command here is a scoped observation, never full R5C2 acceptance.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import time
import uuid
import zlib

spec = importlib.util.spec_from_file_location("public_qa_desktop", Path(__file__).with_name("qa-desktop.py"))
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)
network = desktop.network
PREFIX = "io.browser-platform."


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def screenshot(control, worker, output, stem):
    remote = "/tmp/browser-platform-public-dns-" + uuid.uuid4().hex + ".xwd"
    control.run("xwd", "-root", "-silent", "-out", remote)
    target = output / (stem + ".xwd")
    network.docker("cp", worker + ":" + remote, str(target))
    raw = target.read_bytes()
    header = struct.unpack(">25I", raw[:100])
    size, version, form, depth, width, height, _, order, _, _, _, bpp, stride, visual, red, green, blue, _, _, colors, *_ = header
    require(version == 7 and form == 2 and depth == 24 and order == 0 and bpp in (24, 32) and visual in (4, 5) and
            (red, green, blue) == (0xff0000, 0xff00, 0xff) and 0 < width <= 4096 and 0 < height <= 4096,
            "Unexpected QA XWD layout; original screenshot retained")
    pixels = raw[size + colors * 12:]
    step = bpp // 8
    require(stride >= width * step and len(pixels) == stride * height, "Incomplete QA XWD pixels")
    rows = []
    for y in range(height):
        row = pixels[y * stride:y * stride + width * step]
        rows.append(b"\0" + b"".join(bytes((row[x + 2], row[x + 1], row[x])) for x in range(0, len(row), step)))
    def chunk(kind, value):
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")
    (output / (stem + ".png")).write_bytes(data)


class PublicBrowsers:
    def __init__(self, qa):
        self.qa = qa.resolve()
        require(self.qa.name == "qa", "Explicit QA root required")
        controller = json.loads(network.docker("inspect", network.SERVER).stdout)[0]
        require(controller["Config"]["Labels"].get(PREFIX + "qa") == "network-20260913" and
                any(m["Source"] == str(self.qa / "config") and m["Destination"] == "/config" for m in controller["Mounts"]),
                "Controller does not belong to this QA root")
        self.client = network.SecureClient(self.qa)
        admin = json.loads((self.qa / "admin.json").read_text())
        self.admin = network.SecureClient(self.qa, username=admin["username"], private=admin["private_key"].encode(),
                                          public=admin["server_public_key"].encode())
        self.path = self.qa / "public-browser-state.json"
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.scope = hashlib.sha256(str(self.qa / "config/.config/sealskin/sessions.yml").encode()).hexdigest()

    def save(self):
        network.write_json(self.path, self.state)

    def snapshot(self, role):
        request = self.state["roles"][role]["request"]
        require(request["home_name"] in {"network-qa-home-a", "network-qa-home-b"}, "QA Home required")
        status, result = self.client.call("GET", "/api/profile-runtime/" + request["home_name"])
        require(status == 200, "QA inventory unavailable")
        return result

    def owned(self, role, identifier):
        value = json.loads(network.docker("inspect", identifier).stdout)[0]
        labels = value["Config"].get("Labels", {})
        require(labels.get(PREFIX + "scope") == self.scope and labels.get(PREFIX + "owner") == "network-qa" and
                labels.get(PREFIX + "home") == self.state["roles"][role]["request"]["home_name"], "Resource ownership mismatch")
        return value

    def journal(self, role):
        operation = self.state["roles"][role]["request"]["operation_id"]
        values = [json.loads(p.read_text()) for p in (self.qa / "config/.config/sealskin/profile-network-runtime").glob("*.json")]
        matches = [v for v in values if v["identity"]["operation"] == operation]
        require(len(matches) == 1 and matches[0]["identity"]["owner"] == "network-qa", "QA journal mismatch")
        return matches[0]

    def prepare(self, bundle, template, plan_path):
        require(not self.state, "Refusing to replace prepared browser state")
        spec = importlib.util.spec_from_file_location("public_dns_plan", Path(__file__).with_name("check-public-dns-ttl.py"))
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        plan = json.loads(plan_path.read_text())
        checker.validate_plan(plan)
        plan_sha = digest(plan)
        for role in ("before", "after"):
            node = bundle / role
            manifest = json.loads((node / "manifest.json").read_text())
            require(manifest["plan_sha256"] == plan_sha and manifest["endpoint"] == role, "Bundle DNS plan mismatch")
            for name, expected in manifest["files"].items():
                path = (node / name).resolve()
                require(path.is_relative_to(node) and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                        "Bundle content mismatch")
        endpoint = json.loads((bundle / "before/config.json").read_text())
        require(endpoint["endpoint_id"] == "before", "Before endpoint bundle required")
        names = {key: value.rstrip(".") for key, value in plan["names"].items()}
        require(endpoint["website_names"] == [names["direct"], names["upstream"]] and
                endpoint["proxy_name"] == names["bootstrap"], "Bundle names do not match the DNS plan")
        images = json.loads((self.qa / "images.json").read_text())
        app_template = json.loads(template.read_text())
        require(app_template["users"] == ["network-qa"], "QA application template required")
        allowed = json.loads((self.qa / "allow.json").read_text())
        allowed["images"] = sorted(set(allowed["images"] + [app_template["provider_config"]["image"]]))
        allowed["readonly_sources"] = sorted(set(allowed["readonly_sources"] + [
            m["Source"] for m in app_template["provider_config"]["docker_overrides"].get("mounts", [])]))
        require(images["relay"] in allowed["direct_images"], "DIRECT capability not prepared")
        network.write_json(self.qa / "allow.json", allowed)
        secrets_dir = self.qa / "config/.config/sealskin/network-secrets"
        credentials = json.loads((bundle / "before/credentials.json").read_text())
        references = {}
        for key, content in {"username": credentials["username"].encode(), "password": credentials["password"].encode(),
                             "probe_ca": (bundle / "before/ca.pem").read_bytes()}.items():
            path = secrets_dir / ("public-" + key)
            require(not path.exists(), "Refusing credential replacement")
            path.write_bytes(content)
            path.chmod(0o600)
            references[key + "_file"] = "/config/.config/sealskin/network-secrets/" + path.name
            references[key + "_sha256"] = hashlib.sha256(content).hexdigest()
        registry_path = self.qa / "config/.config/sealskin/profile-network-policies.json"
        registry = json.loads(registry_path.read_text())
        self.state = {"version": 1, "run_id": endpoint["run_id"], "endpoint_config": endpoint,
                      "plan": plan, "plan_sha256": plan_sha, "roles": {}}
        for role, suffix, name in [("direct", "a", endpoint["website_names"][0]), ("proxy", "b", endpoint["website_names"][1])]:
            home, profile, app_id = "network-qa-home-" + suffix, "network-qa-" + suffix, "camoufox-public-dns-" + role
            status, inventory = self.client.call("GET", "/api/profile-runtime/" + home)
            require(status == 200 and not any(inventory[key] for key in ("records", "workers", "resources")), "QA Home is occupied")
            browser_profile = self.qa / "storage/network-qa" / home / ".camoufox/profile"
            browser_profile.mkdir(mode=0o700, parents=True, exist_ok=False)
            nss = self.qa.parent / "nss-tools/extracted/usr"
            command = ["/lib64/ld-linux-x86-64.so.2", "--library-path", str(nss / "lib/x86_64-linux-gnu"), str(nss / "bin/certutil")]
            for arguments in [["-N", "--empty-password", "-d", "sql:" + str(browser_profile)],
                              ["-A", "-d", "sql:" + str(browser_profile), "-n", "Public DNS QA CA", "-t", "C,,", "-i", str(bundle / "before/ca.pem")]]:
                require(subprocess.run(command + arguments, capture_output=True).returncode == 0, "QA CA import failed")
            policy = dict(username="network-qa", profile_id=profile, home_name=home, application_id=app_id,
                          mode="direct" if role == "direct" else "proxy_required", relay_image=images["relay"], probe_image=images["probe"],
                          upstream_host="", upstream_port=0, username_file="", username_sha256="", password_file="", password_sha256="",
                          probe_url=f"https://{name}:{endpoint['ports']['https']}/probe", probe_timeout_seconds=10,
                          probe_ca_file=references["probe_ca_file"], probe_ca_sha256=references["probe_ca_sha256"])
            if role == "direct":
                resolver = plan["config"]["paths"]["direct"]
                policy.update(approved_resolver_id=resolver["resolver_id"], approved_resolver_ip=resolver["resolver_ipv4"])
            else:
                resolver = plan["config"]["paths"]["bootstrap"]
                policy.update(upstream_host=endpoint["proxy_name"], upstream_port=endpoint["ports"]["socks5"],
                              upstream_protocol="socks5", upstream_auth="username_password", **references,
                              bootstrap_resolver_id=resolver["resolver_id"], bootstrap_resolver_ip=resolver["resolver_ipv4"])
            # Use the installed candidate's real model/canonicalization.
            source = "from app.network_runtime import NetworkPolicy;import json;print(json.dumps(NetworkPolicy.model_validate(json.loads(" + repr(json.dumps(policy)) + ")).model_dump()))"
            policy = json.loads(network.docker("exec", "-w", "/app", network.SERVER, "python3", "-c", source).stdout)
            policy_id = "public-dns-" + role + "-" + endpoint["run_id"]
            registry["policies"][policy_id] = policy
            network.write_json(registry_path, registry)
            app = copy.deepcopy(app_template)
            app.update(id=app_id, source_app_id=app_id, name="Public DNS QA " + role)
            app["provider_config"].update(network_policy_id=policy_id, network_policy_sha256=digest(policy))
            status, _ = self.admin.call("POST", "/api/admin/apps/installed", app)
            require(status == 201, "QA application registration failed")
            request = dict(url=policy["probe_url"], application_id=app_id, home_name=home, profile_id=profile,
                           operation_id=uuid.uuid4().hex, network_policy_id=policy_id, network_policy_sha256=digest(policy),
                           language="zh_TW.UTF-8", timezone="Asia/Taipei", wayland_mode=False, launch_in_room_mode=False)
            stop = {key: request[key] for key in ("application_id", "profile_id", "operation_id", "network_policy_id", "network_policy_sha256")}
            stop["bootstrap_url"] = request["url"]
            self.state["roles"][role] = {"request": request, "stop": stop, "policy": policy, "website": name}
            self.save()
        return {"result": "PREPARED", "browsers_started": 0, "run_id": endpoint["run_id"], "plan_sha256": plan_sha}

    def start(self, role, output):
        entry = self.state["roles"][role]
        snapshot = self.snapshot(role)
        require(not any(snapshot[key] for key in ("records", "workers", "resources")), "QA generation already exists")
        started = time.time()
        status, result = self.client.call("POST", "/api/launch/url", entry["request"])
        network.write_json(output / (role + "-launch.json"), {"status": status, "result": result,
                                                            "started_at": started, "finished_at": time.time()})
        require(status == 200, "Public QA launch failed; inspect private evidence")
        entry["stop"]["session_id"] = result["session_id"]
        snapshot = self.snapshot(role)
        require(len(snapshot["workers"]) == len(snapshot["records"]) == 1, "Unexpected QA generation count")
        entry["worker"] = snapshot["workers"][0]["instance_id"]
        self.owned(role, entry["worker"])
        self.save()
        network.write_json(output / (role + "-generation.json"), snapshot)
        network.write_json(output / (role + "-journal.json"), self.journal(role))
        return {"result": "STARTED", "role": role, "operation_id": entry["request"]["operation_id"]}

    def stop(self, role, output):
        entry = self.state["roles"][role]
        snapshot = self.snapshot(role)
        network.write_json(output / (role + "-before-stop.json"), snapshot)
        if any(snapshot[key] for key in ("records", "workers", "resources")):
            status, result = self.client.call("POST", "/api/profile-runtime/" + entry["request"]["home_name"] + "/stop", entry["stop"])
            network.write_json(output / (role + "-stop.json"), {"status": status, "result": result})
            require(status == 204, "QA stop failed; retained resources require reconciliation")
        after = self.snapshot(role)
        require(not any(after[key] for key in ("records", "workers", "resources")), "QA resources still exist")
        return {"result": "STOPPED", "role": role}

    def new_operation(self, role, output):
        entry = self.state["roles"][role]
        snapshot = self.snapshot(role)
        require(not any(snapshot[key] for key in ("records", "workers", "resources")), "Stop the old QA generation first")
        network.write_json(output / (role + "-previous-operation.json"), entry)
        entry["request"]["operation_id"] = uuid.uuid4().hex
        entry["stop"]["operation_id"] = entry["request"]["operation_id"]
        entry["stop"].pop("session_id", None)
        entry.pop("worker", None)
        entry.pop("suspended", None)
        self.save()
        return {"result": "NEW_OPERATION", "role": role, "operation_id": entry["request"]["operation_id"]}

    def relay_restart(self, role, output):
        before = self.journal(role)
        identifier = before["allocation"]["relay_id"]
        self.owned(role, identifier)
        worker = self.owned(role, self.state["roles"][role]["worker"])
        network.write_json(output / (role + "-before-journal.json"), before)
        network.docker("restart", "-t", "3", identifier)
        after = self.journal(role)
        require(after["allocation"] == before["allocation"] and after.get("bootstrap_dns") == before.get("bootstrap_dns"),
                "Restart changed the frozen allocation or DNS observation")
        current = self.owned(role, worker["Id"])
        require(current["State"]["StartedAt"] == worker["State"]["StartedAt"] and current["State"]["Running"],
                "Relay restart changed the browser")
        network.write_json(output / (role + "-after-journal.json"), after)
        return {"result": "RELAY_RESTARTED", "role": role, "allocation_unchanged": True, "browser_unchanged": True}

    def suspend(self, role, output):
        entry = self.state["roles"][role]
        before = self.snapshot(role)
        journal = self.journal(role)
        worker = self.owned(role, entry["worker"])
        require(worker["Config"]["Labels"].get(PREFIX + "browser-shutdown") == "1", "Normal browser shutdown support required")
        require(not entry.get("suspended"), "QA generation is already suspended")
        entry["suspended"] = {"resources": {v["kind"]: v["id"] for v in before["resources"]},
                              "allocation": journal["allocation"], "bootstrap_dns": journal.get("bootstrap_dns")}
        self.save()
        network.write_json(output / (role + "-before-suspend.json"), before)
        started = time.time()
        network.docker("stop", "-t", "30", entry["worker"])
        stopped = self.owned(role, entry["worker"])
        messages = [line for line in network.docker("logs", entry["worker"]).stdout.splitlines()
                    if line.startswith("BROWSER_SHUTDOWN_")]
        require(stopped["State"]["ExitCode"] == 0 and not stopped["State"]["OOMKilled"] and
                messages[-1:] == ["BROWSER_SHUTDOWN_CONFIRMED"], "Normal QA browser shutdown failed")
        for kind in ("guard", "relay"):
            identifier = journal["allocation"][kind + "_id"]
            self.owned(role, identifier)
            network.docker("stop", "-t", "3", identifier)
        result = {"result": "SUSPENDED", "role": role, "started_at": started, "finished_at": time.time(),
                  "browser_exit_code": 0, "shutdown": messages[-1]}
        network.write_json(output / (role + "-suspend.json"), result)
        return result

    def resume(self, role, output, expected):
        entry = self.state["roles"][role]
        require(entry.get("suspended"), "An explicitly suspended QA generation is required")
        started = time.time()
        status, result = self.client.call("POST", "/api/profile-runtime/" + entry["request"]["home_name"] + "/resume", entry["stop"])
        network.write_json(output / (role + "-resume-api.json"), {"status": status, "result": result,
                                                                "started_at": started, "finished_at": time.time()})
        worker = self.owned(role, entry["worker"])
        if expected == "blocked":
            require(status == 503 and worker["State"]["Status"] == "exited", "Offline upstream unexpectedly resumed the browser")
        else:
            require(status == 200 and result["resumed"] is True and result["instance_id"] == entry["worker"],
                    "QA same-generation resume failed")
            require(result["steps"] == ["relay", "guard", "controller", "relay-accepting", "probe", "worker", "display", "committed"],
                    "Unexpected resume ordering")
        snapshot = self.snapshot(role)
        journal = self.journal(role)
        require({v["kind"]: v["id"] for v in snapshot["resources"]} == entry["suspended"]["resources"] and
                journal["allocation"] == entry["suspended"]["allocation"] and
                journal.get("bootstrap_dns") == entry["suspended"]["bootstrap_dns"], "Resume changed the frozen generation")
        network.write_json(output / (role + "-resumed-journal.json"), journal)
        if expected != "blocked":
            entry.pop("suspended")
            self.save()
        return {"result": "RESUME_BLOCKED" if expected == "blocked" else "RESUMED", "role": role,
                "same_generation": True, "allocation_unchanged": True}

    def capture_start(self, role, output):
        require(not self.state.get("captures", {}).get(role), "Finish existing QA captures first")
        images = json.loads((self.qa / "images.json").read_text())
        journal = self.journal(role)
        allocation = journal["allocation"]
        captures = self.state.setdefault("captures", {}).setdefault(role, [])
        for kind in ("guard", "relay"):
            instance = allocation[kind + "_id"]
            value = self.owned(role, instance)
            require(value["State"]["Running"] and value["HostConfig"]["NetworkMode"] != "host", "Running QA namespace required")
            if kind == "guard":
                interface, source = "eth0", allocation["guard_ip"]
            else:
                route = network.docker("exec", instance, "ip", "route", "get", self.state["endpoint_config"]["peer_ipv4"][0]).stdout
                interface = route.split(" dev ", 1)[1].split()[0]
                source = route.split(" src ", 1)[1].split()[0]
            require(interface in ("eth0", "eth1"), "Unexpected QA interface")
            name = "network-qa-public-wire-" + uuid.uuid4().hex[:12]
            script = Path(__file__).with_name("network-wire.py").resolve()
            identifier = network.docker("run", "-d", "--name", name,
                "--label", PREFIX + "qa=network-20260913", "--label", PREFIX + "public-dns-run=" + self.state["run_id"],
                "--network", "container:" + instance, "--cap-drop", "ALL", "--cap-add", "NET_RAW", "--read-only",
                "--security-opt", "no-new-privileges:true", "--memory", "64m", "--pids-limit", "16",
                "-v", str(script) + ":/run/wire.py:ro", "--entrypoint", "python3", images["probe"], "/run/wire.py",
                "--worker-ip", source, "--interface", interface, "--seconds", "900").stdout.strip()
            captures.append({"id": identifier, "name": name, "instance": instance, "kind": kind,
                             "source": source, "interface": interface, "allocation": allocation,
                             "frozen_upstream_ipv4": journal.get("upstream_ipv4", [None])[0],
                             "started_at": time.time(), "script": str(script)})
            self.save()
            network.wait(lambda: '"wire_capture_ready": true' in network.docker("logs", identifier).stdout,
                         "public QA packet metadata capture", seconds=15)
        network.write_json(output / (role + "-captures.json"), captures)
        return {"result": "CAPTURING", "role": role, "namespaces": ["guard", "relay"], "payloads_recorded": False}

    def capture_stop(self, role, output):
        captures = self.state.get("captures", {}).get(role, [])
        require(len(captures) == 2, "Expected two explicit QA captures")
        observations = []
        for capture in captures:
            value = json.loads(network.docker("inspect", capture["id"]).stdout)[0]
            labels = value["Config"].get("Labels", {})
            require(labels.get(PREFIX + "qa") == "network-20260913" and
                    labels.get(PREFIX + "public-dns-run") == self.state["run_id"] and
                    value["HostConfig"]["NetworkMode"] == "container:" + capture["instance"] and
                    any(m["Source"] == capture["script"] and m["Destination"] == "/run/wire.py" and not m["RW"]
                        for m in value["Mounts"]), "Capture ownership mismatch")
            network.write_json(output / (role + "-" + capture["kind"] + "-container.json"), value)
            network.docker("stop", "-t", "3", capture["id"])
            raw = network.docker("logs", capture["id"]).stdout
            (output / (role + "-" + capture["kind"] + "-wire.jsonl")).write_text(raw)
            rows = [json.loads(line) for line in raw.splitlines() if line.startswith("{")]
            wire = next(row for row in rows if "outbound" in row)
            require(wire["directionSource"] == "AF_PACKET.sll_pkttype == PACKET_OUTGOING", "Missing kernel packet direction")
            allocation = capture["allocation"]
            def allowed(flow):
                if flow["family"] != 4:
                    return False
                if capture["kind"] == "guard":
                    return flow["protocol"] == 6 and (
                        flow["destination"] == allocation["relay_ip"] and flow["destination_port"] == 1080 or
                        flow["destination"] == allocation["controller_ip"] and flow["source_port"] == 3000)
                if role == "proxy":
                    return flow["protocol"] == 6 and flow["destination"] == capture["frozen_upstream_ipv4"] and \
                        flow["destination_port"] == self.state["endpoint_config"]["ports"]["socks5"]
                resolver = self.state["roles"][role]["policy"]["approved_resolver_ip"]
                return (flow["destination"] == resolver and flow["destination_port"] == 53 and flow["protocol"] in (6, 17) or
                        flow["protocol"] == 6 and ipaddress.IPv4Address(flow["destination"]).is_global and
                        flow["destination"] not in self.state["endpoint_config"]["client_ipv4"] and
                        flow["destination_port"] not in (53, 853))
            forbidden = [flow for flow in wire["outbound"] if not allowed(flow)]
            observation = {**capture, "finished_at": time.time(), "flow_count": len(wire["outbound"]),
                           "forbidden": forbidden, "result": "PASS" if wire["outbound"] and not forbidden else "FAIL"}
            observations.append(observation)
            network.write_json(output / (role + "-" + capture["kind"] + "-capture-check.json"), observation)
            network.docker("rm", "-v", capture["id"])
        self.state["captures"].pop(role)
        self.save()
        require(all(v["result"] == "PASS" for v in observations), "QA packet path verification failed")
        return {"result": "CAPTURE_VERIFIED", "role": role, "namespaces": 2,
                "flows": sum(v["flow_count"] for v in observations), "forbidden_flows": 0}

    def bypass(self, role, output):
        entry = self.state["roles"][role]
        self.owned(role, entry["worker"])
        allocation = self.journal(role)["allocation"]
        other = self.journal("proxy" if role == "direct" else "direct")["allocation"]
        config = self.state["endpoint_config"]
        targets = [("website-" + str(i) + "-" + scheme, address, config["ports"][scheme], "tcp")
                   for i, address in enumerate(config["peer_ipv4"]) for scheme in ("http", "https")]
        targets += [("proxy-" + str(i), address, config["ports"]["socks5"], "tcp")
                    for i, address in enumerate(config["peer_ipv4"])]
        targets += [(label + "-" + transport, address, 53, transport)
                    for label, address in (("approved-dns", config["resolver"]["ipv4"]),
                                           ("unapproved-dns", "8.8.8.8"), ("docker-dns", "127.0.0.11"))
                    for transport in ("udp", "tcp")]
        targets += [("direct-doh", "1.1.1.1", 443, "tcp"), ("direct-dot", "1.1.1.1", 853, "tcp"),
                    ("controller", allocation["controller_ip"], 8000, "tcp"),
                    ("other-display", other["guard_ip"], 3000, "tcp"), ("other-relay", other["relay_ip"], 1080, "tcp"),
                    ("quic", config["peer_ipv4"][1], 443, "udp"), ("stun", config["peer_ipv4"][1], 3478, "udp"),
                    ("ipv6", "2606:4700:4700::1111", 443, "tcp")]
        query_name = "bypass-" + uuid.uuid4().hex + "." + config["zone"]
        def dropped():
            rules = json.loads(network.docker("exec", allocation["guard_id"], "nft", "-j", "list", "table", "inet", "bp_guard").stdout)
            return sum(e.get("counter", {}).get("packets", 0) for item in rules["nftables"]
                       if item.get("rule", {}).get("chain") == "output" and any("drop" in e for e in item["rule"]["expr"])
                       for e in item["rule"]["expr"])
        source = """import socket,struct,json,os
targets=TARGETS
name=NAME
query=struct.pack('!HHHHHH',1234,256,1,0,0,0)+b''.join(bytes([len(x)])+x.encode() for x in name.split('.'))+b'\\0'+struct.pack('!HH',1,1)
out=[]
for label,address,port,transport in targets:
 with socket.socket(socket.AF_INET6 if ':' in address else socket.AF_INET,socket.SOCK_DGRAM if transport=='udp' else socket.SOCK_STREAM) as s:
  s.settimeout(.4)
  try:
   s.connect((address,port))
   if transport=='udp':
    s.send(query if port==53 else os.urandom(1200));s.recv(4096)
   reachable=True
  except OSError:reachable=False
  out.append({'target':label,'address':address,'port':port,'transport':transport,'reachable':reachable})
print(json.dumps({'query':name,'results':out}))
""".replace("TARGETS", repr(targets)).replace("NAME", repr(query_name))
        before = dropped()
        started = time.time()
        result = json.loads(network.docker("exec", "--user", "1000", entry["worker"], "python3", "-c", source).stdout)
        result.update(started_at=started, finished_at=time.time(), drops_before=before, drops_after=dropped())
        network.write_json(output / (role + "-bypass.json"), result)
        require(all(not row["reachable"] for row in result["results"]) and result["drops_after"] > before,
                "QA Worker bypass was not blocked")
        return {"result": "BYPASS_BLOCKED", "role": role, "targets": len(targets), "query": query_name,
                "guard_drops": result["drops_after"] - before}

    def bridge_start(self, role, output):
        require(role == "proxy" and not self.state.get("bridge_capture"), "One proxy transition capture is supported")
        journal = self.journal(role)
        allocation = journal["allocation"]
        relay = self.owned(role, allocation["relay_id"])
        bridge = json.loads(network.docker("network", "inspect", allocation["egress_id"]).stdout)[0]
        labels = bridge["Labels"]
        require(labels.get(PREFIX + "scope") == self.scope and labels.get(PREFIX + "owner") == "network-qa" and
                labels.get(PREFIX + "home") == self.state["roles"][role]["request"]["home_name"] and
                set(bridge["Containers"]) == {relay["Id"]} and bridge["Driver"] == "bridge" and not bridge["Internal"],
                "Dedicated QA egress bridge required")
        interface = "br-" + bridge["Id"][:12]
        require(not bridge["Options"].get("com.docker.network.bridge.name") and Path("/sys/class/net", interface).exists(),
                "Default Docker QA bridge interface required")
        endpoint = bridge["Containers"][relay["Id"]]
        source = endpoint["IPv4Address"].split("/")[0]
        mac = endpoint["MacAddress"].lower()
        images = json.loads((self.qa / "images.json").read_text())
        script = Path(__file__).with_name("public-dns-bridge-wire.py").resolve()
        name = "network-qa-public-bridge-" + uuid.uuid4().hex[:12]
        identifier = network.docker("run", "-d", "--name", name,
            "--label", PREFIX + "qa=network-20260913", "--label", PREFIX + "public-dns-run=" + self.state["run_id"],
            "--network", "host", "--cap-drop", "ALL", "--cap-add", "NET_RAW", "--read-only",
            "--security-opt", "no-new-privileges:true", "--memory", "64m", "--pids-limit", "16",
            "-v", str(script) + ":/run/bridge-wire.py:ro", "--entrypoint", "python3", images["probe"],
            "/run/bridge-wire.py", "--interface", interface, "--relay-ip", source, "--relay-mac", mac, "--seconds", "900").stdout.strip()
        self.state["bridge_capture"] = {"id": identifier, "interface": interface, "network": bridge["Id"],
            "relay_id": relay["Id"], "source": source, "mac": mac, "script": str(script), "started_at": time.time(),
            "frozen_upstream": journal["upstream_ipv4"][0], "upstream_port": self.state["endpoint_config"]["ports"]["socks5"]}
        self.save()
        network.wait(lambda: '"bridge_capture_ready": true' in network.docker("logs", identifier).stdout,
                     "QA bridge transition capture", seconds=15)
        network.write_json(output / "proxy-bridge-capture.json", {**self.state["bridge_capture"], "bridge_inspect": bridge})
        return {"result": "BRIDGE_CAPTURING", "role": role, "interface": interface, "payloads_recorded": False}

    def bridge_stop(self, role, output):
        require(role == "proxy" and self.state.get("bridge_capture"), "Explicit proxy transition capture required")
        capture = self.state["bridge_capture"]
        value = json.loads(network.docker("inspect", capture["id"]).stdout)[0]
        require(value["Config"]["Labels"].get(PREFIX + "public-dns-run") == self.state["run_id"] and
                value["HostConfig"]["NetworkMode"] == "host" and
                any(m["Source"] == capture["script"] and m["Destination"] == "/run/bridge-wire.py" and not m["RW"]
                    for m in value["Mounts"]), "Transition capture ownership mismatch")
        self.owned(role, capture["relay_id"])
        bridge = json.loads(network.docker("network", "inspect", capture["network"]).stdout)[0]
        require(bridge["Labels"].get(PREFIX + "scope") == self.scope and
                set(bridge["Containers"]) == {capture["relay_id"]} and
                bridge["Containers"][capture["relay_id"]]["IPv4Address"].split("/")[0] == capture["source"],
                "QA egress attachment changed during transition capture")
        network.write_json(output / "proxy-bridge-container.json", value)
        network.docker("stop", "-t", "3", capture["id"])
        raw = network.docker("logs", capture["id"]).stdout
        (output / "proxy-bridge-wire.jsonl").write_text(raw)
        rows = [json.loads(line) for line in raw.splitlines() if line.startswith("{")]
        summary = next(row for row in rows if row.get("bridge_capture_complete"))
        require(summary["directionSource"] == "Dedicated QA bridge ingress: AF_PACKET.sll_pkttype != PACKET_OUTGOING; sole Relay attachment",
                "Missing bridge ingress direction evidence")
        forbidden = [row for row in summary["flows"] if row["family"] != 4 or row["protocol"] != 6 or
                     row["source"] != capture["source"] or row["packet_type"] == 4 or
                     row["destination"] != capture["frozen_upstream"] or row["destination_port"] != capture["upstream_port"]]
        result = {"result": "PASS" if summary["flows"] and not forbidden else "FAIL", **capture,
                  "finished_at": summary["finished_at"], "flows": len(summary["flows"]), "forbidden": forbidden,
                  "final_mac": bridge["Containers"][capture["relay_id"]]["MacAddress"].lower(),
                  "observed_macs": sorted({row["source_mac_hex"] for row in summary["flows"]}), "bridge_after": bridge}
        network.write_json(output / "proxy-bridge-check.json", result)
        network.docker("rm", "-v", capture["id"])
        self.state.pop("bridge_capture")
        self.save()
        require(result["result"] == "PASS", "Proxy transition path verification failed")
        return {"result": "BRIDGE_CAPTURE_VERIFIED", "role": role, "flows": result["flows"], "forbidden_flows": 0}

    def dns_start(self, role, output):
        require(role == "direct" and not self.state.get("dns_capture"), "One DIRECT DNS capture is supported")
        capture = next(value for value in self.state["captures"][role] if value["kind"] == "relay")
        self.owned(role, capture["instance"])
        images = json.loads((self.qa / "images.json").read_text())
        wheels = list((self.qa.parent / "build").rglob("dnspython-2.8.0-py3-none-any.whl"))
        require(len(wheels) == 1, "One locked DNS wheel required")
        script = Path(__file__).with_name("public-dns-wire.py").resolve()
        resolver = self.state["roles"][role]["policy"]["approved_resolver_ip"]
        name = "network-qa-public-dns-" + uuid.uuid4().hex[:12]
        identifier = network.docker("run", "-d", "--name", name,
            "--label", PREFIX + "qa=network-20260913", "--label", PREFIX + "public-dns-run=" + self.state["run_id"],
            "--network", "container:" + capture["instance"], "--cap-drop", "ALL", "--cap-add", "NET_RAW", "--read-only",
            "--security-opt", "no-new-privileges:true", "--memory", "64m", "--pids-limit", "16",
            "-v", str(script) + ":/run/dns-wire.py:ro", "-v", str(wheels[0]) + ":/run/dnspython.whl:ro",
            "--entrypoint", "python3", images["probe"], "/run/dns-wire.py", "--source", capture["source"],
            "--interface", capture["interface"], "--resolver", resolver, "--name", self.state["plan"]["names"]["direct"],
            "--wheel", "/run/dnspython.whl", "--seconds", "900").stdout.strip()
        self.state["dns_capture"] = {"id": identifier, "instance": capture["instance"], "script": str(script),
                                     "resolver": resolver, "started_at": time.time(), "plan_sha256": self.state["plan_sha256"]}
        self.save()
        network.wait(lambda: '"dns_capture_ready": true' in network.docker("logs", identifier).stdout, "DIRECT DNS capture", seconds=15)
        network.write_json(output / "direct-dns-capture.json", self.state["dns_capture"])
        return {"result": "DNS_CAPTURING", "role": role, "names": [self.state["plan"]["names"]["direct"]]}

    def dns_stop(self, role, output):
        require(role == "direct" and self.state.get("dns_capture"), "Explicit DIRECT DNS capture required")
        capture = self.state["dns_capture"]
        value = json.loads(network.docker("inspect", capture["id"]).stdout)[0]
        require(value["Config"]["Labels"].get(PREFIX + "public-dns-run") == self.state["run_id"] and
                value["HostConfig"]["NetworkMode"] == "container:" + capture["instance"] and
                any(m["Source"] == capture["script"] and m["Destination"] == "/run/dns-wire.py" and not m["RW"]
                    for m in value["Mounts"]), "DNS capture ownership mismatch")
        network.write_json(output / "direct-dns-container.json", value)
        network.docker("stop", "-t", "3", capture["id"])
        raw = network.docker("logs", capture["id"]).stdout
        (output / "direct-dns-wire.jsonl").write_text(raw)
        rows = [json.loads(line) for line in raw.splitlines() if line.startswith("{")]
        summary = next(row for row in rows if row.get("dns_capture_complete"))
        require(summary["exchanges"] > 0 and summary["tcp_frames"] == 0, "Complete UDP DNS exchanges required; TCP needs separate verification")
        network.write_json(output / "direct-dns-capture.json", {**capture, **summary})
        network.docker("rm", "-v", capture["id"])
        self.state.pop("dns_capture")
        self.save()
        return {"result": "DNS_CAPTURED", "role": role, "exchanges": summary["exchanges"], "verification": "PENDING"}

    def visit(self, role, output, expected):
        entry = self.state["roles"][role]
        self.owned(role, entry["worker"])
        control = desktop.Desktop(entry["worker"])
        started = time.time()
        nonce = uuid.uuid4().hex
        url = f"http://{entry['website']}:{self.state['endpoint_config']['ports']['http']}/test?nonce={nonce}"
        network.wait(lambda: bool(control.available_title()), "public QA browser window", seconds=60)
        for _ in range(3):
            control.key("ctrl+l")
            control.key("ctrl+a")
            control.type(url)
            control.key("ctrl+a")
            control.key("ctrl+c")
            copied = ""
            copy_deadline = time.monotonic() + 2
            while time.monotonic() < copy_deadline:
                clipboard = network.docker("exec", "--user", "1000", "-e", "DISPLAY=:1", entry["worker"],
                                           "xclip", "-selection", "clipboard", "-t", "UTF8_STRING", "-o", check=False)
                if clipboard.returncode == 0 and clipboard.stdout == url:
                    copied = clipboard.stdout
                    break
                time.sleep(.1)
            if copied == url:
                break
            time.sleep(.2)
        else:
            raise ValueError("QA address bar mismatch")
        control.key("Return")
        observed = None
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if control.available_title().startswith("R5C2 "):
                window = control.run("xdotool", "getactivewindow").strip()
                control.run("xdotool", "mousemove", "--window", window, "400", "300", "click", "1")
                control.key("ctrl+a")
                control.key("ctrl+c")
                try:
                    clipboard = network.docker("exec", "--user", "1000", "-e", "DISPLAY=:1", entry["worker"],
                                               "xclip", "-selection", "clipboard", "-t", "UTF8_STRING", "-o", check=False)
                    value = json.loads(clipboard.stdout) if clipboard.returncode == 0 else None
                    if not isinstance(value, dict):
                        continue
                    if value.get("nonce") == nonce:
                        observed = value
                        break
                except (ValueError, AttributeError):
                    pass
            time.sleep(.5)
        result = {"role": role, "url": url, "nonce": nonce, "observed": observed, "title": control.available_title(),
                  "expected_endpoint": expected, "started_at": started, "captured_at": time.time(),
                  "plan_sha256": self.state["plan_sha256"]}
        network.write_json(output / (role + "-browser.json"), result)
        screenshot(control, entry["worker"], output, role + "-browser")
        require(observed is not None and observed.get("status") == "PASS" and all(
            observed.get(kind, {}).get("endpoint") == expected and observed[kind].get("nonce") == nonce
            for kind in ("http", "https", "ws", "wss")), "Public browser transport observation failed")
        network.write_json(output / (role + "-journal.json"), self.journal(role))
        return {"result": "OBSERVED", "role": role, "nonce": nonce, "endpoint": expected, "transports": ["http", "https", "ws", "wss"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "start", "visit", "snapshot", "stop", "new-operation", "relay-restart", "suspend", "resume",
                                          "capture-start", "capture-stop", "bypass", "dns-start", "dns-stop", "bridge-start", "bridge-stop"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--role", choices=("direct", "proxy", "both"), default="both")
    parser.add_argument("--expect", choices=("before", "after", "blocked"))
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    run = PublicBrowsers(args.root)
    results = []
    try:
        if args.action == "prepare":
            require(args.bundle and args.template and args.plan, "Bundle, plan and QA application template required")
            results.append(run.prepare(args.bundle.resolve(), args.template.resolve(), args.plan.resolve()))
        else:
            for role in ("direct", "proxy") if args.role == "both" else (args.role,):
                if args.action == "visit":
                    require(args.expect in ("before", "after"), "Expected website endpoint required")
                    result = run.visit(role, args.output, args.expect)
                elif args.action == "resume":
                    require(args.expect, "Expected resume result required")
                    result = run.resume(role, args.output, args.expect)
                elif args.action == "snapshot":
                    network.write_json(args.output / (role + "-generation.json"), run.snapshot(role))
                    network.write_json(args.output / (role + "-journal.json"), run.journal(role))
                    result = {"result": "CAPTURED", "role": role}
                else:
                    result = getattr(run, args.action.replace("-", "_"))(role, args.output)
                results.append(result)
                print(json.dumps(result), flush=True)
        network.write_json(args.output / "results.json", {"result": "SCOPED_PASS", "observations": results, "r5c2_acceptance": "NOT_COMPLETE"})
    except Exception as exc:
        network.write_json(args.output / "failure.json", {"action": args.action, "error_type": type(exc).__name__,
                                                         "completed_observations": results})
        raise


if __name__ == "__main__":
    main()
