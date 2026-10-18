"""Add recovery_requests counter for budget integrity observability.

Revision ID: 0016_scan_recovery_requests
Revises: 0015_scan_cancel_requested
Create Date: 2026-10-18 11:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_scan_recovery_requests"
down_revision: str | None = "0015_scan_cancel_requested"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scans",
        sa.Column("recovery_requests", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scans", "recovery_requests")
