"""Add remediation_runs.state_revision for optimistic concurrency (CAS).

Revision ID: 0008_remediation_state_revision
Revises: 0007_evidence_same_scan
Create Date: 2026-10-15 03:30:00.000000

``state_revision`` enables compare-and-set lifecycle transitions so concurrent
workers cannot overwrite a newer lifecycle result with a stale transition.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_remediation_state_revision"
down_revision: str | None = "0007_evidence_same_scan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "remediation_runs",
        sa.Column("state_revision", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("remediation_runs", "state_revision")
