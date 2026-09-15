"""The QA proxy may mount only the matching Worker's private Session input."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import uuid


def test_private_display_mount_cannot_be_writable_shared_or_relabelled():
    spec = importlib.util.spec_from_file_location("qa_display_proxy", Path(__file__).with_name("qa-network-docker-proxy.py"))
    proxy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proxy)
    with tempfile.TemporaryDirectory(prefix="bp-display-qa-", dir="/dev/shm") as temporary:
        root = Path(temporary)
        sid = str(uuid.uuid4())
        path = root / ("session-" + sid)
        path.mkdir(mode=0o700)
        marker = path / "binding.json"
        marker.write_text(json.dumps({"version": 1, "session_id": sid, "uid": os.geteuid()}))
        marker.chmod(0o600)
        allowed = {"display_runtime_root": str(root)}
        labels = {proxy.PREFIX + "session": sid, proxy.PREFIX + "session-auth": "1"}
        def check(**kwargs):
            value = dict(allowed=allowed, labels=labels, source=str(path), destination=proxy.DISPLAY_TARGET, readonly=True)
            value.update(kwargs)
            return proxy.display_bind_allowed(**value)
        assert check()
        assert not check(readonly=False)
        assert not check(source=str(root))
        assert not check(labels={**labels, proxy.PREFIX + "session": str(uuid.uuid4())})
        assert not check(labels={**labels, proxy.PREFIX + "role": "relay"})
        assert not check(destination="/run")
        marker.chmod(0o644)
        assert not check()
        marker.chmod(0o600)
        marker.unlink()
        marker.symlink_to(root / "outside")
        assert not check()
