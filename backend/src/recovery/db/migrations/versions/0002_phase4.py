"""Pilot quotas, worker liveness, non-content model usage and default-deny RLS."""

import sqlalchemy as sa
from alembic import op

revision = "0002_phase4"
down_revision = "0001_phase2"
branch_labels = None
depends_on = None

TABLES = (
    "cases",
    "documents",
    "extractions",
    "comparisons",
    "drafts",
    "jobs",
    "case_events",
    "document_confirmations",
    "idempotency_keys",
    "invoice_identities",
    "deletion_tasks",
    "usage_counters",
    "worker_heartbeats",
    "model_usage",
)


def upgrade():
    op.create_table(
        "usage_counters",
        sa.Column("owner_id", sa.Uuid(), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False),
    )
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "model_usage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_usd", sa.Numeric(20, 8), nullable=True),
    )
    # Supabase's public Data API must never bypass the Python owner checks.
    # Table-owner API/worker connections retain access; no browser policies exist.
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        for role in ("anon", "authenticated"):
            op.execute(f"""DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    REVOKE ALL ON TABLE "{table}" FROM {role};
                END IF;
            END $$""")


def downgrade():
    raise RuntimeError("Security migration requires a reviewed restore, not automatic downgrade.")
