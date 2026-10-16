"""Durable scan progress events and job checkpoints.

Revision ID: 0006_progress_checkpoints
Revises: 0005_scan_jobs
Create Date: 2026-10-14 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_progress_checkpoints"
down_revision: str | None = "0005_scan_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("progress_stage", sa.String(length=100), nullable=True))
    op.add_column("scans", sa.Column("progress_message", sa.Text(), nullable=True))
    op.add_column("scans", sa.Column("progress_percent", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("progress_current", sa.Integer(), nullable=True))
    op.add_column("scans", sa.Column("progress_total", sa.Integer(), nullable=True))
    op.add_column(
        "scans",
        sa.Column("progress_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "scan_jobs",
        sa.Column(
            "checkpoint_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column(
        "scan_jobs",
        sa.Column("llm_usd_checkpoint", sa.Float(), nullable=False, server_default="0"),
    )

    op.add_column(
        "verification_runs",
        sa.Column(
            "verification_method",
            sa.String(length=64),
            nullable=False,
            server_default="heuristic_post_pr",
        ),
    )
    op.add_column(
        "verification_runs",
        sa.Column(
            "fully_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "verification_runs",
        sa.Column(
            "is_full_rescan",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "scan_progress_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False, server_default="progress"),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("stage", sa.String(length=100), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("percent", sa.Integer(), nullable=True),
        sa.Column("current", sa.Integer(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("scan_id", "seq", name="uq_scan_progress_events_scan_seq"),
    )
    op.create_index(
        "ix_scan_progress_events_scan_id_seq",
        "scan_progress_events",
        ["scan_id", "seq"],
    )


def downgrade() -> None:
    op.drop_index("ix_scan_progress_events_scan_id_seq", table_name="scan_progress_events")
    op.drop_table("scan_progress_events")
    op.drop_column("verification_runs", "is_full_rescan")
    op.drop_column("verification_runs", "fully_verified")
    op.drop_column("verification_runs", "verification_method")
    op.drop_column("scan_jobs", "llm_usd_checkpoint")
    op.drop_column("scan_jobs", "checkpoint_json")
    op.drop_column("scans", "progress_updated_at")
    op.drop_column("scans", "progress_total")
    op.drop_column("scans", "progress_current")
    op.drop_column("scans", "progress_percent")
    op.drop_column("scans", "progress_message")
    op.drop_column("scans", "progress_stage")
