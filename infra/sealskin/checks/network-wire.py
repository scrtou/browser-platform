#!/usr/bin/env python3
"""Record outbound L3/L4 metadata on one private QA namespace interface.

Payloads, DNS question text, headers, cookies and credentials are never stored.
Run as an ephemeral diagnostic container sharing only the QA guard namespace.
"""

import argparse
import ipaddress
import json
import signal
import socket
import struct
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-ip", required=True)
    parser.add_argument("--interface", choices=("eth0", "eth1"), default="eth0")
    parser.add_argument("--seconds", type=int, default=300)
    args = parser.parse_args()
    worker = str(ipaddress.IPv4Address(args.worker_ip))
    assert 1 <= args.seconds <= 900
    stop = False

    def finish(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, finish)
    signal.signal(signal.SIGINT, finish)
    packets = {}
    inbound_ipv6 = {}
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3)) as capture:
        capture.bind((args.interface, 0))
        capture.settimeout(0.25)
        print(json.dumps({"wire_capture_ready": True}), flush=True)
        deadline = time.monotonic() + args.seconds
        while not stop and time.monotonic() < deadline:
            try:
                raw, link = capture.recvfrom(65535)
            except TimeoutError:
                continue
            if len(raw) < 34:
                continue
            kind = struct.unpack("!H", raw[12:14])[0]
            # AF_PACKET also receives LAN multicast. Its address tuple carries
            # the kernel's direction; IPv6 source addresses alone cannot tell
            # whether this namespace emitted a frame. Retain received IPv6 as
            # diagnostic evidence, but never call it Worker outbound traffic.
            if link[2] != socket.PACKET_OUTGOING:
                if kind == 0x86DD and len(raw) >= 54:
                    key = (socket.inet_ntop(socket.AF_INET6, raw[22:38]),
                           socket.inet_ntop(socket.AF_INET6, raw[38:54]), link[2])
                    if key not in inbound_ipv6 and len(inbound_ipv6) >= 10000:
                        raise RuntimeError("QA received-packet metadata limit exceeded")
                    inbound_ipv6[key] = inbound_ipv6.get(key, 0) + 1
                continue
            if kind == 0x800:
                header = (raw[14] & 15) * 4
                protocol = raw[23]
                source = socket.inet_ntop(socket.AF_INET, raw[26:30])
                destination = socket.inet_ntop(socket.AF_INET, raw[30:34])
                if source != worker:
                    continue
                offset, family = 14 + header, 4
            elif kind == 0x86DD and len(raw) >= 54:
                protocol = raw[20]
                source = socket.inet_ntop(socket.AF_INET6, raw[22:38])
                destination = socket.inet_ntop(socket.AF_INET6, raw[38:54])
                offset, family = 54, 6
            else:
                continue
            sport = dport = 0
            if protocol in (6, 17) and len(raw) >= offset + 4:
                sport, dport = struct.unpack("!HH", raw[offset : offset + 4])
            key = (family, protocol, source, destination, sport, dport)
            if key not in packets and len(packets) >= 10000:
                raise RuntimeError("QA packet metadata limit exceeded")
            packets[key] = packets.get(key, 0) + 1
    print(
        json.dumps(
            {
                "directionSource": "AF_PACKET.sll_pkttype == PACKET_OUTGOING",
                "receivedIPv6": [dict(source=k[0], destination=k[1], packetType=k[2], packets=count)
                                 for k, count in inbound_ipv6.items()],
                "outbound": [
                    dict(
                        family=k[0],
                        protocol=k[1],
                        source=k[2],
                        destination=k[3],
                        source_port=k[4],
                        destination_port=k[5],
                        packets=count,
                    )
                    for k, count in packets.items()
                ]
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
