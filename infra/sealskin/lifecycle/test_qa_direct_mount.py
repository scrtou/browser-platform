"""Host address evidence must stay exclusive to an approved DIRECT generation."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("qa_direct_proxy", Path(__file__).with_name("qa-network-docker-proxy.py"))
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


@pytest.mark.parametrize("change", ["valid", "worker", "guard", "probe", "image", "source", "target", "writable",
                                    "profile", "operation", "mode", "revision", "missing", "symlink"])
def test_direct_host_mount_requires_exact_approved_generation(tmp_path, change):
    root = tmp_path / "qa"
    home = root / "storage/network-qa/qa-home"
    identity = {"scope": "b" * 64, "owner": "network-qa", "home": "qa-home",
                "home_hash": hashlib.sha256(str(home).encode()).hexdigest(),
                "app": "qa-app", "profile": "qa-profile", "operation": "c" * 32}
    policy = {"mode": "direct", "approved_resolver_id": "qa-dns", "approved_resolver_ip": "172.30.9.2"}
    digest = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    record = {"identity": identity, "policy": policy, "policy_id": "qa-direct", "policy_sha256": digest}
    path = root / "config/.config/sealskin/profile-network-runtime" / (identity["home_hash"] + ".json")
    path.parent.mkdir(parents=True)
    labels = {proxy.PREFIX + key: value for key, value in identity.items()}
    labels.update({proxy.PREFIX + "role": "relay", proxy.PREFIX + "network-policy": "qa-direct",
                   proxy.PREFIX + "network-policy-sha256": digest})
    allowed = {"direct_images": ["qa-direct-image"]}
    image, source, destination, readonly = "qa-direct-image", proxy.DIRECT_HOST_SOURCE, proxy.DIRECT_HOST_TARGET, True
    if change in {"worker", "guard", "probe"}:
        labels[proxy.PREFIX + "role"] = change
    elif change == "image":
        image = "other-image"
    elif change == "source":
        source = "/proc/2/net/fib_trie"
    elif change == "target":
        destination = "/config/host-addresses"
    elif change == "writable":
        readonly = False
    elif change in {"profile", "operation"}:
        labels[proxy.PREFIX + change] = "different"
    elif change == "mode":
        policy["mode"] = "proxy_required"
    elif change == "revision":
        labels[proxy.PREFIX + "network-policy-sha256"] = "0" * 64
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    if change == "missing":
        path.unlink()
    elif change == "symlink":
        target = path.with_suffix(".target")
        path.rename(target)
        path.symlink_to(target)
    result = proxy.direct_host_bind_allowed(root, allowed, labels, image, source, destination, readonly)
    assert result is (change == "valid")
