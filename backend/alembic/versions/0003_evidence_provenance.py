"""Add evidence provenance columns and intent+chunk+phase uniqueness (Phase 2 Stage 2).

Revision ID: 0003_evidence_provenance
Revises: 0002_scan_integrity
Create Date: 2026-10-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_evidence_provenance"
down_revision: str | None = "0002_scan_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("source_url", sa.String(length=1024), nullable=True))
    op.add_column("evidence", sa.Column("excerpt", sa.Text(), nullable=True))
    op.add_column("evidence", sa.Column("dom_path", sa.Text(), nullable=True))
    op.add_column("evidence", sa.Column("evidence_role", sa.String(length=50), nullable=True))
    op.add_column(
        "evidence",
        sa.Column(
            "observation_phase",
            sa.String(length=50),
            nullable=False,
            server_default="scan",
        ),
    )
    op.add_column(
        "evidence",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Deduplicate legacy duplicates before unique constraint (keep lowest id).
    # Phase is always 'scan' for pre-existing rows after the server_default backfill.
    op.execute(
        """
        DELETE FROM evidence e
        USING evidence e2
        WHERE e.intent_id = e2.intent_id
          AND e.chunk_id = e2.chunk_id
          AND e.observation_phase = e2.observation_phase
          AND e.id > e2.id
        """
    )
    op.create_unique_constraint(
        "uq_evidence_intent_chunk_phase",
        "evidence",
        ["intent_id", "chunk_id", "observation_phase"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_evidence_intent_chunk_phase", "evidence", type_="unique")
    op.drop_column("evidence", "created_at")
    op.drop_column("evidence", "observation_phase")
    op.drop_column("evidence", "evidence_role")
    op.drop_column("evidence", "dom_path")
    op.drop_column("evidence", "excerpt")
    op.drop_column("evidence", "source_url")
