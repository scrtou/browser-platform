"""The installer must reject unusable DNS dependencies before mutating app files."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.parametrize("package_name,module", [("dnspython", "dns"), ("Babel", "babel")])
@pytest.mark.parametrize("dependency", ["missing", "wrong-version", "valid"])
def test_dependency_preflight_is_atomic(tmp_path, dependency, package_name, module):
    package = Path(__file__).resolve().parent
    payload = tmp_path / "payload"
    destination = tmp_path / "installed" / "app"
    destination.mkdir(parents=True)
    (destination / "__init__.py").write_text("")
    (payload / "app").mkdir(parents=True)
    (destination / "example.py").write_text("before\n")
    (payload / "app/example.py").write_text("after\n")
    sha = lambda value: hashlib.sha256(value.encode()).hexdigest()
    lock = json.loads((package / "python-dependencies.json").read_text())
    (payload / "manifest.json").write_text(json.dumps({"release": "qa", "python_dependencies": lock["runtime"],
        "files": {"example.py": {"before": sha("before\n"), "after": sha("after\n")}}}))
    shutil.copyfile(package / "install.py", payload / "install.py")
    if dependency != "valid":
        fake = destination.parent / module
        fake.mkdir()
        (fake / "__init__.py").write_text("raise ImportError('unavailable')\n" if dependency == "missing"
                                          else "__version__ = '0.0.0'\n")
    env = {**os.environ, "PYTHONPATH": str(destination.parent) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    result = subprocess.run([sys.executable, str(payload / "install.py"), "--app-dir", str(destination)],
                            env=env, capture_output=True, text=True)
    if dependency == "valid":
        assert result.returncode == 0, result.stderr
        assert (destination / "example.py").read_text() == "after\n"
    else:
        assert result.returncode != 0 and "Runtime dependency missing or mismatched: " + package_name in result.stderr
        assert (destination / "example.py").read_text() == "before\n"
