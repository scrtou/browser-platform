#!/usr/bin/env python3
"""Bounded QA DNS front end: authoritative zone or exact-name recursion.

No cache, synthetic answer, address rewrite, system resolver or arbitrary
recursive forwarding is implemented here. The recursive backend is Unbound;
the authoritative backend is the unchanged CoreDNS zone. Both are loopback
high ports. Only explicitly listed A questions with RD use recursion.
"""

import argparse
import asyncio
import hashlib
import ipaddress
import json
import logging
import logging.handlers
import os
from pathlib import Path
import resource
import signal
import struct
import time

import dns.asyncquery
import dns.flags
import dns.message
import dns.name
import dns.rcode


def require(value, message):
    if not value:
        raise ValueError(message)


def validate(config):
    require(config["version"] == 1, "Unsupported dispatcher version")
    address = ipaddress.IPv4Address(config["listen_ipv4"])
    require(str(address) == config["listen_ipv4"] and not (address.is_multicast or address.is_unspecified), "Explicit listener required")
    require(1 <= config["listen_port"] <= 65535 and 1 <= config["lifetime_seconds"] <= 21600, "Invalid listener or lifetime")
    zone = dns.name.from_text(config["zone"])
    require(zone.is_absolute() and len(zone.labels) >= 3, "Explicit delegated QA zone required")
    names = config["recursive_names"]
    require(type(names) is list and 1 <= len(names) <= 8 and len(names) == len(set(names)), "Bounded explicit recursion names required")
    require(all(dns.name.from_text(name).is_subdomain(zone) and name == dns.name.from_text(name).to_text().lower() for name in names),
            "Recursive names must belong to the QA zone")
    delegation = config.get("delegation_names", [])
    require(type(delegation) is list and len(delegation) <= 4 and len(delegation) == len(set(delegation)) and
            not set(names) & set(delegation), "Bounded separate NS address names required")
    require(all(name == dns.name.from_text(name).to_text().lower() and
                dns.name.from_text(name).is_subdomain(zone.parent()) for name in delegation),
            "Explicit NS names must belong to the QA parent zone")
    require(config["authoritative_port"] != config["recursive_port"] and
            all(1024 <= config[key] <= 65535 for key in ("authoritative_port", "recursive_port")), "Separate loopback backends required")
    require(("run_as_uid" in config) == ("run_as_gid" in config), "Privilege drop needs both UID and GID")
    if "run_as_uid" in config:
        require(all(type(config[key]) is int and 1000 <= config[key] < 65534 for key in ("run_as_uid", "run_as_gid")),
                "Dedicated unprivileged UID and GID required")


