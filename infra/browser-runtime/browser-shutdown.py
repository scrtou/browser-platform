#!/usr/bin/env python3
"""Request normal X11 browser closure; never signal or kill browser processes.

Run as the desktop user. A timeout (including a beforeunload dialog) is a
failure: an API caller must keep the container and its Home reservation.
"""

import argparse
import ctypes as C
import fcntl
import os
from pathlib import Path
import sys
import time


EXECUTABLES = {
    "/opt/camoufox/browser/camoufox",
    "/usr/lib/firefox/firefox", "/usr/lib/firefox/firefox-bin",
}
LAUNCHER = b"/usr/local/lib/browser-platform/environment.py"


def browsers():
    """Use executable identity and start time, never titles or a bare PID."""
    active, launching = {}, False
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            if path.stat().st_uid != os.getuid():
                continue
            args = (path / "cmdline").read_bytes().split(b"\0")
            if LAUNCHER in args and b"launch" in args:
                launching = True
            comm = (path / "comm").read_text().strip()
            if comm not in {"camoufox", "firefox", "firefox-bin"}:
                continue
            if "-contentproc" in [arg.decode(errors="replace") for arg in args]:
                continue
            if os.readlink(path / "exe") not in EXECUTABLES:
                raise RuntimeError("BROWSER_IDENTITY_UNCONFIRMED")
            stat = (path / "stat").read_text().rsplit(")", 1)[1].split()
            if stat[0] not in {"Z", "X"}:
                active[int(path.name)] = stat[19]  # /proc stat field 22
        except (FileNotFoundError, ProcessLookupError):
            continue
    return active, launching


class ClientData(C.Union):
    _fields_ = [("b", C.c_char * 20), ("s", C.c_short * 10), ("l", C.c_long * 5)]


class ClientMessage(C.Structure):
    _fields_ = [("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
                ("display", C.c_void_p), ("window", C.c_ulong), ("message_type", C.c_ulong),
                ("format", C.c_int), ("data", ClientData)]


class Event(C.Union):
    _fields_ = [("client", ClientMessage), ("padding", C.c_long * 24)]


class Display:
    def __init__(self):
        self.x = C.CDLL("libX11.so.6")
        signatures = {
            "XOpenDisplay": ([C.c_char_p], C.c_void_p),
            "XCloseDisplay": ([C.c_void_p], C.c_int),
            "XDefaultRootWindow": ([C.c_void_p], C.c_ulong),
            "XInternAtom": ([C.c_void_p, C.c_char_p, C.c_int], C.c_ulong),
            "XGetWindowProperty": ([C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long,
                C.c_int, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_int),
                C.POINTER(C.c_ulong), C.POINTER(C.c_ulong), C.POINTER(C.c_void_p)], C.c_int),
            "XFree": ([C.c_void_p], C.c_int),
            "XSendEvent": ([C.c_void_p, C.c_ulong, C.c_int, C.c_long, C.POINTER(Event)], C.c_int),
            "XSync": ([C.c_void_p, C.c_int], C.c_int),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.x, name)
            function.argtypes, function.restype = args, result
        # Windows can disappear between enumeration and XGetWindowProperty.
        # Process exit is checked separately; an X error never proves exit.
        self.error_handler = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)(lambda *_: 0)
        self.x.XSetErrorHandler(self.error_handler)
        self.display = self.x.XOpenDisplay(b":1")
        if not self.display:
            raise RuntimeError("BROWSER_DISPLAY_UNAVAILABLE")
        self.root = self.x.XDefaultRootWindow(self.display)
        self.atoms = {}

    def atom(self, name):
        if name not in self.atoms:
            self.atoms[name] = self.x.XInternAtom(self.display, name.encode(), 0)
        return self.atoms[name]

    def values(self, window, name, expected_type):
        actual, fmt, count, after, data = C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong(), C.c_void_p()
        result = self.x.XGetWindowProperty(self.display, window, self.atom(name), 0, 4096,
            0, expected_type, C.byref(actual), C.byref(fmt), C.byref(count), C.byref(after), C.byref(data))
        try:
            if result or actual.value != expected_type or fmt.value != 32 or after.value:
                return []
            return list(C.cast(data, C.POINTER(C.c_ulong))[:count.value]) if data else []
        finally:
            if data:
                self.x.XFree(data)

    def close_windows(self, active, sent):
        for window in self.values(self.root, "_NET_CLIENT_LIST", 33):  # XA_WINDOW
            pid = self.values(window, "_NET_WM_PID", 6)  # XA_CARDINAL
            if len(pid) != 1 or pid[0] not in active:
                continue
            identity = (pid[0], active[pid[0]], window)
            if identity in sent or self.values(window, "WM_TRANSIENT_FOR", 33):
                continue
            if self.atom("_NET_WM_WINDOW_TYPE_DIALOG") in self.values(window, "_NET_WM_WINDOW_TYPE", 4):
                continue
            if self.atom("WM_DELETE_WINDOW") not in self.values(window, "WM_PROTOCOLS", 4):
                continue
            # Reconfirm the process after reading window properties.
            current, _ = browsers()
            if current.get(pid[0]) != active[pid[0]]:
                continue
            event = Event()
            event.client.type = 33  # ClientMessage
            event.client.send_event = 1
            event.client.display = self.display
            event.client.window = window
            event.client.message_type = self.atom("WM_PROTOCOLS")
            event.client.format = 32
            event.client.data.l[0] = self.atom("WM_DELETE_WINDOW")
            event.client.data.l[1] = 0  # CurrentTime
            if self.x.XSendEvent(self.display, window, 0, 0, C.byref(event)):
                sent.add(identity)
        self.x.XSync(self.display, 0)

    def close(self):
        self.x.XCloseDisplay(self.display)


def home_released():
    path = Path("/config/.camoufox/worker.lock")
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    except FileNotFoundError:
        return True
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(descriptor)


def shutdown(timeout):
    deadline, sent, display = time.monotonic() + timeout, set(), None
    try:
        while time.monotonic() < deadline:
            active, launching = browsers()
            if not active and not launching and home_released():
                return
            if active:
                display = display or Display()
                display.close_windows(active, sent)
            time.sleep(.05)
        raise RuntimeError("BROWSER_SHUTDOWN_TIMEOUT")
    finally:
        if display:
            display.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=12)
    args = parser.parse_args()
    if not 0 < args.timeout <= 15:
        parser.error("timeout must be in (0, 15] seconds")
    try:
        if os.getuid() == 0:
            raise RuntimeError("BROWSER_SHUTDOWN_USER_INVALID")
        shutdown(args.timeout)
        print("BROWSER_SHUTDOWN_CONFIRMED")
    except (OSError, RuntimeError) as error:
        message = str(error) if isinstance(error, RuntimeError) else "BROWSER_SHUTDOWN_UNAVAILABLE"
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
