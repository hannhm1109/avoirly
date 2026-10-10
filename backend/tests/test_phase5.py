"""Manual tracking acceptance: real PostgreSQL, private synthetic evidence, no mail."""

import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import test_backend as backend_cases
import test_phase4 as hosted_cases
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from recovery.api.app import create_app
from recovery.api.tracking_schemas import CreditRequest, NoteRequest, SentRequest
from recovery.backup import create_backup, digest, run_pg, verify_restore
from recovery.db.models import CaseEvent, DeletionTask, RecoveryEntry, RecoveryEvidence
from recovery.storage import PrivateStorage
from recovery.worker import Worker

ROOT = Path(__file__).resolve().parents[2]
env = backend_cases.env
postgres = backend_cases.postgres
today = lambda: datetime.now(UTC).date().isoformat()


def proof_bytes(reference="CN-1"):
    image = Image.new("RGB", (500, 150), "white")
    ImageDraw.Draw(image).text((20, 20), "SYNTHETIC CREDIT EVIDENCE " + reference, fill="black")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def drafted(env, pair_dict):
    client, settings, sessions = env
    case = backend_cases.ready(client)
    backend_cases.analyze(client, case)
    runner, _ = backend_cases.worker(settings, sessions, pair_dict)
    runner.run_once()
    return backend_cases.detail(client, case)


def action(client, case, name, *, key=None, **fields):
    return client.post(
        f"/api/v1/cases/{case['id']}/tracking/{name}",
        headers={"Idempotency-Key": key or uuid4().hex},
        json={"expected_version": case["version"], **fields},
    )


def sent(client, case, amount="200.00"):
    result = action(
        client,
        case,
        "sent",
        occurred_on=today(),
        recipient="supplier@example.test",
        amount_net=amount,
        currency="MAD",
        draft_id=case["draft"]["id"],
        sent_outside_app=True,
    )
    assert result.status_code == 201, result.text
    return backend_cases.detail(client, case)


def evidence(client, case, reference="CN-1"):
    result = client.post(
        f"/api/v1/cases/{case['id']}/evidence",
        data={"expected_version": case["version"]},
        files={"file": (reference + ".png", proof_bytes(reference), "image/png")},
    )
    assert result.status_code == 201, result.text
    return backend_cases.detail(client, case), result.json()["evidence_id"]


def credit(client, case, evidence_id, *, amount="75.25", reference="CN-1", key=None):
    return action(
        client,
        case,
        "credit",
        key=key,
        occurred_on=today(),
        note="Montant HT et facture vérifiés.",
        currency="MAD",
        amount_net=amount,
        reference=reference,
        evidence_id=evidence_id,
        received_and_verified=True,
    )


@pytest.mark.parametrize("bad", [10, 10.5, "-1", "0.001", "NaN", "1e2", "01", " 10", "10,00"])
def test_money_wire_values_are_strings_with_exact_cents(bad):
    with pytest.raises(ValueError):
        SentRequest.model_validate(
            {
                "expected_version": 1,
                "occurred_on": today(),
                "recipient": "test",
                "amount_net": bad,
                "currency": "MAD",
                "draft_id": str(uuid4()),
                "sent_outside_app": True,
            }
        )


@pytest.mark.parametrize("bad", [False, 1, "true", None])
def test_credit_requires_explicit_received_and_verified_declaration(bad):
    with pytest.raises(ValueError):
        CreditRequest.model_validate(
            {
                "expected_version": 1,
                "occurred_on": today(),
                "note": "test",
                "amount_net": "10",
                "currency": "MAD",
                "reference": "CN",
                "evidence_id": str(uuid4()),
                "received_and_verified": bad,
            }
        )


@pytest.mark.parametrize("bad", [1728000000, "2026-10-10T10:00:00Z", "2026-02-30"])
def test_calendar_dates_reject_epoch_and_invalid_dates(bad):
    with pytest.raises(ValueError):
        NoteRequest.model_validate({"expected_version": 1, "occurred_on": bad, "note": "test"})


