"""Add durable scan integrity columns for cold hydration (P1).

Revision ID: 0002_scan_integrity
Revises: 0001_initial_schema
Create Date: 2026-10-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_scan_integrity"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("integrity_version", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("execution_mode", sa.String(length=50), nullable=True))
    op.add_column("scans", sa.Column("result_source", sa.String(length=50), nullable=True))
    op.add_column("scans", sa.Column("outcome", sa.String(length=50), nullable=True))
    op.add_column("scans", sa.Column("score_source", sa.String(length=50), nullable=True))
    op.add_column("scans", sa.Column("patches_source", sa.String(length=50), nullable=True))
    op.add_column("scans", sa.Column("remediation_eligible", sa.Boolean(), nullable=True))
    op.add_column(
        "scans",
        sa.Column(
            "intelligence_warnings",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column("scans", sa.Column("data_source", sa.String(length=50), nullable=True))
    op.add_column("scans", sa.Column("llm_calls_made", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("dag_evaluations_count", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("synthetic_intents_count", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("pages_crawled", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("dom_chunks_extracted", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("error", sa.Text(), nullable=True))
    op.add_column(
        "scans",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scans", "completed_at")
    op.drop_column("scans", "error")
    op.drop_column("scans", "dom_chunks_extracted")
    op.drop_column("scans", "pages_crawled")
    op.drop_column("scans", "synthetic_intents_count")
    op.drop_column("scans", "dag_evaluations_count")
    op.drop_column("scans", "llm_calls_made")
    op.drop_column("scans", "data_source")
    op.drop_column("scans", "intelligence_warnings")
    op.drop_column("scans", "remediation_eligible")
    op.drop_column("scans", "patches_source")
    op.drop_column("scans", "score_source")
    op.drop_column("scans", "outcome")
    op.drop_column("scans", "result_source")
    op.drop_column("scans", "execution_mode")
    op.drop_column("scans", "integrity_version")