class Dispatcher:
    def __init__(self, config, root):
        validate(config)
        self.config, self.root = config, root
        self.stop = asyncio.Event()
        self.jobs, self.writers = set(), set()
        self.counts = {"authoritative": 0, "recursive": 0, "refused": 0, "failed": 0}
        self.logger = logging.Logger("r5c2-dns-dispatch")
        handler = logging.handlers.RotatingFileHandler(root / "events.jsonl", maxBytes=2097152, backupCount=2, delay=True)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)

    def log(self, event, **fields):
        self.logger.info(json.dumps({"time": time.time(), "event": event, **fields}, separators=(",", ":")))

    async def answer(self, payload, peer, transport):
        if len(payload) > 4096:
            return None
        try:
            request = dns.message.from_wire(payload)
        except Exception:
            return None
        if request.flags & dns.flags.QR:
            return None
        response = dns.message.make_response(request)
        response.set_rcode(dns.rcode.REFUSED)
        if request.opcode() != 0 or len(request.question) != 1:
            return response.to_wire()
        question = request.question[0]
        name = question.name.to_text().lower()
        recursive = bool(request.flags & dns.flags.RD and question.rdtype == 1 and
                         name in self.config["recursive_names"] + self.config.get("delegation_names", []))
        if question.rdclass != 1 or question.rdtype in (251, 252, 255) or not (
                question.name.is_subdomain(dns.name.from_text(self.config["zone"])) or recursive):
            self.counts["refused"] += 1
            self.log("refused", client=peer[0], transport=transport, reason="OUTSIDE_QA_QUERY_SCOPE")
            return response.to_wire()
        route = "recursive" if recursive else "authoritative"
        port = self.config[route + "_port"]
        started = time.time()
        self.counts[route] += 1
        try:
            method = dns.asyncquery.udp if transport == "udp" else dns.asyncquery.tcp
            response = await method(request, "127.0.0.1", port=port, timeout=4)
            require(request.is_response(response), "Backend response mismatch")
            wire = response.to_wire(max_size=4096)
        except Exception as exc:
            self.counts["failed"] += 1
            response = dns.message.make_response(request)
            response.set_rcode(dns.rcode.SERVFAIL)
            wire = response.to_wire()
            self.log("backend_failed", route=route, name=name, error_type=type(exc).__name__)
        self.log("exchange", client=peer[0], client_port=peer[1], route=route, name=name, type=question.rdtype,
                 transport=transport, backend_port=port, started_at=started, received_at=time.time(),
                 request_wire_hex=payload.hex(), response_wire_hex=wire.hex())
        return wire

    async def tcp(self, reader, writer):
        if len(self.writers) >= 32:
            writer.close()
            return
        self.writers.add(writer)
        try:
            size = struct.unpack("!H", await asyncio.wait_for(reader.readexactly(2), 2))[0]
            require(12 <= size <= 4096, "DNS TCP query bound")
            payload = await asyncio.wait_for(reader.readexactly(size), 2)
            response = await self.answer(payload, writer.get_extra_info("peername"), "tcp")
            if response:
                writer.write(struct.pack("!H", len(response)) + response)
                await asyncio.wait_for(writer.drain(), 2)
        except (OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError):
            pass
        finally:
            self.writers.discard(writer)
            writer.close()

    async def run(self):
        owner = self

        class UDP(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, peer):
                if len(owner.jobs) >= 64:
                    return
                async def reply():
                    response = await owner.answer(data, peer, "udp")
                    if response:
                        self.transport.sendto(response, peer)
                task = asyncio.create_task(reply())
                owner.jobs.add(task)
                task.add_done_callback(owner.jobs.discard)

        loop = asyncio.get_running_loop()
        udp, _ = await loop.create_datagram_endpoint(UDP, local_addr=(self.config["listen_ipv4"], self.config["listen_port"]))
        tcp = await asyncio.start_server(self.tcp, self.config["listen_ipv4"], self.config["listen_port"], limit=4096, backlog=32)
        if "run_as_uid" in self.config:
            # Bind first, then permanently remove identity-changing and bind
            # capabilities before processing a request or opening a log file.
            os.setgroups([])
            os.setgid(self.config["run_as_gid"])
            os.setuid(self.config["run_as_uid"])
            status = Path("/proc/self/status").read_text().splitlines()
            require(all(int(line.split()[1], 16) == 0 for line in status
                        if line.startswith(("CapPrm:", "CapEff:", "CapAmb:"))), "Capabilities survived privilege drop")
        started = time.time()
        ready = {"pid": os.getpid(), "uid": os.geteuid(), "gid": os.getegid(), "started_at": started,
                 "config_sha256": hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest()}
        (self.root / "ready.json").write_text(json.dumps(ready))
        self.log("ready", **ready)
        print(json.dumps({"dns_dispatch_ready": True}), flush=True)
        try:
            await asyncio.wait_for(self.stop.wait(), self.config["lifetime_seconds"])
        except asyncio.TimeoutError:
            pass
        finally:
            udp.close()
            tcp.close()
            for writer in tuple(self.writers):
                writer.close()
            for task in tuple(self.jobs):
                task.cancel()
            await tcp.wait_closed()
            await asyncio.gather(*self.jobs, return_exceptions=True)
            value = {"counts": self.counts, "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                     "elapsed_seconds": time.time() - started}
            (self.root / "metrics.json").write_text(json.dumps(value))
            self.log("stopped", **value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    config = json.loads(args.config.read_text())
    validate(config)
    if args.validate_only:
        print(json.dumps({"result": "VALID", "names": config["recursive_names"]}))
        return
    args.state.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(not args.state.is_symlink() and args.state.stat().st_mode & 0o077 == 0, "Private owned state required")
    dispatcher = Dispatcher(config, args.state)
    async def run():
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(signum, dispatcher.stop.set)
        await dispatcher.run()
    asyncio.run(run())


if __name__ == "__main__":
    main()
