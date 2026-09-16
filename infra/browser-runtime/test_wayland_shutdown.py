import array
import importlib.util
import os
from pathlib import Path
import socket
import time
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location("wayland_shutdown", Path(__file__).with_name("wayland_shutdown.py"))
wayland = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wayland)


class WaylandShutdownTests(unittest.TestCase):
    def setUp(self):
        self.protocol = wayland.Protocol()
        self.manager = self.protocol.allocate("manager")

    def window(self, offset, app_id="firefox", parent=0, ready=True):
        handle = 0xFF000000 + offset
        self.protocol.event(self.manager, 0, wayland.integers(handle))
        self.protocol.event(handle, 1, wayland.wire_string(app_id))
        self.protocol.event(handle, 7, wayland.integers(parent))
        if ready:
            self.protocol.event(handle, 5, b"")
        return handle

    def test_only_ready_firefox_root_windows_are_closed(self):
        root = self.window(0)
        self.window(1, parent=root)
        self.window(2, app_id="terminal")
        self.window(3, ready=False)
        self.assertEqual(self.protocol.firefox_roots(), [root])

    def test_pending_parent_or_app_id_changes_are_not_used(self):
        root = self.window(0)
        self.protocol.event(root, 1, wayland.wire_string("terminal"))
        self.assertEqual(self.protocol.firefox_roots(), [])
        self.protocol.event(root, 5, b"")
        self.assertEqual(self.protocol.firefox_roots(), [])
        self.protocol.event(root, 1, wayland.wire_string("firefox"))
        self.protocol.event(root, 7, wayland.integers(0xFF000001))
        self.protocol.event(root, 5, b"")
        self.assertEqual(self.protocol.firefox_roots(), [])

    def test_closed_windows_and_reused_handles_are_rejected(self):
        root = self.window(0)
        self.protocol.event(root, 6, b"")
        self.assertEqual(self.protocol.firefox_roots(), [])
        with self.assertRaises(RuntimeError):
            self.protocol.event(root, 5, b"")
        with self.assertRaises(RuntimeError):
            self.window(0)

    def test_titles_are_not_retained(self):
        root = self.window(0)
        self.protocol.event(root, 0, wayland.wire_string("private page title"))
        self.protocol.event(root, 5, b"")
        self.assertNotIn("private page title", repr(self.protocol.__dict__))

    def test_malformed_strings_and_events_fail_closed(self):
        for value in [b"", wayland.integers(0), wayland.integers(8) + b"x\0\0\0",
                      wayland.integers(4) + b"abcd", wayland.integers(4) + b"a\0b\0",
                      wayland.integers(2) + b"\xff\0\0\0"]:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                wayland.read_string(value)
        root = self.window(0)
        for identifier, opcode, payload in [(100, 0, b""), (root, 7, b""),
                (root, 5, b"x"), (root, 4, wayland.integers(8, 1)),
                (self.manager, 0, wayland.integers(3))]:
            with self.subTest(opcode=opcode), self.assertRaises(RuntimeError):
                self.protocol.event(identifier, opcode, payload)

    def test_manager_removal_prevents_further_window_use(self):
        registry = self.protocol.allocate("registry")
        self.protocol.manager_global = 10
        self.protocol.event(registry, 0, wayland.integers(10) + wayland.wire_string(wayland.MANAGER) + wayland.integers(3))
        self.protocol.event(registry, 1, wayland.integers(10))
        self.assertTrue(self.protocol.finished)

    def test_protocol_without_parent_events_is_refused(self):
        def discovery(client):
            client.protocol.globals[10] = (wayland.MANAGER, 2)
        with patch.object(wayland.Client, "roundtrip", discovery), patch.object(wayland.Client, "send"):
            with self.assertRaisesRegex(RuntimeError, "PROTOCOL_UNSUPPORTED"):
                wayland.Client(Mock(), time.monotonic() + 1)

    def test_close_is_sent_once_and_identity_change_is_refused(self):
        root = self.window(0)
        display = wayland.WaylandDisplay.__new__(wayland.WaylandDisplay)
        display.pid, display.started = 101, "400"
        display.active = {101: "400"}
        display.probe = lambda: ({101: "400"}, False)
        display.compositor = 202, "500"
        display.client = Mock(protocol=self.protocol)
        sent = set()
        with patch.object(wayland, "process_identity", side_effect=lambda pid, _: "400" if pid == 101 else "500"):
            display.close_windows(display.active, sent)
            display.close_windows(display.active, sent)
            display.client.send.assert_called_once_with(root, 5)
            display.probe = lambda: ({101: "999"}, False)
            sent.clear()
            with self.assertRaises(RuntimeError):
                display.close_windows(display.active, sent)
            display.client.send.assert_called_once_with(root, 5)

    def test_new_compositor_or_additional_browser_is_refused(self):
        display = wayland.WaylandDisplay.__new__(wayland.WaylandDisplay)
        display.pid, display.started, display.active = 101, "400", {101: "400"}
        display.probe = lambda: ({101: "400"}, False)
        display.compositor = 202, "500"
        with patch.object(wayland, "process_identity", side_effect=lambda pid, _: "400" if pid == 101 else "999"):
            with self.assertRaises(RuntimeError):
                display.confirm()
        display.probe = lambda: ({101: "400", 102: "450"}, False)
        with self.assertRaises(RuntimeError):
            display.confirm()

    def test_wire_rejects_invalid_frames_and_closes_unexpected_fds(self):
        def client(connection):
            value = wayland.Client.__new__(wayland.Client)
            value.connection, value.deadline = connection, time.monotonic() + 1
            value.protocol, value.buffer = self.protocol, b""
            return value
        left, right = socket.socketpair()
        try:
            left.sendall(wayland.HEADER.pack(1, 4 << 16))
            with self.assertRaisesRegex(RuntimeError, "PROTOCOL_INVALID"):
                client(right).receive()
        finally:
            left.close()
            right.close()
        left, right = socket.socketpair()
        descriptor = os.open("/dev/null", os.O_RDONLY)
        try:
            before = len(list(Path("/proc/self/fd").iterdir()))
            left.sendmsg([b"\0" * 8], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [descriptor]))])
            with self.assertRaisesRegex(RuntimeError, "CONNECTION_INVALID"):
                client(right).receive()
            self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), before)
        finally:
            os.close(descriptor)
            left.close()
            right.close()


if __name__ == "__main__":
    unittest.main()
