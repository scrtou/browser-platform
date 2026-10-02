"""The QA socket admits one fixed command on the current dynamic Relay only."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("dynamic_proxy", Path(__file__).with_name("qa-network-docker-proxy.py"))
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


@pytest.fixture
def harness(tmp_path):
    root = tmp_path / "qa"
    path = root / "config/.config/sealskin/profile-network-runtime" / ("b" * 64 + ".json")
    path.parent.mkdir(parents=True)
    identity = dict(scope="a" * 64, owner="network-qa", home="qa-home", home_hash="b" * 64,
                    app="qa-app", profile="qa-profile", operation="c" * 32)
    record = {"identity": {**identity, "home_source": str(root / "storage/network-qa/qa-home")},
              "allocation": {"relay_id": "d" * 64, "dynamic_upstream_version": 1}}
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    labels = {proxy.PREFIX + k: v for k, v in identity.items()}
    labels.update({proxy.PREFIX + "role": "relay", proxy.PREFIX + "network-version": "1"})
    value = {"Image": "approved-image", "Config": {"Labels": labels}, "Mounts": [{"Destination": proxy.DYNAMIC_TARGET,
        "Type": "bind", "Source": str(path.parent / ("b" * 64 + "-" + "c" * 32)), "RW": False}]}
    allow = root / "allow.json"
    allow.write_text(json.dumps({"dynamic_images": ["approved-image"]}))
    handler = object.__new__(proxy.Handler)
    handler.server = SimpleNamespace(root=root, scope="a" * 64, allow=allow)
    handler.inspect = lambda category, identifier: value if identifier == "d" * 64 else None
    return handler, value, path, record


@pytest.mark.parametrize("change", ["valid", "command", "user", "peer", "scope", "owner", "operation",
    "worker", "image", "mount", "writable", "missing", "symlink", "public_record", "stale", "source", "static"])
def test_fixed_exec_generation_boundary(harness, change):
    handler, value, path, record = harness
    instance, command, user = "d" * 64, list(proxy.DYNAMIC_COMMAND), "0:0"
    labels = value["Config"]["Labels"]
    if change == "command":
        command[-1] = "--inspect"
    elif change == "user":
        user = "0"
    elif change == "peer":
        instance = "e" * 64
    elif change in {"scope", "owner", "operation"}:
        labels[proxy.PREFIX + change] = "foreign"
    elif change == "worker":
        labels[proxy.PREFIX + "role"] = "worker"
    elif change == "image":
        value["Image"] = "unapproved"
    elif change == "mount":
        value["Mounts"][0]["Source"] += "-peer"
    elif change == "writable":
        value["Mounts"][0]["RW"] = True
    elif change == "missing":
        path.unlink()
    elif change == "symlink":
        target = path.with_suffix(".saved")
        path.rename(target)
        path.symlink_to(target)
    elif change == "public_record":
        path.chmod(0o644)
    elif change in {"stale", "source", "static"}:
        if change == "stale":
            record["allocation"]["relay_id"] = "e" * 64
        elif change == "source":
            record["identity"]["home_source"] += "-peer"
        else:
            record["allocation"]["dynamic_upstream_version"] = 0
        path.write_text(json.dumps(record))
    assert handler.dynamic_command(instance, command, user) == (change == "valid")


@pytest.mark.parametrize("change", ["valid", "privileged", "tty", "stdin", "stdout", "stderr", "command", "user"])
def test_exec_start_revalidates_command_and_io(harness, monkeypatch, change):
    handler, _, _, _ = harness
    process = {"entrypoint": proxy.DYNAMIC_COMMAND[0], "arguments": proxy.DYNAMIC_COMMAND[1:], "user": "0:0",
               "privileged": False, "tty": False}
    value = {"ContainerID": "d" * 64, "ProcessConfig": process, "OpenStdin": False, "OpenStdout": True, "OpenStderr": True}
    if change in {"privileged", "tty"}:
        process[change] = True
    elif change in {"stdin", "stdout", "stderr"}:
        value["Open" + change.capitalize()] = change == "stdin"
    elif change == "command":
        process["entrypoint"] = "sh"
    elif change == "user":
        process["user"] = "1000:1000"
    monkeypatch.setattr(proxy.base, "upstream", lambda *args: (200, [], json.dumps(value).encode()))
    assert handler.dynamic_exec("f" * 64) == (change == "valid")


@pytest.mark.parametrize("response,accepted", [
    (b"HTTP/1.1 101 UPGRADED\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n\r\n" +
     b"\x01\x00\x00\x00\x00\x00\x00\x03ok\n", True),
    (b"HTTP/1.1 200 OK\r\n\r\n", False),
    (b"HTTP/1.1 101 UPGRADED\r\n", False),
    (b"HTTP/1.1 101 UPGRADED\r\n\r\n" + b"x" * 8192, False),
])
def test_attached_output_preserved_and_bounded(harness, monkeypatch, response, accepted):
    handler, _, _, _ = harness
    remaining = io.BytesIO(response)
    sent = []
    closed = []
    sock = SimpleNamespace(sendall=sent.append, recv=remaining.read)
    connection = SimpleNamespace(connect=lambda: None, sock=sock, close=lambda: closed.append(True))
    monkeypatch.setattr(proxy.base, "UnixConnection", lambda *a, **k: connection)
    handler.wfile = io.BytesIO()
    handler.event = lambda *a: None
    if accepted:
        handler.start_dynamic_exec("f" * 64, b'{"Tty":false,"Detach":false}')
        assert handler.wfile.getvalue() == response
    else:
        with pytest.raises(ValueError):
            handler.start_dynamic_exec("f" * 64, b'{"Tty":false,"Detach":false}')
        assert not handler.wfile.getvalue().endswith(b"x" * 4096)
    assert closed == [True] and b"Connection: Upgrade\r\nUpgrade: tcp" in sent[0]


@pytest.mark.parametrize("change", ["valid", "peer", "stage", "addresses", "scope", "worker"])
def test_crash_gate_requires_exact_transaction_and_owned_relay(harness, monkeypatch, change):
    handler, value, _, _ = harness
    directory = Path(value["Mounts"][0]["Source"])
    directory.mkdir()
    (directory / "relay-network.json").write_text(json.dumps({"upstream_ipv4": ["192.0.2.10"]}))
    policy = {"mode": "dynamic-hold", "instance": "d" * 64, "stage": "create", "addresses": ["192.0.2.10"]}
    if change == "peer":
        policy["instance"] = "e" * 64
    elif change == "stage":
        policy["stage"] = "result"
    elif change == "addresses":
        policy["addresses"] = ["192.0.2.11"]
    elif change == "scope":
        value["Config"]["Labels"][proxy.PREFIX + "scope"] = "foreign"
    elif change == "worker":
        value["Config"]["Labels"][proxy.PREFIX + "role"] = "worker"
    handler.server.policy = handler.server.root / "policy.json"
    handler.server.policy.write_text(json.dumps(policy))
    handler.event = lambda *args: None
    clock = iter([0, 31])
    monkeypatch.setattr(proxy.time, "monotonic", lambda: next(clock))
    assert handler.hold_dynamic("d" * 64, "create") == (change == "valid")
    assert (handler.server.root / "dynamic-held.json").exists() == (change == "valid")
