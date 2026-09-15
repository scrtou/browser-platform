#!/usr/bin/env python3
"""Private DNS, website and HTTP/HTTPS/SOCKS5 proxy fixtures for network QA.

This is not a general proxy or DNS resolver. It only serves its fixed QA zone
and local test listeners. Logs contain test names, nonces and transport metadata.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.server
import ipaddress
import json
import re
import select
import socket
import socketserver
import ssl
import struct
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ZONE = "leak.qa.test"
LOCK = threading.Lock()
ROOT = None
IPV4 = None


def log(event, **values):
    with LOCK, (ROOT / "events.jsonl").open("a") as handle:
        handle.write(json.dumps({"time": time.time(), "event": event, **values}) + "\n")


def mode():
    return json.loads((ROOT / "mode.json").read_text()).get("mode", "online")


def authentication(protocol):
    path = ROOT / "proxy-auth.json"
    value = json.loads(path.read_text()) if path.exists() else {}
    return value.get(protocol, "username_password" if protocol == "socks5" else "basic")


def credentials():
    path = ROOT / "proxy-credentials.json"
    value = json.loads(path.read_text()) if path.exists() else {
        "username": "network-observer-user", "password": "network-observer-password"}
    return value["username"].encode(), value["password"].encode()


def tunnel(left, right):
    while mode() != "offline":
        readable = [value for value in (left, right) if isinstance(value, ssl.SSLSocket) and value.pending()]
        if not readable:
            readable, _, _ = select.select([left, right], [], [], 0.2)
        for connection in readable:
            data = connection.recv(65536)
            if not data:
                return
            (right if connection is left else left).sendall(data)


def approved_target(target):
    if re.fullmatch(r"[a-z0-9-]{1,63}\.leak\.qa\.test", target):
        return resolve(target), 3
    address = ipaddress.ip_address(target)
    if str(address) not in {IPV4, "::1"}:
        raise ValueError("outside private QA targets")
    return str(address), 1 if address.version == 4 else 4


def read_exact(connection, size):
    data = b""
    while len(data) < size:
        part = connection.recv(size - len(data))
        if not part:
            raise OSError("connection closed")
        data += part
    return data


def question(name, kind=1):
    wire = b"".join(bytes([len(label)]) + label.encode() for label in name.split("."))
    return (
        struct.pack("!HHHHHH", 1234, 0x100, 1, 0, 0, 0)
        + wire
        + b"\0"
        + struct.pack("!HH", kind, 1)
    )


def decode_question(raw):
    if len(raw) < 17 or len(raw) > 4096 or struct.unpack("!H", raw[4:6])[0] != 1:
        raise ValueError("invalid query")
    labels, cursor = [], 12
    while True:
        size = raw[cursor]
        cursor += 1
        if not size:
            break
        if size > 63 or cursor + size >= len(raw):
            raise ValueError("invalid label")
        labels.append(raw[cursor : cursor + size].decode("ascii").lower())
        cursor += size
    kind, cls = struct.unpack("!HH", raw[cursor : cursor + 4])
    name = ".".join(labels)
    if cls != 1 or not re.fullmatch(r"[a-z0-9-]{1,63}\.leak\.qa\.test", name):
        raise ValueError("outside the private test zone")
    return name, kind, raw[12 : cursor + 4]


def answer(raw, source, transport):
    try:
        name, kind, query = decode_question(raw)
    except (ValueError, IndexError, UnicodeError, struct.error):
        return raw[:2] + struct.pack("!HHHHH", 0x8005, 0, 0, 0, 0)
    data = b""
    if kind == 1 and not name.startswith("aaaa-"):
        data = ipaddress.IPv4Address(IPV4).packed
    if kind == 28:
        data = ipaddress.IPv6Address("::1").packed
    flags = 0x8400 | (struct.unpack("!H", raw[2:4])[0] & 0x100)
    result = raw[:2] + struct.pack("!HHHHH", flags, 1, int(bool(data)), 0, 0) + query
    if data:
        result += b"\xc0\x0c" + struct.pack("!HHIH", kind, 1, 0, len(data)) + data
    log(
        "dns",
        name=name,
        qtype=kind,
        source=source,
        transport=transport,
        authoritative=True,
        answers=int(bool(data)),
    )
    return result


class DNSUDP(socketserver.BaseRequestHandler):
    def handle(self):
        raw, connection = self.request
        connection.sendto(
            answer(raw, self.client_address[0], "udp"), self.client_address
        )


class DNSTCP(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.request.settimeout(5)
            size = struct.unpack("!H", read_exact(self.request, 2))[0]
            raw = read_exact(self.request, min(size, 4096))
            data = answer(raw, self.client_address[0], self.server.transport)
            self.request.sendall(struct.pack("!H", len(data)) + data)
        except OSError:
            pass


def resolve(name):
    # A real DNS wire request, through the authoritative listener, for every
    # uncached test name. The private upstream chooses A then AAAA explicitly.
    for kind in (1, 28):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.settimeout(2)
            connection.sendto(question(name, kind), ("127.0.0.1", 53))
            raw, _ = connection.recvfrom(4096)
        if struct.unpack("!H", raw[6:8])[0]:
            return str(ipaddress.ip_address(raw[-4:] if kind == 1 else raw[-16:]))
    raise OSError("no test address")


class SOCKS(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.request.settimeout(15)
            version, count = read_exact(self.request, 2)
            auth = authentication("socks5")
            selected = 0 if auth == "none" else 2
            if version != 5 or selected not in read_exact(self.request, count):
                return
            if selected == 0 and mode() == "bad-auth":
                self.request.sendall(b"\x05\xff")
                log("auth_rejected", protocol="socks5", auth=auth, source=self.client_address[0])
                return
            self.request.sendall(bytes([5, selected]))
            if selected == 2:
                version, size = read_exact(self.request, 2)
                username = read_exact(self.request, size)
                password = read_exact(self.request, read_exact(self.request, 1)[0])
                expected_user, expected_password = credentials()
                if (version != 1 or not hmac.compare_digest(username, expected_user) or
                        not hmac.compare_digest(password, expected_password) or mode() == "bad-auth"):
                    self.request.sendall(b"\x01\x01")
                    log("auth_rejected", protocol="socks5", auth=auth, source=self.client_address[0])
                    return
                self.request.sendall(b"\x01\x00")
            version, command, reserved, atyp = read_exact(self.request, 4)
            if (version, command, reserved) != (5, 1, 0):
                return
            if atyp == 3:
                target = (
                    read_exact(self.request, read_exact(self.request, 1)[0])
                    .decode("ascii")
                    .lower()
                )
                if not re.fullmatch(r"[a-z0-9-]{1,63}\.leak\.qa\.test", target):
                    return
                address = resolve(target)
            elif atyp in (1, 4):
                target = address = str(
                    ipaddress.ip_address(
                        read_exact(self.request, 4 if atyp == 1 else 16)
                    )
                )
                if address not in {IPV4, "::1"}:
                    return
            else:
                return
            port = struct.unpack("!H", read_exact(self.request, 2))[0]
            log(
                "socks",
                target=target,
                atyp=atyp,
                port=port,
                source=self.client_address[0],
                mode=mode(),
                auth=auth,
            )
            if port not in {80, 443} or mode() == "offline":
                self.request.sendall(b"\x05\x05\x00\x01" + b"\0" * 6)
                return
            with socket.create_connection((address, port), timeout=5) as upstream:
                self.request.sendall(b"\x05\x00\x00\x01" + b"\0" * 6)
                tunnel(self.request, upstream)
        except (OSError, ValueError, UnicodeError):
            pass


class HTTPProxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def do_CONNECT(self):
        self.close_connection = True
        protocol = "https" if isinstance(self.connection, ssl.SSLSocket) else "http"
        auth = authentication(protocol)
        expected = "" if auth == "none" else "Basic " + base64.b64encode(b":".join(credentials())).decode()
        if (mode() == "bad-auth" or not hmac.compare_digest(self.headers.get("Proxy-Authorization", ""), expected)):
            self.send_error(407)
            log("auth_rejected", protocol=protocol, auth=auth, source=self.client_address[0])
            return
        try:
            target = urlsplit("//" + self.path)
            if target.username or target.password or target.path or target.query or target.fragment:
                raise ValueError("invalid CONNECT authority")
            address, atyp = approved_target(target.hostname)
            port = target.port
            log(protocol + "_connect", target=target.hostname, atyp=atyp, port=port,
                source=self.client_address[0], mode=mode(), auth=auth)
            if port not in {80, 443} or mode() == "offline":
                self.send_error(502)
                return
            with socket.create_connection((address, port), timeout=5) as upstream:
                self.send_response(200, "Connection established")
                self.end_headers()
                self.wfile.flush()
                tunnel(self.connection, upstream)
        except (OSError, ValueError, UnicodeError, TypeError):
            pass


class HTTPS(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def response(self, data, content_type="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Alt-Svc", 'h3=":443"; ma=60')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlsplit(self.path)
        host = self.headers.get("Host", "").split(":", 1)[0]
        params = parse_qs(parsed.query)
        nonce = params.get("nonce", [""])[0]
        if not re.fullmatch(r"[a-z0-9-]{1,63}\.leak\.qa\.test", host):
            self.send_error(403)
            return
        log(
            "https" if isinstance(self.connection, ssl.SSLSocket) else "http",
            host=host,
            path=parsed.path,
            nonce=nonce if re.fullmatch(r"[a-f0-9]{32}", nonce) else "",
            source=self.client_address[0],
        )
        try:
            if parsed.path == "/test":
                self.response(
                    (ROOT / "network-fixture.html").read_bytes(),
                    "text/html; charset=utf-8",
                )
            elif parsed.path == "/client":
                self.response((ROOT / "client-fixture.html").read_bytes(), "text/html; charset=utf-8")
            elif parsed.path == "/dns-query":
                encoded = params.get("dns", [""])[0]
                raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                self.response(
                    answer(raw, self.client_address[0], "doh"),
                    "application/dns-message",
                )
            elif parsed.path == "/ws":
                self.websocket()
            elif parsed.path == "/download":
                data = b"network-qa-download\n" * 4096
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data) * 150))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                for _ in range(150):
                    self.wfile.write(data)
                    self.wfile.flush()
                    time.sleep(0.1)
            else:
                self.response(json.dumps({"ok": True, "nonce": nonce}).encode())
        except (OSError, ValueError):
            self.close_connection = True

    def websocket(self):
        key = self.headers.get("Sec-WebSocket-Key", "")
        if self.headers.get("Upgrade", "").lower() != "websocket" or len(key) > 64:
            self.send_error(400)
            return
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header(
            "Sec-WebSocket-Accept",
            base64.b64encode(
                hashlib.sha1(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
                ).digest()
            ).decode(),
        )
        self.end_headers()
        self.connection.settimeout(5)
        first, second = read_exact(self.connection, 2)
        size = second & 127
        if first & 15 != 1 or not second & 128 or size >= 126:
            return
        mask = read_exact(self.connection, 4)
        data = read_exact(self.connection, size)
        data = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
        self.connection.sendall(bytes([0x81, size]) + data)
        log("websocket", bytes=len(data), source=self.client_address[0])
        self.close_connection = True


class UDPObserver(socketserver.BaseRequestHandler):
    def handle(self):
        raw, connection = self.request
        if self.server.server_address[1] == 3478:
            valid = (
                len(raw) >= 20
                and raw[:2] == b"\0\x01"
                and raw[4:8] == b"\x21\x12\xa4\x42"
            )
            log(
                "stun",
                valid=valid,
                source=self.client_address[0],
                transaction=raw[8:20].hex() if valid else "",
            )
            if valid:
                port = self.client_address[1] ^ 0x2112
                address = bytes(
                    a ^ b
                    for a, b in zip(
                        socket.inet_aton(self.client_address[0]), b"\x21\x12\xa4\x42"
                    )
                )
                connection.sendto(
                    b"\x01\x01\0\x0c\x21\x12\xa4\x42"
                    + raw[8:20]
                    + b"\0\x20\0\x08\0\x01"
                    + struct.pack("!H", port)
                    + address,
                    self.client_address,
                )
        else:
            valid = (
                len(raw) >= 1200 and raw[0] & 0xC0 == 0xC0 and raw[1:5] == b"\0\0\0\x01"
            )
            log(
                "udp443",
                quic_initial_header=valid,
                source=self.client_address[0],
                bytes=len(raw),
            )
            connection.sendto(b"qa-udp-received", self.client_address)


class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class UDPServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True
    daemon_threads = True


class HTTPS6(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


class ThreadedTLS:
    """Never let a silent TLS client hold the server's accept loop."""

    handshake_timeout = 5
    request_timeout = 30

    def __init__(self, *args, tls_context, **kwargs):
        self.tls_context = tls_context
        super().__init__(*args, **kwargs)

    def get_request(self):
        connection, address = super().get_request()
        try:
            return self.tls_context.wrap_socket(connection, server_side=True, do_handshake_on_connect=False), address
        except Exception:
            connection.close()
            raise

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(self.handshake_timeout)
            request.do_handshake()
            request.settimeout(self.request_timeout)
        except (OSError, ssl.SSLError):
            self.shutdown_request(request)
            return
        super().process_request_thread(request, client_address)


