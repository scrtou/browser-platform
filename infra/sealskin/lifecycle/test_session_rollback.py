"""A code rollback must not discard the only reader for encrypted Session state."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.parametrize("state_kind", ["sealed", "key_without_database", "damaged", "legacy"])
def test_rollback_requires_matching_state_before_mutating_code(tmp_path, state_kind):
    payload, installed = tmp_path / "payload", tmp_path / "installed/app"
    installed.mkdir(parents=True)
    (payload / "original").mkdir(parents=True)
    (installed / "__init__.py").write_text("")
    database = tmp_path / "sessions.yml"
    (installed / "settings.py").write_text("from types import SimpleNamespace\nsettings=SimpleNamespace(sessions_db_path=" + repr(str(database)) + ")\n")
    before, after = b"# original\n", b"# patched\n"
    codec = b"# authenticated state reader\n"
    (installed / "config_store.py").write_bytes(after)
    (installed / "session_secrets.py").write_bytes(codec)
    (payload / "original/config_store.py").write_bytes(before)
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    manifest = {"release": "test", "files": {
        "config_store.py": {"before": digest(before), "after": digest(after)},
        "session_secrets.py": {"before": None, "after": digest(codec)},
    }}
    (payload / "manifest.json").write_text(json.dumps(manifest))
    shutil.copyfile(Path(__file__).with_name("install.py"), payload / "install.py")
    if state_kind == "sealed":
        database.write_text("session_state_version: 1\n")
    elif state_kind == "key_without_database":
        (tmp_path / "session-secrets").mkdir()
    elif state_kind == "damaged":
        database.write_text("sessions: [")
    else:
        database.write_text("{}\n")
    env = dict(os.environ, PYTHONPATH=str(installed.parent))
    result = subprocess.run([sys.executable, str(payload / "install.py"), "--rollback", "--app-dir", str(installed)],
                            env=env, capture_output=True, text=True)
    if state_kind == "legacy":
        assert result.returncode == 0, result.stderr
        assert (installed / "config_store.py").read_bytes() == before
        assert not (installed / "session_secrets.py").exists()
    else:
        assert result.returncode != 0 and "rollback" in result.stderr
        assert (installed / "config_store.py").read_bytes() == after
        assert (installed / "session_secrets.py").read_bytes() == codec
