"""Idempotent intent upsert key + partial-scan / counter columns.

Revision ID: 0010_intent_key_and_partial
Revises: 0009_scan_observability
Create Date: 2026-10-16 20:00:00.000000

Does not drop or recreate the database. Adds:
- intents.intent_key + unique (scan_id, intent_key) for per-batch upserts
- scan-level failed_intent_ids / failure_reason for truthful partial status
- retry/failover/cache/evaluation counters (Phase 5)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_intent_key_and_partial"
down_revision: str | None = "0009_scan_observability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("intents", sa.Column("intent_key", sa.String(length=128), nullable=True))
    op.create_index(
        "uq_intents_scan_intent_key",
        "intents",
        ["scan_id", "intent_key"],
        unique=True,
        postgresql_where=sa.text("intent_key IS NOT NULL"),
        sqlite_where=sa.text("intent_key IS NOT NULL"),
    )
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.add_column("scans", sa.Column("provider_retries", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("provider_failovers", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("duplicate_requests_joined", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("cache_hits", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("evaluations_valid", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("failed_intent_ids", json_type, nullable=True))
    op.add_column("scans", sa.Column("failure_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scans", "failure_reason")
    op.drop_column("scans", "failed_intent_ids")
    op.drop_column("scans", "evaluations_valid")
    op.drop_column("scans", "cache_hits")
    op.drop_column("scans", "duplicate_requests_joined")
    op.drop_column("scans", "provider_failovers")
    op.drop_column("scans", "provider_retries")
    op.drop_index("uq_intents_scan_intent_key", table_name="intents")
    op.drop_column("intents", "intent_key")
