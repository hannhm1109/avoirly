"""Regression checks for revision/closure races and recoverable deletion."""

from unittest.mock import Mock

import pytest
import test_backend
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_backend import analyze, detail, ready, worker

from recovery.api.app import create_app
from recovery.db.models import Draft, Job
from recovery.service import cleanup_deleted

pytestmark = pytest.mark.postgres
postgres = test_backend.postgres
env = test_backend.env


@pytest.mark.parametrize("action", ["review", "close"])
def test_changes_during_drafting_cancel_the_old_worker(env, pair_dict, monkeypatch, action):
    client, settings, sessions = env
    case = ready(client)
    analyze(client, case)
    runner, _ = worker(settings, sessions, pair_dict)
    import recovery.worker as module

    original = module.generate_claim

    def concurrent_change(*args):
        current = detail(client, case)
        assert current["status"] == "DISCREPANCY_FOUND"
        if action == "review":
            response = client.put(
                f"/api/v1/cases/{case['id']}/review",
                json={
                    "expected_version": current["version"],
                    "corrected": pair_dict,
                    "reason": "Rechecked source during drafting",
                },
            )
        else:
            response = client.post(
                f"/api/v1/cases/{case['id']}/close",
                json={"expected_version": current["version"], "close_reason": "DISMISSED"},
            )
        assert response.status_code == 200, response.text
        return original(*args)

    monkeypatch.setattr(module, "generate_claim", concurrent_change)
    runner.run_once()
    current = detail(client, case)
    assert current["status"] == ("PENDING" if action == "review" else "CLOSED")
    assert current["draft"] is None
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Draft)) == 0
        assert session.scalar(select(Job)).status == "FAILED"


def test_non_loopback_client_is_refused(env):
    _, settings, sessions = env
    with TestClient(
        create_app(settings, sessions), base_url="http://127.0.0.1", client=("203.0.113.10", 49000)
    ) as client:
        assert client.post("/api/v1/cases").status_code == 403


def test_deletion_outbox_recovers_storage_failure(env, monkeypatch):
    client, settings, sessions = env
    case = ready(client)
    original_delete = client.app.state.storage.delete
    monkeypatch.setattr(
        client.app.state.storage, "delete", Mock(side_effect=OSError("temporary storage error"))
    )
    response = client.request(
        "DELETE",
        f"/api/v1/cases/{case['id']}",
        json={"expected_version": case["version"], "confirmed": True},
    )
    assert response.status_code == 202
    assert client.get(f"/api/v1/cases/{case['id']}").status_code == 404
    assert len(list(settings.storage_root.iterdir())) == 2
    monkeypatch.setattr(client.app.state.storage, "delete", original_delete)
    cleanup_deleted(sessions, client.app.state.storage)
    assert list(settings.storage_root.iterdir()) == []


def test_unexpected_error_does_not_leak_document_text(env, caplog):
    client, _, _ = env

    @client.app.get("/api/v1/simulated-failure")
    def failing_route():
        raise RuntimeError("private-document-text")

    response = client.get("/api/v1/simulated-failure")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "private-document-text" not in response.text
    assert "private-document-text" not in caplog.text
