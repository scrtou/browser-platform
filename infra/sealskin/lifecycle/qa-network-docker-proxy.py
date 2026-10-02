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
import stat
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

spec = importlib.util.spec_from_file_location(
    "qa_base_proxy", Path(__file__).with_name("qa-docker-proxy.py")
)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
PREFIX = base.PREFIX
SHUTDOWN_COMMAND = ["python3", "/usr/local/lib/browser-platform/browser-shutdown.py", "--timeout", "12"]
DIRECT_HOST_SOURCE = "/proc/1/net/fib_trie"
DIRECT_HOST_TARGET = "/run/browser-platform-host/ipv4-fib-trie"
INSPECT_COMMAND = ["python3", "-B", "/usr/local/lib/browser-platform/network-guard.py",
                   "--network-config", "/run/config/network.json", "--inspect", "--inspect-output"]
OBSERVATION_TARGET = "/run/browser-platform-observation"
DISPLAY_TARGET = "/run/browser-platform-session-input"
DYNAMIC_TARGET = "/run/browser-platform-network"
DYNAMIC_COMMAND = ["python3", "-B", "/usr/local/lib/browser-platform/network-guard.py",
                   "--network-config", DYNAMIC_TARGET + "/relay-network.json", "--apply-only"]


def display_bind_allowed(allowed, labels, source, destination, readonly):
    """Allow this QA Worker's Session directory, never the parent or a peer."""
    if destination != DISPLAY_TARGET or not readonly or labels.get(PREFIX + "role", "worker") != "worker":
        return False
    try:
        root = Path(allowed["display_runtime_root"])
        sid = labels[PREFIX + "session"]
        if labels.get(PREFIX + "session-auth") != "1" or str(uuid.UUID(sid)) != sid:
            return False
        path = Path(source)
        if root.parent != Path("/dev/shm") or path != root / ("session-" + sid):
            return False
        for directory in (root, path):
            info = directory.lstat()
            if (directory.resolve() != directory or not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
                return False
        marker = path / "binding.json"
        info = marker.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_size > 1024):
            return False
        return json.loads(marker.read_bytes()) == {"version": 1, "uid": os.geteuid(), "session_id": sid}
    except (KeyError, OSError, ValueError, TypeError):
        return False


def observation_bind_allowed(root, labels, source, destination, readonly):
    role = labels.get(PREFIX + "role", "worker")
    if destination != OBSERVATION_TARGET or readonly or role not in {"worker", "guard", "relay"}:
        return False
    try:
        home_hash, operation = labels[PREFIX + "home_hash"], labels[PREFIX + "operation"]
        if not re.fullmatch(r"[a-f0-9]{64}", home_hash) or not re.fullmatch(r"[a-f0-9]{32}", operation):
            return False
        expected = root / "config/.config/sealskin/profile-network-runtime" / (home_hash + "-" + operation) / "observations" / role
        path = Path(source)
        info = path.lstat()
        return (path == expected and path.resolve() == expected and stat.S_ISDIR(info.st_mode)
                and stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.geteuid())
    except (KeyError, OSError, ValueError, TypeError):
        return False


