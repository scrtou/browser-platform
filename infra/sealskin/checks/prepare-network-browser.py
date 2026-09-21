#!/usr/bin/env python3
"""Create a QA-only browser Home and private network observation endpoints.

Requires the scoped generation QA controller and unpacked Debian NSS tools in
ROOT.parent/nss-tools/extracted. No production app or Home is changed.
"""

import argparse
import base64
import hashlib
import importlib.util
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--engine", choices=("firefox", "camoufox"), default="firefox")
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--clipboard-addon", type=Path)
    parser.add_argument("--firefox-source-app", default="firefox-personal",
                        help="installed production Firefox app to copy read-only into QA")
    parser.add_argument("--firefox-managed-image",
                        help="exact managed-network Work image ID for isolated QA")
    parser.add_argument("--wayland", action="store_true",
                        help="launch the Firefox QA worker in Wayland mode")
    args = parser.parse_args()
    if args.engine == "camoufox" and not (args.artifact and args.acceptance):
        parser.error("Camoufox requires its frozen artifact and complete acceptance report")
    if args.engine != "firefox" and (args.wayland or args.firefox_source_app != "firefox-personal" or args.firefox_managed_image):
        parser.error("Firefox source app and Wayland mode only apply to --engine firefox")
    if args.firefox_managed_image and not re.fullmatch(r"sha256:[0-9a-f]{64}", args.firefox_managed_image):
        parser.error("Firefox managed image must be an exact sha256 image ID")
    qa = args.root.resolve()
    project = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "network_checks", project / "infra/sealskin/lifecycle/check-network-live.py"
    )
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    runtime = checks.Checks(qa)
    assert qa.name == "qa" and not (qa.parent / "observer").exists()
    observer = qa.parent / "observer"
    observer.mkdir(mode=0o700)
    network = json.loads(
        checks.docker("network", "inspect", "browser-platform-network-qa").stdout
    )[0]
    subnet = ipaddress.ip_network(network["IPAM"]["Config"][0]["Subnet"])
    observer_ip = str(subnet[20])
    assert all(
        value.get("IPv4Address", "").split("/")[0] != observer_ip
        for value in network.get("Containers", {}).values()
    )
    images = json.loads((qa / "images.json").read_text())
    now = datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Private Browser Network QA CA")]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(True, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "*.leak.qa.test")])
        )
        .issuer_name(name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("*.leak.qa.test"),
                    x509.IPAddress(ipaddress.ip_address(observer_ip)),
                    x509.IPAddress(ipaddress.ip_address("::1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(True, False, True, False, False, False, False, False, False),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    for filename, value in {
        "ca.pem": ca.public_bytes(serialization.Encoding.PEM),
        "server.pem": leaf.public_bytes(serialization.Encoding.PEM),
        "server-key.pem": leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    }.items():
        path = observer / filename
        path.write_bytes(value)
        path.chmod(0o600)
    # TLS fault certificates apply only to the QA upstream proxy listener.
    # The website certificate and the frozen browser trust database stay fixed.
    for fault, dns_name, issuer, signing_key in (
        ("wrong-name", "*.other.qa.test", ca.subject, key),
        ("untrusted", "*.leak.qa.test", leaf.subject, leaf_key),
    ):
        certificate = (x509.CertificateBuilder().subject_name(leaf.subject).issuer_name(issuer)
                       .public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=2))
                       .add_extension(x509.SubjectAlternativeName([x509.DNSName(dns_name)]), critical=False)
                       .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                       .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                       .sign(signing_key, hashes.SHA256()))
        path = observer / ("server-" + fault + ".pem")
        path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        path.chmod(0o600)
    checks.write_json(observer / "mode.json", {})
    shutil.copyfile(
        Path(__file__).with_name("network-fixture.html"),
        observer / "network-fixture.html",
    )
    checks.docker(
        "run",
        "-d",
        "--name",
        "network-qa-observer",
        "--label",
        "io.browser-platform.qa=network-20260913",
        "--network",
        "browser-platform-network-qa",
        "--ip",
        observer_ip,
        "--user",
        "1000:1000",
        "--cap-drop",
        "ALL",
        "--read-only",
        "--security-opt",
        "no-new-privileges:true",
        "--memory",
        "128m",
        "--cpus",
        ".5",
        "--pids-limit",
        "128",
        "--sysctl",
        "net.ipv4.ip_unprivileged_port_start=0",
        "-p",
        images["upstream_host"] + ":28191:28191",
        "-p",
        images["upstream_host"] + ":28192:28192",
        "-p",
        images["upstream_host"] + ":28193:28193",
        "-v",
        str(observer) + ":/qa-observer",
        "-v",
        str(Path(__file__).with_name("network-observer.py"))
        + ":/run/network-observer.py:ro",
        "--entrypoint",
        "python3",
        images["probe"],
        "/run/network-observer.py",
        "--root",
        "/qa-observer",
        "--ipv4",
        observer_ip,
    )
    checks.wait(
        lambda: "private network observer ready"
        in checks.docker("logs", "network-qa-observer").stdout,
        "private observation endpoints",
    )
    app_id, home, profile = (
        "camoufox-network-qa-r4" if args.engine == "camoufox" else "network-qa-firefox-network",
        "network-qa-home-browser",
        "network-qa-browser",
    )
    if args.engine == "firefox":
        # Read only the installed Firefox definition; never edit production.
        admin = json.loads((project / "infra/sealskin/config/admin.json").read_text())
        production = checks.SecureClient(qa, username=admin["username"],
            private=admin["private_key"].encode(), public=admin["server_public_key"].encode(), port=8000)
        status, apps = production.call("GET", "/api/admin/apps/installed")
        assert status == 200
        app = next(value for value in apps if value["id"] == args.firefox_source_app)
        app.update(id=app_id, name="Private Browser Network QA", users=["network-qa"], groups=[], auto_update=False)
        provider = app["provider_config"]
        source_image = checks.docker(
            "image", "inspect", provider["image"], "--format", "{{.Id}}"
        ).stdout.strip()
        provider["image"] = source_image
        if args.firefox_managed_image:
            source_details = json.loads(checks.docker("image", "inspect", source_image).stdout)[0]
            managed = json.loads(
                checks.docker("image", "inspect", args.firefox_managed_image).stdout
            )[0]
            labels = managed.get("Config", {}).get("Labels") or {}
            if (
                managed["Id"] != args.firefox_managed_image
                or labels.get("io.browser-platform.managed-firefox-network") != "1"
                or labels.get("io.browser-platform.managed-firefox-network-base") != source_image
                or managed["RootFS"]["Layers"][: len(source_details["RootFS"]["Layers"])]
                != source_details["RootFS"]["Layers"]
            ):
                raise RuntimeError("managed Firefox image is not based on the selected production app")
            provider["image"] = managed["Id"]
        script = "#!/bin/sh\nexec firefox --no-remote --profile /config/network-qa-profile --remote-debugging-port 9228 --new-window about:blank\n"
        provider["custom_autostart_script_b64"] = base64.b64encode(script.encode()).decode()
        provider["custom_autostart_wayland_script_b64"] = provider["custom_autostart_script_b64"]
        provider["docker_overrides"].update(mem_limit="1024m", nano_cpus=1500000000, shm_size="256m", pids_limit=512)
    status, _ = runtime.client.call("POST", "/api/homedirs", {"home_name": home})
    assert status == 201
    browser_profile = qa / "storage/network-qa" / home / (".camoufox/profile" if args.engine == "camoufox" else "network-qa-profile")
    browser_profile.mkdir(mode=0o700, parents=True)
    nss = qa.parent / "nss-tools/extracted/usr"
    command = [
        "/lib64/ld-linux-x86-64.so.2",
        "--library-path",
        str(nss / "lib/x86_64-linux-gnu"),
        str(nss / "bin/certutil"),
    ]
    for extra in (
        ["-N", "--empty-password", "-d", "sql:" + str(browser_profile)],
        [
            "-A",
            "-d",
            "sql:" + str(browser_profile),
            "-n",
            "Private Network QA CA",
            "-t",
            "C,,",
            "-i",
            str(observer / "ca.pem"),
        ],
    ):
        result = subprocess.run(command + extra, capture_output=True, text=True)
        assert result.returncode == 0, "NSS QA trust database preparation failed"
    references = {}
    for kind, value in {
        "username": b"network-observer-user",
        "password": b"network-observer-password",
        "probe_ca": (observer / "ca.pem").read_bytes(),
    }.items():
        path = qa / "config/.config/sealskin/network-secrets" / ("browser-" + kind)
        path.write_bytes(value)
        path.chmod(0o600)
        references[kind + "_file"] = (
            "/config/.config/sealskin/network-secrets/" + path.name
        )
        references[kind + "_sha256"] = hashlib.sha256(value).hexdigest()
    policy = dict(
        username="network-qa",
        profile_id=profile,
        home_name=home,
        application_id=app_id,
        relay_image=images["relay"],
        probe_image=images["probe"],
        upstream_host=images["upstream_host"],
        upstream_port=28191,
        probe_url="https://preflight.leak.qa.test/",
        probe_timeout_seconds=5,
        **references,
    )
    policy_id = "network-browser-observer-r1"
    revision = hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    registry_path = qa / "config/.config/sealskin/profile-network-policies.json"
    registry = json.loads(registry_path.read_text())
    registry["policies"][policy_id] = policy
    checks.write_json(registry_path, registry)
    if args.engine == "camoufox":
        definition = qa / "camoufox-app.json"
        command = [sys.executable, str(project / "infra/camoufox/prepare-sealskin.py"),
                   "--artifact", str(args.artifact.resolve()), "--acceptance", str(args.acceptance.resolve()),
                   "--app-id", app_id, "--username", "network-qa", "--store", "QA",
                   "--session-origin", "https://network.invalid", "--network-policy-id", policy_id,
                   "--network-policy-sha256", revision, "--output", str(definition)]
        if args.clipboard_addon:
            command += ["--clipboard-addon", str(args.clipboard_addon.resolve())]
        prepared = subprocess.run(command, capture_output=True, text=True, timeout=90)
        assert prepared.returncode == 0, "Camoufox definition rejected: " + prepared.stderr[:200]
        app = json.loads(definition.read_text())
        provider = app["provider_config"]
    else:
        provider.update(network_policy_id=policy_id, network_policy_sha256=revision)
    allowed = json.loads((qa / "allow.json").read_text())
    allowed["images"].append(provider["image"])
    allowed["readonly_sources"] = [
        mount["Source"] for mount in provider["docker_overrides"].get("mounts", [])
    ]
    checks.write_json(qa / "allow.json", allowed)
    qa_admin = json.loads((qa / "admin.json").read_text())
    client = checks.SecureClient(
        qa,
        username=qa_admin["username"],
        private=qa_admin["private_key"].encode(),
        public=qa_admin["server_public_key"].encode(),
    )
    status, _ = client.call("POST", "/api/admin/apps/installed", app)
    assert status == 201
    request = dict(
        url="https://entry.leak.qa.test/test",
        application_id=app_id,
        home_name=home,
        profile_id=profile,
        operation_id=os.urandom(16).hex(),
        network_policy_id=policy_id,
        network_policy_sha256=revision,
        # SealSkin's language parameter becomes the POSIX LC_ALL value. The
        # browser's BCP 47 locale remains bound independently by the artifact.
        language="zh_TW.UTF-8",
        timezone="Asia/Taipei",
        wayland_mode=args.wayland,
        launch_in_room_mode=False,
    )
    stop = {
        key: request[key]
        for key in (
            "application_id",
            "profile_id",
            "operation_id",
            "network_policy_id",
            "network_policy_sha256",
        )
    }
    stop["bootstrap_url"] = request["url"]
    checks.write_json(qa / "browser-stop.json", stop)
    checks.write_json(qa / "browser-launch.json", request)
    status, value = runtime.client.call("POST", "/api/launch/url", request)
    assert status == 200, "Private QA Firefox launch failed"
    stop["session_id"] = value["session_id"]
    checks.write_json(qa / "browser-stop.json", stop)
    status, snapshot = runtime.client.call("GET", "/api/profile-runtime/" + home)
    assert status == 200 and len(snapshot["workers"]) == 1
    worker = snapshot["workers"][0]["instance_id"]
    checks.write_json(
        qa / "browser-worker.json",
        {
            "instance_id": worker,
            "home": home,
            "profile": profile,
            "observer_ip": observer_ip,
            "engine": args.engine,
            "source_app": args.firefox_source_app if args.engine == "firefox" else "",
            "managed_image": provider["image"] if args.firefox_managed_image else "",
            "wayland": args.wayland,
        },
    )
    check = ('import socket; s=socket.create_connection(("127.0.0.1",9228),timeout=1);s.close()'
             if args.engine == "firefox" else
             'import subprocess; out=subprocess.check_output(["xdotool","getactivewindow","getwindowname"],env={"DISPLAY":":1"});assert b"Private browser network check" in out')
    checks.wait(
        lambda: checks.docker(
            "exec", "--user", "1000", worker, "python3", "-c", check, check=False
        ).returncode
        == 0,
        "QA browser ready",
    )
    print(
        json.dumps(
            {
                "private_observer": "ready",
                "engine": args.engine,
                "source_app": args.firefox_source_app if args.engine == "firefox" else "",
                "wayland": args.wayland,
                "browser": "ready",
                "strict_test_CA_installed": True,
                "production_mutations": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
