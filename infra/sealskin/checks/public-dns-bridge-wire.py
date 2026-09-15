#!/usr/bin/env python3
"""Record only a QA Relay's L3/L4 metadata on its dedicated host bridge.

The bridge survives container stop/start, so this observation covers resume
probes even if Docker replaces the Relay network namespace. The launcher must
verify the network's owner, sole Relay attachment, IPv4 and MAC before use.
Kernel packet type is preserved; bridge ingress is not called PACKET_OUTGOING.
"""

import argparse
import ipaddress
import json
import re
import signal
import socket
import struct
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", required=True)
    parser.add_argument("--relay-ip", required=True)
    parser.add_argument("--relay-mac", required=True)
    parser.add_argument("--seconds", type=int, default=900)
    args = parser.parse_args()
    if not re.fullmatch(r"br-[0-9a-f]{12}", args.interface) or not 1 <= args.seconds <= 900:
        raise ValueError("Explicit dedicated QA bridge and bounded duration required")
    address = str(ipaddress.IPv4Address(args.relay_ip))
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", args.relay_mac):
        raise ValueError("Explicit Relay MAC required")
    stop, flows = False, {}
    host_emitted = {"ipv4": 0, "ipv6": 0}

    def finish(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, finish)
    signal.signal(signal.SIGINT, finish)
    started = time.time()
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3)) as capture:
        capture.bind((args.interface, 0))
        capture.settimeout(.25)
        print(json.dumps({"bridge_capture_ready": True, "interface": args.interface,
                          "source_ipv4": address, "source_mac": args.relay_mac, "started_at": started}), flush=True)
        deadline = time.monotonic() + args.seconds
        while not stop and time.monotonic() < deadline:
            try:
                raw, link = capture.recvfrom(65535)
            except TimeoutError:
                continue
            if len(raw) < 34:
                continue
            kind = struct.unpack("!H", raw[12:14])[0]
            # On this exclusive bridge, Relay frames arrive from its veth.
            # Host-generated frames and replies sent to the Relay have the
            # opposite kernel direction. Keep their counts separately. MACs
            # may legitimately change when Docker recreates an attachment.
            if link[2] == socket.PACKET_OUTGOING:
                if kind in (0x800, 0x86DD):
                    host_emitted["ipv4" if kind == 0x800 else "ipv6"] += 1
                continue
            if kind == 0x800:
                header = (raw[14] & 15) * 4
                source = socket.inet_ntop(socket.AF_INET, raw[26:30])
                destination = socket.inet_ntop(socket.AF_INET, raw[30:34])
                protocol, offset, family = raw[23], 14 + header, 4
            elif kind == 0x86DD and len(raw) >= 54:
                source = socket.inet_ntop(socket.AF_INET6, raw[22:38])
                destination = socket.inet_ntop(socket.AF_INET6, raw[38:54])
                protocol, offset, family = raw[20], 54, 6
            else:
                continue
            sport = dport = 0
            if protocol in (6, 17) and len(raw) >= offset + 4:
                sport, dport = struct.unpack("!HH", raw[offset:offset + 4])
            key = (family, protocol, source, destination, sport, dport, link[2], raw[6:12].hex())
            if key not in flows:
                if len(flows) >= 10000:
                    raise RuntimeError("QA bridge metadata limit exceeded")
                flows[key] = {"packets": 0, "first_at": time.time(), "syn_at": []}
            row = flows[key]
            row["packets"] += 1
            row["last_at"] = time.time()
            if protocol == 6 and len(raw) >= offset + 14 and raw[offset + 13] & 2 and len(row["syn_at"]) < 64:
                row["syn_at"].append(time.time())
    print(json.dumps({"bridge_capture_complete": True, "started_at": started, "finished_at": time.time(),
                      "directionSource": "Dedicated QA bridge ingress: AF_PACKET.sll_pkttype != PACKET_OUTGOING; sole Relay attachment",
                      "hostEmitted": host_emitted,
                      "flows": [dict(family=k[0], protocol=k[1], source=k[2], destination=k[3],
                                     source_port=k[4], destination_port=k[5], packet_type=k[6], source_mac_hex=k[7], **v)
                                for k, v in flows.items()]}), flush=True)


if __name__ == "__main__":
    main()
