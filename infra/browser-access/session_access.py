"""Read this Worker's display materials without exporting secrets to processes."""

import base64
import json
import logging
import os
from pathlib import Path
import re
import stat
import sys
import uuid

SOURCE = Path("/run/browser-platform-session-input")
OUTPUT = Path("/run/browser-platform-display")
FORBIDDEN = {"PASSWORD", "CUSTOM_USER", "SELKIES_MASTER_TOKEN"}


def fail():
    raise RuntimeError("SESSION_AUTH_INPUT_INVALID")


def mount(path, *, readonly=False):
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        if fields[4] != str(path):
            continue
        separator = fields.index("-")
        if fields[separator + 1] != "tmpfs" or (readonly and "ro" not in fields[5].split(",")):
            fail()
        return
    fail()


def read(name, uid):
    descriptor = os.open(SOURCE / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != uid
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 1024):
            fail()
        value = handle.read(1025)
        if len(value) > 1024:
            fail()
        return value


def inputs():
    if any(name in os.environ for name in FORBIDDEN) or any(name.startswith("FILE__") for name in os.environ):
        fail()
    uid = int(os.environ["PUID"])
    folder = os.environ["SUBFOLDER"]
    sid = folder.strip("/")
    if uid <= 0 or folder != f"/{sid}/" or str(uuid.UUID(sid)) != sid:
        fail()
    info = SOURCE.lstat()
    if (not stat.S_ISDIR(info.st_mode) or SOURCE.resolve() != SOURCE or info.st_uid != uid
            or stat.S_IMODE(info.st_mode) != 0o700):
        fail()
    mount(SOURCE, readonly=True)
    if set(p.name for p in SOURCE.iterdir()) != {"binding.json", "basic.htpasswd", "master-token"}:
        fail()
    if json.loads(read("binding.json", uid)) != {"version": 1, "session_id": sid, "uid": uid}:
        fail()
    basic = read("basic.htpasswd", uid)
    match = re.fullmatch(rb"([a-f0-9-]{36}):\{SSHA\}([A-Za-z0-9+/=]+)\n", basic)
    if not match or str(uuid.UUID(match[1].decode())).encode() != match[1]:
        fail()
    if len(base64.b64decode(match[2], validate=True)) != 36:
        fail()
    master = read("master-token", uid)
    if master and not re.fullmatch(rb"[A-Za-z0-9_-]{32,128}", master):
        fail()
    return basic, master.decode()


def master_token():
    try:
        return inputs()[1]
    except Exception:
        raise RuntimeError("SESSION_AUTH_INPUT_INVALID") from None


def prepare():
    basic, _ = inputs()
    mount(OUTPUT)
    info = OUTPUT.lstat()
    if OUTPUT.resolve() != OUTPUT or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o755:
        fail()
    descriptor = os.open(OUTPUT / "basic.htpasswd", os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != 0:
            fail()
        handle.write(basic)
        os.fchmod(handle.fileno(), 0o644)


def install_safe_logging():
    if getattr(logging, "_browser_platform_safe", False):
        return
    original = logging.getLogRecordFactory()

    def record(*args, **kwargs):
        value = original(*args, **kwargs)
        value.msg, value.args = "WORKER_EVENT", ()
        value.name = "worker"
        value.exc_info = value.exc_text = value.stack_info = None
        return value

    logging.setLogRecordFactory(record)
    logging._browser_platform_safe = True
    sys.excepthook = lambda *_: sys.stderr.write("WORKER_UNCAUGHT_ERROR\n")


if __name__ == "__main__":
    try:
        prepare()
    except Exception:
        raise SystemExit("SESSION_AUTH_INPUT_INVALID") from None
