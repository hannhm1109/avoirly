"""Manual claim and credit ledger, private evidence, audited partial credits."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_phase5"
down_revision = "0002_phase4"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_case_status", "cases", type_="check")
    op.create_check_constraint(
        "ck_case_status",
        "cases",
        "status IN ('PENDING','PROCESSING','NEEDS_REVIEW','NO_DISCREPANCY','DISCREPANCY_FOUND',"
        "'CLAIM_DRAFTED','CLAIM_SENT','AWAITING_RESPONSE','CREDIT_PROMISED','CREDIT_CONFIRMED','FAILED','CLOSED')",
    )
    op.create_table(
        "recovery_evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "case_id", sa.Uuid(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False, unique=True),
        sa.Column("original_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("owner_id", "sha256"),
    )
    op.create_index("ix_recovery_evidence_case_id", "recovery_evidence", ["case_id"])
    op.create_table(
        "recovery_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "case_id", sa.Uuid(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("amount_net", sa.Numeric(38, 2)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("reference_key", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("due_on", sa.Date()),
        sa.Column(
            "evidence_id", sa.Uuid(), sa.ForeignKey("recovery_evidence.id", ondelete="CASCADE")
        ),
        sa.Column("snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by", sa.Uuid()),
        sa.Column("void_reason", sa.Text()),
        sa.CheckConstraint("kind IN ('SENT','NOTE','PROMISE','CREDIT')", name="ck_recovery_kind"),
        sa.CheckConstraint("currency IN ('MAD','EUR','USD','GBP')", name="ck_recovery_currency"),
        sa.CheckConstraint(
            "(kind = 'NOTE' AND amount_net IS NULL) OR (kind <> 'NOTE' AND amount_net IS NOT NULL AND amount_net > 0)",
            name="ck_recovery_amount",
        ),
        sa.CheckConstraint(
            "kind <> 'CREDIT' OR evidence_id IS NOT NULL", name="ck_credit_evidence"
        ),
        sa.CheckConstraint(
            "(voided_at IS NULL AND voided_by IS NULL AND void_reason IS NULL) OR "
            "(voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL AND length(trim(void_reason)) > 0)",
            name="ck_recovery_void",
        ),
    )
    op.create_index("ix_recovery_entries_case_id", "recovery_entries", ["case_id"])
    for name, fields, predicate in (
        ("uq_sent_case", ["case_id"], "kind = 'SENT' AND voided_at IS NULL"),
        (
            "uq_credit_reference",
            ["case_id", "reference_key"],
            "kind = 'CREDIT' AND voided_at IS NULL",
        ),
        ("uq_credit_evidence", ["evidence_id"], "kind = 'CREDIT' AND voided_at IS NULL"),
    ):
        op.create_index(
            name, "recovery_entries", fields, unique=True, postgresql_where=sa.text(predicate)
        )
    for table in ("recovery_entries", "recovery_evidence"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        for role in ("anon", "authenticated"):
            op.execute(f"""DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    REVOKE ALL ON TABLE "{table}" FROM {role};
                END IF;
            END $$""")


def downgrade():
    raise RuntimeError(
        "Recovery evidence requires a reviewed restore, not a destructive downgrade."
    )
