#!/usr/bin/env python3
"""Prepare DNS records and collect bounded delegation/cache evidence.

No zone, resolver configuration, container, or production setting is modified.
Samples originate in this process's network namespace. They do not on their
own prove the DIRECT browser, proxy bootstrap, or upstream website DNS paths;
those require matching browser/packet and authoritative query logs.
"""

import argparse
import hashlib
import ipaddress
import json
import math
import os
import re
import sys
import time
import uuid
from pathlib import Path

import dns
import dns.exception
import dns.flags
import dns.message
import dns.opcode
import dns.query
import dns.rcode
import dns.rdataclass
import dns.rdatatype

PATHS = {"direct", "bootstrap", "upstream"}
PHASES = ("before", "cached", "expired")
EVIDENCE_VERSION = 2
MULTI_CACHE_EVIDENCE_VERSION = 3
TIMEOUT_SECONDS = 5
TTL_ROUNDING_SECONDS = 1


class EvidenceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load(path, with_digest=False):
    with path.open("rb") as handle:
        data = handle.read(4 * 1024 * 1024 + 1)
    require(len(data) <= 4 * 1024 * 1024, "Evidence file exceeds the size limit")
    value = json.loads(data)
    require(type(value) is dict, "Expected an evidence object")
    return (value, hashlib.sha256(data).hexdigest()) if with_digest else value


def write(path, value):
    with path.open("x") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def name(value):
    require(type(value) is str, "DNS name must be text")
    value = value.rstrip(".").lower()
    require(len(value) <= 253 and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", s)
                                    for s in value.split(".")), "Invalid DNS name")
    return value + "."


def address(value, public=False):
    ip = ipaddress.IPv4Address(value)
    require(str(ip) == value and not (ip.is_loopback or ip.is_unspecified or ip.is_multicast),
            "Expected a canonical unicast IPv4 address")
    if public:
        require(ip.is_global, "Public acceptance requires publicly routed fixture/authority addresses")
    return value


def timestamp(value):
    require(type(value) in (int, float) and math.isfinite(value) and value > 0, "Invalid evidence timestamp")
    return value


def validate(config, public=False):
    zone = name(config["zone"])
    require(type(config["ttl_seconds"]) is int and 10 <= config["ttl_seconds"] <= 300, "TTL must be 10 to 300 seconds")
    require(type(config["paths"]) is dict and set(config["paths"]) == PATHS, "All three DNS paths are required")
    authorities = config["authorities"]
    require(type(authorities) is list and 1 <= len(authorities) <= 4, "One to four authorities are required")
    address(config["parent_authority_ipv4"], public)
    for authority in authorities:
        name(authority["name"])
        address(authority["ipv4"], public)
    require(len({name(a["name"]) for a in authorities}) == len(authorities) and
            len({a["ipv4"] for a in authorities}) == len(authorities), "Authority names and addresses must be unique")
    for path in config["paths"].values():
        require(type(path["resolver_id"]) is str and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", path["resolver_id"]),
                "Invalid resolver identity")
        address(path["resolver_ipv4"])
        require(path["before_ipv4"] != path["after_ipv4"], "Rotation must change the endpoint")
        for field in ("before_ipv4", "after_ipv4"):
            address(path[field], public)
    if public:
        require(not zone.endswith((".invalid.", ".test.", ".localhost.", ".example.")), "A real delegated QA zone is required")


def validate_plan(plan):
    require(type(plan["version"]) is int and plan["version"] in (1, 2), "Unsupported plan version")
    if plan["version"] == 2:
        require(type(plan["cache_observations"]) is int and 2 <= plan["cache_observations"] <= 32,
                "Multiple-cache plans require 2 to 32 observations per path and phase")
    else:
        require("cache_observations" not in plan, "Single-observation plan cannot ignore a cache observation count")
    validate(plan["config"], public=True)
    timestamp(plan["created_at"])
    require(type(plan["names"]) is dict and set(plan["names"]) == PATHS, "Plan must name all three DNS paths")
    zone = name(plan["config"]["zone"])
    tokens = set()
    for key, qname in plan["names"].items():
        match = re.fullmatch(re.escape(key) + r"-([a-f0-9]{16})\." + re.escape(zone), qname)
        require(match is not None, "Test name is not bound to this path and delegated zone")
        tokens.add(match.group(1))
    require(len(tokens) == 1, "Test names must belong to the same run")


