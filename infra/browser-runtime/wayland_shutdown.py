"""Normal window close for the pinned labwc/Firefox Wayland Worker.

Uses zwlr_foreign_toplevel_manager_v1 version 3 (including parent events).
The protocol has no per-window PID. Only a single verified Firefox main
process, the expected user-owned labwc socket, and root firefox app IDs are
accepted. No keyboard input, process signal, or browser debugging API is used.
"""

import array
import os
from pathlib import Path
import re
import socket
import stat
import struct
import time


MANAGER = "zwlr_foreign_toplevel_manager_v1"
FIREFOX = {"/usr/lib/firefox/firefox", "/usr/lib/firefox/firefox-bin"}
HEADER = struct.Struct("=II")
UINT = struct.Struct("=I")


def integers(*values):
    return struct.pack("=" + "I" * len(values), *values)


def wire_string(value):
    raw = value.encode() + b"\0"
    return integers(len(raw)) + raw + b"\0" * (-len(raw) % 4)


def read_string(raw, offset=0):
    if offset + 4 > len(raw):
        raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
    size = UINT.unpack_from(raw, offset)[0]
    start, end = offset + 4, offset + 4 + size
    padded = start + (size + 3) // 4 * 4
    if not 1 <= size <= 16384 or padded > len(raw) or raw[end - 1] != 0:
        raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
    try:
        value = raw[start:end - 1].decode("utf-8")
    except UnicodeError:
        raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID") from None
    if "\0" in value:
        raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
    return value, padded


class Protocol:
    """Bounded state for the few Wayland objects used by this client."""

    def __init__(self):
        self.objects = {1: "display"}
        self.next_id = 2
        self.globals = {}
        self.handles = {}
        self.callbacks = set()
        self.manager_global = None
        self.finished = False

    def allocate(self, kind):
        if len(self.objects) >= 4096 or self.next_id >= 0xFF000000:
            raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_LIMIT")
        identifier = self.next_id
        self.next_id += 1
        self.objects[identifier] = kind
        return identifier

    def event(self, identifier, opcode, payload):
        def number():
            if len(payload) != 4:
                raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
            return UINT.unpack(payload)[0]

        kind = self.objects.get(identifier)
        if kind == "display":
            if opcode != 1:  # Any wl_display.error fails without echoing text.
                raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_ERROR")
            removed = number()
            if self.objects.get(removed) != "callback" or removed not in self.callbacks:
                raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
            self.objects.pop(removed)
        elif kind == "registry":
            if opcode == 0:
                if len(payload) < 12:
                    raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
                name = UINT.unpack_from(payload)[0]
                interface, end = read_string(payload, 4)
                if end + 4 != len(payload) or name in self.globals or len(self.globals) >= 4096:
                    raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
                self.globals[name] = (interface, UINT.unpack_from(payload, end)[0])
            elif opcode == 1:
                removed = number()
                self.globals.pop(removed, None)
                if removed == self.manager_global:
                    self.finished = True
            else:
                raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
        elif kind == "callback" and opcode == 0:
            number()  # Serial is unused; its wire shape still must be valid.
            self.callbacks.add(identifier)
        elif kind == "manager":
            if opcode == 0:
                handle = number()
                if handle < 0xFF000000 or handle in self.objects or len(self.objects) >= 4096:
                    raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
                self.objects[handle] = "handle"
                self.handles[handle] = {"parent": 0, "app_id": None, "ready": False, "closed": False}
            elif opcode == 1 and not payload:
                self.finished = True
            else:
                raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
        elif kind == "handle":
            handle = self.handles[identifier]
            if handle["closed"]:
                raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
            if opcode in (0, 1):  # Titles are decoded for framing, never retained.
                value, end = read_string(payload)
                if end != len(payload):
                    raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
                if opcode == 1:
                    handle["app_id"] = value
                handle["ready"] = False
            elif opcode in (2, 3):  # Output objects are not needed for closing.
                number()
                handle["ready"] = False
            elif opcode == 4:
                if len(payload) < 4 or UINT.unpack_from(payload)[0] != len(payload) - 4 or len(payload) % 4:
                    raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
                handle["ready"] = False
            elif opcode == 5 and not payload:
                handle["ready"] = True
            elif opcode == 6 and not payload:
                handle["closed"] = True
                handle["ready"] = False
            elif opcode == 7:
                handle["parent"] = number()
                handle["ready"] = False
            else:
                raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
        else:
            raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")

    def firefox_roots(self):
        return [identifier for identifier, value in self.handles.items()
                if value["ready"] and not value["closed"] and value["parent"] == 0
                and value["app_id"] == "firefox"]


