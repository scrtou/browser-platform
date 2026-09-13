#!/usr/bin/env python3
"""QA-only Docker socket proxy with scoped mutations and stop fault injection.

Never use this as a production Docker proxy. It buffers HTTP responses and
does not implement streaming, exec or attach. Request bodies are not logged.
"""

import argparse
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import threading
from urllib.parse import urlsplit

PREFIX = "io.browser-platform."


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect("/var/run/docker.sock")


def upstream(method, path, body=None, headers=None):
    connection = UnixConnection("docker", timeout=35)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.getheaders(), response.read()
    finally:
        connection.close()


class Proxy(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, status, body=b"", headers=()):
        self.send_response(status)
        for key, value in headers:
            if key.lower() not in {"connection", "transfer-encoding", "content-length", "server", "date"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def error(self, status, message):
        self.reply(status, json.dumps({"message": message}).encode(), [("Content-Type", "application/json")])

    def event(self, mode, action, instance=""):
        with self.server.event_lock:
            with self.server.events.open("a") as handle:
                handle.write(json.dumps({"mode": mode, "action": action, "instance": instance}) + "\n")

    def owned(self, instance):
        status, _, data = upstream("GET", "/containers/" + instance + "/json")
        if status == 404:
            return False
        if status != 200:
            raise RuntimeError("Could not inspect mutation target")
        container = json.loads(data)
        labels = container.get("Config", {}).get("Labels") or {}
        return (labels.get(PREFIX + "scope") == self.server.scope and
                labels.get(PREFIX + "owner") == "lifecycle-qa" and
                labels.get(PREFIX + "version") == "1")

    def create_allowed(self, data):
        labels = data.get("Labels") or {}
        host = data.get("HostConfig") or {}
        if (labels.get(PREFIX + "scope") != self.server.scope or
                labels.get(PREFIX + "owner") != "lifecycle-qa" or
                data.get("Image") != self.server.image or
                host.get("NetworkMode") != self.server.network or
                host.get("Privileged") or host.get("PidMode") == "host" or
                host.get("PortBindings") or host.get("Devices") or host.get("Mounts")):
            return False
        binds = host.get("Binds") or []
        return bool(binds) and all(
            Path(bind.split(":", 1)[0]).resolve().is_relative_to(self.server.storage)
            for bind in binds
        )

    def handle_request(self):
        try:
            if self.headers.get("Transfer-Encoding"):
                return self.error(400, "Streaming requests are unsupported in QA")
            length = int(self.headers.get("Content-Length", 0))
            if length < 0 or length > 4 * 1024 * 1024:
                return self.error(413, "QA request limit")
            body = self.rfile.read(length) if length else None
            path = re.sub(r"^/v[0-9.]+(?=/)", "", urlsplit(self.path).path)
            policy = json.loads(self.server.policy.read_text())
            if policy.get("mode") == "inventory-error" and path == "/containers/json":
                self.event("inventory-error", "list")
                return self.error(500, "Injected QA Docker inventory failure")
            if self.command not in {"GET", "HEAD"}:
                if path == "/images/create":
                    return self.reply(200, b'{"status":"QA uses the preloaded pinned image"}\n', [("Content-Type", "application/json")])
                if path == "/containers/create" and self.command == "POST":
                    if not self.create_allowed(json.loads(body or b"{}")):
                        self.event("denied", "create")
                        return self.error(403, "QA create is outside the isolated scope")
                else:
                    match = re.fullmatch(r"/containers/([a-f0-9]{64})(?:/(start|stop|pause|unpause|wait|kill))?", path)
                    if not match or not self.owned(match[1]):
                        self.event("denied", "mutation")
                        return self.error(403, "QA mutation is outside the isolated scope")
                    instance, action = match[1], match[2] or "remove"
                    if instance == policy.get("instance") and action == "stop":
                        if policy.get("mode") == "false-ack":
                            self.event("false-ack", action, instance)
                            return self.reply(204)
                        if policy.get("mode") == "stop-error":
                            self.event("stop-error", action, instance)
                            return self.error(500, "Injected QA Docker stop failure")
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() not in {"connection", "host", "content-length"}}
            status, response_headers, response_body = upstream(self.command, self.path, body, headers)
            self.reply(status, response_body, response_headers)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self.event("proxy-error", type(exc).__name__)
            self.error(502, "QA proxy failed without forwarding an unverified mutation")

    do_GET = do_HEAD = do_POST = do_DELETE = handle_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--network", default="browser-platform-lifecycle-qa")
    args = parser.parse_args()
    root = args.root.resolve()
    if root.name != "qa" or not (root / "policy.json").is_file():
        raise SystemExit("An explicitly prepared QA directory is required")
    if args.socket.exists():
        raise SystemExit("Refusing to replace an existing Docker proxy socket")
    with Proxy(str(args.socket), Handler) as server:
        os.chmod(args.socket, 0o660)
        server.scope = hashlib.sha256(str(root / "config/.config/sealskin/sessions.yml").encode()).hexdigest()
        server.storage = root / "storage"
        server.policy = root / "policy.json"
        server.events = root / "proxy-events.jsonl"
        server.event_lock = threading.Lock()
        server.image = args.image
        server.network = args.network
        server.serve_forever()


if __name__ == "__main__":
    main()