class TLSHTTPServer(ThreadedTLS, http.server.ThreadingHTTPServer):
    daemon_threads = True


class TLSHTTP6(ThreadedTLS, HTTPS6):
    daemon_threads = True


class TLSTCPServer(ThreadedTLS, TCPServer):
    pass


def main():
    global ROOT, IPV4
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ipv4", required=True)
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        raise SystemExit("The observer must run in its private QA container")
    ROOT, IPV4 = args.root, str(ipaddress.IPv4Address(args.ipv4))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ROOT / "server.pem", ROOT / "server-key.pem")
    proxy_contexts = {}
    for key, certificate in (("valid", "server.pem"), ("wrong-name", "server-wrong-name.pem"),
                             ("untrusted", "server-untrusted.pem")):
        if (ROOT / certificate).exists():
            value = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            value.minimum_version = ssl.TLSVersion.TLSv1_2
            value.load_cert_chain(ROOT / certificate, ROOT / "server-key.pem")
            proxy_contexts[key] = value

    def proxy_sni(connection, server_name, _):
        path = ROOT / "proxy-tls-mode.json"
        selected = json.loads(path.read_text()).get("mode", "valid") if path.exists() else "valid"
        log("proxy_tls_attempt", tls_mode=selected, expected_name=server_name == "proxy.leak.qa.test",
            source=connection.getpeername()[0])
        if selected not in proxy_contexts:
            return ssl.ALERT_DESCRIPTION_ACCESS_DENIED
        connection.context = proxy_contexts[selected]

    proxy_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    proxy_context.minimum_version = ssl.TLSVersion.TLSv1_2
    proxy_context.load_cert_chain(ROOT / "server.pem", ROOT / "server-key.pem")
    proxy_context.set_servername_callback(proxy_sni)
    servers = [
        UDPServer(("0.0.0.0", 53), DNSUDP),
        TCPServer(("0.0.0.0", 53), DNSTCP),
        TLSTCPServer(("0.0.0.0", 853), DNSTCP, tls_context=context),
        TLSHTTPServer(("0.0.0.0", 443), HTTPS, tls_context=context),
        TLSHTTP6(("::1", 443), HTTPS, tls_context=context),
        TCPServer(("0.0.0.0", 28191), SOCKS),
        UDPServer(("0.0.0.0", 3478), UDPObserver),
        UDPServer(("0.0.0.0", 443), UDPObserver),
        http.server.ThreadingHTTPServer(("0.0.0.0", 80), HTTPS),
        HTTPS6(("::1", 80), HTTPS),
        http.server.ThreadingHTTPServer(("0.0.0.0", 28192), HTTPProxy),
        TLSHTTPServer(("0.0.0.0", 28193), HTTPProxy, tls_context=proxy_context),
    ]
    servers[1].transport = "tcp"
    servers[2].transport = "dot"
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print("private network observer ready", flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