def prepare(config_path, output, cache_observations=1):
    config = load(config_path)
    validate(config)
    require(type(cache_observations) is int and 1 <= cache_observations <= 32, "Cache observation count must be 1 to 32")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    token = uuid.uuid4().hex[:16]
    plan = {"version": 1, "config": config, "created_at": time.time(),
            "names": {key: name(f"{key}-{token}." + config["zone"]) for key in sorted(PATHS)}}
    if cache_observations > 1:
        plan.update(version=2, cache_observations=cache_observations)
    write(output / "plan.json", plan)
    delegation = [f"{name(config['zone'])} {config['ttl_seconds']} IN NS {name(a['name'])}" for a in config["authorities"]]
    delegation += [f"{name(a['name'])} {config['ttl_seconds']} IN A {a['ipv4']}" for a in config["authorities"]
                   if name(a["name"]).endswith("." + name(config["zone"]))]
    (output / "parent-delegation.txt").write_text("\n".join(delegation) + "\n")
    for phase, field in (("before", "before_ipv4"), ("after", "after_ipv4")):
        records = [f"{plan['names'][key]} {config['ttl_seconds']} IN A {config['paths'][key][field]}" for key in sorted(PATHS)]
        (output / (phase + "-records.txt")).write_text("\n".join(records) + "\n")
    print(json.dumps({"result": "PREPARED", "plan_sha256": digest(plan), "external_changes": 0,
                      "records": str(output), "public_acceptance": "NOT_RUN"}))
    return plan


def wire(value):
    require(type(value) is str and 24 <= len(value) <= 131070 and re.fullmatch(r"[a-f0-9]+", value) and len(value) % 2 == 0,
            "Missing or invalid DNS wire")
    try:
        return dns.message.from_wire(bytes.fromhex(value), one_rr_per_rrset=True, ignore_trailing=False)
    except (dns.exception.DNSException, ValueError) as exc:
        raise EvidenceError("Malformed DNS wire") from exc


def response_header(request, response, truncated=False):
    require(request.is_response(response) and response.question == request.question and
            response.opcode() == dns.opcode.QUERY and response.rcode() == dns.rcode.NOERROR and
            bool(response.flags & dns.flags.TC) == truncated and
            bool(response.flags & dns.flags.RD) == bool(request.flags & dns.flags.RD),
            "DNS response does not match its successful query")


def record_list(response):
    records = [{"section": section_name, "name": rr.name.to_text().lower(),
                "class": dns.rdataclass.to_text(rr.rdclass), "type": dns.rdatatype.to_text(rr.rdtype),
                "ttl": rr.ttl, "value": record.to_text().lower()}
               for section_name, section in (("answer", response.answer), ("authority", response.authority), ("additional", response.additional))
               for rr in section for record in rr]
    require(len(records) <= 128, "Too many DNS records")
    return records


def query(server, qname, qtype, recursive=True):
    request = dns.message.make_query(qname, qtype, use_edns=False)
    if not recursive:
        request.flags &= ~dns.flags.RD
    deadline = time.monotonic() + TIMEOUT_SECONDS
    started = time.time()
    response = dns.query.udp(request, server, timeout=TIMEOUT_SECONDS, one_rr_per_rrset=True)
    transports = ["udp"]
    truncated_wire = None
    if response.flags & dns.flags.TC:
        response_header(request, response, truncated=True)
        truncated_wire = response.to_wire().hex()
        timeout = deadline - time.monotonic()
        require(timeout > 0, "DNS query exceeded its total budget")
        response = dns.query.tcp(request, server, timeout=timeout, one_rr_per_rrset=True)
        transports.append("tcp")
    response_header(request, response)
    require(time.monotonic() <= deadline, "DNS query exceeded its total budget")
    received = time.time()
    return {"server": server, "name": qname, "type": qtype, "recursive": recursive,
            "authoritative": bool(response.flags & dns.flags.AA), "transports": transports,
            "started_at": started, "received_at": received, "records": record_list(response),
            "query_wire_hex": request.to_wire().hex(), "wire_hex": response.to_wire().hex(),
            "truncated_response_wire_hex": truncated_wire}


