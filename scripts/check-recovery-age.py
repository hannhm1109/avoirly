"""Host-side recovery freshness checks; logs contain booleans only."""

import argparse
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path


def check(directory, now=None):
    now = now or datetime.now(UTC)
    name = (directory / "latest").read_text().strip()
    if not re.fullmatch(r"full-\d{8}T\d{6}Z-[a-f0-9]{32}", name):
        raise ValueError("Invalid recovery snapshot name")
    report = json.loads((directory / (name + ".json")).read_text())
    archive = directory / (name + ".bin")
    if (
        not report.get("encrypted")
        or not report.get("authenticated_round_trip")
        or not archive.is_file()
        or archive.stat().st_size != report["bytes"]
    ):
        raise ValueError("Incomplete recovery snapshot")
    created = datetime.fromisoformat(report["created_at"])
    copied = datetime.fromisoformat(
        (directory / "last-offvm-confirmed").read_text().strip().replace("Z", "+00:00")
    )
    return {
        "full_recovery_snapshot_fresh": timedelta(0)
        <= now - created
        < timedelta(hours=30),
        "off_server_copy_fresh": timedelta(0) <= now - copied < timedelta(hours=36),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        state = check(args.directory)
        print(json.dumps(state))
        raise SystemExit(0 if all(state.values()) else 1)
    except Exception as exc:  # noqa: BLE001 - redact private host paths
        print(json.dumps({"recovery_monitor_failed": type(exc).__name__}))
        raise SystemExit(1) from None