@pytest.mark.postgres
def test_sent_promise_and_partial_received_credits_remain_distinct(env, pair_dict):
    client, _, sessions = env
    case = drafted(env, pair_dict)
    assert case["recovery"]["confirmed_net"] == "0.00"
    case = sent(client, case)
    snapshot = case["recovery"]["entries"][0]["snapshot"]
    assert "200.00 MAD" in snapshot["body"]
    assert case["draft"] is None and case["status"] == "CLAIM_SENT"
    assert action(client, case, "await").status_code == 200
    case = backend_cases.detail(client, case)
    assert case["status"] == "AWAITING_RESPONSE"
    assert (
        action(
            client,
            case,
            "promise",
            occurred_on=today(),
            amount_net="100.00",
            currency="MAD",
            reference="Email 1",
            note="Le fournisseur annonce un avoir partiel.",
        ).status_code
        == 201
    )
    case = backend_cases.detail(client, case)
    assert case["status"] == "CREDIT_PROMISED"
    assert (
        case["recovery"]["promised_net"] == "100.00" and case["recovery"]["confirmed_net"] == "0.00"
    )
    case, eid = evidence(client, case)
    assert credit(client, case, eid).status_code == 201
    case = backend_cases.detail(client, case)
    assert case["status"] == "CREDIT_CONFIRMED"
    assert case["recovery"]["confirmed_net"] == "75.25"
    assert case["recovery"]["remaining_claim_net"] == "124.75"
    assert not case["recovery"]["fully_credited"]
    case, eid2 = evidence(client, case, "CN-2")
    assert credit(client, case, eid2, amount="124.75", reference="CN-2").status_code == 201
    case = backend_cases.detail(client, case)
    assert case["recovery"]["fully_credited"] and case["recovery"]["confirmed_net"] == "200.00"
    assert case["recovery"]["promised_net"] == "100.00"
    page = client.get("/api/v1/cases").json()
    assert page["recovery_by_currency"] == {
        "sent": {"MAD": "200.00"},
        "promised": {"MAD": "100.00"},
        "confirmed": {"MAD": "200.00"},
    }
    assert client.get(f"/api/v1/evidence/{eid}/content").content == proof_bytes()
    with sessions() as session:
        assert (
            session.scalar(select(CaseEvent).where(CaseEvent.event == "credit_confirmed"))
            is not None
        )


@pytest.mark.postgres
def test_guards_dates_money_currency_and_current_saved_draft(env, pair_dict):
    client, _, _ = env
    incomplete = backend_cases.ready(client)
    assert (
        action(client, incomplete, "note", occurred_on=today(), note="too early").json()["code"]
        == "CLAIM_NOT_SENT"
    )
    client.request(
        "DELETE",
        f"/api/v1/cases/{incomplete['id']}",
        json={"expected_version": incomplete["version"], "confirmed": True},
    )
    case = drafted(env, pair_dict)
    base = {
        "occurred_on": today(),
        "recipient": "supplier",
        "currency": "MAD",
        "amount_net": "200.00",
        "draft_id": case["draft"]["id"],
        "sent_outside_app": True,
    }
    for overrides, code in [
        ({"draft_id": str(uuid4())}, "NO_CURRENT_DRAFT"),
        (
            {"occurred_on": (datetime.now(UTC).date() + timedelta(days=1)).isoformat()},
            "INVALID_TRACKING_DATE",
        ),
        ({"amount_net": "200.01"}, "INVALID_TRACKING_AMOUNT"),
        ({"amount_net": "0"}, "INVALID_TRACKING_AMOUNT"),
        ({"currency": "EUR"}, "INVALID_TRACKING_AMOUNT"),
        ({"recipient": " "}, "INVALID_INPUT"),
    ]:
        assert action(client, case, "sent", **(base | overrides)).json()["code"] == code
    case = sent(client, case, "180.00")
    future = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    assert action(client, case, "note", occurred_on=future, note="future").status_code == 422
    for path, method, body in [
        ("draft", client.patch, {"subject": "changed", "body": "changed"}),
        ("review", client.put, {"corrected": pair_dict, "reason": "changed"}),
    ]:
        response = method(
            f"/api/v1/cases/{case['id']}/{path}", json={"expected_version": case["version"], **body}
        )
        assert response.status_code in (409, 422)
    response = client.post(
        f"/api/v1/cases/{case['id']}/documents",
        data={"role": "PO", "expected_version": case["version"]},
        files={"file": ("po.pdf", (ROOT / "samples/po.pdf").read_bytes())},
    )
    assert response.json()["code"] == "CLAIM_FROZEN"
    case, eid = evidence(client, case)
    assert credit(client, case, eid, amount="180.01").json()["code"] == "CREDIT_EXCEEDS_CLAIM"
    result = credit(client, case, str(uuid4()))
    assert result.status_code == 404


