"""Add durable scan observability columns (provider/batch/cost estimates).

Revision ID: 0009_scan_observability
Revises: 0008_remediation_state_revision
Create Date: 2026-10-15 05:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_scan_observability"
down_revision: str | None = "0008_remediation_state_revision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("llm_usd_estimated", sa.Float(), nullable=True))
    op.add_column("scans", sa.Column("provider_successes", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("provider_failures", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("primary_llm_model", sa.String(length=128), nullable=True))
    op.add_column("scans", sa.Column("fallback_provider_used", sa.Boolean(), nullable=True))
    op.add_column("scans", sa.Column("batches_total", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("batches_completed", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("batches_failed", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("llm_tokens_in", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("llm_tokens_out", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("scans", "llm_tokens_out")
    op.drop_column("scans", "llm_tokens_in")
    op.drop_column("scans", "batches_failed")
    op.drop_column("scans", "batches_completed")
    op.drop_column("scans", "batches_total")
    op.drop_column("scans", "fallback_provider_used")
    op.drop_column("scans", "primary_llm_model")
    op.drop_column("scans", "provider_failures")
    op.drop_column("scans", "provider_successes")
    op.drop_column("scans", "llm_usd_estimated")
