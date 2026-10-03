#!/usr/bin/env python3
"""Bounded HTTPS and retained WSS flow inside an isolated QA browser Worker."""
import base64
import hashlib
import http.client
import json
import os
import select
import socket
import ssl
import struct
import sys
import uuid


def exact(conn, size):
    data = b""
    while len(data) < size:
        part = conn.recv(size - len(data))
        if not part:
            raise OSError("CLOSED")
        data += part
    return data


def connect(config, host):
    conn = socket.create_connection((config["relay"], 1080), timeout=10)
    conn.sendall(b"\x05\x01\x00")
    assert exact(conn, 2) == b"\x05\x00"
    domain = host.encode("ascii")
    assert len(domain) < 256
    conn.sendall(b"\x05\x01\x00\x03" + bytes([len(domain)]) + domain + struct.pack("!H", 18443))
    assert exact(conn, 4) == b"\x05\x00\x00\x01"
    exact(conn, 6)
    return ssl.create_default_context(cadata=config["ca"]).wrap_socket(conn, server_hostname=host)


def whoami(config):
    nonce = uuid.uuid4().hex
    with connect(config, config["observer"]) as conn:
        request = (f"GET /whoami?nonce={nonce}&phase=preflight HTTP/1.1\r\n"
                   f"Host: {config['observer']}:18443\r\nConnection: close\r\n\r\n")
        conn.sendall(request.encode())
        response = http.client.HTTPResponse(conn)
        response.begin()
        assert response.status == 200
        value = json.loads(response.read(8192))
        assert value["nonce"] == nonce
        return value


def websocket(config):
    nonce, key = uuid.uuid4().hex, base64.b64encode(os.urandom(16)).decode()
    conn = connect(config, config["website"])
    conn.sendall((f"GET /ws?nonce={nonce} HTTP/1.1\r\nHost: {config['website']}:18443\r\n"
                  f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                  "Sec-WebSocket-Version: 13\r\n\r\n").encode())
    header = b""
    while not header.endswith(b"\r\n\r\n"):
        assert len(header) < 8192
        header += exact(conn, 1)
    assert header.startswith(b"HTTP/1.1 101 ")
    accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
    assert b"Sec-WebSocket-Accept: " + accept in header
    return conn, nonce


def input_line():
    # Do not prefetch commands: select() observes the descriptor, not TextIO buffers.
    value = bytearray()
    while True:
        part = os.read(0, 1)
        if not part or part == b"\n":
            return value.decode()
        value.extend(part)
        assert len(value) <= 65536


def main():
    config = json.loads(input_line())
    conn, nonce = websocket(config)
    try:
        while True:
            ready = select.select([sys.stdin], [], [], 3)[0]
            line = input_line() if ready else "echo"
            if ready and not line:
                break
            command = line.strip()
            if command == "close":
                break
            if command == "whoami":
                result = whoami(config)
            else:
                assert command == "echo"
                mask = os.urandom(4)
                conn.sendall(b"\x81\xa0" + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(nonce.encode())))
                first, size = exact(conn, 2)
                assert first == 0x81 and size < 126
                result = json.loads(exact(conn, size))
                assert result["nonce"] == nonce
            if ready:
                print(json.dumps(result), flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