@pytest.mark.postgres
def test_idempotent_records_duplicate_evidence_and_concurrent_credit(env, pair_dict):
    client, _, sessions = env
    case = sent(client, drafted(env, pair_dict))
    case, eid = evidence(client, case)
    again, same_eid = evidence(client, case)
    assert same_eid == eid and again["version"] == case["version"]
    original = credit(client, case, eid, key="persistent-credit")
    assert original.status_code == 201
    assert credit(client, case, eid, key="persistent-credit").json() == original.json()
    assert (
        credit(client, case, eid, amount="75.26", key="persistent-credit").json()["code"]
        == "IDEMPOTENCY_CONFLICT"
    )
    case = backend_cases.detail(client, case)
    assert credit(client, case, eid, reference="OTHER").json()["code"] == "DUPLICATE_CREDIT"
    case, eid2 = evidence(client, case, "CN-2")
    assert credit(client, case, eid2, reference=" cn-1 ").json()["code"] == "DUPLICATE_CREDIT"
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda i: credit(
                    client, case, eid2, reference="CN-2", amount="10.00", key=f"parallel-{i}"
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert backend_cases.detail(client, case)["recovery"]["confirmed_net"] == "85.25"
    with sessions() as session:
        assert (
            len(list(session.scalars(select(RecoveryEntry).where(RecoveryEntry.kind == "CREDIT"))))
            == 2
        )


@pytest.mark.postgres
def test_void_corrections_preserve_history_and_restore_guards(env, pair_dict):
    client, _, _ = env
    case = sent(client, drafted(env, pair_dict))
    assert (
        action(
            client,
            case,
            "promise",
            occurred_on=today(),
            amount_net="100",
            currency="MAD",
            reference="P-1",
            note="promise",
        ).status_code
        == 201
    )
    case, eid = evidence(client, backend_cases.detail(client, case))
    assert credit(client, case, eid).status_code == 201
    case = backend_cases.detail(client, case)
    entries = {e["kind"]: e for e in case["recovery"]["entries"]}
    assert (
        action(client, case, entries["SENT"]["id"] + "/void", reason="wrong sending").json()["code"]
        == "ACTIVE_CREDITS"
    )
    assert (
        action(
            client, case, entries["CREDIT"]["id"] + "/void", reason="wrong net amount"
        ).status_code
        == 200
    )
    case = backend_cases.detail(client, case)
    assert case["status"] == "CREDIT_PROMISED" and case["recovery"]["confirmed_net"] == "0.00"
    assert case["recovery"]["entries"][-1]["void_reason"] == "wrong net amount"
    assert len(case["recovery"]["evidence"]) == 1
    assert (
        action(
            client, case, entries["PROMISE"]["id"] + "/void", reason="replaced promise"
        ).status_code
        == 200
    )
    case = backend_cases.detail(client, case)
    assert case["status"] == "CLAIM_SENT"
    assert (
        action(
            client, case, entries["SENT"]["id"] + "/void", reason="external send never completed"
        ).status_code
        == 200
    )
    case = backend_cases.detail(client, case)
    assert case["status"] == "CLAIM_DRAFTED" and case["draft"]
    assert not case["recovery"]["has_sent_record"]
    assert all(e["voided_at"] for e in case["recovery"]["entries"])
    assert case["recovery"]["entries"][0]["snapshot"]["body"] == case["draft"]["body"]


@pytest.mark.postgres
def test_phase5_signed_owner_isolation_and_quota(env, pair_dict):
    client, settings, sessions = env
    case = sent(client, drafted(env, pair_dict))
    case, eid = evidence(client, case)
    key = ec.generate_private_key(ec.SECP256R1())
    other = uuid4()
    config = hosted_cases.hosted(settings, settings.local_owner, other)
    app = create_app(
        config,
        sessions,
        storage=PrivateStorage(settings.storage_root),
        verifier=hosted_cases.verifier(config, key),
    )
    with TestClient(
        app, base_url="https://api.avoirly.example", client=("203.0.113.1", 1234)
    ) as hosted:
        hosted.headers["Authorization"] = "Bearer " + hosted_cases.token(key, other)
        assert hosted.get(f"/api/v1/evidence/{eid}/content").status_code == 404
        assert hosted.get(f"/api/v1/cases/{case['id']}").status_code == 404
        assert action(hosted, case, "note", occurred_on=today(), note="attack").status_code == 404
        entry = case["recovery"]["entries"][0]
        assert action(hosted, case, entry["id"] + "/void", reason="attack").status_code == 404
        hosted.headers["Authorization"] = "Bearer " + hosted_cases.token(key, settings.local_owner)
        assert hosted.get(f"/api/v1/evidence/{eid}/content").status_code == 200
    limited = create_app(replace(settings, daily_tracking=1), sessions)
    with TestClient(
        limited, base_url="http://127.0.0.1", client=("127.0.0.1", 49100)
    ) as restricted:
        assert (
            action(restricted, case, "note", occurred_on=today(), note="over quota").status_code
            == 429
        )


@pytest.mark.postgres
def test_closed_history_and_durable_deletion_remove_credit_evidence(env, pair_dict, monkeypatch):
    client, settings, sessions = env
    case = sent(client, drafted(env, pair_dict))
    case, eid = evidence(client, case)
    assert credit(client, case, eid).status_code == 201
    case = backend_cases.detail(client, case)
    response = client.post(
        f"/api/v1/cases/{case['id']}/close",
        json={"expected_version": case["version"], "close_reason": "EXPORTED"},
    )
    assert response.status_code == 200
    case = backend_cases.detail(client, case)
    assert case["recovery"]["confirmed_net"] == "75.25"
    assert (
        action(client, case, "note", occurred_on=today(), note="too late").json()["code"]
        == "CASE_CLOSED"
    )
    assert client.get("/api/v1/cases").json()["recovery_by_currency"]["confirmed"] == {
        "MAD": "75.25"
    }
    storage = client.app.state.storage
    delete = storage.delete
    monkeypatch.setattr(storage, "delete", lambda _: (_ for _ in ()).throw(OSError("offline")))
    result = client.request(
        "DELETE",
        f"/api/v1/cases/{case['id']}",
        json={"expected_version": case["version"], "confirmed": True},
    )
    assert result.status_code == 202
    assert client.get(f"/api/v1/evidence/{eid}/content").status_code == 404
    with sessions() as session:
        assert len(list(session.scalars(select(DeletionTask)))) == 3
        assert not list(session.scalars(select(RecoveryEntry)))
        assert not list(session.scalars(select(RecoveryEvidence)))
    monkeypatch.setattr(storage, "delete", delete)
    Worker(settings, sessions).run_once()
    assert not list(settings.storage_root.iterdir())


@pytest.mark.postgres
def test_backup_restores_credit_ledger_and_private_evidence(env, pair_dict, tmp_path):
    client, settings, _ = env
    case = sent(client, drafted(env, pair_dict))
    case, eid = evidence(client, case)
    assert credit(client, case, eid).status_code == 201
    archive = tmp_path / "snapshot"
    manifest = create_backup(settings, archive)
    assert manifest["counts"]["recovery_entries"] == 2
    assert manifest["counts"]["recovery_evidence"] == 1
    base = make_url(os.environ["AVOIRLY_TEST_DATABASE_URL"])
    target_name = "avoirly_phase5_restore_" + uuid4().hex
    target = base.set(database=target_name)
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{target_name}"'))
    try:
        result = verify_restore(
            archive, target.render_as_string(hide_password=False), tmp_path / "restored"
        )
        assert result["verified"] and result["objects"] == 3
        restored = create_engine(target)
        with restored.connect() as conn:
            schema = manifest["schema"]
            assert (
                str(
                    conn.scalar(
                        text(
                            f"SELECT amount_net FROM \"{schema}\".recovery_entries WHERE kind='CREDIT'"
                        )
                    )
                )
                == "75.25"
            )
            assert "200.00 MAD" in conn.scalar(
                text(
                    f"SELECT snapshot_json->>'body' FROM \"{schema}\".recovery_entries WHERE kind='SENT'"
                )
            )
        restored.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{target_name}" WITH (FORCE)'))
        admin.dispose()


@pytest.mark.postgres
def test_phase4_cases_survive_migration_and_legacy_archive_verification(postgres, tmp_path):
    base = make_url(os.environ["AVOIRLY_TEST_DATABASE_URL"])
    schema = "avoirly_legacy_" + uuid4().hex
    restore_name = "avoirly_legacy_restore_" + uuid4().hex
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    source_url = base.update_query_dict({"options": "-csearch_path=" + schema})
    source = create_engine(source_url)
    with admin.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.execute(text(f'CREATE DATABASE "{restore_name}"'))
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", source_url.render_as_string(hide_password=False).replace("%", "%%")
    )
    try:
        command.upgrade(config, "0002_phase4")
        case_id, owner = uuid4(), uuid4()
        with source.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO cases (id,owner_id,status,version,current_revision,currency,potential_credit_net,created_at,updated_at) VALUES (:id,:owner,'CLAIM_DRAFTED',7,2,'MAD',200.00,now(),now())"
                ),
                {"id": case_id, "owner": owner},
            )
        # A trusted synthetic Phase 4-format archive, genuinely lacking Phase 5 tables.
        archive = tmp_path / "legacy"
        (archive / "objects").mkdir(parents=True)
        run_pg(
            "pg_dump",
            [
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--schema=" + schema,
                "--file=" + str(archive / "database.dump"),
            ],
            source_url.render_as_string(hide_password=False),
        )
        manifest = {
            "format": 1,
            "schema": schema,
            "objects": [],
            "counts": {"cases": 1, "drafts": 0},
            "database_sha256": digest((archive / "database.dump").read_bytes()),
        }
        (archive / "manifest.json").write_text(json.dumps(manifest))
        result = verify_restore(
            archive,
            base.set(database=restore_name).render_as_string(hide_password=False),
            tmp_path / "legacy-objects",
        )
        assert result["verified"] and result["counts"]["cases"] == 1
        command.upgrade(config, "head")
        with source.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT owner_id,status,version,current_revision,potential_credit_net FROM cases WHERE id=:id"
                ),
                {"id": case_id},
            ).one()
            assert tuple(row) == (owner, "CLAIM_DRAFTED", 7, 2, 200)
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0003_phase5"
            assert (
                conn.scalar(
                    text(
                        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND c.relname IN ('recovery_entries','recovery_evidence') AND c.relrowsecurity"
                    ),
                    {"schema": schema},
                )
                == 2
            )
    finally:
        source.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            conn.execute(text(f'DROP DATABASE "{restore_name}" WITH (FORCE)'))
        admin.dispose()
