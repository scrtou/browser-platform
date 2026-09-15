#!/usr/bin/env python3
"""A fixed, non-recursive DNS fixture for isolated DIRECT network checks.

It answers only the private QA zone, the exact public TLS probe hostname and
localhost as an explicit control proving that the gateway ignores /etc/hosts.
Public probe addresses are pinned during QA preparation, never discovered here.
Private-zone TTL is zero; this fixture is not evidence of public DNS or TTL.
"""

import argparse
import ipaddress
import json
import re
import socketserver
import struct
import threading
import time
from pathlib import Path

ROOT = None
CONFIG = None
LOCK = threading.Lock()


def log(**value):
    with LOCK, (ROOT / "events.jsonl").open("a") as handle:
        handle.write(json.dumps({"time": time.time(), **value}) + "\n")


def name_wire(name):
    return b"".join(bytes([len(label)]) + label.encode("ascii") for label in name.split(".")) + b"\0"


def question(raw):
    if not 17 <= len(raw) <= 4096 or struct.unpack("!H", raw[4:6])[0] != 1:
        raise ValueError("invalid question")
    labels, cursor = [], 12
    while raw[cursor]:
        length = raw[cursor]
        cursor += 1
        if length > 63 or cursor + length >= len(raw):
            raise ValueError("invalid label")
        labels.append(raw[cursor:cursor + length].decode("ascii").lower())
        cursor += length
    cursor += 1
    kind, cls = struct.unpack("!HH", raw[cursor:cursor + 4])
    name = ".".join(labels)
    if (cursor + 4 != len(raw) or cls != 1 or not (
            name in {CONFIG["public_probe"]["name"], "localhost"} or re.fullmatch(r"[a-z0-9-]{1,63}\.leak\.qa\.test", name))):
        raise ValueError("outside fixed QA names")
    return name, kind, raw[12:cursor + 4]


def answer(raw, source, transport):
    try:
        name, kind, query = question(raw)
    except (ValueError, IndexError, UnicodeError, struct.error):
        return raw[:2] + struct.pack("!HHHHH", 0x8005, 0, 0, 0, 0)
    mode = json.loads((ROOT / "mode.json").read_text())
    flags = 0x8000 | (struct.unpack("!H", raw[2:4])[0] & 0x100)
    private_zone = name.endswith(".leak.qa.test")
    if private_zone:
        flags |= 0x400
    records = []
    if mode.get("mode") == "drop":
        log(name=name, qtype=kind, source=source, transport=transport, mode="drop", answers=0)
        return None
    if mode.get("mode") == "servfail":
        flags |= 2
    elif kind == 1:
        values = [CONFIG["fixture_ipv4"]]
        if name == CONFIG["public_probe"]["name"]:
            values = CONFIG["public_probe"]["addresses"]
        elif name.startswith("aaaa-"):
            values = []
        elif name.startswith("private-"):
            values = [CONFIG["private_ipv4"]]
        elif name.startswith("host-"):
            values = CONFIG["host_ipv4"]
        elif name.startswith("metadata-"):
            values = ["169.254.169.254"]
        elif name.startswith("mixed-"):
            values += [CONFIG["private_ipv4"]]
        elif name.startswith("cname-private-"):
            target = "private-" + name[len("cname-private-"):]
            records = [(5, name_wire(target))]
            values = []
        elif name.startswith("rebind-") and mode.get("rebind_private"):
            values = [CONFIG["private_ipv4"]]
        if name.startswith("truncated-") and transport == "udp":
            flags |= 0x200
            values = []
        records += [(1, ipaddress.IPv4Address(value).packed) for value in values]
    elif kind == 28 and private_zone:
        records = [(28, ipaddress.IPv6Address("::1").packed)]
    result = raw[:2] + struct.pack("!HHHHH", flags, 1, len(records), 0, 0) + query
    for rtype, data in records:
        result += b"\xc0\x0c" + struct.pack("!HHIH", rtype, 1, 0, len(data)) + data
    log(name=name, qtype=kind, source=source, transport=transport, authoritative=private_zone,
        answers=len(records), truncated=bool(flags & 0x200), mode=mode.get("mode", "online"))
    return result


class UDP(socketserver.BaseRequestHandler):
    def handle(self):
        raw, connection = self.request
        data = answer(raw, self.client_address[0], "udp")
        if data is not None:
            connection.sendto(data, self.client_address)


class TCP(socketserver.BaseRequestHandler):
    def exact(self, size):
        data = b""
        while len(data) < size:
            part = self.request.recv(size - len(data))
            if not part:
                raise OSError("closed")
            data += part
        return data

    def handle(self):
        try:
            self.request.settimeout(5)
            size = struct.unpack("!H", self.exact(2))[0]
            if not 17 <= size <= 4096:
                return
            data = answer(self.exact(size), self.client_address[0], "tcp")
            if data is not None:
                self.request.sendall(struct.pack("!H", len(data)) + data)
        except OSError:
            pass


def main():
    global ROOT, CONFIG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file(), "Use only the isolated QA container"
    ROOT = args.root
    CONFIG = json.loads((ROOT / "config.json").read_text())
    assert CONFIG["public_probe"]["name"] == "example.com"
    for value in [CONFIG["fixture_ipv4"], *CONFIG["public_probe"]["addresses"], *CONFIG["host_ipv4"]]:
        assert ipaddress.IPv4Address(value).is_global
    servers = [socketserver.ThreadingUDPServer(("0.0.0.0", 53), UDP),
               socketserver.ThreadingTCPServer(("0.0.0.0", 53), TCP)]
    for server in servers:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print("DIRECT QA DNS ready", flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
