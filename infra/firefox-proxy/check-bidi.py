#!/usr/bin/env python3
"""Verify a Firefox WebDriver BiDi page load without printing page contents."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
from typing import Any


class WebSocket:
    def __init__(self, host: str, port: int, path: str = "/session") -> None:
        self.socket = socket.create_connection((host, port), timeout=15)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.socket.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.socket.recv(4096)
        if not response.startswith(b"HTTP/1.1 101"):
            status = response.split(b"\r\n", 1)[0].decode(errors="replace")
            raise RuntimeError(f"WebSocket upgrade failed: {status}")

    def send_json(self, value: dict[str, Any]) -> None:
        data = json.dumps(value, separators=(",", ":")).encode()
        mask = os.urandom(4)
        if len(data) < 126:
            header = bytes((0x81, 0x80 | len(data)))
        elif len(data) < 65536:
            header = bytes((0x81, 0x80 | 126)) + struct.pack("!H", len(data))
        else:
            header = bytes((0x81, 0x80 | 127)) + struct.pack("!Q", len(data))
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.socket.sendall(header + mask + masked)

    def receive_json(self) -> dict[str, Any]:
        while True:
            first, second = self._read_exact(2)
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if second & 0x80 else None
            payload = self._read_exact(length)
            if mask:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 8:
                raise RuntimeError("WebSocket closed")
            if opcode == 1:
                return json.loads(payload)

    def _read_exact(self, length: int) -> bytes:
        result = b""
        while len(result) < length:
            chunk = self.socket.recv(length - len(result))
            if not chunk:
                raise EOFError("WebSocket closed")
            result += chunk
        return result


class BiDi:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.next_id = 0

    def command(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        command_id = self.next_id
        self.websocket.send_json({"id": command_id, "method": method, "params": params})
        while True:
            message = self.websocket.receive_json()
            if message.get("id") != command_id:
                continue
            if message.get("type") == "error":
                raise RuntimeError(f"{method} failed: {message.get('error')}")
            return message["result"]

    def evaluate(self, context: str, expression: str) -> Any:
        result = self.command(
            "script.evaluate",
            {
                "expression": expression,
                "target": {"context": context},
                "awaitPromise": True,
            },
        )
        return result["result"].get("value")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9228)
    args = parser.parse_args()

    bidi = BiDi(WebSocket(args.host, args.port))
    bidi.command("session.new", {"capabilities": {}})
    contexts = bidi.command("browsingContext.getTree", {})["contexts"]
    context = contexts[0]["context"]
    bidi.command(
        "browsingContext.navigate",
        {"context": context, "url": args.url, "wait": "complete"},
    )
    host = bidi.evaluate(context, "location.hostname")
    state = bidi.evaluate(context, "document.readyState")
    body = bidi.evaluate(context, "document.body.innerText.trim()")
    locale = bidi.evaluate(context, "navigator.language")
    languages = bidi.evaluate(context, "navigator.languages.join(',')")
    timezone = bidi.evaluate(context, "Intl.DateTimeFormat().resolvedOptions().timeZone")
    screen = bidi.evaluate(context, "screen.width + 'x' + screen.height")
    dpr = bidi.evaluate(context, "devicePixelRatio")
    webrtc = bidi.evaluate(context, "typeof RTCPeerConnection")
    print("firefox_proxy_bidi=ok")
    print(f"host={host}")
    print(f"ready_state={state}")
    print(f"body_bytes={len(body.encode())}")
    print(f"body_sha256={hashlib.sha256(body.encode()).hexdigest()}")
    print(f"locale={locale}")
    print(f"languages={languages}")
    print(f"timezone={timezone}")
    print(f"screen={screen}")
    print(f"device_pixel_ratio={dpr}")
    print(f"webrtc_type={webrtc}")
    bidi.command("session.end", {})


if __name__ == "__main__":
    main()
