#!/usr/bin/env python3
"""Capture only approved UDP DNS questions for explicitly named QA domains.

Run inside a previously verified QA Relay namespace. Other DNS names, network
payloads and application traffic are discarded. TCP is reported as metadata;
it must not be mistaken for a verified UDP exchange.
"""

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import signal
import socket
import struct
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--resolver", required=True)
    parser.add_argument("--interface", choices=("eth0", "eth1"), required=True)
    parser.add_argument("--name", action="append", required=True)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=900)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 900 or len(args.name) > 3:
        raise ValueError("Bounded QA capture required")
    for address in (args.source, args.resolver):
        if str(ipaddress.IPv4Address(address)) != address:
            raise ValueError("Canonical IPv4 required")
    if hashlib.sha256(args.wheel.read_bytes()).hexdigest() != "01d9bbc4a2d76bf0db7c1f729812ded6d912bd318d3b1cf81d30c0f845dbf3af":
        raise ValueError("Locked DNS wheel required")
    sys.path.insert(0, str(args.wheel))
    import dns.flags
    import dns.message
    names = {name.rstrip(".").lower() + "." for name in args.name}
    if any(not name.startswith(("direct-", "bootstrap-", "upstream-")) for name in names):
        raise ValueError("Explicit public DNS QA names required")
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    pending, exchanges, tcp_frames = {}, 0, 0
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3)) as capture:
        capture.bind((args.interface, 0))
        capture.settimeout(.25)
        print(json.dumps({"dns_capture_ready": True, "source": args.source, "resolver": args.resolver,
                          "names": sorted(names), "started_at": time.time()}), flush=True)
        deadline = time.monotonic() + args.seconds
        while not stopped and time.monotonic() < deadline:
            try:
                raw, link = capture.recvfrom(65535)
            except TimeoutError:
                continue
            received = time.time()
            if len(raw) < 42 or raw[12:14] != b"\x08\x00" or raw[14] >> 4 != 4:
                continue
            header = (raw[14] & 15) * 4
            if header < 20 or len(raw) < 14 + header + 8 or struct.unpack("!H", raw[20:22])[0] & 0x3fff:
                continue
            source, destination = socket.inet_ntoa(raw[26:30]), socket.inet_ntoa(raw[30:34])
            outgoing = link[2] == socket.PACKET_OUTGOING
            if (source, destination) != ((args.source, args.resolver) if outgoing else (args.resolver, args.source)):
                continue
            offset = 14 + header
            sport, dport = struct.unpack("!HH", raw[offset:offset + 4])
            if (dport if outgoing else sport) != 53:
                continue
            if raw[23] == 6:
                tcp_frames += 1
                continue
            if raw[23] != 17:
                continue
            size = struct.unpack("!H", raw[offset + 4:offset + 6])[0]
            payload = raw[offset + 8:offset + size]
            try:
                message = dns.message.from_wire(payload)
            except Exception:
                continue
            if len(message.question) != 1 or message.question[0].name.to_text().lower() not in names:
                continue
            key = (sport if outgoing else dport, message.id)
            if outgoing:
                if message.flags & dns.flags.QR:
                    continue
                pending[key] = {"started_at": received, "request_wire_hex": payload.hex(),
                                "name": message.question[0].name.to_text(), "client_port": sport}
            elif message.flags & dns.flags.QR and key in pending:
                query = pending.pop(key)
                request = dns.message.from_wire(bytes.fromhex(query["request_wire_hex"]))
                if not request.is_response(message):
                    continue
                exchanges += 1
                print(json.dumps({**query, "received_at": received, "response_wire_hex": payload.hex(),
                                  "source": args.source, "resolver": args.resolver, "transport": "udp",
                                  "direction_source": "AF_PACKET.sll_pkttype"}), flush=True)
            if len(pending) > 256 or exchanges > 1024:
                raise RuntimeError("QA DNS capture bound exceeded")
        print(json.dumps({"dns_capture_complete": True, "exchanges": exchanges, "pending": len(pending),
                          "tcp_frames": tcp_frames, "finished_at": time.time()}), flush=True)


if __name__ == "__main__":
    main()
