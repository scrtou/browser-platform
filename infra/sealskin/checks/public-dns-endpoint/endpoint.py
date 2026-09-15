#!/usr/bin/env python3
"""Bounded, authenticated endpoints for one public R5C2 DNS experiment.

This is a disposable QA service, not a general web server or forward proxy.
Only the approved client may use the proxies, and all targets are pinned to
the two experiment IPs, two exact website names and two website ports.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import fcntl
import hashlib
import hmac
import ipaddress
import json
import logging
import logging.handlers
import os
from pathlib import Path
import re
import resource
import signal
import socket
import ssl
import struct
import sys
import time
from urllib.parse import parse_qs, urlsplit

WHEEL = "dnspython-2.8.0-py3-none-any.whl"
WHEEL_SHA256 = "01d9bbc4a2d76bf0db7c1f729812ded6d912bd318d3b1cf81d30c0f845dbf3af"
PORT_NAMES = {"http", "https", "socks5", "http_proxy", "https_proxy"}
NONCE = re.compile(r"[a-f0-9]{32}")
LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class Rejected(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Rejected(code)


def load_dependency(directory):
    path = Path(directory) / WHEEL
    require(hashlib.sha256(path.read_bytes()).hexdigest() == WHEEL_SHA256,
            "DEPENDENCY_HASH_MISMATCH")
    sys.path.insert(0, str(path.resolve()))
    import dns
    require(dns.__version__ == "2.8.0", "DEPENDENCY_VERSION_MISMATCH")


def hostname(value):
    require(isinstance(value, str) and len(value) <= 253, "INVALID_HOSTNAME")
    value = value.rstrip(".").lower()
    require(all(LABEL.fullmatch(part) for part in value.split(".")), "INVALID_HOSTNAME")
    return value


def ipv4(value, isolated=False):
    address = ipaddress.IPv4Address(value)
    require(str(address) == value, "NONCANONICAL_IPV4")
    require(address.is_loopback if isolated else address.is_global, "INVALID_IP_SCOPE")
    return value


def validate(config, isolated=False):
    require(config.get("version") == 1, "CONFIG_VERSION")
    require(re.fullmatch(r"[a-f0-9]{16}", config["run_id"]) is not None, "RUN_ID")
    require(config["endpoint_id"] in {"before", "after"}, "ENDPOINT_ID")
    zone = hostname(config["zone"])
    require(zone == config["zone"] and "." in zone, "ZONE")
    if not isolated:
        require(not zone.endswith((".test", ".invalid", ".localhost", ".example")), "PUBLIC_ZONE_REQUIRED")
    expected = {role: f"{role}-{config['run_id']}.{zone}" for role in ("direct", "bootstrap", "upstream")}
    require(config["website_names"] == [expected["direct"], expected["upstream"]], "EXACT_WEBSITE_NAMES_REQUIRED")
    require(config["proxy_name"] == expected["bootstrap"], "EXACT_PROXY_NAME_REQUIRED")
    if config.get("coherence_domain"):
        require(config["coherence_domain"] == f"observe-{config['run_id']}.{zone}", "EXACT_OBSERVER_DOMAIN_REQUIRED")
    require(type(config.get("rotation_enabled", False)) is bool, "ROTATION_OPTION")
    require(not config.get("rotation_enabled") or config.get("coherence_domain"), "ROTATION_REQUIRES_COHERENCE")
    peers = config["peer_ipv4"]
    require(isinstance(peers, list) and len(peers) == len(set(peers)) == 2, "TWO_DISTINCT_PEERS_REQUIRED")
    for value in peers:
        ipv4(value, isolated)
    require(config["public_ipv4"] in peers, "ENDPOINT_NOT_IN_PEERS")
    require(isinstance(config["client_ipv4"], list) and 1 <= len(config["client_ipv4"]) <= 2, "CLIENT_LIST")
    for value in config["client_ipv4"]:
        ipv4(value, isolated)
    if config["bind_ipv4"] != "0.0.0.0" or isolated:
        ipv4(config["bind_ipv4"], isolated)
        require(config["bind_ipv4"] == config["public_ipv4"], "BIND_ADDRESS")
    resolver = config["resolver"]
    ipv4(resolver["ipv4"], isolated)
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", resolver["id"]) is not None, "RESOLVER_ID")
    require(type(resolver["port"]) is int and 1 <= resolver["port"] <= 65535, "RESOLVER_PORT")
    require(isolated or resolver["port"] == 53, "RESOLVER_PORT_MUST_BE_53")
    ports = config["ports"]
    require(set(ports) == PORT_NAMES and len(set(ports.values())) == 5, "LISTENER_PORTS")
    require(all(type(port) is int and 1024 <= port <= 65535 for port in ports.values()), "UNPRIVILEGED_PORTS_REQUIRED")
    for key, low, high in [("max_connections", 2, 32), ("connection_seconds", 5, 300),
                            ("lifetime_seconds", 10, 21600), ("connection_bytes", 65536, 16777216)]:
        require(type(config[key]) is int and low <= config[key] <= high, "INVALID_LIMIT_" + key.upper())
    for key in ("credentials_file", "certificate_file", "private_key_file"):
        require(config[key] in {"credentials.json", "server-cert.pem", "server-key.pem"}, "CONFIG_FILE_PATH")
    require(config["credentials_file"] == "credentials.json" and
            config["certificate_file"] == "server-cert.pem" and
            config["private_key_file"] == "server-key.pem", "CONFIG_FILE_MAPPING")
    return config


def private_file(path):
    info = path.stat()
    require(info.st_uid == os.getuid() and info.st_mode & 0o077 == 0 and not path.is_symlink(), "INSECURE_PRIVATE_FILE")
    return path.read_bytes()


def atomic_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, sort_keys=True)
        handle.write("\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


class Endpoint:
    def __init__(self, config, root):
        self.config, self.root = config, Path(root)
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700, exist_ok=True)
        require(not self.state.is_symlink() and self.state.stat().st_mode & 0o077 == 0, "INSECURE_STATE_DIRECTORY")
        secret = json.loads(private_file(self.root / config["credentials_file"]))
        expected_fields = {"username", "password"} | ({"peer_password"} if config.get("rotation_enabled") else set())
        require(set(secret) == expected_fields, "CREDENTIAL_FIELDS")
        self.username, self.password = (secret[key].encode("ascii") for key in ("username", "password"))
        require(1 <= len(self.username) <= 128 and 24 <= len(self.password) <= 128 and
                b":" not in self.username and all(33 <= byte <= 126 for byte in self.username + self.password), "CREDENTIAL_FORMAT")
        self.peer_password = secret.get("peer_password", "").encode("ascii")
        if config.get("rotation_enabled"):
            require(24 <= len(self.peer_password) <= 128 and all(33 <= byte <= 126 for byte in self.peer_password), "PEER_CREDENTIAL_FORMAT")
        private_file(self.root / config["private_key_file"])
        self.tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.tls.minimum_version = ssl.TLSVersion.TLSv1_2
        self.tls.load_cert_chain(self.root / config["certificate_file"], self.root / config["private_key_file"])
        self.logger = logging.Logger("r5c2-" + config["endpoint_id"])
        handler = logging.handlers.RotatingFileHandler(self.state / "events.jsonl", maxBytes=2097152, backupCount=2)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)
        self.clients, self.tunnels, self.tasks, self.servers = set(), set(), set(), []
        self.stop = asyncio.Event()
        self.mode = "offline"
        self.rotation = "local"
        self.started = time.monotonic()
        self.counts = {"accepted": 0, "denied": 0, "dns": 0, "origin": 0, "proxy": 0}

    def log(self, event, **fields):
        self.logger.info(json.dumps({"time": time.time(), "event": event, "run_id": self.config["run_id"],
                                    "endpoint": self.config["endpoint_id"], **fields}, separators=(",", ":")))

    def observation_host(self, value):
        domain = self.config.get("coherence_domain")
        if not domain or not isinstance(value, str):
            return False
        if value == domain:
            return True
        nonce, _, suffix = value.partition(".")
        return bool(NONCE.fullmatch(nonce) and suffix == domain)

    def website_host(self, value):
        return value in self.config["website_names"] or self.observation_host(value)

    async def resolve(self, target, connection_id):
        import dns.asyncquery
        import dns.flags
        import dns.message
        import dns.rcode
        import dns.rdataclass
        import dns.rdatatype
        require(self.website_host(target), "TARGET_NAME_DENIED")
        policy = self.config["resolver"]
        request = dns.message.make_query(target + ".", "A")
        self.counts["dns"] += 1
        deadline = time.monotonic() + 5
        response = None
        for transport in ("udp", "tcp"):
            started = time.time()
            self.log("dns_query", connection_id=connection_id, name=target, resolver=policy,
                     transport=transport, request_wire_hex=request.to_wire().hex())
            try:
                method = dns.asyncquery.udp if transport == "udp" else dns.asyncquery.tcp
                response = await method(request, policy["ipv4"], port=policy["port"],
                                        timeout=max(0.001, deadline - time.monotonic()))
                self.log("dns_response", connection_id=connection_id, transport=transport,
                         query_started=started, resolver=policy, response_wire_hex=response.to_wire().hex())
                require(request.is_response(response) and response.flags & dns.flags.QR and
                        response.flags & dns.flags.RA and not response.flags & dns.flags.AA and
                        response.rcode() == dns.rcode.NOERROR, "DNS_INVALID_RESPONSE")
                if response.flags & dns.flags.TC:
                    require(transport == "udp", "DNS_TRUNCATED_TCP")
                    continue
                break
            except Exception as exc:
                self.log("dns_failed", connection_id=connection_id, error_type=type(exc).__name__)
                raise Rejected("DNS_FAILED") from None
        require(response is not None and not response.flags & dns.flags.TC, "DNS_NO_ANSWER")
        require(len(response.answer) == 1, "DNS_UNEXPECTED_ANSWER")
        rrset = response.answer[0]
        require(rrset.name == request.question[0].name and rrset.rdclass == dns.rdataclass.IN and
                rrset.rdtype == dns.rdatatype.A and 1 <= len(rrset) <= 16, "DNS_UNEXPECTED_ANSWER")
        addresses = sorted({item.address for item in rrset})
        require(set(addresses) <= set(self.config["peer_ipv4"]), "DNS_ADDRESS_DENIED")
        self.log("dns_selected", connection_id=connection_id, name=target, resolver=policy,
                 addresses=addresses, selected=addresses[0], ttl_seconds=rrset.ttl)
        return addresses[0]

    async def connect(self, target, port, connection_id, allow_rotation=True):
        require(self.mode == "online", "OFFLINE")
        require(port in {self.config["ports"]["http"], self.config["ports"]["https"]}, "TARGET_PORT_DENIED")
        require(target in self.config["peer_ipv4"] or self.website_host(hostname(target)), "TARGET_NAME_DENIED")
        if allow_rotation and self.config.get("rotation_enabled"):
            route = self.read_rotation()
            require(route in {"local", "peer"}, "ROTATION_UNAVAILABLE")
            if route == "peer":
                return await self.connect_peer(target, port, connection_id)
        if target in self.config["peer_ipv4"]:
            address = target
        else:
            address = await self.resolve(hostname(target), connection_id)
        require(self.mode == "online", "OFFLINE")
        local = (self.config["public_ipv4"], 0) if ipaddress.ip_address(self.config["public_ipv4"]).is_loopback else None
        reader, writer = await asyncio.wait_for(asyncio.open_connection(address, port, family=socket.AF_INET,
                                                                        local_addr=local, limit=16384), 5)
        self.tunnels.add(writer)
        self.log("target_connected", connection_id=connection_id, target=target, address=address, port=port,
                 local=list(writer.get_extra_info("sockname")))
        return reader, writer

    async def connect_peer(self, target, port, connection_id):
        peer = next(ip for ip in self.config["peer_ipv4"] if ip != self.config["public_ipv4"])
        context = ssl.create_default_context(cafile=self.root / "ca.pem")
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        local = (self.config["public_ipv4"], 0) if ipaddress.ip_address(self.config["public_ipv4"]).is_loopback else None
        reader, writer = await asyncio.wait_for(asyncio.open_connection(peer, self.config["ports"]["https"],
                ssl=context, server_hostname=self.config["proxy_name"], ssl_handshake_timeout=5,
                family=socket.AF_INET, local_addr=local, limit=16384), 6)
        try:
            auth = base64.b64encode(self.username + b":" + self.peer_password).decode()
            writer.write((f"CONNECT {target}:{port} HTTP/1.1\r\nHost: {target}:{port}\r\n"
                          f"Proxy-Authorization: Basic {auth}\r\nX-QA-Run: {self.config['run_id']}\r\n\r\n").encode())
            await asyncio.wait_for(writer.drain(), 3)
            response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 6)
            require(response == b"HTTP/1.1 200 Connection Established\r\n\r\n", "PEER_CONNECT_REJECTED")
        except BaseException:
            writer.close()
            raise
        self.tunnels.add(writer)
        self.log("peer_tunnel_connected", connection_id=connection_id, peer=peer, target=target, port=port)
        return reader, writer

    async def peer_tunnel(self, reader, writer, target, headers, listener, connection_id):
        peer = writer.get_extra_info("peername")[0]
        require(self.config.get("rotation_enabled") and listener == "https" and
                peer in self.config["peer_ipv4"] and peer != self.config["public_ipv4"], "PEER_SOURCE_DENIED")
        require(self.read_rotation() in {"local", "peer"}, "ROTATION_UNAVAILABLE")
        expected = "Basic " + base64.b64encode(self.username + b":" + self.peer_password).decode()
        require(hmac.compare_digest(headers.get("proxy-authorization", ""), expected) and
                headers.get("x-qa-run") == self.config["run_id"], "PEER_AUTH_REJECTED")
        parsed = urlsplit("//" + target)
        require(parsed.hostname and not (parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment), "CONNECT_AUTHORITY")
        # The final endpoint always dials locally. A peer request cannot recurse
        # through the other peer or turn the two services into an open proxy.
        remote_reader, remote_writer = await self.connect(parsed.hostname, parsed.port, connection_id, allow_rotation=False)
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        self.log("peer_exit_connected", connection_id=connection_id, source=peer, target=parsed.hostname, port=parsed.port)
        await self.tunnel(reader, writer, remote_reader, remote_writer)

    async def pipe(self, reader, writer):
        total = 0
        while self.mode == "online" and not self.stop.is_set():
            data = await asyncio.wait_for(reader.read(16384), 15)
            if not data:
                return
            total += len(data)
            require(total <= self.config["connection_bytes"], "CONNECTION_BYTE_LIMIT")
            writer.write(data)
            await asyncio.wait_for(writer.drain(), 5)

    async def tunnel(self, reader, writer, remote_reader, remote_writer):
        self.tunnels.add(writer)
        tasks = [asyncio.create_task(self.pipe(reader, remote_writer)),
                 asyncio.create_task(self.pipe(remote_reader, writer))]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.tunnels.discard(writer)
            self.tunnels.discard(remote_writer)
            remote_writer.close()

    async def socks(self, reader, writer, connection_id):
        version, count = await reader.readexactly(2)
        require(version == 5 and count > 0, "SOCKS_GREETING")
        methods = await reader.readexactly(count)
        if 2 not in methods:
            writer.write(b"\x05\xff")
            await writer.drain()
            raise Rejected("AUTH_REQUIRED")
        writer.write(b"\x05\x02")
        await writer.drain()
        version, size = await reader.readexactly(2)
        username = await reader.readexactly(size)
        password = await reader.readexactly((await reader.readexactly(1))[0])
        if not (version == 1 and hmac.compare_digest(username, self.username) and
                hmac.compare_digest(password, self.password)):
            writer.write(b"\x01\x01")
            await writer.drain()
            raise Rejected("AUTH_REJECTED")
        writer.write(b"\x01\x00")
        await writer.drain()
        version, command, reserved, kind = await reader.readexactly(4)
        require((version, command, reserved) == (5, 1, 0), "SOCKS_CONNECT_ONLY")
        if kind == 3:
            target = (await reader.readexactly((await reader.readexactly(1))[0])).decode("ascii")
        elif kind == 1:
            target = str(ipaddress.IPv4Address(await reader.readexactly(4)))
        else:
            raise Rejected("SOCKS_IPV4_OR_DOMAIN_ONLY")
        port = struct.unpack("!H", await reader.readexactly(2))[0]
        try:
            remote_reader, remote_writer = await self.connect(target, port, connection_id)
        except (Rejected, OSError, asyncio.TimeoutError):
            writer.write(b"\x05\x02\x00\x01" + b"\0" * 6)
            await writer.drain()
            raise
        writer.write(b"\x05\x00\x00\x01" + b"\0" * 6)
        await writer.drain()
        self.counts["proxy"] += 1
        await self.tunnel(reader, writer, remote_reader, remote_writer)

    async def headers(self, reader):
        raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
        require(len(raw) <= 8192, "HEADER_LIMIT")
        lines = raw[:-4].decode("ascii").split("\r\n")
        method, target, version = lines[0].split(" ")
        require(version in {"HTTP/1.0", "HTTP/1.1"} and len(target) <= 2048, "HTTP_REQUEST")
        fields = {}
        for line in lines[1:]:
            key, value = line.split(":", 1)
            key = key.lower()
            require(re.fullmatch(r"[a-z0-9-]+", key) and key not in fields, "HTTP_HEADER")
            fields[key] = value.strip()
        require("transfer-encoding" not in fields and fields.get("content-length", "0") == "0", "HTTP_BODY_DENIED")
        return method, target, fields

    async def respond(self, writer, status, body=b"", content_type="application/json", extra=()):
        reasons = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found",
                   405: "Method Not Allowed", 407: "Proxy Authentication Required", 502: "Bad Gateway", 503: "Service Unavailable"}
        headers = [f"HTTP/1.1 {status} {reasons[status]}", f"Content-Length: {len(body)}",
                   f"Content-Type: {content_type}", "Connection: close", "Cache-Control: no-store", *extra, "", ""]
        writer.write("\r\n".join(headers).encode() + body)
        await asyncio.wait_for(writer.drain(), 5)

    async def http_proxy(self, reader, writer, connection_id):
        method, target, headers = await self.headers(reader)
        expected = "Basic " + base64.b64encode(self.username + b":" + self.password).decode()
        if not hmac.compare_digest(headers.get("proxy-authorization", ""), expected):
            await self.respond(writer, 407, extra=('Proxy-Authenticate: Basic realm="R5C2 QA"',))
            raise Rejected("AUTH_REJECTED")
        require(method == "CONNECT", "CONNECT_REQUIRED")
        parsed = urlsplit("//" + target)
        require(parsed.hostname and not (parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment), "CONNECT_AUTHORITY")
        try:
            remote_reader, remote_writer = await self.connect(parsed.hostname, parsed.port, connection_id)
        except (Rejected, OSError, asyncio.TimeoutError):
            await self.respond(writer, 502)
            raise
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        self.counts["proxy"] += 1
        await self.tunnel(reader, writer, remote_reader, remote_writer)

    def page(self, host, nonce):
        urls = {kind: f"{scheme}://{host}:{self.config['ports'][port]}/{path}?nonce={nonce}"
                for kind, scheme, port, path in [("http", "http", "http", "echo"), ("https", "https", "https", "echo"),
                                                 ("ws", "ws", "http", "ws"), ("wss", "wss", "https", "ws")]}
        data = json.dumps({"nonce": nonce, "urls": urls})
        return ("<!doctype html><meta charset=utf-8><title>R5C2 transport check</title><pre id=result>Running</pre>"
                "<script>const plan=" + data + ";window.qaResults={nonce:plan.nonce};"
                "const ws=url=>new Promise((resolve,reject)=>{const w=new WebSocket(url);"
                "const timer=setTimeout(()=>{w.close();reject(Error('timeout'))},8000);"
                "w.onopen=()=>w.send(plan.nonce);w.onmessage=e=>{clearTimeout(timer);w.close();resolve(JSON.parse(e.data))};"
                "w.onerror=()=>{clearTimeout(timer);reject(Error('websocket'))}});"
                "(async()=>{try{for(const [kind,url] of Object.entries(plan.urls)){"
                "const value=kind.startsWith('ws')?await ws(url):await (await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(8000)})).json();"
                "if(value.nonce!==plan.nonce||!['before','after'].includes(value.endpoint))throw Error('response');"
                "qaResults[kind]=value;}qaResults.status='PASS';}catch(e){qaResults.status='FAIL';qaResults.error=e.message;}"
                "document.querySelector('#result').textContent=JSON.stringify(qaResults,null,2);"
                "document.title='R5C2 '+qaResults.status;await fetch('/complete?nonce='+plan.nonce+'&result='+qaResults.status,{cache:'no-store'});})();"
                "</script>").encode()

    async def websocket(self, reader, writer, headers, nonce, connection_id):
        key = headers.get("sec-websocket-key", "")
        require(headers.get("upgrade", "").lower() == "websocket" and
                "upgrade" in [part.strip().lower() for part in headers.get("connection", "").split(",")] and
                headers.get("sec-websocket-version") == "13" and
                len(base64.b64decode(key, validate=True)) == 16, "WEBSOCKET_HANDSHAKE")
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        await writer.drain()
        self.tunnels.add(writer)
        try:
            while self.mode == "online":
                first, second = await reader.readexactly(2)
                size = second & 127
                if first == 0x88:
                    return
                require(first == 0x81 and second & 128 and size == 32, "WEBSOCKET_FRAME")
                mask = await reader.readexactly(4)
                encoded = await reader.readexactly(size)
                message = bytes(value ^ mask[index % 4] for index, value in enumerate(encoded))
                require(message == nonce.encode(), "WEBSOCKET_NONCE")
                body = json.dumps({"endpoint": self.config["endpoint_id"], "nonce": nonce}).encode()
                writer.write(bytes([0x81, len(body)]) + body)
                await writer.drain()
                self.log("websocket_echo", connection_id=connection_id, nonce=nonce)
        finally:
            self.tunnels.discard(writer)

    async def origin(self, reader, writer, listener, connection_id):
        method, target, headers = await self.headers(reader)
        if method == "CONNECT":
            return await self.peer_tunnel(reader, writer, target, headers, listener, connection_id)
        require(method == "GET", "GET_REQUIRED")
        parsed_host = urlsplit("//" + headers.get("host", ""))
        require((self.website_host(parsed_host.hostname) or parsed_host.hostname in self.config["peer_ipv4"]) and
                not (parsed_host.username or parsed_host.password or parsed_host.path or parsed_host.query or parsed_host.fragment) and
                parsed_host.port == self.config["ports"][listener], "HOST_DENIED")
        parsed = urlsplit(target)
        require(not parsed.netloc and not parsed.scheme and not parsed.fragment, "ORIGIN_FORM_REQUIRED")
        if self.observation_host(parsed_host.hostname):
            require(listener == "https", "OBSERVER_HTTPS_REQUIRED")
            return await self.observation_origin(writer, parsed_host.hostname, parsed, connection_id)
        params = parse_qs(parsed.query, strict_parsing=True, max_num_fields=2)
        nonce = params.get("nonce", [""])[0]
        require(set(params) <= {"nonce", "result"} and all(len(value) == 1 for value in params.values()), "QUERY_FIELDS")
        require(parsed.path in {"/probe", "/test", "/echo", "/ws", "/download", "/complete", "/client"}, "PATH_DENIED")
        require(parsed.path == "/probe" or NONCE.fullmatch(nonce) is not None, "NONCE_REQUIRED")
        if parsed.path == "/client":
            require(listener == "https" and parsed_host.hostname in self.config["website_names"] and
                    set(params) == {"nonce"}, "CLIENT_FIXTURE_SCOPE_REQUIRED")
        if self.mode != "online":
            await self.respond(writer, 503)
            return
        self.counts["origin"] += 1
        fields = {"connection_id": connection_id, "host": parsed_host.hostname, "path": parsed.path,
                  "nonce": nonce, "transport": listener, "source": writer.get_extra_info("peername")[0]}
        self.log("origin_request", **fields)
        body = json.dumps({"ok": True, "endpoint": self.config["endpoint_id"], "nonce": nonce}).encode()
        cors = ("Access-Control-Allow-Origin: *",)
        if parsed.path == "/test":
            await self.respond(writer, 200, self.page(parsed_host.hostname, nonce), "text/html; charset=utf-8")
        elif parsed.path == "/client":
            # The fixed QA page uses its own origin's synthetic browser data.
            # Observation hosts stay restricted to their separate allowlist.
            fixture = (self.root / "client-fixture.html").read_bytes()
            require(len(fixture) <= 65536, "CLIENT_FIXTURE_TOO_LARGE")
            await self.respond(writer, 200, fixture, "text/html; charset=utf-8",
                               extra=("X-Content-Type-Options: nosniff", "Referrer-Policy: no-referrer"))
        elif parsed.path == "/ws":
            await self.websocket(reader, writer, headers, nonce, connection_id)
        elif parsed.path == "/download":
            self.tunnels.add(writer)
            try:
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 1048576\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n")
                for _ in range(64):
                    require(self.mode == "online", "OFFLINE")
                    writer.write(b"r5c2-test-data\n".ljust(16384, b"."))
                    await asyncio.wait_for(writer.drain(), 5)
                    await asyncio.sleep(0.1)
            finally:
                self.tunnels.discard(writer)
        else:
            if parsed.path == "/complete":
                result = params.get("result", [""])[0]
                require(result in {"PASS", "FAIL"}, "BROWSER_RESULT")
                self.log("browser_report", **fields, reported_result=result)
            await self.respond(writer, 200, body, extra=cors)

    async def observation_origin(self, writer, host, parsed, connection_id):
        params = parse_qs(parsed.query, strict_parsing=True, max_num_fields=2)
        require(all(len(value) == 1 for value in params.values()), "QUERY_FIELDS")
        nonce = params.get("nonce", [""])[0]
        require(parsed.path in {"/health", "/whoami", "/environment-test.html"}, "PATH_DENIED")
        if parsed.path == "/health":
            require(not params and host == self.config["coherence_domain"], "QUERY_FIELDS")
        else:
            require(bool(NONCE.fullmatch(nonce)), "NONCE_REQUIRED")
            if parsed.path == "/whoami":
                require(set(params) == {"nonce", "phase"} and params["phase"][0] in {"preflight", "browser"}, "QUERY_FIELDS")
                expected = self.config["coherence_domain"] if params["phase"][0] == "preflight" else nonce + "." + self.config["coherence_domain"]
                require(host == expected, "NONCE_HOST_MISMATCH")
            else:
                require(set(params) == {"nonce", "voices"} and params["voices"][0].isdigit() and
                        0 <= int(params["voices"][0]) <= 256 and host == nonce + "." + self.config["coherence_domain"], "QUERY_FIELDS")
        if self.mode != "online":
            await self.respond(writer, 503)
            return
        peer = writer.get_extra_info("peername")[0]
        self.log("coherence_request", connection_id=connection_id, host=host, path=parsed.path,
                 nonce=nonce, phase=params.get("phase", [""])[0], source=peer)
        if parsed.path == "/environment-test.html":
            script = (self.root / "environment-test.js").read_bytes()
            require(len(script) < 32768, "PAGE_TOO_LARGE")
            sha = base64.b64encode(hashlib.sha256(script).digest()).decode()
            page = b'<!doctype html><meta charset="utf-8"><title>Environment observation</title><body><script>' + script + b'</script>'
            await self.respond(writer, 200, page, "text/html; charset=utf-8", extra=(
                "Content-Security-Policy: default-src 'none'; script-src 'sha256-" + sha + "'; connect-src 'self'; frame-ancestors 'none'",
                "Referrer-Policy: no-referrer", "X-Content-Type-Options: nosniff"))
        elif parsed.path == "/whoami":
            # The accepted socket is the source of truth. Headers are neither
            # trusted for attribution nor echoed into reports/logs.
            value = {"version": 1, "nonce": nonce, "phase": params["phase"][0],
                     "public_ip": peer, "server_time": time.time(), "source_kind": "socket"}
            await self.respond(writer, 200, json.dumps(value).encode())
        else:
            await self.respond(writer, 200, b'{"ok":true}')

    async def accepted(self, reader, writer, listener):
        peer = writer.get_extra_info("peername")[0]
        allowed = set(self.config["client_ipv4"])
        if listener in {"http", "https"}:
            allowed.update(self.config["peer_ipv4"])
        if peer not in allowed or len(self.clients) >= self.config["max_connections"]:
            self.counts["denied"] += 1
            self.log("connection_denied", listener=listener, source=peer,
                     reason="SOURCE_DENIED" if peer not in allowed else "CAPACITY")
            writer.close()
            return
        self.clients.add(writer)
        task = asyncio.current_task()
        self.tasks.add(task)
        self.counts["accepted"] += 1
        connection_id = os.urandom(8).hex()
        self.log("connection", connection_id=connection_id, listener=listener, source=peer)
        try:
            # Count and authorize raw TCP connections before allocating TLS
            # handshake state. Slow or unapproved clients share the same cap.
            if listener in {"https", "https_proxy"}:
                await writer.start_tls(self.tls, ssl_handshake_timeout=5)
            if listener == "socks5":
                operation = self.socks(reader, writer, connection_id)
            elif listener in {"http_proxy", "https_proxy"}:
                operation = self.http_proxy(reader, writer, connection_id)
            else:
                operation = self.origin(reader, writer, listener, connection_id)
            await asyncio.wait_for(operation, self.config["connection_seconds"])
        except Rejected as exc:
            self.log("request_rejected", connection_id=connection_id, code=str(exc))
        except (OSError, ValueError, UnicodeError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError) as exc:
            self.log("request_failed", connection_id=connection_id, error_type=type(exc).__name__)
        finally:
            self.clients.discard(writer)
            self.tasks.discard(task)
            writer.close()

    def read_mode(self):
        try:
            value = json.loads((self.state / "mode.json").read_text())
            require(value == {"mode": "online"} or value == {"mode": "offline"}, "MODE_FILE")
            return value["mode"]
        except (OSError, ValueError):
            return "offline"

    def read_rotation(self):
        if not self.config.get("rotation_enabled"):
            return "local"
        try:
            value = json.loads(private_file(self.state / "rotation.json"))
            require(value == {"exit": "local"} or value == {"exit": "peer"}, "ROTATION_FILE")
            return value["exit"]
        except (OSError, ValueError):
            return "blocked"

    async def run(self):
        self.mode = self.read_mode()
        self.rotation = self.read_rotation()
        try:
            for listener, port in self.config["ports"].items():
                server = await asyncio.start_server(lambda r, w, key=listener: self.accepted(r, w, key),
                                                    self.config["bind_ipv4"], port, family=socket.AF_INET,
                                                    limit=8192, backlog=32)
                self.servers.append(server)
            ready = {"pid": os.getpid(), "started_at": time.time(), "config_sha256": hashlib.sha256(
                json.dumps(self.config, sort_keys=True).encode()).hexdigest(), "mode": self.mode,
                     "ports": self.config["ports"], "endpoint": self.config["endpoint_id"], "run_id": self.config["run_id"]}
            atomic_json(self.state / "ready.json", ready)
            self.log("ready", **ready)
            while not self.stop.is_set() and time.monotonic() - self.started < self.config["lifetime_seconds"]:
                mode = self.read_mode()
                if mode != self.mode:
                    self.mode = mode
                    self.log("mode_changed", mode=mode)
                if self.mode != "online":
                    for writer in tuple(self.tunnels):
                        writer.close()
                rotation = self.read_rotation()
                if rotation != self.rotation:
                    self.rotation = rotation
                    self.log("rotation_changed", exit=rotation)
                    for writer in tuple(self.tunnels):
                        writer.close()
                try:
                    await asyncio.wait_for(self.stop.wait(), 0.2)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.stop.set()
            for server in self.servers:
                server.close()
            for writer in self.clients | self.tunnels:
                writer.close()
            for task in tuple(self.tasks):
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            await asyncio.gather(*(server.wait_closed() for server in self.servers))
            usage = resource.getrusage(resource.RUSAGE_SELF)
            metrics = {"counts": self.counts, "max_rss_kib": usage.ru_maxrss,
                       "cpu_seconds": usage.ru_utime + usage.ru_stime, "elapsed_seconds": time.monotonic() - self.started}
            atomic_json(self.state / "metrics.json", metrics)
            self.log("stopped", **metrics)
            for handler in self.logger.handlers:
                handler.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--isolated-loopback-test", action="store_true",
                        help="Only permits loopback binds, clients, resolver and target IPs; never public evidence")
    args = parser.parse_args()
    require(sys.version_info >= (3, 11), "PYTHON_3_11_REQUIRED")
    os.umask(0o077)
    config = validate(json.loads(args.config.read_text()), args.isolated_loopback_test)
    root = args.config.resolve().parent
    require(root.stat().st_uid == os.getuid() and root.stat().st_mode & 0o077 == 0, "INSECURE_BUNDLE_DIRECTORY")
    load_dependency(Path(__file__).resolve().parent)
    endpoint = Endpoint(config, root)
    if args.validate_only:
        print(json.dumps({"result": "VALID", "run_id": config["run_id"], "endpoint": config["endpoint_id"],
                          "public_acceptance": "NOT_RUN", "isolated": args.isolated_loopback_test}))
        return
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    for kind, cap in [(resource.RLIMIT_NOFILE, 256), (resource.RLIMIT_AS, 268435456)]:
        _, hard = resource.getrlimit(kind)
        cap = min(cap, hard) if hard != resource.RLIM_INFINITY else cap
        resource.setrlimit(kind, (cap, cap))
    with (endpoint.state / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        async def run():
            loop = asyncio.get_running_loop()
            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signum, endpoint.stop.set)
            await endpoint.run()
        asyncio.run(run())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        # Never echo raw requests, config contents, or credentials on failure.
        print(json.dumps({"result": "ERROR", "code": str(error) if isinstance(error, Rejected) else type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
