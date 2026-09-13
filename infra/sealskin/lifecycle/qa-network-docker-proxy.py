#!/usr/bin/env python3
"""Isolated network-lifecycle QA proxy; never a production Docker gateway.

Mutation targets must carry the exact QA deployment/user labels. Network
attachments additionally require an owned container or the one QA controller.
No request bodies, environment values or credentials are logged.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

spec = importlib.util.spec_from_file_location(
    "qa_base_proxy", Path(__file__).with_name("qa-docker-proxy.py")
)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
PREFIX = base.PREFIX


class Handler(base.Handler):
    def event(self, mode, action, instance=""):
        with self.server.event_lock:
            with self.server.events.open("a") as handle:
                handle.write(
                    json.dumps(
                        {
                            "time": time.time(),
                            "mode": mode,
                            "action": action,
                            "instance": instance,
                        }
                    )
                    + "\n"
                )

    def labels_owned(self, labels):
        return (
            labels.get(PREFIX + "scope") == self.server.scope
            and labels.get(PREFIX + "owner") == "network-qa"
            and bool(
                re.fullmatch(r"[a-f0-9]{32}", labels.get(PREFIX + "operation", ""))
            )
        )

    def inspect(self, category, identifier):
        suffix = "/json" if category == "containers" else ""
        status, _, raw = base.upstream(
            "GET", "/" + category + "/" + identifier + suffix
        )
        if status == 404:
            return None
        if status != 200:
            raise RuntimeError("QA ownership inspection unavailable")
        return json.loads(raw)

    def owned(self, instance):
        value = self.inspect("containers", instance)
        if value is None:
            return False
        labels = value.get("Config", {}).get("Labels") or {}
        return self.labels_owned(labels) and (
            labels.get(PREFIX + "version") == "1"
            or labels.get(PREFIX + "network-version") == "1"
        )

    def controller(self, instance):
        value = self.inspect("containers", instance)
        if value is None:
            return False
        return (
            value["Name"] == "/sealskin-network-qa"
            and value["Config"].get("Labels", {}).get(PREFIX + "qa")
            == "network-20260913"
            and any(
                m.get("Source") == str(self.server.root / "config")
                and m.get("Destination") == "/config"
                for m in value.get("Mounts", [])
            )
        )

    def owned_network(self, identifier, internal=None):
        value = self.inspect("networks", identifier)
        if value is None:
            return False
        labels = value.get("Labels") or {}
        return (
            self.labels_owned(labels)
            and labels.get(PREFIX + "network-version") == "1"
            and labels.get(PREFIX + "role") in {"internal", "egress"}
            and (internal is None or bool(value.get("Internal")) == internal)
        )

    def create_allowed(self, data):
        labels = data.get("Labels") or {}
        host = data.get("HostConfig") or {}
        role = labels.get(PREFIX + "role", "worker")
        allowed = json.loads(self.server.allow.read_text())
        mode = host.get("NetworkMode", "")
        private_network = (
            self.owned_network(mode, True)
            if not mode.startswith("container:")
            else False
        )
        if mode.startswith("container:") and role in {"worker", "probe"}:
            guard = self.inspect("containers", mode.split(":", 1)[1])
            guard_labels = (guard or {}).get("Config", {}).get("Labels") or {}
            private_network = (
                self.labels_owned(guard_labels)
                and guard_labels.get(PREFIX + "role") == "guard"
                and all(
                    guard_labels.get(PREFIX + key) == labels.get(PREFIX + key)
                    for key in (
                        "scope",
                        "owner",
                        "home_hash",
                        "operation",
                        "network-policy",
                        "network-policy-sha256",
                    )
                )
            )
        caps = set(host.get("CapAdd") or [])
        permitted_caps = {"NET_ADMIN", "SETUID", "SETGID", "SETPCAP", "DAC_READ_SEARCH"}
        guarded_initializer = role in {"guard", "relay"} and data.get(
            "Image"
        ) in allowed.get("guard_images", [])
        if (
            not self.labels_owned(labels)
            or data.get("Image") not in allowed["images"]
            or not private_network
            or host.get("Privileged")
            or host.get("PidMode") == "host"
            or host.get("PortBindings")
            or host.get("Devices")
            or caps
            and (not guarded_initializer or caps != permitted_caps)
        ):
            return False
        if role not in {"worker", "relay", "guard", "probe"}:
            return False
        if role != "worker" and (
            not host.get("ReadonlyRootfs")
            or labels.get(PREFIX + "network-version") != "1"
        ):
            return False
        if role == "worker" and labels.get(PREFIX + "version") != "1":
            return False
        for mount in host.get("Mounts") or []:
            if (
                mount.get("Type") != "bind"
                or not mount.get("ReadOnly")
                or str(Path(mount.get("Source", "")).resolve())
                not in allowed.get("readonly_sources", [])
            ):
                return False
        for bind in host.get("Binds") or []:
            parts = bind.split(":")
            source = Path(parts[0]).resolve()
            if source.is_relative_to(self.server.root):
                continue
            if (
                len(parts) < 3
                or parts[2] != "ro"
                or str(source) not in allowed.get("readonly_sources", [])
            ):
                return False
        return True

    def network_create_allowed(self, data):
        labels = data.get("Labels") or {}
        kind = labels.get(PREFIX + "role")
        return (
            self.labels_owned(labels)
            and labels.get(PREFIX + "network-version") == "1"
            and kind in {"internal", "egress"}
            and data.get("Driver") == "bridge"
            and bool(data.get("Internal")) == (kind == "internal")
            and not data.get("EnableIPv6")
            and bool(
                re.fullmatch(r"bp-" + kind + "-[a-f0-9]{40}", data.get("Name", ""))
            )
        )

    def handle_request(self):
        try:
            if self.headers.get("Transfer-Encoding"):
                return self.error(400, "QA streaming requests unsupported")
            length = int(self.headers.get("Content-Length", 0))
            if not 0 <= length <= 4 * 1024 * 1024:
                return self.error(413, "QA body limit")
            body = self.rfile.read(length) if length else None
            path = re.sub(r"^/v[0-9.]+(?=/)", "", urlsplit(self.path).path)
            policy = json.loads(self.server.policy.read_text())
            action = role = instance = ""
            if policy.get("mode") == "inventory-error" and path in {
                "/containers/json",
                "/networks",
            }:
                self.event("inventory-error", "list")
                return self.error(500, "Injected QA inventory failure")
            if self.command not in {"GET", "HEAD"}:
                data = json.loads(body or b"{}")
                if path == "/images/create":
                    return self.reply(
                        200,
                        b'{"status":"QA uses preloaded pinned images"}\n',
                        [("Content-Type", "application/json")],
                    )
                if path == "/containers/create" and self.command == "POST":
                    if not self.create_allowed(data):
                        self.event("denied", "container-create")
                        return self.error(
                            403, "QA container create outside approved scope"
                        )
                    action, role = (
                        "create",
                        data["Labels"].get(PREFIX + "role", "worker"),
                    )
                elif path == "/networks/create" and self.command == "POST":
                    if not self.network_create_allowed(data):
                        self.event("denied", "network-create")
                        return self.error(
                            403, "QA network create outside approved scope"
                        )
                    action, role = "create", data["Labels"][PREFIX + "role"]
                elif path.startswith("/networks/"):
                    match = re.fullmatch(
                        r"/networks/([a-f0-9]{64})(?:/(connect|disconnect))?", path
                    )
                    if not match or not self.owned_network(match[1]):
                        self.event("denied", "network-mutation")
                        return self.error(
                            403, "QA network mutation outside approved scope"
                        )
                    instance, action = match[1], match[2] or "network-remove"
                    if match[2] and not (
                        self.owned(data.get("Container", ""))
                        or self.controller(data.get("Container", ""))
                    ):
                        self.event("denied", "network-attachment")
                        return self.error(
                            403, "QA network endpoint outside approved scope"
                        )
                    if (
                        action == "network-remove"
                        and policy.get("mode") == "network-remove-error"
                        and instance == policy.get("instance")
                    ):
                        self.event("network-remove-error", action, instance)
                        return self.error(500, "Injected QA network removal failure")
                else:
                    match = re.fullmatch(
                        r"/containers/([a-f0-9]{64})(?:/(start|stop|unpause|wait|kill))?",
                        path,
                    )
                    if not match or not self.owned(match[1]):
                        self.event("denied", "container-mutation")
                        return self.error(
                            403, "QA container mutation outside approved scope"
                        )
                    instance, action = match[1], match[2] or "remove"
                    if action == "stop" and instance == policy.get("instance"):
                        if policy.get("mode") == "false-ack":
                            self.event("false-ack", action, instance)
                            return self.reply(204)
                        if policy.get("mode") == "stop-error":
                            self.event("stop-error", action, instance)
                            return self.error(500, "Injected QA stop failure")
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"connection", "host", "content-length"}
            }
            status, response_headers, response_body = base.upstream(
                self.command, self.path, body, headers
            )
            if action:
                if action == "create" and status == 201:
                    instance = json.loads(response_body).get("Id", "")
                self.event("forwarded", action + ("-" + role if role else ""), instance)
            if (
                action == "create"
                and status == 201
                and policy.get("mode") == "lost-create"
                and role == policy.get("role")
            ):
                self.event("lost-create", role, instance)
                return self.error(
                    500, "Injected lost create response after Docker allocated resource"
                )
            self.reply(status, response_body, response_headers)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self.event("proxy-error", type(exc).__name__)
            self.error(502, "QA proxy failed before an unverified mutation")

    do_GET = do_HEAD = do_POST = do_DELETE = handle_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if root.name != "qa" or not (root / "allow.json").is_file() or args.socket.exists():
        raise SystemExit(
            "A fresh explicitly prepared QA directory and socket are required"
        )
    with base.Proxy(str(args.socket), Handler) as server:
        os.chmod(args.socket, 0o660)
        server.root = root
        server.scope = hashlib.sha256(
            str(root / "config/.config/sealskin/sessions.yml").encode()
        ).hexdigest()
        server.allow = root / "allow.json"
        server.policy = root / "policy.json"
        server.events = root / "proxy-events.jsonl"
        server.event_lock = threading.Lock()
        server.serve_forever()


if __name__ == "__main__":
    main()
