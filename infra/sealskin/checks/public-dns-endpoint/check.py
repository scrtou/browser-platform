#!/usr/bin/env python3
"""Exercise the standalone service on loopback; never public TTL evidence."""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import socketserver
import ssl
import struct
import subprocess
import sys
import threading
import time

from endpoint import WHEEL, atomic_json, load_dependency, require


def exact(connection, length):
    data = b""
    while len(data) < length:
        part = connection.recv(length - len(data))
        if not part:
            raise EOFError("test connection closed")
        data += part
    return data


def header(connection):
    data = b""
    while not data.endswith(b"\r\n\r\n"):
        data += exact(connection, 1)
        require(len(data) <= 8192, "TEST_HEADER_LIMIT")
    return data


class DNSServer:
    def __init__(self):
        self.mode = "before"
        self.events = []
        owner = self
        class UDP(socketserver.BaseRequestHandler):
            def handle(self):
                raw, connection = self.request
                answer = owner.answer(raw, "udp")
                if answer:
                    connection.sendto(answer, self.client_address)
        class TCP(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(6)
                raw = exact(self.request, struct.unpack("!H", exact(self.request, 2))[0])
                answer = owner.answer(raw, "tcp")
                if answer:
                    self.request.sendall(struct.pack("!H", len(answer)) + answer)
        self.udp = socketserver.ThreadingUDPServer(("127.0.0.1", 0), UDP)
        self.port = self.udp.server_address[1]
        self.tcp = socketserver.ThreadingTCPServer(("127.0.0.1", self.port), TCP)
        for server in (self.udp, self.tcp):
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def answer(self, raw, transport):
        import dns.flags
        import dns.message
        import dns.rcode
        import dns.rrset
        request = dns.message.from_wire(raw)
        self.events.append({"time": time.time(), "transport": transport, "mode": self.mode,
                            "name": request.question[0].name.to_text(), "request_wire_hex": raw.hex()})
        if self.mode == "timeout":
            return None
        response = dns.message.make_response(request)
        response.flags |= dns.flags.RA
        if self.mode == "nxdomain":
            response.set_rcode(dns.rcode.NXDOMAIN)
        elif self.mode == "truncate" and transport == "udp":
            response.flags |= dns.flags.TC
        else:
            addresses = ["127.0.0.2" if self.mode == "after" else "127.0.0.1"]
            if self.mode == "mixed":
                addresses.append("127.0.0.99")
            response.answer = [dns.rrset.from_text(request.question[0].name, 7, "IN", "A", *addresses)]
        if self.mode == "wrong-id":
            response.id ^= 1
        return response.to_wire()

    def close(self):
        for server in (self.udp, self.tcp):
            server.shutdown()
            server.server_close()


class Checks:
    def __init__(self, bundle, output):
        self.output = output
        self.results, self.processes, self.nodes, self.handles = [], [], {}, []
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        load_dependency(bundle / "before")
        self.dns = DNSServer()
        reserved = []
        for _ in range(5):
            connection = socket.socket()
            connection.bind(("127.0.0.1", 0))
            reserved.append(connection)
        ports = dict(zip(("http", "https", "socks5", "http_proxy", "https_proxy"),
                         (connection.getsockname()[1] for connection in reserved)))
        for index, role in enumerate(("before", "after"), 1):
            node = output / role
            shutil.copytree(bundle / role, node)
            node.chmod(0o700)
            shutil.copyfile(Path(__file__).with_name("endpoint.py"), node / "endpoint.py")
            config = json.loads((node / "config.json").read_text())
            config.update(public_ipv4="127.0.0." + str(index), bind_ipv4="127.0.0." + str(index),
                          peer_ipv4=["127.0.0.1", "127.0.0.2"], client_ipv4=["127.0.0.1"], ports=ports,
                          resolver={"id": "loopback-synthetic-only", "ipv4": "127.0.0.1", "port": self.dns.port},
                          connection_seconds=15, lifetime_seconds=180)
            atomic_json(node / "config.json", config)
            self.nodes[role] = config
        for connection in reserved:
            connection.close()
        self.config = self.nodes["before"]
        self.secret = json.loads((output / "before/credentials.json").read_text())
        self.tls = ssl.create_default_context(cafile=output / "before/ca.pem")
        self.nonce = secrets.token_hex(16)
        for role in ("before", "after"):
            node = output / role
            log = (node / "console.log").open("wb")
            self.handles.append(log)
            process = subprocess.Popen([sys.executable, str(node / "endpoint.py"), "--config", str(node / "config.json"),
                                        "--isolated-loopback-test"], stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            self.processes.append(process)
            deadline = time.monotonic() + 8
            while not (node / "state/ready.json").exists():
                require(process.poll() is None and time.monotonic() < deadline, "SERVICE_START_FAILED")
                time.sleep(0.05)

    def run(self, name, operation):
        started = time.monotonic()
        try:
            detail = operation()
            self.results.append({"name": name, "result": "PASS", "detail": detail,
                                 "elapsed_seconds": time.monotonic() - started})
        except Exception as exc:
            self.results.append({"name": name, "result": "FAIL", "error_type": type(exc).__name__,
                                 "elapsed_seconds": time.monotonic() - started})
        print(json.dumps(self.results[-1]), flush=True)

    def curl(self, protocol=None, scheme="http", password=None, expected="before", target=None, port=None):
        host = target or self.config["website_names"][0]
        port = port or self.config["ports"][scheme]
        options = ["silent", "show-error", "fail", "http1.1", 'noproxy = ""', "max-time = 8",
                   f'url = "{scheme}://{host}:{port}/echo?nonce={self.nonce}"',
                   f'cacert = "{self.output / "before/ca.pem"}"']
        if protocol:
            proxy_host = self.config["proxy_name"]
            key = {"socks5h": "socks5", "http": "http_proxy", "https": "https_proxy"}[protocol]
            proxy_port = self.config["ports"][key]
            options += [f'proxy = "{protocol}://{proxy_host}:{proxy_port}"', "proxytunnel",
                        f'proxy-user = "{self.secret["username"]}:{password or self.secret["password"]}"',
                        f'proxy-cacert = "{self.output / "before/ca.pem"}"',
                        f'resolve = "{proxy_host}:{proxy_port}:127.0.0.1"']
        else:
            options += ['proxy = ""', f'resolve = "{host}:{port}:127.0.0.1"']
        process = subprocess.run(["curl", "--config", "-"], input="\n".join(options) + "\n",
                                 capture_output=True, text=True, timeout=10)
        if expected is None:
            require(process.returncode != 0, "EXPECTED_REJECTION")
            return {"curl_exit": process.returncode}
        require(process.returncode == 0, "TRANSPORT_FAILED")
        result = json.loads(process.stdout)
        require(result["endpoint"] == expected and result["nonce"] == self.nonce, "WRONG_ENDPOINT")
        return {"endpoint": result["endpoint"], "nonce_matched": True}

    def socks(self, target=None, port=None):
        connection = socket.create_connection(("127.0.0.1", self.config["ports"]["socks5"]), timeout=6)
        connection.sendall(b"\x05\x01\x02")
        require(exact(connection, 2) == b"\x05\x02", "SOCKS_METHOD")
        username, password = (self.secret[key].encode() for key in ("username", "password"))
        connection.sendall(b"\x01" + bytes([len(username)]) + username + bytes([len(password)]) + password)
        require(exact(connection, 2) == b"\x01\x00", "SOCKS_AUTH")
        target = (target or self.config["website_names"][0]).encode()
        connection.sendall(b"\x05\x01\x00\x03" + bytes([len(target)]) + target + struct.pack("!H", port or self.config["ports"]["http"]))
        require(exact(connection, 10)[:2] == b"\x05\x00", "SOCKS_TARGET")
        return connection

    def websocket(self, secure):
        port = self.config["ports"]["https" if secure else "http"]
        host = self.config["website_names"][0]
        connection = socket.create_connection(("127.0.0.1", port), timeout=6)
        if secure:
            connection = self.tls.wrap_socket(connection, server_hostname=host)
        with connection:
            key = base64.b64encode(secrets.token_bytes(16)).decode()
            connection.sendall((f"GET /ws?nonce={self.nonce} HTTP/1.1\r\nHost: {host}:{port}\r\n"
                                f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: {key}\r\n\r\n").encode())
            require(header(connection).startswith(b"HTTP/1.1 101"), "WEBSOCKET_UPGRADE")
            mask = secrets.token_bytes(4)
            data = self.nonce.encode()
            connection.sendall(bytes([0x81, 0x80 | len(data)]) + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(data)))
            first, length = exact(connection, 2)
            require(first == 0x81, "WEBSOCKET_OPCODE")
            result = json.loads(exact(connection, length))
            require(result["endpoint"] == "before" and result["nonce"] == self.nonce, "WEBSOCKET_RESULT")
        return {"endpoint": "before", "nonce_matched": True}

    def offline(self, invalid=False):
        mode = self.output / "before/state/mode.json"
        try:
            with self.socks() as connection:
                host, port = self.config["website_names"][0], self.config["ports"]["http"]
                connection.sendall(f"GET /download?nonce={self.nonce} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
                require(header(connection).startswith(b"HTTP/1.1 200"), "DOWNLOAD_START")
                received = len(connection.recv(16384))
                if invalid:
                    mode.write_text("{}")
                else:
                    atomic_json(mode, {"mode": "offline"})
                connection.settimeout(2)
                while True:
                    data = connection.recv(16384)
                    if not data:
                        break
                    received += len(data)
                require(0 < received < 1048576, "OLD_TUNNEL_NOT_CLOSED")
            self.curl("socks5h", expected=None)
            self.curl(expected=None)
        finally:
            atomic_json(mode, {"mode": "online"})
            time.sleep(0.3)
        self.curl("socks5h")
        return {"interrupted_bytes": received, "new_requests_denied": True, "recovery": "PASS"}

    def dns_case(self, mode, expected):
        before = len(self.dns.events)
        self.dns.mode = mode
        try:
            result = self.curl("socks5h", expected=expected)
            events = self.dns.events[before:]
            require(bool(events), "NO_RESOLVER_QUERY")
            if mode == "truncate":
                require([item["transport"] for item in events] == ["udp", "tcp"], "NO_SAME_RESOLVER_TCP_FALLBACK")
            return {**result, "resolver_transports": [item["transport"] for item in events]}
        finally:
            self.dns.mode = "before"

    def rejected_without_dns(self, **arguments):
        before = len(self.dns.events)
        result = self.curl(expected=None, **arguments)
        require(len(self.dns.events) == before, "REJECTED_TARGET_REACHED_DNS")
        return result

    def source(self):
        for key in ("http_proxy", "https_proxy", "socks5"):
            with socket.create_connection(("127.0.0.1", self.config["ports"][key]), timeout=2,
                                          source_address=("127.0.0.2", 0)) as connection:
                require(connection.recv(1) == b"", "PEER_ALLOWED_AS_PROXY_CLIENT")
        return {"all_proxy_sources_restricted": True}

    def tls_silence(self):
        with socket.create_connection(("127.0.0.1", self.config["ports"]["https"]), timeout=6) as silent:
            started = time.monotonic()
            self.curl(scheme="https")
            require(time.monotonic() - started < 2, "TLS_LISTENER_BLOCKED")
            require(silent.recv(1) == b"", "TLS_HANDSHAKE_NOT_BOUNDED")
        return {"verified_request_during_silent_client": True, "silent_connection_closed": True}

    def capacity(self):
        connections = []
        try:
            for _ in range(self.config["max_connections"]):
                connections.append(socket.create_connection(("127.0.0.1", self.config["ports"]["https"]), timeout=2))
            time.sleep(0.2)
            with socket.create_connection(("127.0.0.1", self.config["ports"]["https"]), timeout=2) as extra:
                require(extra.recv(1) == b"", "CAPACITY_NOT_ENFORCED_BEFORE_TLS")
        finally:
            for connection in connections:
                connection.close()
            time.sleep(0.2)
        return {"concurrent_connections": self.config["max_connections"], "extra_rejected_before_tls": True}

    def certificate(self):
        for context, name in [(ssl.create_default_context(), self.config["website_names"][0]),
                              (self.tls, "outside.example.invalid")]:
            rejected = False
            try:
                with socket.create_connection(("127.0.0.1", self.config["ports"]["https"]), timeout=3) as raw:
                    with context.wrap_socket(raw, server_hostname=name):
                        pass
            except ssl.SSLCertVerificationError:
                rejected = True
            require(rejected, "TLS_IDENTITY_CHECK_NOT_ENFORCED")
        return {"untrusted_ca_rejected": True, "wrong_hostname_rejected": True}

    def load(self):
        def request(_):
            connection = http.client.HTTPConnection("127.0.0.1", self.config["ports"]["http"], timeout=5)
            try:
                host = self.config["website_names"][0] + ":" + str(self.config["ports"]["http"])
                connection.request("GET", "/echo?nonce=" + self.nonce, headers={"Host": host})
                response = connection.getresponse()
                result = json.loads(response.read())
                require(response.status == 200 and result["nonce"] == self.nonce, "LOAD_RESPONSE")
            finally:
                connection.close()
        started = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(request, range(80)))
        memory = {}
        for role, process in zip(("before", "after"), self.processes):
            values = {}
            for line in Path(f"/proc/{process.pid}/status").read_text().splitlines():
                key, value = line.split(":", 1)
                if key in {"VmRSS", "VmHWM", "VmSize", "Threads"}:
                    values[key] = value.strip()
            memory[role] = values
        return {"clients": 8, "requests": 80, "elapsed_seconds": time.monotonic() - started, "service_memory": memory}

    def client_storage_fixture(self):
        def request(host, path, secure=True):
            port = self.config["ports"]["https" if secure else "http"]
            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                tls_name = self.config["website_names"][0] if host == "127.0.0.1" else host
                stream = self.tls.wrap_socket(raw, server_hostname=tls_name) if secure else raw
                try:
                    stream.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n").encode())
                    response = http.client.HTTPResponse(stream)
                    response.begin()
                    return response.status, dict(response.getheaders()), response.read(65537)
                finally:
                    if secure:
                        stream.close()
        host = self.config["website_names"][0]
        status, headers, body = request(host, "/client?nonce=" + self.nonce)
        require(status == 200 and body == (self.output / "before/client-fixture.html").read_bytes(), "CLIENT_FIXTURE_BODY")
        require(headers.get("Cache-Control") == "no-store" and headers.get("X-Content-Type-Options") == "nosniff",
                "CLIENT_FIXTURE_HEADERS")
        faults = [(host, "/client", True), (host, "/client?nonce=invalid", True),
                  (host, "/client?nonce=" + self.nonce + "&nonce=" + self.nonce, True),
                  (host, "/client?nonce=" + self.nonce + "&result=PASS", True),
                  (host, "/client?nonce=" + self.nonce, False),
                  ("127.0.0.1", "/client?nonce=" + self.nonce, True)]
        if self.config.get("coherence_domain"):
            faults.append((self.config["coherence_domain"], "/client?nonce=" + self.nonce, True))
        for hostname, path, secure in faults:
            try:
                status, _, _ = request(hostname, path, secure)
                require(status >= 400, "CLIENT_FIXTURE_SCOPE_BYPASS")
            except (OSError, http.client.HTTPException):
                pass
        return {"fixed_page": True, "scope_rejections": len(faults), "browser_storage": "NOT_RUN"}

    def coherence(self):
        domain = self.config["coherence_domain"]
        port = self.config["ports"]["https"]
        sensitive = ["qa-cookie-never-echo", "qa-authorization-never-echo"]
        self.coherence_sensitive = sensitive
        def request(host, path, extra=""):
            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                with self.tls.wrap_socket(raw, server_hostname=host) as tls:
                    tls.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n"+extra+"\r\n").encode())
                    response = http.client.HTTPResponse(tls)
                    response.begin()
                    return response.status, dict(response.getheaders()), response.read(65537)
        for phase,host in (("preflight",domain),("browser",self.nonce+"."+domain)):
            status,headers,body=request(host,"/whoami?nonce="+self.nonce+"&phase="+phase,
                "X-Forwarded-For: 8.8.8.8\r\nCookie: "+sensitive[0]+"\r\nAuthorization: Bearer "+sensitive[1]+"\r\n")
            value=json.loads(body)
            require(status==200 and value["public_ip"]=="127.0.0.1" and value["source_kind"]=="socket" and value["nonce"]==self.nonce,
                    "COHERENCE_SOCKET_SOURCE")
            require(set(value)=={"version","nonce","phase","public_ip","source_kind","server_time"},"COHERENCE_SCHEMA")
            require(all(s.encode() not in body for s in sensitive) and headers.get("Cache-Control")=="no-store", "COHERENCE_PRIVATE_FIELDS")
        status,headers,body=request(self.nonce+"."+domain,"/environment-test.html?nonce="+self.nonce+"&voices=0")
        require(status==200 and b"getVoices" in body and "sha256-" in headers.get("Content-Security-Policy",""),"COHERENCE_PAGE_CSP")
        rejected=0
        for host,path in ((domain,"/whoami?nonce="+self.nonce+"&phase=browser"),
                          (self.nonce+"."+domain,"/whoami?nonce="+"b"*32+"&phase=browser"),
                          (domain,"/whoami?nonce="+self.nonce+"&phase=preflight&extra=yes")):
            try:
                status,_,_=request(host,path)
                require(status>=400,"COHERENCE_INVALID_REQUEST_ACCEPTED")
            except (OSError,http.client.HTTPException):
                pass
            rejected+=1
        return {"socket_attribution":True,"ignored_forwarded_headers":True,"no_credentials_echoed":True,"nonce_rejections":rejected,"page_csp":True}

    def rotation(self):
        state = self.output / "before/state/rotation.json"
        domain, port = self.config["coherence_domain"], self.config["ports"]["https"]
        def whoami():
            with self.socks(domain, port) as raw:
                with self.tls.wrap_socket(raw, server_hostname=domain) as tls:
                    tls.sendall((f"GET /whoami?nonce={self.nonce}&phase=preflight HTTP/1.1\r\n"
                                 f"Host: {domain}:{port}\r\nConnection: close\r\n\r\n").encode())
                    response = http.client.HTTPResponse(tls)
                    response.begin()
                    require(response.status == 200, "ROTATION_WHOAMI_FAILED")
                    return json.loads(response.read(8192))["public_ip"]
        require(whoami() == "127.0.0.1", "INITIAL_EXIT_SOURCE")
        try:
            with self.socks() as connection:
                host, website_port = self.config["website_names"][0], self.config["ports"]["http"]
                connection.sendall(f"GET /download?nonce={self.nonce} HTTP/1.1\r\nHost: {host}:{website_port}\r\n\r\n".encode())
                require(header(connection).startswith(b"HTTP/1.1 200"), "ROTATION_DOWNLOAD_START")
                atomic_json(state, {"exit": "peer"})
                received = 0
                while True:
                    data = connection.recv(16384)
                    if not data: break
                    received += len(data)
                require(received < 1048576, "ROTATION_OLD_CONNECTION_RETAINED")
            time.sleep(.3)
            require(whoami() == "127.0.0.2", "PEER_EXIT_SOURCE")
            self.dns.mode = "nxdomain"
            try: self.curl("socks5h", expected=None)
            finally: self.dns.mode = "before"
            state.write_text("{}")
            time.sleep(.3)
            self.curl("socks5h", expected=None)
        finally:
            atomic_json(state, {"exit": "local"})
            time.sleep(.3)
        require(whoami() == "127.0.0.1", "RESTORED_EXIT_SOURCE")
        return {"same_entry_actual_sources": ["127.0.0.1", "127.0.0.2", "127.0.0.1"],
                "old_tunnel_closed": True, "peer_dns_failure_no_fallback": True, "invalid_state_denied": True}

    def peer_rejections(self):
        before = len(self.dns.events)
        port = self.config["ports"]["https"]
        auth = base64.b64encode((self.secret["username"] + ":" + self.secret["peer_password"]).encode()).decode()
        for fault in ("source", "auth", "ordinary_password", "run", "target", "port"):
            source = "127.0.0.1" if fault == "source" else "127.0.0.2"
            authorization = auth
            if fault == "auth": authorization = "incorrect"
            elif fault == "ordinary_password": authorization = base64.b64encode((self.secret["username"] + ":" + self.secret["password"]).encode()).decode()
            run = "0" * 16 if fault == "run" else self.config["run_id"]
            target = "outside.example.invalid" if fault == "target" else self.config["website_names"][0]
            target_port = 22 if fault == "port" else port
            with socket.create_connection(("127.0.0.1", port), timeout=4, source_address=(source, 0)) as raw:
                with self.tls.wrap_socket(raw, server_hostname=self.config["proxy_name"]) as tls:
                    tls.sendall((f"CONNECT {target}:{target_port} HTTP/1.1\r\nHost: {target}:{target_port}\r\n"
                                 f"Proxy-Authorization: Basic {authorization}\r\nX-QA-Run: {run}\r\n\r\n").encode())
                    require(tls.recv(1) == b"", "PEER_REQUEST_ACCEPTED")
        require(len(self.dns.events) == before, "REJECTED_PEER_REACHED_DNS")
        return {"source_auth_run_target_and_port_rejections": 6, "dns_not_contacted": True}

    def close(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
                self.results.append({"name": "graceful_shutdown", "result": "FAIL"})
        self.dns.close()
        for handle in self.handles:
            handle.close()
        metrics = {}
        logs = ""
        for role in ("before", "after"):
            node = self.output / role
            if (node / "state/metrics.json").exists():
                metrics[role] = json.loads((node / "state/metrics.json").read_text())
            for path in (node / "state").glob("events.jsonl*"):
                logs += path.read_text()
            for name in ("server-key.pem", "credentials.json"):
                (node / name).unlink(missing_ok=True)
        require(self.secret["password"] not in logs and base64.b64encode(
            (self.secret["username"] + ":" + self.secret["password"]).encode()).decode() not in logs, "CREDENTIAL_LEAK_IN_LOG")
        if self.secret.get("peer_password"):
            require(self.secret["peer_password"] not in logs and base64.b64encode(
                (self.secret["username"] + ":" + self.secret["peer_password"]).encode()).decode() not in logs, "PEER_CREDENTIAL_LEAK_IN_LOG")
        require(all(value not in logs for value in getattr(self, "coherence_sensitive", [])), "COHERENCE_HEADER_LEAK_IN_LOG")
        atomic_json(self.output / "synthetic-dns-events.json", self.dns.events)
        result = {"result": "PASS" if self.results and all(item["result"] == "PASS" for item in self.results) else "FAIL",
                  "scope": "standalone endpoint loopback integration and footprint; DNS contents/TTL are synthetic",
                  "checks": self.results, "metrics": metrics, "public_acceptance": "NOT_RUN",
                  "endpoint_sha256": hashlib.sha256(Path(__file__).with_name("endpoint.py").read_bytes()).hexdigest(),
                  "credentials_absent_from_logs": True, "fixture_secrets_removed": True,
                  "all_service_processes_exited": all(process.poll() == 0 for process in self.processes)}
        if not result["all_service_processes_exited"]:
            result["result"] = "FAIL"
        atomic_json(self.output / "results.json", result)
        print(json.dumps({key: value for key, value in result.items() if key not in {"checks", "metrics"}}), flush=True)
        return result["result"] == "PASS"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    check = Checks(args.bundle.resolve(), args.output.resolve())
    try:
        for scheme in ("http", "https"):
            check.run("origin_" + scheme, lambda scheme=scheme: check.curl(scheme=scheme))
        for protocol in ("socks5h", "http", "https"):
            for scheme in ("http", "https"):
                check.run(protocol + "_proxy_to_" + scheme,
                          lambda protocol=protocol, scheme=scheme: check.curl(protocol, scheme))
            check.run(protocol + "_wrong_credentials",
                      lambda protocol=protocol: check.rejected_without_dns(protocol=protocol, password="intentionally-wrong"))
        check.run("websocket", lambda: check.websocket(False))
        check.run("secure_websocket", lambda: check.websocket(True))
        check.run("tls_identity", check.certificate)
        check.run("proxy_source_acl_before_tls", check.source)
        for target in ("outside.example.invalid", "127.0.0.99"):
            check.run("target_rejected_" + target, lambda target=target: check.rejected_without_dns(protocol="socks5h", target=target))
        check.run("target_port_rejected", lambda: check.rejected_without_dns(protocol="http", port=22))
        check.run("uncached_dns_selects_changed_endpoint", lambda: check.dns_case("after", "after"))
        check.run("dns_udp_to_tcp", lambda: check.dns_case("truncate", "before"))
        for mode in ("mixed", "nxdomain", "wrong-id", "timeout"):
            check.run("dns_rejects_" + mode, lambda mode=mode: check.dns_case(mode, None))
        check.run("offline_closes_existing_and_rejects_new", check.offline)
        check.run("invalid_mode_fails_closed_and_recovers", lambda: check.offline(True))
        check.run("silent_tls_isolated_and_times_out", check.tls_silence)
        check.run("bounded_capacity_including_tls_handshakes", check.capacity)
        check.run("eight_client_footprint", check.load)
        check.run("client_storage_fixture_scope", check.client_storage_fixture)
        if check.config.get("coherence_domain"):
            check.run("coherence_nonce_source_and_private_headers", check.coherence)
        if check.config.get("rotation_enabled"):
            check.run("peer_bridge_rejections", check.peer_rejections)
            check.run("actual_source_rotation_same_proxy_entry", check.rotation)
    finally:
        success = check.close()
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