def records_of(sample, qname, qtype, sections=("answer",)):
    return [r for r in sample["records"] if r["section"] in sections and r["name"] == qname and
            r["type"] == qtype and r["class"] == "IN"]


def validate_query(value, server, qname, qtype, recursive, window):
    require(type(value) is dict and value["server"] == server and value["name"] == qname and
            value["type"] == qtype and value["recursive"] is recursive, "DNS endpoint or question binding changed")
    started, received = timestamp(value["started_at"]), timestamp(value["received_at"])
    require(window[0] <= started <= received <= window[1] and received - started <= TIMEOUT_SECONDS + 0.25,
            "DNS timestamps are outside the phase or query budget")
    request, response = wire(value["query_wire_hex"]), wire(value["wire_hex"])
    expected = dns.message.make_query(qname, qtype, use_edns=False)
    require(not request.flags & dns.flags.QR and request.opcode() == dns.opcode.QUERY and
            request.question == expected.question and bool(request.flags & dns.flags.RD) is recursive and
            not request.answer and not request.authority and not request.additional and request.edns == -1,
            "Stored DNS request does not match the planned query")
    response_header(request, response)
    require(value["authoritative"] is bool(response.flags & dns.flags.AA) and value["records"] == record_list(response) and
            all(type(record["ttl"]) is int for record in value["records"]),
            "DNS record metadata differs from its wire")
    require(value["transports"] in (["udp"], ["udp", "tcp"]), "Unexpected DNS transport path")
    if value["transports"] == ["udp", "tcp"]:
        response_header(request, wire(value["truncated_response_wire_hex"]), truncated=True)
    else:
        require(value["truncated_response_wire_hex"] is None, "Unexpected truncated response")
    if recursive:
        require(response.flags & dns.flags.RA and not response.flags & dns.flags.AA,
                "Response does not establish an available recursive path")


def delegation(config, evidence):
    zone = name(config["zone"])
    evidence["parent"] = query(config["parent_authority_ipv4"], zone, "NS", recursive=False)
    resolver = config["paths"]["bootstrap"]["resolver_ipv4"]
    for authority in config["authorities"]:
        child = {}
        evidence["children"].append(child)
        child["address"] = query(resolver, name(authority["name"]), "A")
        child["soa"] = query(authority["ipv4"], zone, "SOA", recursive=False)
        child["ns"] = query(authority["ipv4"], zone, "NS", recursive=False)


def validate_delegation(config, evidence, window):
    zone = name(config["zone"])
    expected = {name(a["name"]) for a in config["authorities"]}
    parent = evidence["parent"]
    validate_query(parent, config["parent_authority_ipv4"], zone, "NS", False, window)
    require({r["value"] for r in records_of(parent, zone, "NS", ("answer", "authority"))} == expected,
            "Parent delegation does not match every planned authority")
    children = evidence["children"]
    require(type(children) is list and len(children) == len(config["authorities"]), "Incomplete child authority evidence")
    resolver = config["paths"]["bootstrap"]["resolver_ipv4"]
    for authority, child in zip(config["authorities"], children):
        ns_name = name(authority["name"])
        validate_query(child["address"], resolver, ns_name, "A", True, window)
        require(authority["ipv4"] in {r["value"] for r in records_of(child["address"], ns_name, "A")},
                "Authority address is absent from its recursive answer")
        if ns_name.endswith("." + zone):
            require(authority["ipv4"] in {r["value"] for r in records_of(parent, ns_name, "A", ("additional",))},
                    "In-zone authority has no matching parent glue")
        for kind in ("soa", "ns"):
            validate_query(child[kind], authority["ipv4"], zone, kind.upper(), False, window)
            require(child[kind]["authoritative"], "Child DNS answer is not authoritative")
        require(len(records_of(child["soa"], zone, "SOA")) == 1, "Child SOA evidence is missing")
        require({r["value"] for r in records_of(child["ns"], zone, "NS")} == expected, "Child NS set differs from delegation")


def a_records(value, qname, expected):
    records = records_of(value, qname, "A")
    answers = [record for record in value["records"] if record["section"] == "answer"]
    require(records and len(records) == len(answers) and {r["value"] for r in records} == {expected} and
            all(0 < r["ttl"] <= 300 for r in records), "Unexpected address, answer or TTL")
    return records


