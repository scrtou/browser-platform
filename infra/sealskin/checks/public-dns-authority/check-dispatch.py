#!/usr/bin/env python3
"""Check the QA DNS dispatcher against real backends and bounded failures.

Use an already published diagnostic name, never a fresh TTL experiment name.
These checks are service validation, not evidence of the browser TTL cycle.
"""

import argparse
import asyncio
import copy
import importlib.util
import json
import os
from pathlib import Path
import time

import dns.asyncquery
import dns.flags
import dns.message
import dns.name
import dns.rcode


def require(value, message):
    if not value:
        raise ValueError(message)


async def check(args):
    config = json.loads(args.config.read_text())
    require(args.diagnostic in config["recursive_names"], "Explicit diagnostic name required")
    require(args.authoritative not in config["recursive_names"], "Separate authoritative name required")
    require(not config.get("delegation_names") or args.delegation_address, "NS address expectation required")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    records, checks = [], []

    async def exchange(name, kind="A", rd=True, transport="udp", expected="recursive", expected_address=None):
        query = dns.message.make_query(name, kind)
        if not rd:
            query.flags &= ~dns.flags.RD
        started = time.time()
        method = dns.asyncquery.udp if transport == "udp" else dns.asyncquery.tcp
        response = await method(query, config["listen_ipv4"], port=config["listen_port"], timeout=6)
        records.append({"name": name, "type": kind, "rd": rd, "transport": transport,
                        "started_at": started, "received_at": time.time(),
                        "request_wire_hex": query.to_wire().hex(), "response_wire_hex": response.to_wire().hex()})
        require(query.is_response(response), "Response transaction mismatch")
        if expected == "refused":
            require(response.rcode() == dns.rcode.REFUSED and not response.answer and
                    not response.flags & dns.flags.RA, "Query outside the allowed scope was not refused")
        else:
            require(response.rcode() == dns.rcode.NOERROR, "Expected successful answer")
            require(bool(response.flags & dns.flags.RA) == (expected == "recursive") and
                    bool(response.flags & dns.flags.AA) == (expected == "authoritative"), "Backend route mismatch")
            if kind == "A":
                addresses = {item.address for rrset in response.answer if rrset.rdtype == 1 for item in rrset}
                require(addresses == {expected_address or args.address}, "Unexpected diagnostic endpoint")
        return response

    try:
        for transport in ("udp", "tcp"):
            for name, kind, rd, expected in [
                (args.diagnostic, "A", True, "recursive"),
                (args.diagnostic, "A", False, "authoritative"),
                (args.authoritative, "A", True, "authoritative"),
                (config["zone"], "SOA", True, "authoritative"),
                (config["zone"], "NS", False, "authoritative"),
                ("example.net.", "A", True, "refused"),
                (config["zone"], "AXFR", True, "refused"),
                (config["zone"], "IXFR", True, "refused"),
                (config["zone"], "ANY", True, "refused"),
            ]:
                await exchange(name, kind, rd, transport, expected)
                checks.append({"transport": transport, "name": name, "type": kind, "rd": rd, "result": "PASS"})
            for name in config.get("delegation_names", []):
                await exchange(name, transport=transport, expected_address=args.delegation_address)
                checks.append({"transport": transport, "name": name, "type": "A", "rd": True, "result": "PASS"})
                if not dns.name.from_text(name).is_subdomain(dns.name.from_text(config["zone"])):
                    for kind, rd in (("A", False), ("AAAA", True)):
                        await exchange(name, kind, rd, transport, "refused")
                        checks.append({"transport": transport, "name": name, "type": kind, "rd": rd, "result": "PASS"})

        silent_reader, silent_writer = await asyncio.open_connection(config["listen_ipv4"], config["listen_port"])
        started = time.monotonic()
        try:
            await asyncio.gather(*(exchange(args.diagnostic, transport="tcp" if i % 2 else "udp") for i in range(24)))
            elapsed = time.monotonic() - started
            require(elapsed < 3, "Silent TCP client blocked normal queries")
            require(await asyncio.wait_for(silent_reader.read(1), 3) == b"", "Silent TCP connection was not closed")
        finally:
            silent_writer.close()
            await silent_writer.wait_closed()
        checks.append({"name": "silent_tcp_and_24_concurrent_queries", "seconds": elapsed, "result": "PASS"})

        spec = importlib.util.spec_from_file_location("qa_dns_dispatch", Path(__file__).with_name("dispatch.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loop = asyncio.get_running_loop()
        sink, _ = await loop.create_datagram_endpoint(asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0))
        local = copy.deepcopy(config)
        local["recursive_port"] = sink.get_extra_info("sockname")[1]
        local["listen_ipv4"] = "127.0.0.1"
        dispatcher = module.Dispatcher(local, args.output)
        query = dns.message.make_query(args.diagnostic, "A")
        started = time.monotonic()
        try:
            wire = await dispatcher.answer(query.to_wire(), ("127.0.0.1", 12345), "udp")
            elapsed = time.monotonic() - started
            response = dns.message.from_wire(wire)
            require(query.is_response(response) and response.rcode() == dns.rcode.SERVFAIL and 3.8 <= elapsed < 6,
                    "Silent backend did not fail within its budget")
            require(await dispatcher.answer(b"invalid", ("127.0.0.1", 12345), "udp") is None and
                    await dispatcher.answer(b"x" * 4097, ("127.0.0.1", 12345), "udp") is None,
                    "Malformed or oversized packet accepted")
        finally:
            sink.close()
        checks.extend([{"name": "silent_backend_budget", "seconds": elapsed, "result": "PASS"},
                       {"name": "malformed_and_oversized", "result": "PASS"}])
        result = {"result": "PASS", "checks": checks, "exchanges": len(records), "scope": "QA DNS service only"}
    except Exception as exc:
        result = {"result": "FAIL", "checks": checks, "error_type": type(exc).__name__, "error": str(exc)}
        raise
    finally:
        (args.output / "wire.json").write_text(json.dumps(records, indent=2) + "\n")
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"result": result["result"], "checks": len(checks), "exchanges": len(records)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--diagnostic", required=True)
    parser.add_argument("--authoritative", required=True)
    parser.add_argument("--address", required=True)
    parser.add_argument("--delegation-address")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    asyncio.run(check(args))


if __name__ == "__main__":
    main()
