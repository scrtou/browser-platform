"""The QA Docker gateway must not broaden host access for secret injection."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

import pytest

spec = importlib.util.spec_from_file_location("qa_network_proxy", Path(__file__).with_name("qa-network-docker-proxy.py"))
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


@pytest.mark.parametrize("change", ["valid", "worker", "guard", "rw", "destination", "generation", "profile", "home", "symlink", "permissions", "master_key"])
def test_exact_generation_only(tmp_path, change):
    runtime = Path(tempfile.mkdtemp(prefix="browser-platform-qa-mount-test-", dir="/dev/shm"))
    try:
        identity = dict(scope="a"*64, owner="network-qa", home="qa-home", app="qa-app", profile="qa-profile", operation="b"*32)
        identity["home_source"] = str(tmp_path / "storage/network-qa/qa-home")
        identity["home_hash"] = hashlib.sha256(identity["home_source"].encode()).hexdigest()
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        source = runtime / ("generation-" + digest)
        source.mkdir(mode=0o700)
        labels = {proxy.PREFIX+k:v for k,v in identity.items() if k != "home_source"}
        labels[proxy.PREFIX+"role"] = "relay"
        destination, readonly = "/run/secrets", True
        if change in {"worker", "guard"}:
            labels[proxy.PREFIX+"role"] = change
        if change == "rw": readonly = False
        if change == "destination": destination = "/config"
        if change in {"generation", "profile", "home"}:
            labels[proxy.PREFIX+{"generation":"operation"}.get(change, change)] += "c"
        if change == "symlink":
            other = runtime / "other"
            source.rename(other)
            source.symlink_to(other, target_is_directory=True)
        if change == "permissions": source.chmod(0o755)
        if change == "master_key": source = tmp_path / "master.key"
        result = proxy.credential_bind_allowed(tmp_path, {"credential_runtime_root": str(runtime)}, labels, source, destination, readonly)
        assert result is (change == "valid")
    finally:
        shutil.rmtree(runtime)
