"""Phase 3: evidence provenance fields + API key role for membership gates.

Revision ID: 0017_phase3_integrity
Revises: 0016_scan_recovery_requests
Create Date: 2026-10-18 12:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_phase3_integrity"
down_revision: str | None = "0016_scan_recovery_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "evidence", sa.Column("cache_fingerprint", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "dom_chunks", sa.Column("content_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "api_keys",
        sa.Column("role", sa.String(length=50), nullable=False, server_default="member"),
    )
    # Optional link to org_memberships.user_id so membership removal can revoke keys.
    op.add_column("api_keys", sa.Column("user_id", sa.UUID(), nullable=True))
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_column("api_keys", "user_id")
    op.drop_column("api_keys", "role")
    op.drop_column("dom_chunks", "content_hash")
    op.drop_column("evidence", "cache_fingerprint")
    op.drop_column("evidence", "content_hash")