def direct_host_bind_allowed(root, allowed, labels, image, source, destination, readonly):
    """Allow only an approved DIRECT Relay to read this exact host procfs file."""
    if (image not in allowed.get("direct_images", []) or labels.get(PREFIX + "role") != "relay" or
            str(source) != DIRECT_HOST_SOURCE or destination != DIRECT_HOST_TARGET or not readonly):
        return False
    try:
        identity = {key: labels[PREFIX + key] for key in ("scope", "owner", "home", "home_hash", "app", "profile", "operation")}
        if identity["owner"] != "network-qa" or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identity["home"]):
            return False
        home = root / "storage" / identity["owner"] / identity["home"]
        if hashlib.sha256(str(home).encode()).hexdigest() != identity["home_hash"]:
            return False
        path = root / "config/.config/sealskin/profile-network-runtime" / (identity["home_hash"] + ".json")
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            return False
        record = json.loads(path.read_text())
        policy = record["policy"]
        revision = hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return (all(record["identity"].get(key) == value for key, value in identity.items()) and
                policy.get("mode") == "direct" and record.get("policy_id") == labels.get(PREFIX + "network-policy") and
                revision == record.get("policy_sha256") == labels.get(PREFIX + "network-policy-sha256"))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def credential_bind_allowed(root, allowed, labels, source, destination, readonly):
    """Permit only this Relay generation's private tmpfs directory, never its key."""
    runtime = allowed.get("credential_runtime_root")
    if not runtime or not readonly or destination != "/run/secrets" or labels.get(PREFIX + "role") != "relay":
        return False
    runtime = Path(runtime)
    try:
        info = runtime.lstat()
        if (runtime.parent != Path("/dev/shm") or runtime.resolve() != runtime
                or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077):
            return False
        identity = {key: labels[PREFIX + key] for key in ("scope", "owner", "home", "home_hash", "app", "profile", "operation")}
        if identity["owner"] != "network-qa" or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identity["home"]):
            return False
        identity["home_source"] = str(root / "storage" / identity["owner"] / identity["home"])
        if hashlib.sha256(identity["home_source"].encode()).hexdigest() != identity["home_hash"]:
            return False
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        expected = runtime / ("generation-" + digest)
        info = source.lstat()
        return (source == expected and source.resolve() == expected and stat.S_ISDIR(info.st_mode)
                and info.st_uid == os.geteuid() and not info.st_mode & 0o077)
    except (KeyError, OSError, ValueError):
        return False


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
        if role == "worker" and mode == self.server.legacy_network and labels.get(PREFIX + "version") == "1":
            # Legacy (no-policy) Worker drills: the labelled Worker joins the QA
            # bridge directly, exactly like production's pre-policy generations.
            private_network = True
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
            if mount.get("Target") == DISPLAY_TARGET:
                if mount.get("Type") == "bind" and display_bind_allowed(allowed, labels, mount.get("Source"), mount["Target"], mount.get("ReadOnly")):
                    continue
                return False
            if mount.get("Target") == OBSERVATION_TARGET:
                if mount.get("Type") == "bind" and observation_bind_allowed(self.server.root, labels, mount.get("Source"), mount["Target"], mount.get("ReadOnly")):
                    continue
                return False
            if mount.get("Source") == DIRECT_HOST_SOURCE or mount.get("Target") == DIRECT_HOST_TARGET:
                if mount.get("Type") == "bind" and direct_host_bind_allowed(
                        self.server.root, allowed, labels, data.get("Image"), mount.get("Source"),
                        mount.get("Target"), mount.get("ReadOnly")):
                    continue
                return False
            if mount.get("Type") == "bind" and credential_bind_allowed(
                    self.server.root, allowed, labels, Path(mount.get("Source", "")),
                    mount.get("Target"), mount.get("ReadOnly")):
                continue
            if (
                mount.get("Type") != "bind"
                or not mount.get("ReadOnly")
                or str(Path(mount.get("Source", "")).resolve())
                not in allowed.get("readonly_sources", [])
            ):
                return False
        for bind in host.get("Binds") or []:
            parts = bind.split(":")
            if len(parts) > 1 and parts[1] == DISPLAY_TARGET:
                if len(parts) == 3 and display_bind_allowed(allowed, labels, parts[0], parts[1], parts[2] == "ro"):
                    continue
                return False
            if len(parts) > 1 and parts[1] == OBSERVATION_TARGET:
                if len(parts) == 3 and parts[2] == "rw" and observation_bind_allowed(self.server.root, labels, parts[0], parts[1], False):
                    continue
                return False
            if parts[0] == DIRECT_HOST_SOURCE or len(parts) > 1 and parts[1] == DIRECT_HOST_TARGET:
                if len(parts) == 3 and direct_host_bind_allowed(
                        self.server.root, allowed, labels, data.get("Image"), parts[0], parts[1], parts[2] == "ro"):
                    continue
                return False
            source = Path(parts[0]).resolve()
            if len(parts) == 3 and credential_bind_allowed(
                    self.server.root, allowed, labels, Path(parts[0]), parts[1], parts[2] == "ro"):
                continue
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

    def shutdown_worker(self, instance):
        if not self.owned(instance):
            return False
        value = self.inspect("containers", instance)
        labels = (value or {}).get("Config", {}).get("Labels") or {}
        return labels.get(PREFIX + "browser-shutdown") == "1" and labels.get(PREFIX + "role", "worker") == "worker"

    def shutdown_exec(self, identifier):
        status, _, raw = base.upstream("GET", "/exec/" + identifier + "/json")
        if status != 200:
            return False
        value = json.loads(raw)
        process = value.get("ProcessConfig") or {}
        return (self.shutdown_worker(value.get("ContainerID", ""))
                and process.get("user") == "abc" and not process.get("privileged")
                and not process.get("tty")
                and [process.get("entrypoint"), *process.get("arguments", [])] == SHUTDOWN_COMMAND
                and not any(value.get(key) for key in ("OpenStdin", "OpenStdout", "OpenStderr")))

    def coherence_command(self, instance, command, user):
        if not self.owned(instance) or not isinstance(command, list):
            return False
        value = self.inspect("containers", instance)
        labels = value.get("Config", {}).get("Labels") or {}
        allowed = json.loads(self.server.allow.read_text())
        role = labels.get(PREFIX + "role", "worker")
        if role in {"guard", "relay"}:
            return (user == "0" and value.get("Image") in allowed.get("coherence_guard_images", []) and
                    len(command) == len(INSPECT_COMMAND) + 1 and command[:-1] == INSPECT_COMMAND and
                    isinstance(command[-1], str) and bool(re.fullmatch(r"[a-f0-9]{32}", command[-1])))
        env = dict(v.split("=", 1) for v in value.get("Config", {}).get("Env", []) if "=" in v)
        return (role == "worker" and user == "abc" and env.get("MOZ_MARIONETTE") == "1" and
                len(command) == 4 and command[:2] == ["python3", "-c"] and all(isinstance(v, str) for v in command) and
                len(command[3]) <= 32768 and hashlib.sha256(command[2].encode()).hexdigest() in allowed.get("coherence_observer_sha256", []))

    def coherence_exec(self, identifier):
        status, _, raw = base.upstream("GET", "/exec/" + identifier + "/json")
        if status != 200:
            return False
        value = json.loads(raw)
        process = value.get("ProcessConfig") or {}
        return (not process.get("privileged") and not process.get("tty") and
                not any(value.get(key) for key in ("OpenStdin", "OpenStdout", "OpenStderr")) and
                self.coherence_command(value.get("ContainerID", ""), [process.get("entrypoint"), *process.get("arguments", [])], process.get("user")))

    def dynamic_command(self, instance, command, user):
        if command != DYNAMIC_COMMAND or user != "0:0" or not self.owned(instance):
            return False
        value = self.inspect("containers", instance)
        labels = value.get("Config", {}).get("Labels") or {}
        allowed = json.loads(self.server.allow.read_text())
        if labels.get(PREFIX + "role") != "relay" or value.get("Image") not in allowed.get("dynamic_images", []):
            return False
        try:
            identity = {key: labels[PREFIX + key] for key in ("scope", "owner", "home", "home_hash", "app", "profile", "operation")}
            root = self.server.root / "config/.config/sealskin/profile-network-runtime"
            path = root / (identity["home_hash"] + ".json")
            if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
                return False
            record = json.loads(path.read_text())
            directory = root / (identity["home_hash"] + "-" + identity["operation"])
            mounts = [m for m in value.get("Mounts", []) if m.get("Destination") == DYNAMIC_TARGET]
            return (all(record["identity"].get(k) == v for k, v in identity.items())
                    and record["identity"].get("home_source") == str(self.server.root / "storage/network-qa" / identity["home"])
                    and record["allocation"]["relay_id"] == instance
                    and record["allocation"].get("dynamic_upstream_version") == 1
                    and len(mounts) == 1 and mounts[0].get("Type") == "bind"
                    and mounts[0].get("Source") == str(directory) and mounts[0].get("RW") is False)
        except (KeyError, OSError, ValueError, TypeError):
            return False

    def dynamic_exec(self, identifier):
        status, _, raw = base.upstream("GET", "/exec/" + identifier + "/json")
        if status != 200:
            return False
        value = json.loads(raw)
        process = value.get("ProcessConfig") or {}
        return (not process.get("privileged") and not process.get("tty") and not value.get("OpenStdin")
                and value.get("OpenStdout") is True and value.get("OpenStderr") is True
                and self.dynamic_command(value.get("ContainerID", ""),
                    [process.get("entrypoint"), *process.get("arguments", [])], process.get("user")))

    def hold_dynamic(self, instance, stage):
        """Bounded QA crash point; never execute a released stale request."""
        policy = json.loads(self.server.policy.read_text())
        if (policy.get("mode") != "dynamic-hold" or policy.get("instance") != instance
                or policy.get("stage") != stage or not self.dynamic_command(instance, DYNAMIC_COMMAND, "0:0")):
            return False
        container = self.inspect("containers", instance)
        mount = next(m for m in container["Mounts"] if m.get("Destination") == DYNAMIC_TARGET)
        config = json.loads((Path(mount["Source"]) / "relay-network.json").read_text())
        if config.get("upstream_ipv4") != policy.get("addresses"):
            return False
        marker = self.server.root / "dynamic-held.json"
        temporary = marker.with_suffix(".tmp")
        with temporary.open("w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump({"instance": instance, "stage": stage, "at": time.time()}, stream)
        os.replace(temporary, marker)
        self.event("dynamic-hold", stage, instance)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if json.loads(self.server.policy.read_text()) != policy:
                break
            time.sleep(.05)
        return True

    def start_dynamic_exec(self, identifier, body, instance=""):
        # Docker's attached exec uses an HTTP upgrade, including for output
        # only commands. The ordinary buffered HTTP helper discards that raw
        # stream. Forward bounded output only, with no bidirectional tunnel.
        connection = base.UnixConnection("docker", timeout=35)
        try:
            connection.connect()
            request = ("POST /exec/" + identifier + "/start HTTP/1.1\r\nHost: docker\r\n"
                       "Connection: Upgrade\r\nUpgrade: tcp\r\nContent-Type: application/json\r\n"
                       "Content-Length: " + str(len(body)) + "\r\n\r\n").encode() + body
            connection.sock.sendall(request)
            header = b""
            while not header.endswith(b"\r\n\r\n") and len(header) <= 4096:
                chunk = connection.sock.recv(1)
                if not chunk:
                    break
                header += chunk
            if not header.startswith(b"HTTP/1.1 101 ") or not header.endswith(b"\r\n\r\n"):
                raise ValueError("fixed exec upgrade failed")
            self.event("forwarded", "dynamic-start")
            self.close_connection = True
            # Flush the upgrade before waiting for command output. Docker SDK
            # switches from HTTP parsing to the raw socket at this boundary.
            self.wfile.write(header)
            self.wfile.flush()
            count = 0
            while True:
                chunk = connection.sock.recv(4097 - count)
                if not chunk:
                    break
                count += len(chunk)
                if count > 4096:
                    raise ValueError("fixed exec output limit")
                if instance and self.hold_dynamic(instance, "result"):
                    return
                self.wfile.write(chunk)
                self.wfile.flush()
        finally:
            connection.close()

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
                elif re.fullmatch(r"/containers/[a-f0-9]{64}/exec", path):
                    instance = path.split("/")[2]
                    shutdown = self.shutdown_worker(instance) and data.get("Cmd") == SHUTDOWN_COMMAND and data.get("User") == "abc"
                    coherence = self.coherence_command(instance, data.get("Cmd"), data.get("User"))
                    dynamic = self.dynamic_command(instance, data.get("Cmd"), data.get("User"))
                    output_allowed = (data.get("AttachStdout") is True and data.get("AttachStderr") is True) if dynamic else not (data.get("AttachStdout") or data.get("AttachStderr"))
                    if (self.command != "POST" or not (shutdown or coherence or dynamic) or not output_allowed
                            or any(data.get(key) for key in ("Privileged", "Tty", "AttachStdin", "Env", "WorkingDir"))
                            or set(data) - {"Cmd", "User", "Privileged", "Tty", "AttachStdin", "AttachStdout", "AttachStderr", "Env", "WorkingDir", "Container"}):
                        return self.error(403, "QA only permits the fixed detached browser shutdown command")
                    if dynamic and policy.get("mode") == "dynamic-apply-error" and policy.get("instance") == instance:
                        self.event("dynamic-apply-error", "dynamic-create", instance)
                        return self.error(500, "Injected QA dynamic rule update failure")
                    if dynamic and self.hold_dynamic(instance, "create"):
                        return self.error(503, "Interrupted QA dynamic update")
                    action = "dynamic-create" if dynamic else "coherence-create" if coherence else "browser-shutdown-create"
                elif re.fullmatch(r"/exec/[a-f0-9]{64}/start", path):
                    identifier = path.split("/")[2]
                    dynamic = self.dynamic_exec(identifier)
                    permitted = (data == {"Tty": False, "Detach": False}) if dynamic else (data == {"Tty": False, "Detach": True} and (self.shutdown_exec(identifier) or self.coherence_exec(identifier)))
                    if self.command != "POST" or not permitted:
                        return self.error(403, "QA shutdown exec is outside approved scope")
                    if dynamic:
                        _, _, raw = base.upstream("GET", "/exec/" + identifier + "/json")
                        return self.start_dynamic_exec(identifier, body, json.loads(raw)["ContainerID"])
                    action = "dynamic-start" if dynamic else "fixed-exec-start"
                else:
                    match = re.fullmatch(
                        r"/containers/([a-f0-9]{64})(?:/(start|stop|pause|unpause|wait|kill))?",
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
        server.legacy_network = "browser-platform-network-qa"
        server.policy = root / "policy.json"
        server.events = root / "proxy-events.jsonl"
        server.event_lock = threading.Lock()
        server.serve_forever()


if __name__ == "__main__":
    main()
