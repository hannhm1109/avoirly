"""Hosted boundaries and operating gates, with real signatures and PostgreSQL.

The provider/network is mocked; never claim these are hosted acceptance results.
"""

import json
import os
import secrets
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import pytest

# Reuse the real isolated schema/fixture setup; no developer ownership overrides.
import test_backend as backend_cases
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from test_backend import analyze, detail, ready, worker

from recovery import backup_job
from recovery.api.app import create_app
from recovery.api.errors import DomainError
from recovery.auth import TokenVerifier
from recovery.backup import create_backup, verify_restore
from recovery.backup_job import decrypt, encrypt
from recovery.config import Settings
from recovery.db.models import UsageCounter
from recovery.operations import metrics, usage_record
from recovery.storage import PrivateStorage, SupabaseStorage
from recovery.worker import Worker

ROOT = Path(__file__).resolve().parents[2]
env = backend_cases.env
postgres = backend_cases.postgres


@pytest.fixture
def signing_key():
    return ec.generate_private_key(ec.SECP256R1())


def test_backup_encryption_roundtrip_tampering_and_overwrite_refusal(tmp_path):
    from cryptography.exceptions import InvalidTag

    source = tmp_path / "plain.tar"
    source.write_bytes(os.urandom(150000))
    encrypted = tmp_path / "backup.bin"
    key = os.urandom(32)
    encrypt(source, encrypted, key)
    target = tmp_path / "restored.tar"
    decrypt(encrypted, target, key)
    assert target.read_bytes() == source.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        decrypt(encrypted, target, key)
    with pytest.raises(InvalidTag):
        decrypt(encrypted, tmp_path / "wrong-key.tar", os.urandom(32))
    assert not (tmp_path / "wrong-key.tar").exists()
    data = bytearray(encrypted.read_bytes())
    data[100] ^= 1
    encrypted.write_bytes(data)
    with pytest.raises(InvalidTag):
        decrypt(encrypted, tmp_path / "corrupted.tar", key)
    assert not (tmp_path / "corrupted.tar").exists()


@pytest.mark.parametrize("failure", [None, "public", "upload"])
def test_scheduled_backup_encrypts_before_upload_and_prunes_only_after_success(
    tmp_path, monkeypatch, failure
):
    monkeypatch.setenv("AVOIRLY_BACKUP_KEY", secrets.token_urlsafe(32))
    monkeypatch.setenv("AVOIRLY_BACKUP_BUCKET", "avoirly-backups")
    monkeypatch.setenv("AVOIRLY_BACKUP_RETENTION_DAYS", "14")
    old = "backup-20200101T000000Z-" + "a" * 32 + ".bin"
    future = "backup-20990101T000000Z-" + "b" * 32 + ".bin"
    calls = []
    uploaded = []

    def snapshot(settings, destination):
        destination.mkdir()
        (destination / "manifest.json").write_text('{"synthetic":true}')

    class Vault:
        def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs))
            if method == "GET":
                return httpx.Response(200, json={"public": failure == "public"})
            if path.startswith("object/list/"):
                return httpx.Response(200, json=[{"name": n} for n in (old, future, "keep-me")])
            if method == "POST":
                payload = b"".join(kwargs["content"])
                assert payload.startswith(backup_job.MAGIC)
                assert b'"synthetic"' not in payload
                assert len(payload) == int(kwargs["headers"]["Content-Length"])
                uploaded.append(payload)
                if failure == "upload":
                    raise OSError("simulated storage failure")
            return httpx.Response(200, json={})

    monkeypatch.setattr(backup_job, "create_backup", snapshot)
    monkeypatch.setattr(backup_job, "SupabaseStorage", lambda _: Vault())
    settings = SimpleNamespace(storage_bucket="avoirly-documents")
    if failure:
        with pytest.raises((ValueError, OSError)):
            backup_job.run_backup(settings)
        assert not any(m == "DELETE" or "object/list/" in p for m, p, _ in calls)
        return
    result = backup_job.run_backup(settings)
    assert result == {"encrypted_backup_uploaded": True, "expired_backups_removed": 1}
    assert calls[-1] == ("DELETE", "object/avoirly-backups", {"json": {"prefixes": [old]}})
    encrypted = tmp_path / "uploaded.bin"
    encrypted.write_bytes(uploaded[0])
    restored = tmp_path / "restored.tar"
    decrypt(encrypted, restored, backup_job.encryption_key())
    with tarfile.open(restored) as archive:
        assert archive.extractfile("snapshot/manifest.json").read() == b'{"synthetic":true}'


def hosted(settings, *owners):
    return replace(
        settings,
        mode="hosted",
        local_owner=None,
        database_url=make_url(settings.database_url)
        .update_query_dict({"sslmode": "require"})
        .render_as_string(hide_password=False),
        web_origin="https://avoirly.example",
        api_origin="https://api.avoirly.example",
        supabase_url="https://test-project.supabase.co",
        supabase_secret_key="sb_secret_test_only",
        metrics_token="test-operator-token-" + "x" * 32,
        pilot_owner_ids=owners,
    )