def evidence_version(plan):
    return MULTI_CACHE_EVIDENCE_VERSION if plan["version"] == 2 else EVIDENCE_VERSION


def recursive_observations(plan, item):
    if plan["version"] == 1:
        require("recursive_samples" not in item, "Legacy evidence cannot ignore additional recursive samples")
        return [item["recursive"]]
    values = item["recursive_samples"]
    require(type(values) is list and len(values) == plan["cache_observations"], "Incomplete recursive sample set")
    require(values[0] == item["recursive"], "Primary recursive sample does not match the complete sample set")
    return values


def validate_sample(plan, value, phase):
    require(value["version"] == evidence_version(plan) and value["phase"] == phase and
            value["plan_sha256"] == digest(plan), "Evidence version, phase or plan binding changed")
    origin = value["origin"]
    require(type(origin["hostname"]) is str and origin["hostname"] and type(origin["network_namespace"]) is str and
            re.fullmatch(r"net:\[\d+\]", origin["network_namespace"]), "Missing sampling origin")
    window = timestamp(value["started_at"]), timestamp(value["finished_at"])
    require(plan["created_at"] <= window[0] <= window[1], "Invalid phase timestamps")
    config = plan["config"]
    validate_delegation(config, value["delegation"], window)
    require(type(value["paths"]) is dict and set(value["paths"]) == PATHS, "Missing DNS path evidence")
    for key, policy in config["paths"].items():
        item, qname = value["paths"][key], plan["names"][key]
        require(item["resolver_id"] == policy["resolver_id"], "Resolver identity changed")
        require(type(item["authority"]) is list and len(item["authority"]) == len(config["authorities"]),
                "Incomplete authoritative endpoint evidence")
        field = "before_ipv4" if phase == "before" else "after_ipv4"
        previous_received = window[0]
        for authority, answer in zip(config["authorities"], item["authority"]):
            validate_query(answer, authority["ipv4"], qname, "A", False, window)
            require(answer["authoritative"] and answer["started_at"] >= previous_received, "Invalid authority query sequence")
            records = a_records(answer, qname, policy[field])
            require(all(r["ttl"] == config["ttl_seconds"] for r in records), "Authoritative TTL differs from the reviewed plan")
            previous_received = answer["received_at"]
        expected = policy["after_ipv4"] if phase == "expired" else policy["before_ipv4"]
        for recursive in recursive_observations(plan, item):
            validate_query(recursive, policy["resolver_ipv4"], qname, "A", True, window)
            require(recursive["started_at"] >= previous_received, "Recursive samples overlap or predate the authoritative check")
            require(all(r["ttl"] <= config["ttl_seconds"] for r in a_records(recursive, qname, expected)),
                    "Recursive TTL exceeds the controlled authoritative TTL")
            previous_received = recursive["received_at"]


def sample(run, phase):
    require(dns.__version__ == "2.8.0", "Use the locked DNS dependency")
    require(phase in PHASES, "Unknown sampling phase")
    require(not (run / (phase + ".json")).exists() and not (run / (phase + ".failed.json")).exists(),
            "Phase evidence already exists; use a new run after failure")
    plan = load(run / "plan.json")
    validate_plan(plan)
    for previous in PHASES[:PHASES.index(phase)]:
        validate_sample(plan, load(run / (previous + ".json")), previous)
    config = plan["config"]
    value = {"version": evidence_version(plan), "plan_sha256": digest(plan), "phase": phase,
             "origin": {"hostname": os.uname().nodename, "network_namespace": os.readlink("/proc/self/ns/net")},
             "started_at": time.time(), "delegation": {"children": []}, "paths": {}}
    try:
        delegation(config, value["delegation"])
        for key in sorted(PATHS):
            policy, qname = config["paths"][key], plan["names"][key]
            item = {"resolver_id": policy["resolver_id"], "authority": []}
            value["paths"][key] = item
            for authority in config["authorities"]:
                item["authority"].append(query(authority["ipv4"], qname, "A", recursive=False))
            item["recursive"] = query(policy["resolver_ipv4"], qname, "A")
            if plan["version"] == 2:
                item["recursive_samples"] = [item["recursive"]]
                for _ in range(plan["cache_observations"] - 1):
                    item["recursive_samples"].append(query(policy["resolver_ipv4"], qname, "A"))
        value["finished_at"] = time.time()
        validate_sample(plan, value, phase)
    except (ValueError, KeyError, TypeError, OSError, dns.exception.DNSException) as exc:
        value["finished_at"] = time.time()
        value["failure"] = type(exc).__name__
        write(run / (phase + ".failed.json"), value)
        raise
    write(run / (phase + ".json"), value)
    print(json.dumps({"result": "RECORDED", "phase": phase, "public_acceptance": "PENDING_VERIFICATION"}))
    return value


