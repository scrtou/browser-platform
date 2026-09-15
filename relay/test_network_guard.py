"""Validate the new DIRECT policy before nftables can receive any rule text."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("network_guard", Path(__file__).with_name("network-guard.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@pytest.mark.parametrize("change", [
    {"host_ipv4": []}, {"host_ipv4": ["127.0.0.1"]}, {"host_ipv4": ["10.0.0.1"]},
    {"host_ipv4": ["8.8.8.9", "8.8.8.9"]}, {"host_ipv4": ["::1"]}, {"host_ipv4": "8.8.8.9"},
    {"approved_resolver_ip": "127.0.0.1"}, {"approved_resolver_ip": "dns.invalid"},
    {"approved_resolver_ip": "169.254.169.254"}, {"upstream_port": 1080}, {"role": "unrestricted"},
])
def test_direct_guard_rejects_invalid_or_mixed_evidence(change):
    policy = {"version": 1, "role": "direct", "uid": 1000, "gid": 1000, "internal_cidr": "172.20.0.0/24",
              "approved_resolver_ip": "172.30.9.2", "host_ipv4": ["8.8.8.9"]}
    assert guard.validate(policy) == policy
    with pytest.raises((ValueError, TypeError)):
        guard.rules({**policy, **change})
