#!/usr/bin/env python3
"""Prepare fresh, private Docker fixtures for the generation network checks.

Build the three Adapter binaries into ROOT/bin before running this script.
ROOT must be a new qa directory alongside the prepared SealSkin build.
"""

import argparse
import hashlib
import http.client
import importlib.util
import json
import shlex
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--build", type=Path, required=True)
parser.add_argument("--probe-image", default="lscr.io/linuxserver/sealskin:0.3.2-ls58@sha256:d52c155eb78882b27c7780e77df335939d46cd06a514c9fa310039307542ee6a", help="Explicit imported probe image ID or pinned original reference")
parser.add_argument("--relay-image", required=True, help="Retained version tag from relay/build-guarded-image.py")
parser.add_argument("--secret-runtime-root", type=Path, help="Existing private directory immediately below /dev/shm")
parser.add_argument("--secret-key-directory", type=Path, help="Existing private directory mounted read-only into the controller")
parser.add_argument("--direct-host-evidence", action="store_true", help="Bind the host IPv4 procfs table read-only for DIRECT QA")
parser.add_argument("--session-port", type=int, help="Also publish the QA Session TLS listener on this loopback port")
parser.add_argument("--display-runtime-root", type=Path, help="Private tmpfs directory immediately below /dev/shm for Worker display secrets")
args = parser.parse_args()
if args.session_port is not None and not 1024 <= args.session_port <= 65535:
    parser.error("Session TLS port must be between 1024 and 65535")
secret_mounts = []
display_mounts = []
if args.display_runtime_root:
    import os
    import stat
    path = args.display_runtime_root
    info = path.lstat()
    assert path.parent == Path("/dev/shm") and path.resolve() == path and stat.S_ISDIR(info.st_mode)
    assert info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700
    display_mounts = ["-v", str(path) + ":/run/browser-platform-session-secrets"]
if bool(args.secret_runtime_root) != bool(args.secret_key_directory):
    parser.error("Secret runtime and key directory must be supplied together")
if args.secret_runtime_root:
    import os
    import stat
    for path in (args.secret_runtime_root, args.secret_key_directory):
        info = path.lstat()
        assert path.is_absolute() and path.resolve() == path and stat.S_ISDIR(info.st_mode)
        assert info.st_uid == os.geteuid() and not info.st_mode & 0o077
    assert args.secret_runtime_root.parent == Path("/dev/shm")
    secret_mounts = ["-v", str(args.secret_runtime_root) + ":/run/browser-platform-secrets",
                     "-v", str(args.secret_key_directory) + ":/run/browser-platform-key:ro"]
PROJECT = Path(__file__).resolve().parents[3]
QA = args.root.resolve()
BUILD = args.build.resolve()
ROOT = QA.parent
assert QA.name == "qa" and BUILD.parent == ROOT, (
    "Use a fresh qa directory beside the prepared build"
)
assert all(
    (QA / "bin" / name).is_file()
    for name in ["profile-adapter", "sealskin-provision", "sealskin-install-app"]
), "Build the QA binaries first"
SOCKET = Path("/tmp/browser-platform-network-qa-docker.sock")
LABEL = "io.browser-platform.qa=network-20260913"


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(data, indent=2) + "\n")
    path.chmod(0o600)


