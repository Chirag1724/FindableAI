"""Composite index for tenant scan listing (org_id, created_at DESC, id DESC).

Revision ID: 0014_scans_org_created_id_index
Revises: 0013_scan_jobs_org_id
Create Date: 2026-10-18 10:40:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_scans_org_created_id_index"
down_revision: str | None = "0013_scan_jobs_org_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_scans_org_created_id",
            "scans",
            ["org_id", "created_at", "id"],
            postgresql_ops={"created_at": "DESC", "id": "DESC"},
        )
    else:
        op.create_index(
            "ix_scans_org_created_id",
            "scans",
            ["org_id", "created_at", "id"],
        )


def downgrade() -> None:
    op.drop_index("ix_scans_org_created_id", table_name="scans")
