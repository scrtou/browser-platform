#!/usr/bin/env python3
"""Exercise both Caddy error-log boundaries using isolated loopback TLS sites."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def identity(root):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "entry.r5d.test")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("entry.r5d.test"), x509.DNSName("session.r5d.test")]), False)
            .sign(key, hashes.SHA256()))
    certificate, private_key = root / "cert.pem", root / "key.pem"
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private_key.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
    private_key.chmod(0o600)
    return certificate, private_key


def request(port, certificate, host, path, marker, method="GET", upgrade=False):
    context = ssl.create_default_context(cafile=str(certificate))
    with socket.create_connection(("127.0.0.1", port), timeout=3) as raw:
        with context.wrap_socket(raw, server_hostname=host) as connection:
            payload = (f"{method} {path}?access_token={marker} HTTP/1.1\r\nHost: {host}:{port}\r\n"
                       f"Cookie: display={marker}\r\nAuthorization: Bearer {marker}\r\n"
                       f"User-Agent: {marker}\r\nOrigin: https://{host}:{port}\r\n")
            if upgrade:
                payload += "Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            else:
                payload += "Connection: close\r\n"
            body = "password=" + marker if method == "POST" else ""
            payload += f"Content-Length: {len(body)}\r\nContent-Type: application/x-www-form-urlencoded\r\n\r\n" + body
            connection.sendall(payload.encode())
            response = http.client.HTTPResponse(connection)
            response.begin()
            result = response.read(1 << 20)
            return response.status, marker.encode() in result


def check(args, name, source, certificate, private_key):
    root = args.output / name
    root.mkdir(mode=0o700)
    port, upstream = free_port(), free_port()
    text = source
    if name == "session":
        text = text.replace("{{SESSION_PORT}}", str(port)).replace("{{API_PORT}}", str(upstream))
        text = text.replace("{{PROXY_CERT_PATH}}", str(certificate)).replace("{{PROXY_KEY_PATH}}", str(private_key))
        text = text.replace(f"https://:{port} {{", f"https://:{port} {{\n    bind 127.0.0.1")
        # Disable its normally container-local admin listener for a host check.
        text = text.replace("auto_https off", "auto_https off\n    admin off", 1)
    else:
        text = text.replace("admin off", "admin off\n    auto_https off", 1)
        text = text.replace("mybrowser.example.com, mysession.example.com {",
                            f"https://entry.r5d.test:{port}, https://session.r5d.test:{port} {{\n"
                            f"    bind 127.0.0.1\n    tls {certificate} {private_key}")
        text = text.replace("127.0.0.1:8080", f"127.0.0.1:{upstream}")
    config = root / "Caddyfile"
    config.write_text(text)
    environment = dict(os.environ, XDG_CONFIG_HOME=str(root / "config"), XDG_DATA_HOME=str(root / "data"))
    validation = subprocess.run([args.caddy, "adapt", "--config", str(config), "--adapter", "caddyfile", "--validate"],
                                env=environment, capture_output=True, timeout=15)
    (root / "validation.log").write_bytes(validation.stderr)
    (root / "adapted.json").write_bytes(validation.stdout)
    if validation.returncode:
        raise RuntimeError("CADDY_CONFIG_INVALID")
    marker = "r5d-log-sentinel-" + os.urandom(12).hex()
    statuses = []
    with (root / "process.log").open("wb") as log:
        process = subprocess.Popen([args.caddy, "run", "--config", str(config), "--adapter", "caddyfile"],
                                   env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("CADDY_START_FAILED")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.05)
            for host, path, method, upgrade in [
                    ("entry.r5d.test", "/auth/login", "POST", False),
                    ("session.r5d.test", "/2d3aaeda-bf75-4a4e-b31d-44dd999a713f/", "GET", False),
                    ("session.r5d.test", "/2d3aaeda-bf75-4a4e-b31d-44dd999a713f/ws", "GET", True)]:
                status, echoed = request(port, certificate, host, path, marker, method, upgrade)
                if status != 502 or echoed:
                    raise RuntimeError("CADDY_FAILURE_RESPONSE_INVALID")
                statuses.append(status)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    raw = (root / "process.log").read_bytes()
    records = []
    for line in raw.splitlines():
        try:
            records.append(json.loads(line))
        except (ValueError, UnicodeError):
            pass
    errors = [r for r in records if r.get("level") == "error" or r.get("level") == "ERROR"]
    leaked = marker.encode() in raw
    result = {"result": "FAIL" if leaked or len(errors) < 3 else "PASS", "requests": len(statuses), "statuses": statuses,
              "error_events": len(errors), "sentinel_leaked": leaked, "process_exit": process.returncode,
              "source_sha256": hashlib.sha256(source.encode()).hexdigest(), "listener_removed": True}
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=.3):
            result["listener_removed"], result["result"] = False, "FAIL"
    except OSError:
        pass
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--session-template", type=Path, required=True)
    parser.add_argument("--front-template", type=Path,
                        default=Path(__file__).resolve().parents[1] / "entry-auth/Caddyfile.example")
    parser.add_argument("--caddy", default="caddy")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    cert, key = identity(args.output)
    try:
        results = {name: check(args, name, path.read_text(), cert, key)
                   for name, path in (("session", args.session_template), ("front", args.front_template))}
        result = {"result": "PASS" if all(r["result"] == "PASS" for r in results.values()) else "FAIL", "layers": results,
                  "caddy_version": subprocess.check_output([args.caddy, "version"], text=True).strip()}
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0 if result["result"] == "PASS" else 1
    except Exception as exc:
        (args.output / "result.json").write_text(json.dumps({"result": "FAIL", "error_type": type(exc).__name__}) + "\n")
        raise
    finally:
        key.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