def docker(*args):
    result = subprocess.run(
        ["sg", "docker", "-c", shlex.join(["docker", *args])],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("QA Docker command failed: " + result.stderr[:200])
    return result.stdout


def start(args, logname, pidname):
    with (QA / logname).open("ab") as log:
        process = subprocess.Popen(
            args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
    write(QA / pidname, {"pid": process.pid})
    return process


def wait(predicate, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except (OSError, http.client.HTTPException):
            pass
        time.sleep(0.3)
    raise RuntimeError("QA readiness timeout")


def ready():
    c = http.client.HTTPConnection("127.0.0.1", 28110, timeout=2)
    try:
        c.request("POST", "/api/handshake/initiate")
        r = c.getresponse()
        r.read()
        return r.status == 200
    finally:
        c.close()


assert not (QA / "config").exists() and not SOCKET.exists(), "Requires fresh QA scope"
QA.chmod(0o700)
for path in [QA / "config/.config/sealskin/network-secrets", QA / "storage"]:
    path.mkdir(parents=True, mode=0o700)
(QA / "config/.config/sealskin/app_stores.yml").write_text("[]\n")
(QA / "config/.config/sealskin/app_stores.yml").chmod(0o600)
release = json.loads((BUILD / "release.json").read_text())
probe_id = docker(
    "image",
    "inspect",
    args.probe_image,
    "--format",
    "{{.Id}}",
).strip()
relay_id = docker(
    "image", "inspect", args.relay_image, "--format", "{{.Id}}"
).strip()
bridge = json.loads(docker("network", "inspect", "bridge"))[0]["IPAM"]["Config"][0][
    "Gateway"
]
write(QA / "allow.json", {"images": [probe_id, relay_id], "guard_images": [relay_id], "readonly_sources": [],
                         **({"display_runtime_root": str(args.display_runtime_root)} if args.display_runtime_root else {}),
                         **({"direct_images": [relay_id]} if args.direct_host_evidence else {}),
                         **({"credential_runtime_root": str(args.secret_runtime_root)} if args.secret_runtime_root else {})})
write(QA / "policy.json", {})
write(QA / "upstream-mode.json", {})
write(
    QA / "images.json",
    {
        "probe": probe_id,
        "relay": relay_id,
        "controller": release["image"],
        "upstream_host": bridge,
        "build": BUILD.name,
    },
)
ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Network Lifecycle QA CA")])
now = datetime.now(timezone.utc)
ca = (
    x509.CertificateBuilder()
    .subject_name(name)
    .issuer_name(name)
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=5))
    .not_valid_after(now + timedelta(days=2))
    .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )
    .add_extension(
        x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
    )
    .add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
        critical=False,
    )
    .sign(ca_key, hashes.SHA256())
)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
leaf = (
    x509.CertificateBuilder()
    .subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "probe.qa.invalid")])
    )
    .issuer_name(name)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=5))
    .not_valid_after(now + timedelta(days=2))
    .add_extension(
        x509.SubjectAlternativeName([x509.DNSName("probe.qa.invalid")]), critical=False
    )
    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=True,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )
    .add_extension(
        x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
    )
    .add_extension(
        x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
    )
    .add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
        critical=False,
    )
    .sign(ca_key, hashes.SHA256())
)
for path, data in [
    (QA / "mock-server.pem", leaf.public_bytes(serialization.Encoding.PEM)),
    (
        QA / "mock-server-key.pem",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    ),
    (
        QA / "config/.config/sealskin/network-secrets/probe-ca.pem",
        ca.public_bytes(serialization.Encoding.PEM),
    ),
]:
    path.write_bytes(data)
    path.chmod(0o600)
for kind, value in [
    ("username", "network-qa-user"),
    ("password", "network-qa-password"),
]:
    path = QA / "config/.config/sealskin/network-secrets" / kind
    path.write_text(value)
    path.chmod(0o600)
proxy = start(
    [
        "sg",
        "docker",
        "-c",
        shlex.join(
            [
                "python3",
                str(PROJECT / "infra/sealskin/lifecycle/qa-network-docker-proxy.py"),
                "--root",
                str(QA),
                "--socket",
                str(SOCKET),
            ]
        ),
    ],
    "proxy.log",
    "proxy-pid.json",
)
wait(SOCKET.exists)
assert proxy.poll() is None
docker("network", "create", "--label", LABEL, "browser-platform-network-qa")
upstream_dir = QA / "upstream"
upstream_dir.mkdir(mode=0o700)
for name in ["mock-server.pem", "mock-server-key.pem", "upstream-mode.json"]:
    (upstream_dir / name).write_bytes((QA / name).read_bytes())
    (upstream_dir / name).chmod(0o600)
docker(
    "run",
    "-d",
    "--name",
    "network-qa-upstream",
    "--label",
    LABEL,
    "--network",
    "browser-platform-network-qa",
    "--memory",
    "64m",
    "--cpus",
    ".5",
    "--pids-limit",
    "64",
    "--user",
    "1000:1000",
    "--read-only",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges:true",
    "-p",
    bridge + ":28181:28181",
    "-v",
    str(upstream_dir) + ":/qa",
    "-v",
    str(PROJECT / "infra/sealskin/lifecycle/qa-network-upstream.py")
    + ":/run/qa-upstream.py:ro",
    "--entrypoint",
    "python3",
    probe_id,
    "/run/qa-upstream.py",
    "--root",
    "/qa",
    "--bind",
    "0.0.0.0",
)
docker(
    "run",
    "-d",
    "--name",
    "sealskin-network-qa",
    "--label",
    LABEL,
    "--network",
    "browser-platform-network-qa",
    "--memory",
    "512m",
    "--cpus",
    "1.5",
    "--pids-limit",
    "256",
    "-e",
    "PUID=1000",
    "-e",
    "PGID=1000",
    "-e",
    "TZ=Etc/UTC",
    "-e",
    "HOST_URL=network.invalid",
    "--add-host",
    "proxy.leak.qa.test:" + bridge,
    "-v",
    str(QA / "config") + ":/config",
    "-v",
    str(QA / "storage") + ":/storage",
    "-v",
    str(SOCKET) + ":/var/run/docker.sock",
    "-p",
    "127.0.0.1:28110:8000",
    *(["-p", "127.0.0.1:" + str(args.session_port) + ":8443"] if args.session_port else []),
    *secret_mounts, *display_mounts,
    *(["--mount", "type=bind,src=/proc/1/net/fib_trie,dst=/run/browser-platform-host/ipv4-fib-trie,readonly"]
      if args.direct_host_evidence else []),
    release["image"],
)
wait(ready)
admin = json.loads((QA / "config/admin.json").read_text())
admin["server_endpoint"] = "http://127.0.0.1:28110"
admin["api_port"] = 28110
write(QA / "admin.json", admin)
(QA / "server-public.pem").write_text(admin["server_public_key"])
(QA / "server-public.pem").chmod(0o600)
result = subprocess.run(
    [
        str(QA / "bin/sealskin-provision"),
        "--admin-config",
        str(QA / "admin.json"),
        "--username",
        "network-qa",
        "--private-key",
        str(QA / "client-private.pem"),
    ],
    capture_output=True,
    text=True,
)
assert result.returncode == 0, "QA user provisioning failed: " + result.stderr[:200]

