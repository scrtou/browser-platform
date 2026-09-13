#!/usr/bin/env python3
"""Private QA SOCKS5 server forwarding only one approved HTTPS test target."""

import argparse
import http.server
import json
import select
import socket
import socketserver
import ssl
import threading
from pathlib import Path


def exact(connection, size):
    data = b""
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            raise OSError("closed")
        data += chunk
    return data


class HTTPSHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        body = b"network-lifecycle-qa\n"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class SOCKSHandler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.request.settimeout(20)
            version, count = exact(self.request, 2)
            methods = exact(self.request, count)
            if version != 5 or 2 not in methods:
                return
            self.request.sendall(b"\x05\x02")
            auth_version, length = exact(self.request, 2)
            username = exact(self.request, length)
            password = exact(self.request, exact(self.request, 1)[0])
            if (
                auth_version != 1
                or username != b"network-qa-user"
                or password != b"network-qa-password"
            ):
                self.request.sendall(b"\x01\x01")
                return
            self.request.sendall(b"\x01\x00")
            version, command, reserved, atyp = exact(self.request, 4)
            if (version, command, reserved, atyp) != (5, 1, 0, 3):
                return
            domain = exact(self.request, exact(self.request, 1)[0])
            port = int.from_bytes(exact(self.request, 2), "big")
            mode = json.loads(
                (self.server.root / "upstream-mode.json").read_text()
            ).get("mode")
            if mode == "offline" or domain != b"probe.qa.invalid" or port != 443:
                self.request.sendall(b"\x05\x05\x00\x01" + b"\x00" * 6)
                return
            with socket.create_connection(
                ("127.0.0.1", self.server.tls_port), timeout=10
            ) as upstream:
                self.request.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
                with self.server.lock:
                    with (self.server.root / "upstream-events.jsonl").open("a") as log:
                        log.write(
                            json.dumps(
                                {
                                    "authenticated": True,
                                    "domain_atyp": True,
                                    "approved_target": True,
                                }
                            )
                            + "\n"
                        )
                while True:
                    readers, _, _ = select.select([self.request, upstream], [], [], 20)
                    if not readers:
                        break
                    for reader in readers:
                        data = reader.recv(65536)
                        if not data:
                            return
                        (upstream if reader is self.request else self.request).sendall(
                            data
                        )
        except (OSError, ValueError):
            pass


class SOCKSServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", type=int, default=28181)
    parser.add_argument("--tls-port", type=int, default=28182)
    args = parser.parse_args()
    root = args.root.resolve()
    if root.name != "qa" or not (
        args.bind.startswith("172.")
        or args.bind == "0.0.0.0"
        and Path("/.dockerenv").is_file()
    ):
        raise SystemExit("Use an explicit QA directory and Docker bridge address")
    https = http.server.ThreadingHTTPServer(("127.0.0.1", args.tls_port), HTTPSHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(root / "mock-server.pem", root / "mock-server-key.pem")
    https.socket = context.wrap_socket(https.socket, server_side=True)
    threading.Thread(target=https.serve_forever, daemon=True).start()
    with SOCKSServer((args.bind, args.port), SOCKSHandler) as server:
        server.root, server.tls_port, server.lock = (
            root,
            args.tls_port,
            threading.Lock(),
        )
        print("private QA upstream ready", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
