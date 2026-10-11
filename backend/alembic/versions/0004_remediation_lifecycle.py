"""Add remediation_runs and verification_runs for PR lifecycle + verify.

Revision ID: 0004_remediation_lifecycle
Revises: 0003_evidence_provenance
Create Date: 2026-10-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_remediation_lifecycle"
down_revision: str | None = "0003_evidence_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "remediation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=512), nullable=False),
        sa.Column("repo_full_name", sa.String(length=255), nullable=False),
        sa.Column("base_branch", sa.String(length=255), nullable=False),
        sa.Column("base_sha", sa.String(length=64), nullable=True),
        sa.Column("head_branch", sa.String(length=255), nullable=True),
        sa.Column("head_sha", sa.String(length=64), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("pr_url", sa.String(length=1024), nullable=True),
        sa.Column("lifecycle_state", sa.String(length=50), nullable=False),
        sa.Column("changed_files", postgresql.JSONB(), nullable=True),
        sa.Column("validation_results", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_remediation_runs_idempotency"),
    )
    op.create_index("ix_remediation_runs_scan_id", "remediation_runs", ["scan_id"])
    op.create_index("ix_remediation_runs_lifecycle_state", "remediation_runs", ["lifecycle_state"])

    op.create_table(
        "verification_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "remediation_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("remediation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evaluated_revision", sa.String(length=64), nullable=True),
        sa.Column("issue_outcome", sa.String(length=50), nullable=False),
        sa.Column("operational_status", sa.String(length=50), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("fresh_evidence", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_verification_runs_scan_id", "verification_runs", ["scan_id"])
    op.create_index(
        "ix_verification_runs_remediation_run_id",
        "verification_runs",
        ["remediation_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_verification_runs_remediation_run_id", table_name="verification_runs")
    op.drop_index("ix_verification_runs_scan_id", table_name="verification_runs")
    op.drop_table("verification_runs")
    op.drop_index("ix_remediation_runs_lifecycle_state", table_name="remediation_runs")
    op.drop_index("ix_remediation_runs_scan_id", table_name="remediation_runs")
    op.drop_table("remediation_runs")
