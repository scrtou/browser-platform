"""Install the shutdown hook only over the reviewed LinuxServer desktop hook."""

import hashlib
from pathlib import Path

ROOT = Path("/usr/local/lib/browser-platform")
SERVICES = Path("/etc/s6-overlay/s6-rc.d")
EXPECTED = "ea9989721b19bd056db03d0cc741fc6634e7ec56a6a684bec89a9e52e5731b42"

if hashlib.sha256((SERVICES / "svc-de/finish").read_bytes()).hexdigest() != EXPECTED:
    raise SystemExit("unreviewed desktop shutdown hook; refusing to replace it")
service = SERVICES / "browser-platform-shutdown"
service.mkdir()
(service / "type").write_text("oneshot\n")
(service / "up").write_text("/bin/true\n")
(service / "down").write_text(str(ROOT / "before-desktop-stop") + "\n")
(service / "timeout-down").write_text("15000\n")
(service / "dependencies.d").mkdir()
for name in ("svc-de", "svc-dbus"):
    if not (SERVICES / name / "type").is_file():
        raise SystemExit("required desktop service is missing")
    (service / "dependencies.d" / name).touch()
(SERVICES / "user/contents.d/browser-platform-shutdown").touch()
(ROOT / "before-desktop-stop").chmod(0o755)
