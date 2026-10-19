"""AI Website Health Brief cache table (scan_summaries).

Revision ID: 0018_scan_summaries
Revises: 0017_phase3_integrity
Create Date: 2026-10-19 23:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_scan_summaries"
down_revision: str | None = "0017_phase3_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_summaries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scan_id",
            "input_hash",
            "prompt_version",
            "model",
            name="uq_scan_summaries_cache_key",
        ),
    )
    op.create_index(
        "ix_scan_summaries_scan_id",
        "scan_summaries",
        ["scan_id"],
        unique=False,
    )
    op.create_index(
        "ix_scan_summaries_org_id",
        "scan_summaries",
        ["org_id"],
        unique=False,
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_scan_summaries_scan_created",
            "scan_summaries",
            ["scan_id", "created_at"],
            unique=False,
            postgresql_ops={"created_at": "DESC"},
        )
    else:
        op.create_index(
            "ix_scan_summaries_scan_created",
            "scan_summaries",
            ["scan_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index("ix_scan_summaries_scan_created", table_name="scan_summaries")
    op.drop_index("ix_scan_summaries_org_id", table_name="scan_summaries")
    op.drop_index("ix_scan_summaries_scan_id", table_name="scan_summaries")
    op.drop_table("scan_summaries")
