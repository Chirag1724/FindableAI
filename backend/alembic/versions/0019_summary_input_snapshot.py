"""Persist versioned AI Summary input snapshot on scans.

Revision ID: 0019_summary_input_snapshot
Revises: 0018_scan_summaries
Create Date: 2026-10-20 02:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019_summary_input_snapshot"
down_revision: str | None = "0018_scan_summaries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scans",
        sa.Column(
            "summary_input",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "scans",
        sa.Column("summary_input_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "scans",
        sa.Column(
            "summary_input_prepared_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("scans", "summary_input_prepared_at")
    op.drop_column("scans", "summary_input_hash")
    op.drop_column("scans", "summary_input")
