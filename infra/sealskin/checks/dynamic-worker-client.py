#!/usr/bin/env python3
"""Long-lived HTTPS connection through the actual QA Worker's local Relay."""
import http.client
import json
import socket
import ssl
import sys


def exact(conn, length):
    result = b""
    while len(result) < length:
        part = conn.recv(length - len(result))
        if not part:
            raise OSError("closed")
        result += part
    return result


def connect(relay, ca):
    conn = socket.create_connection((relay, 1080), timeout=10)
    conn.sendall(b"\x05\x01\x00")
    assert exact(conn, 2) == b"\x05\x00"
    domain = b"probe.qa.invalid"
    conn.sendall(b"\x05\x01\x00\x03" + bytes([len(domain)]) + domain + b"\x01\xbb")
    assert exact(conn, 4) == b"\x05\x00\x00\x01"
    exact(conn, 6)
    return ssl.create_default_context(cadata=ca).wrap_socket(conn, server_hostname=domain.decode())


def main():
    config = json.loads(sys.stdin.readline())
    with connect(config["relay"], config["ca"]) as conn:
        for line in sys.stdin:
            if line.strip() == "close":
                break
            assert line.strip() == "get"
            conn.sendall(b"GET / HTTP/1.1\r\nHost: probe.qa.invalid\r\nConnection: keep-alive\r\n\r\n")
            response = http.client.HTTPResponse(conn)
            response.begin()
            body = response.read().decode().strip()
            assert response.status == 200 and body in {"A", "B"}
            print(json.dumps({"endpoint": body, "status": response.status}), flush=True)


if __name__ == "__main__":
    main()
