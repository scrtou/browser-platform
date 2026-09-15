"""A real silent TCP peer must not block an independent TLS/HTTP request."""

from datetime import datetime, timedelta, timezone
import http.server
import importlib.util
from pathlib import Path
import socket
import ssl
import threading
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest

spec = importlib.util.spec_from_file_location("observer", Path(__file__).with_name("network-observer.py"))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


@pytest.mark.parametrize("kind", ["https", "dot"])
def test_silent_client_cannot_block_other_tls_or_live_past_deadline(tmp_path, kind):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "qa.test")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(minutes=5))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("qa.test")]), critical=False)
            .sign(key, hashes.SHA256()))
    (tmp_path / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(tmp_path / "cert.pem", tmp_path / "key.pem")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"qa-ok")

        def log_message(self, *args):
            pass

    server_class = observer.TLSHTTPServer if kind == "https" else observer.TLSTCPServer
    server = server_class(("127.0.0.1", 0), Handler, tls_context=context)
    server.handshake_timeout = 0.4
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    client_context = ssl.create_default_context(cafile=str(tmp_path / "cert.pem"))
    try:
        with socket.create_connection(server.server_address, timeout=1) as idle:
            time.sleep(0.05)
            start = time.monotonic()
            with socket.create_connection(server.server_address, timeout=0.25) as connection:
                with client_context.wrap_socket(connection, server_hostname="qa.test") as tls:
                    tls.sendall(b"GET / HTTP/1.0\r\nHost: qa.test\r\n\r\n")
                    data = b""
                    while part := tls.recv(4096):
                        data += part
                    assert b"200 OK" in data and data.endswith(b"qa-ok")
            assert time.monotonic() - start < server.handshake_timeout
            assert idle.recv(1) == b""  # Silent handshake is closed at its own deadline.
    finally:
        server.shutdown()
        server.server_close()
        thread.join(1)
