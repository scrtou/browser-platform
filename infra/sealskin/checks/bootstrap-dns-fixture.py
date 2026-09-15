#!/usr/bin/env python3
"""Private, authoritative-only DNS fixture for bootstrap packet/rotation checks.

This is not a recursive resolver, public delegation, or public TTL acceptance.
It serves only two exact QA names, with bounded configurable answers and faults.
"""

import argparse
import ipaddress
import json
import socketserver
import struct
import threading
import time
from pathlib import Path

import dns.flags
import dns.message
import dns.rcode
import dns.rdataclass
import dns.rdatatype
import dns.rrset

ROOT = None
LOCK = threading.Lock()
NAMES = {"proxy.leak.qa.test.", "endpoint.leak.qa.test."}


def answer(raw, source, transport):
    if not 12 <= len(raw) <= 4096:
        return None
    try:
        query = dns.message.from_wire(raw)
    except dns.exception.DNSException:
        return None
    if len(query.question) != 1:
        return None
    question = query.question[0]
    name = question.name.to_text().lower()
    response = dns.message.make_response(query)
    response.flags |= dns.flags.AA
    mode = json.loads((ROOT / "mode.json").read_text())
    fault = mode.get("fault", "")
    ttl = mode.get("ttl_seconds", 3)
    assert type(ttl) is int and 0 <= ttl <= 300
    if name not in NAMES or question.rdtype != dns.rdatatype.A or question.rdclass != dns.rdataclass.IN:
        response.set_rcode(dns.rcode.REFUSED)
    elif fault in {"servfail", "nxdomain"}:
        response.set_rcode(dns.rcode.SERVFAIL if fault == "servfail" else dns.rcode.NXDOMAIN)
    elif mode.get("truncate") and transport == "udp":
        response.flags |= dns.flags.TC
    elif fault != "drop":
        if name == "proxy.leak.qa.test." and mode.get("cname"):
            response.answer.append(dns.rrset.from_text(name, ttl + 1, "IN", "CNAME", "endpoint.leak.qa.test."))
        else:
            addresses = mode["addresses"]
            assert isinstance(addresses, list) and 1 <= len(addresses) <= 8
            for value in addresses:
                assert str(ipaddress.IPv4Address(value)) == value
            response.answer.append(dns.rrset.from_text(name, ttl, "IN", "A", *addresses))
    if fault == "bad-id":
        response.id ^= 1
    event = {"at": time.time(), "scope": "private-fixture", "name": name, "source": source,
             "transport": transport, "fault": fault, "ttl_seconds": ttl,
             "truncated": bool(response.flags & dns.flags.TC),
             "answer": [value.to_text() for value in response.answer]}
    with LOCK, (ROOT / "events.jsonl").open("a") as handle:
        handle.write(json.dumps(event) + "\n")
    return None if fault == "drop" else response.to_wire(want_shuffle=False)


class UDP(socketserver.BaseRequestHandler):
    def handle(self):
        raw, connection = self.request
        result = answer(raw, self.client_address[0], "udp")
        if result is not None:
            connection.sendto(result, self.client_address)


class TCP(socketserver.BaseRequestHandler):
    def read(self, count):
        data = b""
        while len(data) < count:
            part = self.request.recv(count - len(data))
            if not part:
                raise OSError("closed")
            data += part
        return data

    def handle(self):
        try:
            self.request.settimeout(5)
            count = struct.unpack("!H", self.read(2))[0]
            if not 12 <= count <= 4096:
                return
            result = answer(self.read(count), self.client_address[0], "tcp")
            if result is not None:
                self.request.sendall(struct.pack("!H", len(result)) + result)
        except OSError:
            pass


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file(), "Run only in the isolated DNS QA container"
    ROOT = args.root
    udp = socketserver.ThreadingUDPServer(("0.0.0.0", 53), UDP)
    tcp = socketserver.ThreadingTCPServer(("0.0.0.0", 53), TCP)
    udp.daemon_threads = tcp.daemon_threads = True
    threading.Thread(target=udp.serve_forever, daemon=True).start()
    print("Private bootstrap DNS fixture ready", flush=True)
    tcp.serve_forever()


if __name__ == "__main__":
    main()
