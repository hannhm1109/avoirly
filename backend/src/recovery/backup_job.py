"""Encrypt complete snapshots before uploading to a separate private backup bucket."""

import argparse
import base64
import json
import os
import re
import tarfile
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .backup import create_backup
from .config import Settings
from .storage import SupabaseStorage

MAGIC = b"AVOIRLY-BACKUP-1\x00"


def encryption_key():
    encoded = os.environ["AVOIRLY_BACKUP_KEY"]
    key = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
    if len(key) != 32:
        raise ValueError("Backup key must encode 32 random bytes")
    return key


def encrypt(source, destination, key):
    nonce = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    cipher.authenticate_additional_data(MAGIC)
    with Path(source).open("rb") as incoming, Path(destination).open("xb") as out:
        out.write(MAGIC + nonce)
        while chunk := incoming.read(65536):
            out.write(cipher.update(chunk))
        out.write(cipher.finalize())
        out.write(cipher.tag)


def decrypt(source, destination, key):
    target = Path(destination)
    if target.exists():
        raise ValueError("Refusing to overwrite a restore archive")
    with Path(source).open("rb") as incoming:
        if incoming.read(len(MAGIC)) != MAGIC:
            raise ValueError("Unknown encrypted backup format")
        nonce = incoming.read(12)
        remaining = Path(source).stat().st_size - len(MAGIC) - 12 - 16
        if remaining < 0:
            raise ValueError("Truncated backup")
        incoming.seek(-16, 2)
        tag = incoming.read(16)
        incoming.seek(len(MAGIC) + 12)
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        cipher.authenticate_additional_data(MAGIC)
        # Never expose a completed plaintext artifact until authentication succeeds.
        with tempfile.TemporaryDirectory(prefix="avoirly-decrypt-", dir=target.parent) as temporary:
            checked = Path(temporary) / "verified.tar"
            with checked.open("wb") as out:
                while remaining:
                    chunk = incoming.read(min(65536, remaining))
                    if not chunk:
                        raise ValueError("Truncated backup")
                    remaining -= len(chunk)
                    out.write(cipher.update(chunk))
                out.write(cipher.finalize())
            with target.open("xb") as out, checked.open("rb") as data:
                while chunk := data.read(65536):
                    out.write(chunk)


def run_backup(settings):
    key = encryption_key()
    bucket = os.environ["AVOIRLY_BACKUP_BUCKET"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", bucket) or bucket == settings.storage_bucket:
        raise ValueError("Use a separate private backup bucket")
    retention = int(os.environ.get("AVOIRLY_BACKUP_RETENTION_DAYS", "14"))
    if not 1 <= retention <= 90:
        raise ValueError("Retention must be 1–90 days")
    storage = SupabaseStorage(settings)
    metadata = storage.request("GET", f"bucket/{bucket}").json()
    if metadata.get("public") is not False:
        raise ValueError("Backup bucket must be private")
    name = f"backup-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex}.bin"
    with tempfile.TemporaryDirectory(prefix="avoirly-backup-") as temp:
        root = Path(temp)
        create_backup(settings, root / "snapshot")
        archive = root / "snapshot.tar"
        with tarfile.open(archive, "w") as tar:
            tar.add(root / "snapshot", arcname="snapshot")
        encrypted = root / "encrypted.bin"
        encrypt(archive, encrypted, key)
        with encrypted.open("rb") as data:
            storage.request(
                "POST",
                f"object/{bucket}/{name}",
                content=iter(lambda: data.read(65536), b""),
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(encrypted.stat().st_size),
                    "x-upsert": "false",
                },
            )
    # Retention runs only after a successful new snapshot upload. Only our own names.
    old = []
    offset = 0
    cutoff = datetime.now(UTC) - timedelta(days=retention)
    while True:
        rows = storage.request(
            "POST",
            f"object/list/{bucket}",
            json={
                "prefix": "",
                "limit": 100,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            },
        ).json()
        for row in rows:
            match = re.fullmatch(r"backup-(\d{8}T\d{6}Z)-[a-f0-9]{32}\.bin", row.get("name", ""))
            if match and datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC) < cutoff:
                old.append(row["name"])
        if len(rows) < 100:
            break
        offset += len(rows)
    for start in range(0, len(old), 100):
        storage.request("DELETE", f"object/{bucket}", json={"prefixes": old[start : start + 100]})
    return {"encrypted_backup_uploaded": True, "expired_backups_removed": len(old)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decrypt")
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        if args.decrypt:
            if not args.out:
                parser.error("--out is required when decrypting")
            decrypt(args.decrypt, args.out, encryption_key())
            print('{"decrypted":true}')
        else:
            print(json.dumps(run_backup(Settings.from_env())))
    except Exception as exc:  # noqa: BLE001 - operator logs must not include SQL/content/secrets
        print(json.dumps({"backup_failed": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
