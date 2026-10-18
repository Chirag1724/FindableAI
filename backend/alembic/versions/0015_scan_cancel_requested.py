"""Add cancel_requested / cancel metadata for cooperative scan cancellation.

Revision ID: 0015_scan_cancel_requested
Revises: 0014_scans_org_created_id_index
Create Date: 2026-10-18 11:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_scan_cancel_requested"
down_revision: str | None = "0014_scans_org_created_id_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scan_jobs",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "scans",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("scans", sa.Column("cancel_reason", sa.Text(), nullable=True))
    op.add_column("scans", sa.Column("cancelled_by", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("scans", "cancelled_by")
    op.drop_column("scans", "cancel_reason")
    op.drop_column("scans", "cancel_requested")
    op.drop_column("scan_jobs", "cancel_requested")
