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
from pathlib import Path

TABLE = "bp_guard"


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
    else:
        ipv4(value["upstream_ip"])
        number(value["upstream_port"])
    return value


def rules(value):
    value = validate(value)
    incoming = ""
    outgoing = ""
    if value["role"] == "worker":
        incoming = f"ip saddr {value['controller_ip']} tcp dport {value['display_port']} counter accept"
        outgoing = f"ip daddr {value['relay_ip']} tcp dport 1080 counter accept"
    else:
        incoming = f"ip saddr {value['internal_cidr']} tcp dport 1080 counter accept"
        outgoing = f"ip daddr {value['upstream_ip']} tcp dport {value['upstream_port']} counter accept"
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-config", type=Path)
    parser.add_argument("--relay-config", type=Path)
    parser.add_argument("--hold")
    args = parser.parse_args()
    if args.hold:
        hold(args.hold)
        return
    if not args.network_config:
        raise ValueError("A network policy is required")
    value = load(args.network_config)
    if bool(args.relay_config) != (value["role"] == "relay"):
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
