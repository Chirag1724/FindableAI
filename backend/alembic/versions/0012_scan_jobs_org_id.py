"""Add nullable org_id to scan_jobs for tenant-scoped durable jobs.

Revision ID: 0012_scan_jobs_org_id
Revises: 0011_organizations_and_api_keys
Create Date: 2026-10-17 22:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012_scan_jobs_org_id"
down_revision: str | None = "0011_organizations_and_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_type = sa.UUID().with_variant(postgresql.UUID(as_uuid=True), "postgresql")
    op.add_column(
        "scan_jobs",
        sa.Column(
            "org_id",
            uuid_type,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_scan_jobs_org_id", "scan_jobs", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_scan_jobs_org_id", table_name="scan_jobs")
    op.drop_column("scan_jobs", "org_id")