def token(key, owner, **changes):
    claims = {
        "sub": str(owner),
        "iss": "https://test-project.supabase.co/auth/v1",
        "aud": "authenticated",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
        "role": "authenticated",
    }
    claims.update(changes)
    return jwt.encode(claims, key, algorithm="ES256", headers={"kid": "test-key"})


def verifier(settings, key):
    class Keys:
        def get_signing_key_from_jwt(self, raw):
            return SimpleNamespace(key=key.public_key())

    return TokenVerifier(settings, Keys())


@pytest.mark.parametrize(
    "changed",
    [
        {"exp": 1},
        {"iss": "https://attacker.example"},
        {"aud": "service_role"},
        {"sub": "not-a-uuid"},
        {"role": "service_role"},
        {"is_anonymous": True},
        {"iat": 4102444800},
    ],
)
def test_invalid_signed_claims_rejected(signing_key, changed, tmp_path):
    owner = uuid4()
    settings = hosted(Settings("postgresql+psycopg://localhost/test", tmp_path, owner), owner)
    with pytest.raises(DomainError) as error:
        verifier(settings, signing_key).owner("Bearer " + token(signing_key, owner, **changed))
    assert error.value.status == 401


def test_signature_algorithm_and_pilot_allowlist(signing_key, tmp_path):
    owner = uuid4()
    settings = hosted(Settings("postgresql+psycopg://localhost/test", tmp_path, owner), owner)
    verify = verifier(settings, signing_key)
    assert verify.owner("Bearer " + token(signing_key, owner)) == owner
    for raw in (
        "",
        "Bearer malformed",
        "Bearer " + token(ec.generate_private_key(ec.SECP256R1()), owner),
        "Bearer "
        + jwt.encode(
            {"sub": str(owner)}, "test-secret-never-accepted-as-auth" * 2, algorithm="HS256"
        ),
    ):
        with pytest.raises(DomainError) as error:
            verify.owner(raw)
        assert error.value.status == 401
    with pytest.raises(DomainError) as error:
        verify.owner("Bearer " + token(signing_key, uuid4()))
    assert error.value.code == "PILOT_ACCESS_REQUIRED"


@pytest.mark.postgres
def test_two_real_signed_identities_cannot_read_change_or_download_each_other(env, signing_key):
    _, settings, sessions = env
    a, b = uuid4(), uuid4()
    settings = hosted(settings, a, b)
    app = create_app(
        settings,
        sessions,
        storage=PrivateStorage(settings.storage_root),
        verifier=verifier(settings, signing_key),
    )
    with TestClient(app, base_url=settings.api_origin, client=("203.0.113.1", 55000)) as client:
        assert client.get("/api/v1/cases").status_code == 401
        client.headers["Authorization"] = "Bearer " + token(signing_key, a)
        case = ready(client)
        doc = detail(client, case)["documents"]["PO"]["id"]
        client.headers["Authorization"] = "Bearer " + token(signing_key, b)
        assert client.get("/api/v1/cases").json()["items"] == []
        for method, path, kwargs in [
            ("get", f"/cases/{case['id']}", {}),
            ("get", f"/documents/{doc}/content", {}),
            ("get", f"/cases/{case['id']}/events", {}),
            (
                "delete",
                f"/cases/{case['id']}",
                {"json": {"expected_version": case["version"], "confirmed": True}},
            ),
            (
                "post",
                f"/cases/{case['id']}/close",
                {"json": {"expected_version": case["version"], "close_reason": "ABANDONED"}},
            ),
            (
                "post",
                f"/cases/{case['id']}/analyze",
                {
                    "json": {"expected_version": case["version"]},
                    "headers": {"Idempotency-Key": "foreign"},
                },
            ),
        ]:
            assert client.request(method, "/api/v1" + path, **kwargs).status_code == 404
        assert (
            client.get("/api/v1/cases", headers={"Origin": "https://attacker.example"}).status_code
            == 403
        )
        assert client.get("/api/v1/cases", headers={"X-Owner-ID": str(a)}).json()["items"] == []
        assert client.get("/ops/metrics").status_code == 401
        result = client.get(
            "/ops/metrics", headers={"Authorization": "Bearer " + settings.metrics_token}
        )
        assert result.status_code == 200
        assert "supplier" not in result.text and "original_name" not in result.text
        client.headers["Authorization"] = "Bearer " + token(signing_key, a)
        assert client.get(f"/api/v1/documents/{doc}/content").status_code == 200


@pytest.mark.postgres
def test_daily_quota_is_atomic_and_survives_delete_and_restart(env):
    _, settings, sessions = env
    settings = replace(settings, daily_cases=1)
    app = create_app(settings, sessions)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50001)) as client:
        with ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(lambda _: client.post("/api/v1/cases"), range(2)))
        assert sorted(r.status_code for r in responses) == [201, 429]
        case = next(r.json() for r in responses if r.status_code == 201)
        assert (
            client.request(
                "DELETE",
                f"/api/v1/cases/{case['id']}",
                json={"expected_version": case["version"], "confirmed": True},
            ).status_code
            == 202
        )
    with TestClient(
        create_app(settings, sessions), base_url="http://127.0.0.1", client=("127.0.0.1", 50002)
    ) as client:
        assert client.post("/api/v1/cases").json()["code"] == "DAILY_QUOTA"
    with sessions() as session:
        assert session.scalar(select(UsageCounter.used).where(UsageCounter.kind == "cases")) == 1