class Client:
    def __init__(self, connection, deadline):
        self.connection, self.deadline = connection, deadline
        self.protocol, self.buffer = Protocol(), b""
        registry = self.protocol.allocate("registry")
        self.send(1, 1, integers(registry))
        self.roundtrip()
        managers = [(name, version) for name, (interface, version) in self.protocol.globals.items()
                    if interface == MANAGER]
        if len(managers) != 1 or managers[0][1] < 3:
            raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_UNSUPPORTED")
        self.protocol.manager_global = managers[0][0]
        manager = self.protocol.allocate("manager")
        self.send(registry, 0, integers(managers[0][0]) + wire_string(MANAGER) + integers(3, manager))
        self.roundtrip()

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("BROWSER_SHUTDOWN_TIMEOUT")
        return remaining

    def send(self, identifier, opcode, payload=b""):
        self.connection.settimeout(self.remaining())
        self.connection.sendall(HEADER.pack(identifier, (8 + len(payload)) << 16 | opcode) + payload)

    def receive(self):
        while True:
            if len(self.buffer) >= 8:
                identifier, word = HEADER.unpack_from(self.buffer)
                size, opcode = word >> 16, word & 0xFFFF
                if size < 8 or size % 4:
                    raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_INVALID")
                if len(self.buffer) >= size:
                    payload, self.buffer = self.buffer[8:size], self.buffer[size:]
                    self.protocol.event(identifier, opcode, payload)
                    return
            self.connection.settimeout(self.remaining())
            data, ancillary, flags, _ = self.connection.recvmsg(65536, socket.CMSG_SPACE(256))
            # This protocol subset never transfers descriptors. Close unexpected
            # SCM_RIGHTS descriptors before rejecting the message.
            for level, kind, value in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    descriptors = array.array("i")
                    descriptors.frombytes(value[:len(value) // descriptors.itemsize * descriptors.itemsize])
                    for descriptor in descriptors:
                        os.close(descriptor)
            if not data or ancillary or flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC):
                raise RuntimeError("BROWSER_WAYLAND_CONNECTION_INVALID")
            self.buffer += data
            if len(self.buffer) > 131072:
                raise RuntimeError("BROWSER_WAYLAND_PROTOCOL_LIMIT")

    def roundtrip(self):
        callback = self.protocol.allocate("callback")
        self.send(1, 0, integers(callback))
        while callback not in self.protocol.callbacks:
            self.receive()
        if self.protocol.finished:
            raise RuntimeError("BROWSER_WAYLAND_DISPLAY_UNAVAILABLE")


def process_identity(pid, executables):
    path = Path("/proc", str(pid))
    if path.stat().st_uid != os.getuid() or os.readlink(path / "exe") not in executables:
        raise RuntimeError("BROWSER_WAYLAND_IDENTITY_UNCONFIRMED")
    fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
    if fields[0] in {"Z", "X"}:
        raise RuntimeError("BROWSER_WAYLAND_IDENTITY_UNCONFIRMED")
    return fields[19]


class WaylandDisplay:
    def __init__(self, active, probe, deadline):
        if len(active) != 1:
            raise RuntimeError("BROWSER_WAYLAND_IDENTITY_UNCONFIRMED")
        self.active, self.probe, self.connection = dict(active), probe, None
        self.pid, self.started = next(iter(active.items()))
        if process_identity(self.pid, FIREFOX) != self.started:
            raise RuntimeError("BROWSER_WAYLAND_IDENTITY_UNCONFIRMED")
        env = dict(value.split(b"=", 1) for value in Path("/proc", str(self.pid), "environ").read_bytes().split(b"\0") if b"=" in value)
        directory = env.get(b"XDG_RUNTIME_DIR", b"")
        display = env.get(b"WAYLAND_DISPLAY", b"")
        if directory != b"/config/.XDG" or not re.fullmatch(rb"wayland-[0-9]{1,5}", display):
            raise RuntimeError("BROWSER_WAYLAND_SOCKET_INVALID")
        path = Path(directory.decode(), display.decode())
        parent, endpoint = path.parent.lstat(), path.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o022
                or not stat.S_ISSOCK(endpoint.st_mode) or endpoint.st_uid != os.getuid()):
            raise RuntimeError("BROWSER_WAYLAND_SOCKET_INVALID")
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.settimeout(max(0.001, deadline - time.monotonic()))
            connection.connect(str(path))
            pid, uid, _ = struct.unpack("=iii", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise RuntimeError("BROWSER_WAYLAND_IDENTITY_UNCONFIRMED")
            self.compositor = pid, process_identity(pid, {"/usr/bin/labwc"})
            self.client = Client(connection, deadline)
            if not self.confirm():
                raise RuntimeError("BROWSER_WAYLAND_IDENTITY_UNCONFIRMED")
            self.connection = connection
        except BaseException:
            connection.close()
            raise

    def confirm(self):
        current, _ = self.probe()
        if not current:
            return False
        if current != self.active or process_identity(self.pid, FIREFOX) != self.started:
            raise RuntimeError("BROWSER_WAYLAND_IDENTITY_UNCONFIRMED")
        pid, started = self.compositor
        if process_identity(pid, {"/usr/bin/labwc"}) != started:
            raise RuntimeError("BROWSER_WAYLAND_IDENTITY_UNCONFIRMED")
        return True

    def close_windows(self, active, sent):
        if active != self.active:
            raise RuntimeError("BROWSER_WAYLAND_IDENTITY_UNCONFIRMED")
        self.client.roundtrip()
        for handle in self.client.protocol.firefox_roots():
            identity = self.pid, self.started, handle
            if identity in sent:
                continue
            if not self.confirm():
                return
            self.client.send(handle, 5)  # zwlr_foreign_toplevel_handle_v1.close
            sent.add(identity)

    def close(self):
        self.connection.close()
