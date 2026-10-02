#!/usr/bin/env python3
"""Install a private network namespace policy before starting any workload.

The controller supplies immutable, non-secret numeric endpoints. This process
never changes host firewall tables. Only the trusted initializer has NET_ADMIN;
the persistent namespace holder and Relay run with an empty capability set.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

TABLE = "bp_guard"
DIRECT_DENIED = json.loads((Path(__file__).parent / "internal/proxy/direct-denied-ipv4.json").read_text())


def direct_public_ipv4(value):
    address = ipaddress.IPv4Address(value)
    return not any(address in ipaddress.IPv4Network(cidr) for cidr in DIRECT_DENIED)


def ipv4(value):
    address = ipaddress.IPv4Address(value)
    if address.is_loopback or address.is_unspecified or address.is_multicast:
        raise ValueError("Unusable endpoint address")
    return str(address)


def number(value, maximum=65535):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError("Invalid numeric policy field")
    return value


def validate(value):
    common = {"version", "role", "uid", "gid", "internal_cidr"}
    fields = {
        "worker": {"relay_ip", "controller_ip", "display_port"},
        "relay": {"upstream_ip", "upstream_port"},
        "relay-v2": {"upstream_ipv4", "upstream_port"},
        "direct": {"approved_resolver_ip", "host_ipv4"},
    }
    if value.get("version") != 1 or value.get("role") not in fields:
        raise ValueError("Unsupported policy")
    if set(value) != common | fields[value["role"]]:
        raise ValueError("Unexpected policy fields")
    number(value["uid"], 2**31 - 1)
    number(value["gid"], 2**31 - 1)
    subnet = ipaddress.IPv4Network(value["internal_cidr"], strict=True)
    if subnet.prefixlen < 16 or subnet.prefixlen > 29 or not subnet.is_private:
        raise ValueError("Unexpected internal subnet")
    if value["role"] == "worker":
        for key in ("relay_ip", "controller_ip"):
            if ipaddress.IPv4Address(ipv4(value[key])) not in subnet:
                raise ValueError("Endpoint is outside the generation network")
        if value["relay_ip"] == value["controller_ip"]:
            raise ValueError("Controller and Relay addresses collide")
        number(value["display_port"])
    elif value["role"] == "relay":
        ipv4(value["upstream_ip"])
        number(value["upstream_port"])
    elif value["role"] == "relay-v2":
        addresses = value["upstream_ipv4"]
        if (not isinstance(addresses, list) or not 1 <= len(addresses) <= 64 or
                any(not isinstance(item, str) for item in addresses)):
            raise ValueError("Invalid relay endpoint set")
        normalized = [ipv4(item) for item in addresses]
        if sorted(set(normalized)) != normalized:
            raise ValueError("Relay endpoint set must be sorted and unique")
        number(value["upstream_port"])
    else:
        resolver = ipaddress.IPv4Address(ipv4(value["approved_resolver_ip"]))
        if resolver.is_link_local or resolver.is_reserved:
            raise ValueError("Invalid approved resolver")
        addresses = value["host_ipv4"]
        if (not isinstance(addresses, list) or not 1 <= len(addresses) <= 64 or
                any(not isinstance(item, str) or not direct_public_ipv4(item) for item in addresses) or
                sorted(set(addresses)) != addresses):
            raise ValueError("Invalid host address evidence")
    return value


def rules(value):
    value = validate(value)
    incoming = ""
    outgoing = ""
    restrictions = ""
    if value["role"] == "worker":
        incoming = f"ip saddr {value['controller_ip']} tcp dport {value['display_port']} counter accept"
        outgoing = f"ip daddr {value['relay_ip']} tcp dport 1080 counter accept"
    elif value["role"] == "relay":
        incoming = f"ip saddr {value['internal_cidr']} tcp dport 1080 counter accept"
        outgoing = f"ip daddr {value['upstream_ip']} tcp dport {value['upstream_port']} counter accept"
    elif value["role"] == "relay-v2":
        incoming = f"ip saddr {value['internal_cidr']} tcp dport 1080 counter accept"
        endpoints = ", ".join(value["upstream_ipv4"])
        outgoing = f"ip daddr {{ {endpoints} }} tcp dport {value['upstream_port']} counter accept"
    else:
        incoming = f"ip saddr {value['internal_cidr']} tcp dport 1080 counter accept"
        denied = ", ".join(DIRECT_DENIED)
        hosts = ", ".join(value["host_ipv4"])
        # The sole private-network exception is DNS to the approved numeric
        # resolver. Targets requested via SOCKS can never use DNS/DoT ports.
        # Replies to the accepted internal SOCKS5 listener are not new LAN
        # connections. Admit only their conntrack reply direction before the
        # protected-destination filter; a new connection, even from port 1080,
        # must still be rejected.
        restrictions = f"""ip daddr {value['internal_cidr']} tcp sport 1080 ct direction reply ct state established counter accept
  ip daddr {value['approved_resolver_ip']} udp dport 53 counter accept
  ip daddr {value['approved_resolver_ip']} tcp dport 53 counter accept
  ip daddr {{ {denied} }} counter drop
  ip daddr {{ {hosts} }} counter drop
  tcp dport {{ 53, 853 }} counter drop"""
        outgoing = "meta nfproto ipv4 meta l4proto tcp counter accept"
    # The entire replacement is one nftables transaction. No permissive window.
    return f"""add table inet {TABLE}
