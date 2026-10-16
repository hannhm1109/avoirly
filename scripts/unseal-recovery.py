"""Authenticate a trusted operator snapshot and prepare isolated recovery files."""

import argparse
import hashlib
import ipaddress
import json
import re
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from recovery.backup_job import decrypt, encryption_key


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def unpack():
    root = Path("/verify")
    decrypt("/input.bin", root / "verified.tar", encryption_key())
    with tarfile.open(root / "verified.tar") as archive:
        archive.extractall(root, filter="data")
    source = root / "snapshot"
    manifest = json.loads((source / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        target = (source / name).resolve()
        if not target.is_relative_to(source.resolve()) or digest(target) != expected:
            raise ValueError("Snapshot checksum mismatch")
    for name, destination in [
        ("postgres.data.tar.gz", "database"),
        ("storage.tar.gz", "storage"),
        ("postgresql-custom.tar.gz", "postgresql-custom"),
    ]:
        target = root / destination
        target.mkdir(mode=0o700)
        with tarfile.open(source / name) as archive:
            archive.extractall(target, filter="data")
    # A temporary CA prevents recovery traffic from reaching public services.
    hosts = []
    for line in (source / "runtime/.env").read_text().splitlines():
        if re.match(r"^AVOIRLY_(WEB|API|AUTH)_HOST=", line):
            host = line.split("=", 1)[1].strip().strip("\"'")
            if not re.fullmatch(r"[a-z0-9.-]+", host):
                raise ValueError("Invalid recovery hostname")
            hosts.append(host)
    if len(hosts) != 3:
        raise ValueError("Missing recovery origins")
    tls = root / "tls"
    tls.mkdir(mode=0o700)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Avoirly isolated recovery")]
    )
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(x) for x in hosts]
                + [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    (tls / "cert.pem").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    (tls / "key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    (tls / "key.pem").chmod(0o600)
    print(
        json.dumps(
            {"snapshot_authenticated": True, "files_verified": len(manifest["files"])}
        )
    )


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    try:
        unpack()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"unseal_failed": type(exc).__name__}))
        raise SystemExit(1) from None