@pytest.mark.postgres
def test_analysis_retry_limit_and_idempotency_charge_once(env, pair_dict):
    client, settings, sessions = env
    case = ready(client)
    queued = analyze(client, case)
    assert analyze(client, case) == queued
    with sessions() as session:
        assert session.scalar(select(UsageCounter.used).where(UsageCounter.kind == "analyses")) == 1
    runner, _ = worker(settings, sessions, pair_dict, fail_role="PO")
    for attempt in range(3):
        assert runner.run_once()
        failed = detail(client, case)
        response = client.post(
            f"/api/v1/cases/{case['id']}/retry",
            json={"expected_version": failed["version"]},
            headers={"Idempotency-Key": f"retry-{attempt}"},
        )
        assert response.status_code == (202 if attempt < 2 else 429)
    assert response.json()["code"] == "RETRY_LIMIT"


def test_private_cloud_storage_roundtrip_and_no_secret_bearer(tmp_path):
    settings = Settings(
        "postgresql+psycopg://localhost/test",
        tmp_path,
        uuid4(),
        supabase_secret_key="sb_secret_testing",
    )
    objects = {}

    def handle(request):
        assert request.headers["apikey"] == "sb_secret_testing"
        assert "authorization" not in request.headers
        path = request.url.path
        if "/bucket/" in path:
            return httpx.Response(200, json={"public": False})
        if request.method == "POST":
            objects[path.rsplit("/", 1)[1]] = request.content
            return httpx.Response(200, json={})
        if request.method == "DELETE":
            for key in json.loads(request.content)["prefixes"]:
                objects.pop(key, None)
            return httpx.Response(200, json=[])
        return httpx.Response(200, content=objects[path.rsplit("/", 1)[1]])

    client = httpx.Client(
        base_url="https://test-project.supabase.co/storage/v1/",
        headers={"apikey": settings.supabase_secret_key},
        transport=httpx.MockTransport(handle),
    )
    storage = SupabaseStorage(settings, client)
    storage.check_private()
    with (ROOT / "samples/po.pdf").open("rb") as source:
        key, checked = storage.save_upload(source, "../../po.pdf")
    assert storage.read(key) == checked.data
    with storage.materialize(key) as materialized:
        assert materialized.read_bytes() == checked.data
    assert not materialized.exists()
    storage.delete(key)
    storage.delete(key)
    assert not objects
    with pytest.raises(ValueError):
        storage.read("../secret")
    bad = httpx.Client(
        base_url="https://test-project.supabase.co/",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"public": True})),
    )
    with pytest.raises(RuntimeError):
        SupabaseStorage(settings, bad).check_private()


@pytest.mark.postgres
def test_heartbeat_metrics_and_decimal_cost(env):
    _, settings, sessions = env
    assert metrics(sessions)["worker_healthy"] is False
    Worker(settings, sessions).run_once()
    assert metrics(sessions)["worker_healthy"] is True
    record = usage_record(
        replace(settings, input_usd_per_million="1.25", output_usd_per_million="10"),
        settings.model,
        {"token_usage": {"prompt_tokens": 1000, "completion_tokens": 100}},
    )
    assert str(record.estimated_usd) == "0.00225"
    assert (
        usage_record(
            settings, settings.model, {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        ).estimated_usd
        is None
    )


@pytest.mark.postgres
def test_consistent_backup_restores_real_documents_and_draft(env, pair_dict, tmp_path):
    client, settings, sessions = env
    case = ready(client)
    analyze(client, case)
    runner, _ = worker(settings, sessions, pair_dict)
    runner.run_once()
    target_name = "avoirly_restore_" + uuid4().hex
    base = make_url(os.environ["AVOIRLY_TEST_DATABASE_URL"])
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    target = base.set(database=target_name)
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{target_name}"'))
    try:
        archive = tmp_path / "backup"
        manifest = create_backup(settings, archive)
        result = verify_restore(
            archive, target.render_as_string(hide_password=False), tmp_path / "restored"
        )
        assert result["verified"] and result["objects"] == 2
        assert result["counts"]["drafts"] == 1
        restored = create_engine(target)
        with restored.connect() as conn:
            assert "200.00 MAD" in conn.scalar(
                text(f'SELECT body FROM "{manifest["schema"]}".drafts')
            )
        restored.dispose()
        with pytest.raises(ValueError, match="empty"):
            verify_restore(
                archive, target.render_as_string(hide_password=False), tmp_path / "another"
            )
        (archive / "objects" / manifest["objects"][0]["key"]).write_bytes(b"corrupted")
        with pytest.raises(ValueError, match="checksum"):
            verify_restore(
                archive, target.render_as_string(hide_password=False), tmp_path / "another"
            )
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{target_name}" WITH (FORCE)'))
        admin.dispose()
