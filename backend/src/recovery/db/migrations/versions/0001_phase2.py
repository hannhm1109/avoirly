"""Initial Phase 2 schema. Frozen migration; does not import application models."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_phase2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cases",
        sa.Column("owner_id", sa.Uuid(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(32), nullable=False, primary_key=False),
        sa.Column("processing_step", sa.String(32), nullable=True, primary_key=False),
        sa.Column("version", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("current_revision", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("currency", sa.String(3), nullable=True, primary_key=False),
        sa.Column("potential_credit_net", sa.Numeric(38, 2), nullable=True, primary_key=False),
        sa.Column("close_reason", sa.String(32), nullable=True, primary_key=False),
        sa.Column("error_code", sa.String(64), nullable=True, primary_key=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','NEEDS_REVIEW','NO_DISCREPANCY','DISCREPANCY_FOUND','CLAIM_DRAFTED','FAILED','CLOSED')",
            name="ck_case_status",
        ),
        sa.CheckConstraint("version > 0 AND current_revision >= 0", name="ck_case_version"),
    )
    op.create_index("ix_cases_owner_created", "cases", ["owner_id", "created_at"], unique=False)
    op.create_index("ix_cases_owner_id", "cases", ["owner_id"], unique=False)
    op.create_table(
        "deletion_tasks",
        sa.Column("storage_key", sa.Text(), nullable=False, primary_key=False),
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_table(
        "case_events",
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False, primary_key=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True, primary_key=False),
        sa.Column("event", sa.String(64), nullable=False, primary_key=False),
        sa.Column("old_status", sa.String(32), nullable=False, primary_key=False),
        sa.Column("new_status", sa.String(32), nullable=False, primary_key=False),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, primary_key=False),
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )
    op.create_index("ix_case_events_case_id", "case_events", ["case_id"], unique=False)
    op.create_table(
        "comparisons",
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("result_json", postgresql.JSONB(), nullable=False, primary_key=False),
        sa.Column("validated_json", postgresql.JSONB(), nullable=True, primary_key=False),
        sa.Column("extraction_ids", postgresql.JSONB(), nullable=False, primary_key=False),
        sa.Column("engine_version", sa.String(32), nullable=False, primary_key=False),
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint("case_id", "revision", "engine_version"),
    )
    op.create_index("ix_comparisons_case_id", "comparisons", ["case_id"], unique=False)
    op.create_table(
        "document_confirmations",
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("kind", sa.String(32), nullable=False, primary_key=False),
        sa.Column("value_json", postgresql.JSONB(), nullable=False, primary_key=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False, primary_key=False),
        sa.Column("reason", sa.Text(), nullable=False, primary_key=False),
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )
    op.create_index(
        "ix_document_confirmations_case_id", "document_confirmations", ["case_id"], unique=False
    )
    op.create_table(
        "documents",
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False, primary_key=False),
        sa.Column("role", sa.String(8), nullable=False, primary_key=False),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("storage_key", sa.Text(), nullable=False, primary_key=False),
        sa.Column("original_name", sa.Text(), nullable=False, primary_key=False),
        sa.Column("mime_type", sa.String(64), nullable=False, primary_key=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("sha256", sa.String(64), nullable=False, primary_key=False),
        sa.Column("page_count", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint("case_id", "role", "revision"),
        sa.CheckConstraint("role IN ('PO','INVOICE')", name="ck_document_role"),
    )
    op.create_index("ix_documents_case_id", "documents", ["case_id"], unique=False)
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"], unique=False)
    op.create_index("ix_documents_sha256", "documents", ["sha256"], unique=False)
    op.create_table(
        "idempotency_keys",
        sa.Column("owner_id", sa.Uuid(), nullable=False, primary_key=False),
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("route", sa.String(128), nullable=False, primary_key=False),
        sa.Column("key", sa.String(128), nullable=False, primary_key=False),
        sa.Column("request_hash", sa.String(64), nullable=False, primary_key=False),
        sa.Column("response", postgresql.JSONB(), nullable=False, primary_key=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint("owner_id", "route", "key"),
    )
    op.create_table(
        "invoice_identities",
        sa.Column("owner_id", sa.Uuid(), nullable=False, primary_key=False),
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("supplier_key", sa.Text(), nullable=False, primary_key=False),
        sa.Column("invoice_key", sa.Text(), nullable=False, primary_key=False),
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint("owner_id", "supplier_key", "invoice_key"),
    )
    op.create_index(
        "ix_invoice_identities_case_id", "invoice_identities", ["case_id"], unique=False
    )
    op.create_table(
        "jobs",
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False, primary_key=False),
        sa.Column("revision", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("status", sa.String(16), nullable=False, primary_key=False),
        sa.Column("attempt", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("language", sa.String(2), nullable=False, primary_key=False),
        sa.Column("model", sa.Text(), nullable=False, primary_key=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True, primary_key=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True, primary_key=False),
        sa.Column("error_code", sa.String(64), nullable=True, primary_key=False),
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
    )
    op.create_index("ix_jobs_case_id", "jobs", ["case_id"], unique=False)
    op.create_index("ix_jobs_owner_id", "jobs", ["owner_id"], unique=False)
    op.create_index("ix_jobs_poll", "jobs", ["status", "available_at"], unique=False)
    op.create_index(
        "uq_active_job_revision",
        "jobs",
        ["case_id", "revision"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )
    op.create_table(
        "drafts",
        sa.Column(
            "case_id",
            sa.Uuid(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column(
            "comparison_id",
            sa.Uuid(),
            sa.ForeignKey("comparisons.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("subject", sa.Text(), nullable=False, primary_key=False),
        sa.Column("body", sa.Text(), nullable=False, primary_key=False),
        sa.Column("language", sa.String(2), nullable=False, primary_key=False),
        sa.Column("edited_by", sa.Uuid(), nullable=True, primary_key=False),
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint("comparison_id", "version"),
    )
    op.create_index("ix_drafts_case_id", "drafts", ["case_id"], unique=False)
    op.create_table(
        "extractions",
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, primary_key=False),
        sa.Column("raw_json", postgresql.JSONB(), nullable=False, primary_key=False),
        sa.Column("corrected_json", postgresql.JSONB(), nullable=True, primary_key=False),
        sa.Column("model", sa.Text(), nullable=False, primary_key=False),
        sa.Column("prompt_version", sa.String(32), nullable=False, primary_key=False),
        sa.Column("schema_version", sa.String(32), nullable=False, primary_key=False),
        sa.Column("input_hash", sa.String(64), nullable=False, primary_key=False),
        sa.Column("request_id", sa.Text(), nullable=True, primary_key=False),
        sa.Column("token_usage", postgresql.JSONB(), nullable=True, primary_key=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True, primary_key=False),
        sa.Column("corrected_by", sa.Uuid(), nullable=True, primary_key=False),
        sa.Column("correction_reason", sa.Text(), nullable=True, primary_key=False),
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, primary_key=False),
        sa.UniqueConstraint("document_id", "version"),
    )
    op.create_index("ix_extractions_document_id", "extractions", ["document_id"], unique=False)


def downgrade():
    op.drop_table("extractions")
    op.drop_table("drafts")
    op.drop_table("jobs")
    op.drop_table("invoice_identities")
    op.drop_table("idempotency_keys")
    op.drop_table("documents")
    op.drop_table("document_confirmations")
    op.drop_table("comparisons")
    op.drop_table("case_events")
    op.drop_table("deletion_tasks")
    op.drop_table("cases")
