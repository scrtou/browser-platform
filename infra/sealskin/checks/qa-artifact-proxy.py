#!/usr/bin/env python3
"""QA-only SOCKS5 fixture for the frozen artifact's example.com TLS check.

No published port, production Relay or credentials are required. The caller
must attach this fixture to the isolated artifact network as profile-relay.
"""

import argparse
import ipaddress
import json
from pathlib import Path
import select
import socket
import socketserver
import threading
import time


def exact(connection, count):
    value = b""
    while len(value) < count:
        part = connection.recv(count - len(value))
        if not part:
            raise OSError("CLOSED")
        value += part
    return value


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        if not self.server.slots.acquire(blocking=False):
            return
        try:
            self.request.settimeout(10)
            version, count = exact(self.request, 2)
            if version != 5 or not count or 0 not in exact(self.request, count):
                return
            self.request.sendall(b"\x05\x00")
            if exact(self.request, 4) != b"\x05\x01\x00\x03":
                return
            domain = exact(self.request, exact(self.request, 1)[0])
            port = int.from_bytes(exact(self.request, 2), "big")
            if domain != b"example.com" or port != 443:
                self.request.sendall(b"\x05\x02\x00\x01" + b"\x00" * 6)
                print(json.dumps({"event": "ARTIFACT_PROXY_DENIED"}), flush=True)
                return
            addresses = socket.getaddrinfo("example.com", 443, socket.AF_INET, socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                return
            with socket.create_connection(addresses[0][4], timeout=10) as upstream:
                self.request.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
                print(json.dumps({"event": "ARTIFACT_PROXY_APPROVED"}), flush=True)
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    readers, _, _ = select.select([self.request, upstream], [], [], 15)
                    if not readers:
                        return
                    for source in readers:
                        data = source.recv(65536)
                        if not data:
                            return
                        (upstream if source is self.request else self.request).sendall(data)
        except (OSError, ValueError):
            print(json.dumps({"event": "ARTIFACT_PROXY_UNAVAILABLE"}), flush=True)
        finally:
            self.server.slots.release()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    slots = threading.BoundedSemaphore(16)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", required=True)
    args = parser.parse_args()
    address = ipaddress.ip_address(args.bind)
    if not Path("/.dockerenv").exists() or address.version != 4 or not address.is_private or address.is_loopback:
        parser.error("bind to this fixture's private QA interface")
    with Server((args.bind, 1080), Handler) as server:
        print(json.dumps({"event": "ARTIFACT_PROXY_READY"}), flush=True)
        server.serve_forever()
