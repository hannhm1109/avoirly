"""Consistent database/object backup and verification in an EMPTY restore database.

Archives contain private content. Store encrypted; never put them in Git.
Only restore trusted operator-created archives. No production restore is automatic.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from .config import Settings
from .storage import check_key, create_storage


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pg_environment(url):
    parsed = make_url(url)
    env = {
        **os.environ,
        "PGHOST": parsed.host or "localhost",
        "PGPORT": str(parsed.port or 5432),
        "PGUSER": parsed.username or "",
        "PGPASSWORD": parsed.password or "",
        "PGDATABASE": parsed.database or "",
    }
    for field in ("sslmode", "sslrootcert", "sslcert", "sslkey", "options"):
        if field in parsed.query:
            env["PG" + field.upper()] = parsed.query[field]
        else:
            env.pop("PG" + field.upper(), None)
    return env


def pg_tool(name):
    directory = os.environ.get("AVOIRLY_PG_BIN")
    return (
        str(Path(directory) / (name + (".exe" if os.name == "nt" else ""))) if directory else name
    )


def run_pg(name, args, url):
    result = subprocess.run(
        [pg_tool(name), *args],
        env=pg_environment(url),
        capture_output=True,
        check=False,
        timeout=600,
    )
    if result.returncode:
        # pg tools can echo identifiers/SQL; never include raw stderr in logs.
        raise RuntimeError(
            f"{name} failed; check operator configuration (exit {result.returncode})."
        )


def create_backup(settings, destination, *, storage=None):
    folder = Path(destination).resolve()
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    objects = folder / "objects"
    objects.mkdir(mode=0o700)
    storage = storage or create_storage(settings)
    storage.check_private()
    engine = create_engine(settings.database_url)
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:  # noqa: SIM117 - explicit snapshot lifetime
            with conn.begin():
                schema = conn.scalar(text("SELECT current_schema()"))
                if not re.fullmatch(r"[a-z][a-z0-9_]*", schema):
                    raise RuntimeError("Unsupported database schema name.")
                snapshot = conn.scalar(text("SELECT pg_export_snapshot()"))
                rows = conn.execute(
                    text(
                        "SELECT storage_key, sha256, size_bytes FROM documents UNION SELECT storage_key, sha256, size_bytes FROM recovery_evidence"
                    )
                ).all()
                manifest = {"format": 1, "schema": schema, "objects": [], "counts": {}}
                for key, sha, size in rows:
                    check_key(key)
                    data = storage.read(key)
                    if digest(data) != sha or len(data) != size:
                        raise RuntimeError(
                            "Source changed or is missing; retry backup. No complete manifest was written."
                        )
                    (objects / key).write_bytes(data)
                    manifest["objects"].append({"key": key, "sha256": sha, "size": size})
                for table in (
                    "cases",
                    "documents",
                    "extractions",
                    "comparisons",
                    "drafts",
                    "jobs",
                    "usage_counters",
                    "recovery_entries",
                    "recovery_evidence",
                ):
                    manifest["counts"][table] = conn.scalar(text(f'SELECT count(*) FROM "{table}"'))
                run_pg(
                    "pg_dump",
                    [
                        "--format=custom",
                        "--no-owner",
                        "--no-acl",
                        f"--schema={schema}",
                        f"--snapshot={snapshot}",
                        f"--file={folder / 'database.dump'}",
                    ],
                    settings.database_url,
                )
        manifest["database_sha256"] = digest((folder / "database.dump").read_bytes())
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    finally:
        engine.dispose()


def verify_restore(archive, target_url, target_storage):
    source = Path(archive).resolve()
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or not re.fullmatch(r"[a-z][a-z0-9_]*", manifest["schema"]):
        raise ValueError("Unsupported backup manifest")
    if digest((source / "database.dump").read_bytes()) != manifest["database_sha256"]:
        raise ValueError("Database archive checksum mismatch")
    for item in manifest["objects"]:
        data = (source / "objects" / check_key(item["key"])).read_bytes()
        if len(data) != item["size"] or digest(data) != item["sha256"]:
            raise ValueError("Object archive checksum mismatch")
    target = Path(target_storage).resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError("Restore storage must be empty")
    engine = create_engine(target_url)
    try:
        with engine.connect() as conn:
            if conn.scalar(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind IN ('r','p','v','m','S') AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'"
                )
            ):
                raise ValueError(
                    "Restore database must be empty; live data will never be overwritten"
                )
        run_pg(
            "pg_restore",
            [
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-acl",
                "--dbname=" + make_url(target_url).database,
                str(source / "database.dump"),
            ],
            target_url,
        )
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        for item in manifest["objects"]:
            (target / item["key"]).write_bytes((source / "objects" / item["key"]).read_bytes())
        with engine.connect() as conn:
            schema = manifest["schema"]
            for table, expected in manifest["counts"].items():
                if table not in (
                    "cases",
                    "documents",
                    "extractions",
                    "comparisons",
                    "drafts",
                    "jobs",
                    "usage_counters",
                    "recovery_entries",
                    "recovery_evidence",
                ):
                    raise ValueError("Unsupported table in manifest")
                actual = conn.scalar(text(f'SELECT count(*) FROM "{schema}"."{table}"'))
                if actual != expected:
                    raise ValueError("Restored database count mismatch")
            sources = f'SELECT storage_key, sha256 FROM "{schema}".documents'
            # Phase 4 archives have no recovery tables and remain verifiable.
            if "recovery_evidence" in manifest["counts"]:
                sources += f' UNION SELECT storage_key, sha256 FROM "{schema}".recovery_evidence'
            rows = conn.execute(text(sources)).all()
            for key, sha in rows:
                if digest((target / check_key(key)).read_bytes()) != sha:
                    raise ValueError("Restored source checksum mismatch")
        return {"verified": True, "objects": len(rows), "counts": manifest["counts"]}
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Private backup and isolated restore verification")
    commands = parser.add_subparsers(dest="action", required=True)
    backup = commands.add_parser("create")
    backup.add_argument("--out", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--archive", required=True)
    verify.add_argument("--storage", required=True)
    args = parser.parse_args()
    if args.action == "create":
        result = create_backup(Settings.from_env(), args.out)
        print(json.dumps({"backup_complete": True, "objects": len(result["objects"])}))
    else:
        print(
            json.dumps(
                verify_restore(
                    args.archive, os.environ["AVOIRLY_RESTORE_DATABASE_URL"], args.storage
                )
            )
        )


if __name__ == "__main__":
    main()
