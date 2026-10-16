import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check-recovery-age.py"
SPEC = importlib.util.spec_from_file_location("avoirly_recovery_age", SCRIPT)
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


def snapshot(tmp_path, *, age, copied_age):
    now = datetime(2026, 10, 16, 12, tzinfo=UTC)
    name = "full-20261016T100000Z-" + "a" * 32
    (tmp_path / "latest").write_text(name)
    (tmp_path / (name + ".json")).write_text(json.dumps({"created_at": (now - age).isoformat()}))
    (tmp_path / "last-offvm-confirmed").write_text((now - copied_age).isoformat())
    return monitor.check(tmp_path, now=now)


def test_recovery_freshness_requires_both_snapshot_and_independent_copy(tmp_path):
    assert all(snapshot(tmp_path, age=timedelta(hours=2), copied_age=timedelta(hours=1)).values())
    state = snapshot(tmp_path, age=timedelta(hours=30), copied_age=timedelta(hours=1))
    assert not state["full_recovery_snapshot_fresh"]
    assert state["off_server_copy_fresh"]
    state = snapshot(tmp_path, age=timedelta(hours=1), copied_age=timedelta(hours=36))
    assert state["full_recovery_snapshot_fresh"]
    assert not state["off_server_copy_fresh"]


def test_recovery_monitor_rejects_path_traversal_and_future_ack(tmp_path):
    state = snapshot(tmp_path, age=timedelta(0), copied_age=timedelta(minutes=-1))
    assert not state["off_server_copy_fresh"]
    (tmp_path / "latest").write_text("../outside")
    with pytest.raises(ValueError, match="Invalid recovery snapshot name"):
        monitor.check(tmp_path)