spec = importlib.util.spec_from_file_location(
    "network_qa_checks", Path(__file__).with_name("check-network-live.py")
)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
client = checks.SecureClient(QA)
for suffix in ("a", "b"):
    status, _ = client.call(
        "POST", "/api/homedirs", {"home_name": "network-qa-home-" + suffix}
    )
    assert status == 201, "QA Home creation failed"


def digest(policy):
    return hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


policies = {}
definitions = []
worker_code = 'from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer\nclass H(BaseHTTPRequestHandler):\n def log_message(self,*args): pass\n def do_GET(self):\n  self.send_response(200); self.send_header("Content-Length","2"); self.end_headers(); self.wfile.write(b"ok")\nThreadingHTTPServer(("0.0.0.0",3000),H).serve_forever()\n'
for suffix in ["a", "b"]:
    profile = "network-qa-" + suffix
    home = "network-qa-home-" + suffix
    app = "network-qa-app-" + suffix
    policy_id = "network-qa-socks-" + suffix + "-r1"
    refs = {}
    for kind, name in [
        ("username", "username"),
        ("password", "password"),
        ("probe_ca", "probe-ca.pem"),
    ]:
        source = QA / "config/.config/sealskin/network-secrets" / name
        refs[kind + "_file"] = "/config/.config/sealskin/network-secrets/" + name
        refs[kind + "_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    policy = dict(
        username="network-qa",
        profile_id=profile,
        home_name=home,
        application_id=app,
        relay_image=relay_id,
        probe_image=probe_id,
        upstream_host=bridge,
        upstream_port=28181,
        probe_url="https://probe.qa.invalid/",
        probe_timeout_seconds=4,
        **refs,
    )
    policies[policy_id] = policy
    revision = digest(policy)
    definition = {
        "id": app,
        "name": "Network QA " + suffix,
        "logo": "",
        "url": "https://network.invalid",
        "source": "QA",
        "source_app_id": app,
        "provider": "docker",
        "home_directories": True,
        "users": ["network-qa"],
        "groups": [],
        "auto_update": False,
        "app_template": "Default",
        "provider_config": {
            "image": probe_id,
            "port": 3000,
            "nvidia_support": False,
            "dri3_support": False,
            "type": "browser",
            "url_support": True,
            "open_support": False,
            "extensions": [],
            "autostart": False,
            "env": [],
            "network_policy_id": policy_id,
            "network_policy_sha256": revision,
            "docker_overrides": {
                "entrypoint": ["python3", "-c", worker_code],
                "command": [],
                "user": "1000:1000",
                "mem_limit": "64m",
                "nano_cpus": 500000000,
                "shm_size": "64m",
                "pids_limit": 64,
            },
        },
    }
    write(QA / ("app-" + suffix + ".json"), definition)
    definitions.append(
        {
            "id": profile,
            "application_id": app,
            "home_name": home,
            "start_url": "https://probe.qa.invalid/",
            "wayland_mode": False,
            "network_policy_id": policy_id,
            "network_policy_sha256": revision,
        }
    )
write(
    QA / "config/.config/sealskin/profile-network-policies.json",
    {"version": 1, "policies": policies},
)
for suffix in ["a", "b"]:
    result = subprocess.run(
        [
            str(QA / "bin/sealskin-install-app"),
            "--admin-config",
            str(QA / "admin.json"),
            "--api-base-url",
            "http://127.0.0.1:28110",
            "--definition",
            str(QA / ("app-" + suffix + ".json")),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "QA app installation failed: " + result.stderr[:200]
write(
    QA / "adapter-config.json",
    {
        "listen_address": "127.0.0.1:29110",
        "public_base_url": "https://network.invalid",
        "state_file": "adapter-state.json",
        "control_socket": "/tmp/browser-platform-network-qa.sock",
        "sealskin": {
            "api_base_url": "http://127.0.0.1:28110",
            "public_session_base_url": "https://network.invalid",
            "username": "network-qa",
            "server_public_key_file": "server-public.pem",
            "client_private_key_file": "client-private.pem",
            "allow_unencrypted_http": True,
            "lifecycle_enabled": True,
        },
        "profiles": definitions,
    },
)
print(
    json.dumps(
        {
            "qa_ready": True,
            "profiles": [d["id"] for d in definitions],
            "controller": "sealskin-network-qa",
            "mock_upstream": "private Docker-published bridge port",
        }
    )
)
