"""Seal a protected full-server snapshot; never emit its contents or secrets."""

import hashlib
import json
import os
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from recovery.backup_job import decrypt, encrypt, encryption_key


def main():
    root = Path("/recovery")
    source = root / "snapshot"
    required = [
        "postgres.data.tar.gz",
        "postgresql-custom.tar.gz",
        "excluded-backup-bucket.txt",
        "runtime/.env",
        "runtime/docker-compose.yml",
        "storage.tar.gz",
        "operations/alerts.env",
    ]
    if any(not (source / name).is_file() for name in required):
        raise ValueError("Incomplete recovery snapshot")
    entries = {}
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Unexpected snapshot symlink")
        if path.is_file():
            entries[str(path.relative_to(source))] = hashlib.file_digest(
                path.open("rb"), "sha256"
            ).hexdigest()
    manifest = {
        "version": 2,
        "created_at": datetime.now(UTC).isoformat(),
        "files": entries,
        "database_format": "clean-shutdown PostgreSQL data directory tar gzip",
        "database_image": os.environ["AVOIRLY_DATABASE_IMAGE"],
        "application_release": os.environ["AVOIRLY_RECOVERY_RELEASE"],
    }
    (source / "manifest.json").write_text(json.dumps(manifest, indent=2))
    archive = root / "snapshot.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(source, arcname="snapshot")
    encrypted = root / "snapshot.bin"
    encrypt(archive, encrypted, encryption_key())
    verified = root / "verified.tar"
    decrypt(encrypted, verified, encryption_key())
    if (
        hashlib.file_digest(archive.open("rb"), "sha256").digest()
        != hashlib.file_digest(verified.open("rb"), "sha256").digest()
    ):
        raise ValueError("Recovery authentication round trip failed")
    report = {
        "created_at": manifest["created_at"],
        "encrypted": True,
        "authenticated_round_trip": True,
        "excludes_nested_application_archives": True,
        "database_image": manifest["database_image"],
        "application_release": manifest["application_release"],
        "snapshot_files": len(entries),
        "bytes": encrypted.stat().st_size,
        "sha256": hashlib.file_digest(encrypted.open("rb"), "sha256").hexdigest(),
    }
    (root / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - raw errors may expose secret paths
        print(json.dumps({"recovery_seal_failed": type(exc).__name__}))
        raise SystemExit(1) from None
