"""Add composite GIN indexes, active queue partial indexing, and tenant token ledger.

Revision ID: 0012_composite_indexes_and_token_ledger
Revises: 0011_organizations_and_api_keys
Create Date: 2026-10-17 19:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012_composite_indexes_and_token_ledger"
down_revision: str | None = "0011_organizations_and_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_type = sa.UUID().with_variant(postgresql.UUID(as_uuid=True), "postgresql")

    # 1. Tenant Token & Spend Ledger Table
    op.create_table(
        "org_token_ledger",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "org_id",
            uuid_type,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scan_id",
            uuid_type,
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_org_token_ledger_org_id", "org_token_ledger", ["org_id"])
    op.create_index("ix_org_token_ledger_scan_id", "org_token_ledger", ["scan_id"])
    op.create_index(
        "ix_org_token_ledger_org_created",
        "org_token_ledger",
        ["org_id", "created_at"],
    )

    # 2. High-Performance PostgreSQL-Specific Indexing
    if is_postgres:
        # Enable btree_gin to support composite (scan_id, content_tsv) GIN index
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin;")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_dom_chunks_scan_tsv "
            "ON dom_chunks USING gin (scan_id, content_tsv);"
        )

        # Partial index for worker queue polling: only index active / claimable jobs
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_scan_jobs_active_queue "
            "ON scan_jobs (status, available_at, lease_expires_at) "
            "WHERE status IN ('queued', 'retry_scheduled', 'claimed', 'running');"
        )

        # Partial index for active scans (in-flight poll & SSE stream recovery)
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_scans_active "
            "ON scans (id, status) "
            "WHERE status NOT IN ('completed', 'failed');"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_scans_active;")
        op.execute("DROP INDEX IF EXISTS ix_scan_jobs_active_queue;")
        op.execute("DROP INDEX IF EXISTS ix_dom_chunks_scan_tsv;")

    op.drop_index("ix_org_token_ledger_org_created", table_name="org_token_ledger")
    op.drop_index("ix_org_token_ledger_scan_id", table_name="org_token_ledger")
    op.drop_index("ix_org_token_ledger_org_id", table_name="org_token_ledger")
    op.drop_table("org_token_ledger")
