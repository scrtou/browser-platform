#!/usr/bin/env python3
"""Private SOCKS5 authentication fixture; forwards only probe.qa.invalid:443."""
import argparse
import http.server
import json
from pathlib import Path
import select
import socket
import socketserver
import ssl
import threading
import time


def exact(conn, size):
    data = b""
    while len(data) < size:
        part = conn.recv(size - len(data))
        if not part:
            raise OSError("closed")
        data += part
    return data


class HTTPS(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        body = (self.server.marker + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class SOCKS(socketserver.BaseRequestHandler):
    def event(self, result):
        with self.server.lock, (self.server.root / "events.jsonl").open("a") as log:
            log.write(json.dumps({"at": time.time(), "result": result, "endpoint": self.server.marker}) + "\n")

    def handle(self):
        try:
            self.request.settimeout(10)
            version, count = exact(self.request, 2)
            methods = exact(self.request, count)
            if version != 5 or 2 not in methods:
                return
            self.request.sendall(b"\x05\x02")
            version, length = exact(self.request, 2)
            username = exact(self.request, length)
            password = exact(self.request, exact(self.request, 1)[0])
            config = json.loads((self.server.root / "mode.json").read_text())
            accepted = (version == 1 and username == config["username"].encode()
                        and password == config["password"].encode() and not config.get("reject_auth"))
            self.request.sendall(b"\x01\x00" if accepted else b"\x01\x01")
            if not accepted:
                self.event("auth_rejected")
                return
            if exact(self.request, 4) != b"\x05\x01\x00\x03":
                return
            domain = exact(self.request, exact(self.request, 1)[0])
            port = int.from_bytes(exact(self.request, 2), "big")
            if domain != b"probe.qa.invalid" or port != 443:
                self.request.sendall(b"\x05\x02\x00\x01" + b"\x00" * 6)
                return
            with socket.create_connection(("127.0.0.1", 28182), timeout=10) as target:
                self.event("authenticated_target")
                self.request.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
                while True:
                    readable, _, _ = select.select([self.request, target], [], [], 120)
                    if not readable:
                        return
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        (target if source is self.request else self.request).sendall(data)
        except (OSError, ValueError):
            pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--marker", choices=["A", "B"], required=True)
    args = parser.parse_args()
    assert Path("/.dockerenv").exists() and args.root == Path("/qa-dynamic")
    https = http.server.ThreadingHTTPServer(("127.0.0.1", 28182), HTTPS)
    https.marker = args.marker
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(args.root / "server.pem", args.root / "server-key.pem")
    https.socket = tls.wrap_socket(https.socket, server_side=True)
    threading.Thread(target=https.serve_forever, daemon=True).start()
    with Server(("0.0.0.0", 28181), SOCKS) as server:
        server.root, server.marker, server.lock = args.root, args.marker, threading.Lock()
        print("Private dynamic upstream ready", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
