#!/usr/bin/env python3
"""Build private, standalone R5C2 endpoint bundles from an actual DNS plan.

No remote login, listener, DNS write or application deployment is performed.
The output contains temporary credentials and keys and must remain private.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tarfile

from endpoint import WHEEL, WHEEL_SHA256, atomic_json, load_dependency, require, validate

PORTS = {"http": 18080, "https": 18443, "socks5": 18180, "http_proxy": 18181, "https_proxy": 18182}


def openssl(*args):
    result = subprocess.run(["openssl", *map(str, args)], capture_output=True, timeout=30)
    require(result.returncode == 0, "CERTIFICATE_GENERATION_FAILED")


def certificates(root, names, addresses):
    ca = root / "ca"
    ca.mkdir(mode=0o700)
    openssl("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
            "-keyout", ca / "ca-key.pem", "-out", ca / "ca.pem", "-days", "2",
            "-subj", "/CN=R5C2 disposable QA CA", "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    for role in ("before", "after"):
        node = root / role
        node.mkdir(mode=0o700)
        extensions = ca / (role + ".ext")
        extensions.write_text("basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
                              "extendedKeyUsage=serverAuth\nsubjectAltName=" + ",".join(
                                  ["DNS:" + name for name in names] + ["IP:" + address for address in addresses]) + "\n")
        openssl("req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
                "-keyout", node / "server-key.pem", "-out", ca / (role + ".csr"), "-subj", "/CN=" + names[0])
        openssl("x509", "-req", "-in", ca / (role + ".csr"), "-CA", ca / "ca.pem", "-CAkey", ca / "ca-key.pem",
                "-set_serial", str(int.from_bytes(secrets.token_bytes(16), "big")), "-out", node / "server-cert.pem",
                "-days", "2", "-extfile", extensions)
        shutil.copyfile(ca / "ca.pem", node / "ca.pem")
        (node / "server-key.pem").chmod(0o600)
    (ca / "ca-key.pem").chmod(0o600)


def build(plan_path, dependency_directory, client, output, coherence=False, rotation=False):
    require(not rotation or coherence, "ROTATION_REQUIRES_COHERENCE")
    load_dependency(dependency_directory)
    checker_path = Path(__file__).resolve().parent.parent / "check-public-dns-ttl.py"
    spec = importlib.util.spec_from_file_location("public_dns_plan", checker_path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    plan = json.loads(plan_path.read_text())
    checker.validate_plan(plan)
    require(ipaddress.IPv4Address(client).is_global and str(ipaddress.IPv4Address(client)) == client, "CLIENT_MUST_BE_PUBLIC_IPV4")
    paths = plan["config"]["paths"]
    peers = [paths["direct"][field] for field in ("before_ipv4", "after_ipv4")]
    require(all([path["before_ipv4"], path["after_ipv4"]] == peers for path in paths.values()), "THIS_BUNDLE_REQUIRES_TWO_SHARED_ENDPOINTS")
    require(client not in peers, "DIRECT_TARGET_CANNOT_BE_BROWSER_HOST")
    require(plan_path.parent != output and not output.exists(), "OUTPUT_MUST_BE_NEW")
    run_id = plan["names"]["direct"].split(".", 1)[0].removeprefix("direct-")
    names = {role: value.rstrip(".") for role, value in plan["names"].items()}
    output.mkdir(mode=0o700, parents=True)
    observer = f"observe-{run_id}.{plan['config']['zone'].rstrip('.')}"
    certificates(output, list(names.values()) + ([observer, "*." + observer] if coherence else []), peers)
    credentials = {"username": ("r5c3-" if coherence else "r5c2-") + run_id, "password": secrets.token_urlsafe(32)}
    if rotation:
        credentials["peer_password"] = secrets.token_urlsafe(32)
    entries = {}
    for index, role in enumerate(("before", "after")):
        node = output / role
        config = {"version": 1, "run_id": run_id, "endpoint_id": role, "zone": plan["config"]["zone"].rstrip("."),
                  "public_ipv4": peers[index], "bind_ipv4": peers[index], "client_ipv4": [client], "peer_ipv4": peers,
                  "website_names": [names["direct"], names["upstream"]], "proxy_name": names["bootstrap"],
                  "resolver": {"id": paths["upstream"]["resolver_id"], "ipv4": paths["upstream"]["resolver_ipv4"], "port": 53},
                  "ports": PORTS, "credentials_file": "credentials.json", "certificate_file": "server-cert.pem",
                  "private_key_file": "server-key.pem", "max_connections": 16, "connection_seconds": 120,
                  "lifetime_seconds": 21600, "connection_bytes": 4194304}
        if coherence:
            config["coherence_domain"] = observer
        if rotation:
            config["rotation_enabled"] = True
        validate(config)
        for name, source in [("endpoint.py", Path(__file__).with_name("endpoint.py")),
                             ("environment-test.js", Path(__file__).with_name("environment-test.js")),
                             ("client-fixture.html", Path(__file__).parent.parent / "client-fixture.html"),
                             (WHEEL, dependency_directory / WHEEL)]:
            shutil.copyfile(source, node / name)
        atomic_json(node / "config.json", config)
        atomic_json(node / "credentials.json", credentials)
        (node / "state").mkdir(mode=0o700)
        atomic_json(node / "state" / "mode.json", {"mode": "online"})
        if rotation:
            atomic_json(node / "state" / "rotation.json", {"exit": "local"})
        files = {str(path.relative_to(node)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(node.rglob("*")) if path.is_file()}
        manifest = {"run_id": run_id, "endpoint": role, "files": files,
                    "plan_sha256": checker.digest(plan), "dependency_sha256": WHEEL_SHA256}
        atomic_json(node / "manifest.json", manifest)
        archive = output / (role + ".tar.gz")
        with tarfile.open(archive, "w:gz") as tar:
            for path in sorted(node.rglob("*")):
                tar.add(path, arcname=str(path.relative_to(node)), recursive=False)
        archive.chmod(0o600)
        entries[role] = {"ipv4": peers[index], "archive": archive.name, "archive_bytes": archive.stat().st_size,
                         "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "ports": PORTS}
    atomic_json(output / "bundle.json", {"result": "PREPARED", "run_id": run_id, "nodes": entries,
                                       "remote_deployment": "NOT_RUN", "public_acceptance": "NOT_RUN"})
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--dependency-directory", required=True, type=Path)
    parser.add_argument("--client-ipv4", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--coherence", action="store_true", help="Include a nonce-scoped R5C3 observation origin")
    parser.add_argument("--rotation", action="store_true", help="Allow an authenticated, target-restricted HTTPS bridge between the two peers")
    args = parser.parse_args()
    os.umask(0o077)
    entries = build(args.plan, args.dependency_directory, args.client_ipv4, args.output, args.coherence, args.rotation)
    print(json.dumps({"result": "PREPARED", "nodes": entries, "remote_deployment": "NOT_RUN",
                      "public_acceptance": "NOT_RUN"}))


if __name__ == "__main__":
    main()
