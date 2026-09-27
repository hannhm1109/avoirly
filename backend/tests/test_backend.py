"""Real PostgreSQL acceptance tests, isolated in a fresh disposable schema."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from recovery.api.app import create_app, get_owner
from recovery.api.errors import DomainError
from recovery.config import Settings
from recovery.db.models import Base, Comparison, Document, Draft, Job
from recovery.extraction import ProcessingError
from recovery.models import Invoice, PurchaseOrder
from recovery.worker import Worker, acquire_job, guarded, heartbeat, requeue_expired

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def postgres():
    url = os.environ.get("AVOIRLY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set AVOIRLY_TEST_DATABASE_URL for real PostgreSQL acceptance tests")
    admin = create_engine(url)
    schema = "avoirly_test_" + uuid4().hex
    with admin.begin() as session:
        session.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_url = make_url(url).update_query_dict({"options": "-csearch_path=" + schema})
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", test_url.render_as_string(hide_password=False).replace("%", "%%")
    )
    command.upgrade(config, "head")
    engine = create_engine(test_url, pool_pre_ping=True)
    yield engine, sessionmaker(engine, expire_on_commit=False), config
    engine.dispose()
    with admin.begin() as session:
        session.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


@pytest.fixture
def env(postgres, tmp_path):
    engine, sessions, _config = postgres
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    settings = Settings(
        engine.url.render_as_string(hide_password=False),
        tmp_path / "private",
        uuid4(),
        model="mock-vision",
        lease_seconds=12,
    )
    app = create_app(settings, sessions)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 49100)) as client:
        yield client, settings, sessions


def create(client):
    response = client.post("/api/v1/cases")
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, case, role, *, data=None, filename=None):
    path = ROOT / "samples" / ("po.pdf" if role == "PO" else "invoice.png")
    response = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        data={"role": role, "expected_version": case["version"]},
        files={"file": (filename or path.name, data or path.read_bytes())},
    )
    assert response.status_code == 201, response.text
    return response.json()


def ready(client):
    case = upload(client, create(client), "PO")
    return upload(client, case, "INVOICE")


def analyze(client, case, key="request-1", route="analyze"):
    response = client.post(
        f"/api/v1/cases/{case['id']}/{route}",
        json={"expected_version": case["version"], "language": "fr"},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    return response.json()


def detail(client, case):
    response = client.get(f"/api/v1/cases/{case['id']}")
    assert response.status_code == 200, response.text
    return response.json()


class FakeExtractor:
    def __init__(self, raw, fail_role=None):
        self.raw, self.fail_role = raw, fail_role
        self.calls, self.metadata = [], []

    def extract(self, file, role):
        self.calls.append(role)
        if role == self.fail_role:
            raise ProcessingError("NETWORK_ERROR", "Simulated interruption")
        schema, name = (PurchaseOrder, "purchase_order") if role == "PO" else (Invoice, "invoice")
        self.metadata.append(
            {"request_id": "mock-request", "duration_ms": 1, "token_usage": {"total_tokens": 10}}
        )
        return schema.model_validate(self.raw[name])


def worker(settings, sessions, pair_dict, **kwargs):
    adapter = FakeExtractor(pair_dict, **kwargs)
    return Worker(settings, sessions, extractor_factory=lambda model: adapter), adapter


def test_migration_and_health(env, postgres):
    client, _, _ = env
    assert client.get("/api/v1/health").json()["status"] == "ok"
    command.check(postgres[2])


def test_audited_manual_inputs_without_provider_configuration(env, pair_dict):
    client, settings, sessions = env
    case = ready(client)
    app = create_app(replace(settings, model=""), sessions)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 49100)) as manual:
        missing = manual.post(
            f"/api/v1/cases/{case['id']}/analyze",
            json={"expected_version": case["version"]},
            headers={"Idempotency-Key": "missing-model"},
        )
        assert missing.status_code == 422
        assert missing.json()["code"] == "MISSING_MODEL"
        revised = manual.put(
            f"/api/v1/cases/{case['id']}/review",
            json={
                "expected_version": case["version"],
                "corrected": pair_dict,
                "reason": "Manually verified both synthetic documents",
            },
        ).json()
        analyze(manual, revised)
        factory = Mock(side_effect=AssertionError("Manual inputs must not call a provider"))
        runner = Worker(replace(settings, model=""), sessions, extractor_factory=factory)
        assert runner.run_once()
        final = detail(manual, case)
        assert final["status"] == "CLAIM_DRAFTED"
        assert final["potential_credit_net"] == "200.00"
        factory.assert_not_called()
        listing = manual.get("/api/v1/cases").json()
        assert listing["items"][0]["supplier_name"] == "Atlas Supplies"
        assert listing["items"][0]["invoice_number"] == "INV-8821"
        assert listing["potential_credit_by_currency"] == {"MAD": "200.00"}


def test_list_totals_are_exact_currency_scoped_and_exclude_review(env):
    from decimal import Decimal

    from recovery.db.models import Case

    client, settings, sessions = env
    with sessions.begin() as session:
        for currency, amount, status in [
            ("MAD", "9000000000.01", "CLAIM_DRAFTED"),
            ("MAD", "0.02", "DISCREPANCY_FOUND"),
            ("EUR", "30.40", "CLAIM_DRAFTED"),
            ("MAD", "100.00", "NEEDS_REVIEW"),
            ("MAD", "100.00", "CLOSED"),
        ]:
            session.add(
                Case(
                    owner_id=settings.local_owner,
                    status=status,
                    currency=currency,
                    potential_credit_net=Decimal(amount),
                )
            )
    totals = client.get("/api/v1/cases").json()["potential_credit_by_currency"]
    assert totals == {"MAD": "9000000000.03", "EUR": "30.40"}


def test_configured_web_origin_still_rejects_remote_origins(env):
    _, settings, sessions = env
    app = create_app(replace(settings, web_origin="http://127.0.0.1:3001"), sessions)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 49100)) as client:
        assert (
            client.get("/api/v1/cases", headers={"Origin": "http://127.0.0.1:3001"}).status_code
            == 200
        )
        assert (
            client.get("/api/v1/cases", headers={"Origin": "https://example.com"}).status_code
            == 403
        )
    with pytest.raises(RuntimeError):
        replace(settings, web_origin="https://example.com").validate()


def test_end_to_end_private_files_decimal_report_and_audit(env, pair_dict):
    client, settings, sessions = env
    case = ready(client)
    queued = analyze(client, case)
    runner, adapter = worker(settings, sessions, pair_dict)
    assert runner.run_once()
    final = detail(client, case)
    assert final["status"] == "CLAIM_DRAFTED", final
    assert final["potential_credit_net"] == "200.00"
    assert "200.00 MAD" in final["draft"]["body"]
    assert adapter.calls == ["PO", "INVOICE"]
    doc = final["documents"]["PO"]["id"]
    assert client.get(f"/api/v1/documents/{doc}/content").content.startswith(b"%PDF-")
    assert client.get("/private/anything").status_code == 404
    events = client.get(f"/api/v1/cases/{case['id']}/events").json()["items"]
    assert [e["new_status"] for e in events][-3:] == [
        "PROCESSING",
        "DISCREPANCY_FOUND",
        "CLAIM_DRAFTED",
    ]
    with sessions() as session:
        assert session.get(Job, UUID(queued["job_id"])).status == "SUCCEEDED"
        comparison = session.scalar(select(Comparison))
        assert set(comparison.extraction_ids) == {"PO", "INVOICE"}


def test_idempotency_persists_across_app_restart(env):
    client, settings, sessions = env
    case = ready(client)
    first = analyze(client, case)
    app2 = create_app(settings, sessions)
    with TestClient(app2, base_url="http://127.0.0.1", client=("127.0.0.1", 49000)) as other:
        assert analyze(other, case) == first
        response = other.post(
            f"/api/v1/cases/{case['id']}/analyze",
            json={"expected_version": case["version"], "language": "en"},
            headers={"Idempotency-Key": "request-1"},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "IDEMPOTENCY_CONFLICT"
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_concurrent_analyze_creates_one_job(env):
    client, _, sessions = env
    case = ready(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: analyze(client, case), range(2)))
    assert results[0] == results[1]
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_two_workers_claim_once(env):
    client, _, sessions = env
    analyze(client, ready(client))
    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(lambda _: acquire_job(sessions, 12), range(2)))
    assert sum(lease is not None for lease in leases) == 1


def test_partial_extraction_retry_reuses_only_successful_snapshot(env, pair_dict):
    client, settings, sessions = env
    case = ready(client)
    analyze(client, case)
    first, _ = worker(settings, sessions, pair_dict, fail_role="INVOICE")
    first.run_once()
    failed = detail(client, case)
    assert failed["status"] == "FAILED"
    assert set(failed["extractions"]) == {"PO"}
    analyze(client, failed, key="retry-1", route="retry")
    second, adapter = worker(settings, sessions, pair_dict)
    second.run_once()
    assert detail(client, case)["status"] == "CLAIM_DRAFTED"
    assert adapter.calls == ["INVOICE"]


def test_expired_lease_cannot_commit_and_is_explicitly_requeued(env, pair_dict):
    client, settings, sessions = env
    case = ready(client)
    analyze(client, case)
    lease = acquire_job(sessions, 12)
    with sessions.begin() as session:
        session.execute(
            update(Job)
            .where(Job.id == lease.job_id)
            .values(leased_until=func.clock_timestamp() - text("interval '1 second'"))
        )
    with pytest.raises(DomainError, match="Worker no longer"), guarded(sessions, lease):
        pytest.fail("Stale worker can commit")
    assert requeue_expired(sessions, 12) == 1
    assert requeue_expired(sessions, 12) == 0
    runner, _ = worker(settings, sessions, pair_dict)
    runner.run_once()
    assert detail(client, case)["status"] == "CLAIM_DRAFTED"
    with sessions() as session:
        jobs = list(session.scalars(select(Job).order_by(Job.attempt)))
        assert [j.status for j in jobs] == ["FAILED", "SUCCEEDED"]
        assert [j.attempt for j in jobs] == [1, 2]


def test_heartbeat_extends_lease(env):
    client, _, sessions = env
    analyze(client, ready(client))
    lease = acquire_job(sessions, 12)
    with sessions() as session:
        before = session.get(Job, lease.job_id).leased_until
    heartbeat(sessions, lease, 30)
    with sessions() as session:
        assert session.get(Job, lease.job_id).leased_until > before


def test_draft_failure_resumes_saved_comparison(env, pair_dict, monkeypatch):
    client, settings, sessions = env
    case = ready(client)
    analyze(client, case)
    runner, _ = worker(settings, sessions, pair_dict)
    import recovery.worker as module

    original = module.generate_claim
    monkeypatch.setattr(
        module, "generate_claim", Mock(side_effect=RuntimeError("draft interrupted"))
    )
    runner.run_once()
    failed = detail(client, case)
    assert failed["status"] == "FAILED"
    assert failed["comparison"]["potential_credit_net"] == "200.00"
    monkeypatch.setattr(module, "generate_claim", original)
    analyze(client, failed, key="retry-draft", route="retry")
    second, adapter = worker(settings, sessions, pair_dict)
    second.run_once()
    assert adapter.calls == []
    assert detail(client, case)["status"] == "CLAIM_DRAFTED"
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Comparison)) == 1
        assert session.scalar(select(func.count()).select_from(Draft)) == 1


def test_corrections_preserve_originals_invalidate_drafts_and_rerun_rules(env, pair_dict):
    client, settings, sessions = env
    case = ready(client)
    analyze(client, case)
    runner, _ = worker(settings, sessions, pair_dict)
    runner.run_once()
    current = detail(client, case)
    pair_dict["invoice"]["prices_include_tax"] = True
    response = client.put(
        f"/api/v1/cases/{case['id']}/review",
        json={
            "expected_version": current["version"],
            "corrected": pair_dict,
            "reason": "Printed prices include tax",
        },
    )
    assert response.status_code == 200, response.text
    revised = detail(client, case)
    assert (
        revised["status"] == "PENDING"
        and revised["draft"] is None
        and revised["comparison"] is None
    )
    assert revised["extractions"]["INVOICE"]["raw"]["prices_include_tax"] is False
    assert revised["extractions"]["INVOICE"]["corrected"]["prices_include_tax"] is True
    analyze(client, revised, key="corrected-1")
    runner.run_once()
    reviewed = detail(client, case)
    assert reviewed["status"] == "NEEDS_REVIEW" and reviewed["draft"] is None
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Draft)) == 1
        assert session.scalar(select(func.count()).select_from(Comparison)) == 2


def test_draft_edits_versioned_stale_update_conflicts(env, pair_dict):
    client, settings, sessions = env
    case = ready(client)
    analyze(client, case)
    runner, _ = worker(settings, sessions, pair_dict)
    runner.run_once()
    final = detail(client, case)
    body = {
        "expected_version": final["version"],
        "subject": "Please verify",
        "body": "Edited by owner",
    }
    response = client.patch(f"/api/v1/cases/{case['id']}/draft", json=body)
    assert response.status_code == 200
    assert client.patch(f"/api/v1/cases/{case['id']}/draft", json=body).status_code == 409
    assert detail(client, case)["draft"]["version"] == 2
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Draft)) == 2


def test_foreign_owner_cannot_read_write_or_download(env):
    client, _, _ = env
    case = ready(client)
    doc_id = case["document_id"]
    client.app.dependency_overrides[get_owner] = lambda: uuid4()
    try:
        assert client.get(f"/api/v1/cases/{case['id']}").status_code == 404
        assert client.get(f"/api/v1/documents/{doc_id}/content").status_code == 404
        assert client.get("/api/v1/cases").json()["items"] == []
        response = client.post(
            f"/api/v1/cases/{case['id']}/analyze",
            json={"expected_version": case["version"]},
            headers={"Idempotency-Key": "foreign"},
        )
        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_client_owner_header_ignored_and_hosted_startup_refused(env):
    client, settings, _ = env
    case = create(client)
    assert (
        client.get(f"/api/v1/cases/{case['id']}", headers={"X-Owner-ID": str(uuid4())}).status_code
        == 200
    )
    with pytest.raises(RuntimeError, match="local mode only"):
        create_app(replace(settings, mode="production"))
    assert (
        client.post("/api/v1/cases", headers={"Origin": "https://attacker.example"}).status_code
        == 403
    )


def test_delete_cancels_worker_purges_content_and_sources(env):
    client, settings, sessions = env
    case = ready(client)
    analyze(client, case)
    lease = acquire_job(sessions, 12)
    current = detail(client, case)
    response = client.request(
        "DELETE",
        f"/api/v1/cases/{case['id']}",
        json={"expected_version": current["version"], "confirmed": True},
    )
    assert response.status_code == 202, response.text
    assert client.get(f"/api/v1/cases/{case['id']}").status_code == 404
    assert list(settings.storage_root.iterdir()) == []
    with pytest.raises(DomainError), guarded(sessions, lease):
        pytest.fail("Deleted case was writable")
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 0
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_duplicate_upload_surfaces_existing_case(env):
    client, _, _ = env
    first = ready(client)
    second = create(client)
    response = client.post(
        f"/api/v1/cases/{second['id']}/documents",
        data={"role": "PO", "expected_version": second["version"]},
        files={"file": ("po.pdf", (ROOT / "samples/po.pdf").read_bytes())},
    )
    assert response.status_code == 409
    assert response.json()["details"]["existing_case_id"] == first["id"]


@pytest.mark.parametrize(
    "first_needs_review,renamed", [(False, False), (True, False), (False, True)]
)
def test_duplicate_invoice_identity_blocks_different_files(
    env, pair_dict, first_needs_review, renamed
):
    client, settings, sessions = env
    first = ready(client)
    analyze(client, first)
    if first_needs_review:
        pair_dict["invoice"]["prices_include_tax"] = None
    runner, _ = worker(settings, sessions, pair_dict)
    runner.run_once()
    pair_dict["invoice"]["prices_include_tax"] = False
    if renamed:
        pair_dict["invoice"]["supplier"]["name"] = "Atlas Supplies New Name"
        pair_dict["purchase_order"]["supplier"]["name"] = "Atlas Supplies New Name"
    second = create(client)
    for role, color in (("PO", "red"), ("INVOICE", "blue")):
        image = BytesIO()
        Image.new("RGB", (20, 20), color).save(image, format="PNG")
        second = upload(client, second, role, data=image.getvalue(), filename="other.png")
    analyze(client, second, key="second")
    runner.run_once()
    final = detail(client, second)
    assert final["status"] == "NEEDS_REVIEW"
    assert final["review_issues"][0]["code"] == "DUPLICATE_INVOICE"
    assert final["draft"] is None and final["potential_credit_net"] is None


def test_invalid_upload_and_structured_errors(env):
    client, _, _ = env
    case = create(client)
    response = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        data={"role": "PO", "expected_version": case["version"]},
        files={"file": ("fake.pdf", b"not a PDF")},
    )
    assert response.status_code == 415
    assert set(response.json()) == {"code", "message", "details", "request_id"}
    assert (
        client.post(f"/api/v1/cases/{case['id']}/analyze", json={"expected_version": 1}).status_code
        == 422
    )


def test_closed_case_is_terminal(env, pair_dict):
    client, settings, sessions = env
    case = ready(client)
    analyze(client, case)
    runner, _ = worker(settings, sessions, pair_dict)
    runner.run_once()
    final = detail(client, case)
    response = client.post(
        f"/api/v1/cases/{case['id']}/close",
        json={"expected_version": final["version"], "close_reason": "EXPORTED"},
    )
    assert response.status_code == 200 and response.json()["status"] == "CLOSED"
    assert "SENT" not in response.text
    response = client.post(
        f"/api/v1/cases/{case['id']}/retry",
        json={"expected_version": response.json()["version"]},
        headers={"Idempotency-Key": "closed"},
    )
    assert response.status_code == 409


def test_real_worker_process_restart_preserves_queue(env, pair_dict):
    client, settings, sessions = env
    case = ready(client)
    # Record a human correction so the actual worker subprocess needs no API key.
    response = client.put(
        f"/api/v1/cases/{case['id']}/review",
        json={
            "expected_version": case["version"],
            "corrected": pair_dict,
            "reason": "Synthetic labeled fixture",
        },
    )
    assert response.status_code == 200, response.text
    revised = response.json()
    analyze(client, revised)
    environment = {
        **os.environ,
        "DATABASE_URL": settings.database_url,
        "AVOIRLY_MODE": "local",
        "AVOIRLY_STORAGE_ROOT": str(settings.storage_root),
        "AVOIRLY_LOCAL_OWNER_ID": str(settings.local_owner),
        "OPENAI_MODEL": settings.model,
    }
    result = subprocess.run(
        [sys.executable, "-m", "recovery.worker", "--once"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert detail(client, case)["status"] == "CLAIM_DRAFTED"
    again = subprocess.run(
        [sys.executable, "-m", "recovery.worker", "--once"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert again.returncode == 0
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Draft)) == 1
