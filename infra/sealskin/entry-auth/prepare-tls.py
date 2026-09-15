#!/usr/bin/env python3
"""Create a private TLS identity with an exact DNS SAN in a new directory."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def create(directory, name, days=365):
    if (not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", name)
            or any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in name.split("."))
            or not 1 <= days <= 365):
        raise ValueError("PRIVATE_TLS_NAME_OR_LIFETIME_INVALID")
    directory = Path(directory).absolute()
    if directory.parent.resolve() != directory.parent:
        raise ValueError("PRIVATE_TLS_PARENT_UNSAFE")
    directory.mkdir(mode=0o700, exist_ok=False)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
        .add_extension(x509.KeyUsage(True, False, True, False, False, True, True, False, False), True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .sign(key, hashes.SHA256()))
    values = {"cert.pem": certificate.public_bytes(serialization.Encoding.PEM),
              "key.pem": key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption())}
    for filename, raw in values.items():
        descriptor = os.open(directory / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    result = {"name": name, "certificate_sha256": hashlib.sha256(values["cert.pem"]).hexdigest(),
              "not_after": (now + timedelta(days=days)).replace(microsecond=0).isoformat()}
    (directory / "identity.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()
    print(json.dumps(create(args.output, args.name, args.days)))
