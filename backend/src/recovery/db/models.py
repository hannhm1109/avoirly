"""Immutable snapshots, durable jobs, and owner-scoped case metadata."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Case(Identity, Base):
    __tablename__ = "cases"
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    processing_step: Mapped[str | None] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer, default=1)
    current_revision: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str | None] = mapped_column(String(3))
    potential_credit_net: Mapped[Decimal | None] = mapped_column(Numeric(38, 2))
    close_reason: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("ix_cases_owner_created", "owner_id", "created_at"),
        CheckConstraint(
            "status IN ('PENDING','PROCESSING','NEEDS_REVIEW','NO_DISCREPANCY','DISCREPANCY_FOUND','CLAIM_DRAFTED','CLAIM_SENT','AWAITING_RESPONSE','CREDIT_PROMISED','CREDIT_CONFIRMED','FAILED','CLOSED')",
            name="ck_case_status",
        ),
        CheckConstraint("version > 0 AND current_revision >= 0", name="ck_case_version"),
    )


class Document(Identity, Base):
    __tablename__ = "documents"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    role: Mapped[str] = mapped_column(String(8))
    revision: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(Text)
    original_name: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("case_id", "role", "revision"),
        CheckConstraint("role IN ('PO','INVOICE')", name="ck_document_role"),
    )


class Extraction(Identity, Base):
    __tablename__ = "extractions"
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    raw_json: Mapped[dict] = mapped_column(JSONB)
    corrected_json: Mapped[dict | None] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[str] = mapped_column(String(32))
    input_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(Text)
    token_usage: Mapped[dict | None] = mapped_column(JSONB)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    corrected_by: Mapped[UUID | None] = mapped_column(Uuid)
    correction_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("document_id", "version"),)


class Comparison(Identity, Base):
    __tablename__ = "comparisons"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    result_json: Mapped[dict] = mapped_column(JSONB)
    validated_json: Mapped[dict | None] = mapped_column(JSONB)
    extraction_ids: Mapped[dict] = mapped_column(JSONB)
    engine_version: Mapped[str] = mapped_column(String(32), default="1")
    __table_args__ = (UniqueConstraint("case_id", "revision", "engine_version"),)


class Draft(Identity, Base):
    __tablename__ = "drafts"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    comparison_id: Mapped[UUID] = mapped_column(ForeignKey("comparisons.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(2))
    edited_by: Mapped[UUID | None] = mapped_column(Uuid)
    __table_args__ = (UniqueConstraint("comparison_id", "version"),)


class Job(Identity, Base):
    __tablename__ = "jobs"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    attempt: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(2), default="fr")
    model: Mapped[str] = mapped_column(Text)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    error_code: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        Index(
            "uq_active_job_revision",
            "case_id",
            "revision",
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
        Index("ix_jobs_poll", "status", "available_at"),
    )


class CaseEvent(Identity, Base):
    __tablename__ = "case_events"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid)
    event: Mapped[str] = mapped_column(String(64))
    old_status: Mapped[str] = mapped_column(String(32))
    new_status: Mapped[str] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class Confirmation(Identity, Base):
    __tablename__ = "document_confirmations"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    value_json: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[UUID] = mapped_column(Uuid)
    reason: Mapped[str] = mapped_column(Text)


class IdempotencyKey(Identity, Base):
    __tablename__ = "idempotency_keys"
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    route: Mapped[str] = mapped_column(String(128))
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("owner_id", "route", "key"),)


class InvoiceIdentity(Identity, Base):
    """Unique claim reservation prevents concurrent duplicate invoice claims."""

    __tablename__ = "invoice_identities"
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    supplier_key: Mapped[str] = mapped_column(Text)
    invoice_key: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("owner_id", "supplier_key", "invoice_key"),)


class DeletionTask(Identity, Base):
    """Outbox contains only random storage keys, no document text or identities."""

    __tablename__ = "deletion_tasks"
    storage_key: Mapped[str] = mapped_column(Text, unique=True)


class UsageCounter(Base):
    """Non-content daily limits survive case deletion and process restarts."""

    __tablename__ = "usage_counters"
    owner_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelUsage(Identity, Base):
    """Reported token usage only; no source text, case ID or supplier identity."""

    __tablename__ = "model_usage"
    model: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    estimated_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))


class RecoveryEvidence(Identity, Base):
    __tablename__ = "recovery_evidence"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    original_name: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("owner_id", "sha256"),)


class RecoveryEntry(Identity, Base):
    """Manual ledger: amounts never overwrite history; corrections void an entry."""

    __tablename__ = "recovery_entries"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid)
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(8))
    occurred_on: Mapped[date] = mapped_column(Date)
    amount_net: Mapped[Decimal | None] = mapped_column(Numeric(38, 2))
    currency: Mapped[str] = mapped_column(String(3))
    reference: Mapped[str] = mapped_column(Text)
    reference_key: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    due_on: Mapped[date | None] = mapped_column(Date)
    evidence_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("recovery_evidence.id", ondelete="CASCADE")
    )
    snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[UUID | None] = mapped_column(Uuid)
    void_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("kind IN ('SENT','NOTE','PROMISE','CREDIT')", name="ck_recovery_kind"),
        CheckConstraint("currency IN ('MAD','EUR','USD','GBP')", name="ck_recovery_currency"),
        CheckConstraint(
            "(kind = 'NOTE' AND amount_net IS NULL) OR (kind <> 'NOTE' AND amount_net IS NOT NULL AND amount_net > 0)",
            name="ck_recovery_amount",
        ),
        CheckConstraint("kind <> 'CREDIT' OR evidence_id IS NOT NULL", name="ck_credit_evidence"),
        CheckConstraint(
            "(voided_at IS NULL AND voided_by IS NULL AND void_reason IS NULL) OR "
            "(voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL AND length(trim(void_reason)) > 0)",
            name="ck_recovery_void",
        ),
        Index(
            "uq_sent_case",
            "case_id",
            unique=True,
            postgresql_where=text("kind = 'SENT' AND voided_at IS NULL"),
        ),
        Index(
            "uq_credit_reference",
            "case_id",
            "reference_key",
            unique=True,
            postgresql_where=text("kind = 'CREDIT' AND voided_at IS NULL"),
        ),
        Index(
            "uq_credit_evidence",
            "evidence_id",
            unique=True,
            postgresql_where=text("kind = 'CREDIT' AND voided_at IS NULL"),
        ),
    )