def verify(run):
    require(dns.__version__ == "2.8.0", "Use the locked DNS dependency")
    require(not (run / "verification.json").exists(), "Verification output already exists")
    plan = load(run / "plan.json")
    validate_plan(plan)
    snapshots = {phase: load(run / (phase + ".json"), with_digest=True) for phase in PHASES}
    samples = {phase: entry[0] for phase, entry in snapshots.items()}
    for phase, value in samples.items():
        validate_sample(plan, value, phase)
    require(all(value["origin"] == samples["before"]["origin"] for value in samples.values()),
            "Sampling origin changed between cache phases")
    require(samples["before"]["finished_at"] <= samples["cached"]["started_at"] and
            samples["cached"]["finished_at"] <= samples["expired"]["started_at"], "Sampling phases overlap or are out of order")
    for key in sorted(PATHS):
        qname = plan["names"][key]
        before, cached, expired = (recursive_observations(plan, samples[phase]["paths"][key]) for phase in PHASES)
        # Replies report whole seconds at some point between request and receipt.
        # Compare their possible expiry intervals; a refreshed/full TTL is not a
        # decaying cache observation merely because the old address is retained.
        def expiry(answer):
            ttl = min(r["ttl"] for r in records_of(answer, qname, "A"))
            return answer["started_at"] + ttl, answer["received_at"] + ttl + TTL_ROUNDING_SECONDS
        initial_expiries = [expiry(answer) for answer in before]
        for answer in cached:
            cached_expiry = expiry(answer)
            require(max(v["received_at"] for v in before) < answer["started_at"] and
                    answer["received_at"] < min(v[0] for v in initial_expiries),
                    "Cached observation is not wholly before initial expiry")
            require(any(max(initial[0], cached_expiry[0]) <= min(initial[1], cached_expiry[1]) for initial in initial_expiries),
                    "Cached TTL does not decay with the observed elapsed time")
        require(all(answer["started_at"] >= max(v[1] for v in initial_expiries) for answer in expired),
                "Expired observation is too early after allowing for TTL rounding")
    result = {"result": "PARTIAL", "delegation_and_recursive_ttl": "PASS", "public_N04_N08": "NOT_COMPLETE",
              "evidence_version": evidence_version(plan), "plan_sha256": digest(plan), "checked_at": time.time(),
              "cache_observations_per_path_phase": plan.get("cache_observations", 1),
              "evidence_sha256": {phase: entry[1] for phase, entry in snapshots.items()},
              "remaining": ["Root-to-parent delegation trace and authoritative query logs matching the approved recursive sources",
                            "Normal DIRECT browser, proxy-bootstrap generation and real upstream website DNS path evidence",
                            "Worker bypass capture and endpoint rotation/failure/recovery evidence from the same run"]}
    write(run / "verification.json", result)
    print(json.dumps(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("prepare")
    create.add_argument("--config", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--cache-observations", type=int, default=1,
                        help="Use a version 2 plan with 2 to 32 complete observations per path and phase; default retains the single-cache model")
    observe = commands.add_parser("sample")
    observe.add_argument("--run", type=Path, required=True)
    observe.add_argument("--phase", choices=PHASES, required=True)
    check = commands.add_parser("verify")
    check.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.config, args.output, args.cache_observations)
        elif args.command == "sample":
            sample(args.run, args.phase)
        else:
            verify(args.run)
    except (ValueError, KeyError, TypeError, OSError, dns.exception.DNSException) as exc:
        print(json.dumps({"result": "REJECTED", "reason": str(exc)}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