flush table inet {TABLE}
table inet {TABLE} {{
 chain input {{
  type filter hook input priority 0; policy drop;
  ct state invalid counter drop
  iifname "lo" counter accept
  ct state established,related counter accept
  {incoming}
  counter drop
 }}
 chain output {{
  type filter hook output priority 0; policy drop;
  ct state invalid counter drop
  ip daddr 127.0.0.11 counter drop
  oifname "lo" counter accept
  {restrictions}
  ct state established,related counter accept
  {outgoing}
  counter drop
 }}
 chain forward {{
  type filter hook forward priority 0; policy drop;
  counter drop
 }}
}}
"""


def load(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 16384:
        raise ValueError("Policy must be a private regular file")
    return validate(json.loads(path.read_text()))


def namespace_is_private(role):
    # The controller also forbids host network mode. Refuse host-like interface
    # inventories before invoking nft, even if a container was misconfigured.
    names = set(os.listdir("/sys/class/net"))
    allowed = {"lo", "eth0"} if role == "worker" else {"lo", "eth0", "eth1"}
    if not Path("/.dockerenv").exists() or names != allowed:
        raise ValueError("Expected a dedicated Docker network namespace")


def hold(revision):
    if len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("Invalid revision")
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
    )
    if (
        os.getuid() == 0
        or any(
            int(status[key].strip(), 16)
            for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
        )
        or status["NoNewPrivs"].strip() != "1"
    ):
        raise ValueError("Capabilities were not dropped")
    print(json.dumps({"network_guard_ready": revision}), flush=True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    while True:
        signal.pause()


def inspect_rules(value):
    """Read the effective table, excluding volatile handles and counters from its hash."""
    namespace_is_private(value["role"])
    result = subprocess.run(["nft", "-j", "list", "table", "inet", TABLE],
                            text=True, capture_output=True, check=True, timeout=3)
    if len(result.stdout) > 256 * 1024:
        raise ValueError("Rules observation too large")
    table = json.loads(result.stdout)
    drops = 0
    for entry in table.get("nftables", []):
        rule = entry.get("rule", {})
        if rule.get("chain") == "output" and any("drop" in expr for expr in rule.get("expr", [])):
            drops += sum(expr["counter"].get("packets", 0) for expr in rule["expr"] if "counter" in expr)

    def stable(item):
        if isinstance(item, dict):
            return {key: stable(value) for key, value in item.items()
                    if key not in {"handle", "packets", "bytes", "metainfo"}}
        if isinstance(item, list):
            return [stable(value) for value in item if not isinstance(value, dict) or "metainfo" not in value]
        return item

    encode = lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")).encode()
    return {"version": 1, "role": value["role"], "config_sha256": hashlib.sha256(encode(value)).hexdigest(),
            "rules_sha256": hashlib.sha256(encode(stable(table))).hexdigest(), "output_dropped_packets": drops}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-config", type=Path)
    parser.add_argument("--relay-config", type=Path)
    parser.add_argument("--hold")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--inspect-output")
    parser.add_argument("--apply-only", action="store_true")
    args = parser.parse_args()
    if args.hold:
        hold(args.hold)
        return
    if not args.network_config:
        raise ValueError("A network policy is required")
    value = load(args.network_config)
    if args.inspect and args.apply_only:
        raise ValueError("Inspect and apply-only are mutually exclusive")
    if args.inspect:
        observed = inspect_rules(value)
        if args.inspect_output:
            nonce = args.inspect_output
            if len(nonce) != 32 or any(char not in "0123456789abcdef" for char in nonce):
                raise ValueError("Invalid observation nonce")
            observed["nonce"] = nonce
            # Inspect with NET_ADMIN, then write as the controller's configured
            # UID. Docker's archive API cannot see this daemon's /dev/shm view.
            os.setgid(value["gid"])
            os.setuid(value["uid"])
            fd, temporary = tempfile.mkstemp(prefix=".bp-coherence-", dir="/run/browser-platform-observation")
            with os.fdopen(fd, "w") as handle:
                os.fchmod(handle.fileno(), 0o600)
                json.dump(observed, handle)
            os.replace(temporary, "/run/browser-platform-observation/result.json")
        else:
            print(json.dumps(observed, sort_keys=True), flush=True)
        return
    if args.apply_only:
        if args.relay_config or value["role"] != "relay-v2":
            raise ValueError("Apply-only is restricted to dynamic Relay policy")
        namespace_is_private(value["role"])
        policy = rules(value)
        for command in (["nft", "--check", "-f", "-"], ["nft", "-f", "-"]):
            subprocess.run(command, input=policy, text=True, check=True, capture_output=True)
        revision = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        print(json.dumps({"network_guard_applied": revision}), flush=True)
        return
    if bool(args.relay_config) != (value["role"] in {"relay", "relay-v2", "direct"}):
        raise ValueError("Role and process do not match")
    namespace_is_private(value["role"])
    policy = rules(value)
    for command in (["nft", "--check", "-f", "-"], ["nft", "-f", "-"]):
        subprocess.run(
            command, input=policy, text=True, check=True, capture_output=True
        )
    revision = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    child = [sys.executable, "-B", __file__, "--hold", revision]
    if args.relay_config:
        child = ["/profile-relay", "-config", str(args.relay_config)]
    # setpriv performs the privilege transition before exec. Bounding and ambient
    # capabilities are empty in the long-lived process, including after restart.
    os.execvp(
        "setpriv",
        [
            "setpriv",
            "--reuid=" + str(value["uid"]),
            "--regid=" + str(value["gid"]),
            "--clear-groups",
            "--bounding-set=-all",
            "--inh-caps=-all",
            "--ambient-caps=-all",
            "--no-new-privs",
            *child,
        ],
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print("NETWORK_GUARD_INITIALIZATION_FAILED", file=sys.stderr)
        sys.exit(1)
