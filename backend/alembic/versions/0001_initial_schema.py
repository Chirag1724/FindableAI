"""Initial schema with pgvector, businesses, scans, dom_chunks, intents, evidence, contradictions, patches

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-23 23:45:00.000000

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Businesses table
    op.create_table(
        "businesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_businesses_url", "businesses", ["url"], unique=True)

    # 3. Scans table
    op.create_table(
        "scans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="in_progress", nullable=False),
        sa.Column("f_score", sa.Float(), nullable=True),
        sa.Column("s_ans", sa.Float(), nullable=True),
        sa.Column("s_con", sa.Float(), nullable=True),
        sa.Column("s_str", sa.Float(), nullable=True),
        sa.Column("s_acc", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_scans_url", "scans", ["url"])
    op.create_index("ix_scans_status", "scans", ["status"])
    op.create_index("ix_scans_business_id", "scans", ["business_id"])

    # 4. DOM Chunks table
    op.create_table(
        "dom_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("dom_path", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tag", sa.String(length=50), nullable=False),
        sa.Column("word_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1536), nullable=True),
        sa.Column(
            "content_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_dom_chunks_scan_id", "dom_chunks", ["scan_id"])
    op.create_index(
        "ix_dom_chunks_content_tsv", "dom_chunks", ["content_tsv"], postgresql_using="gin"
    )
    # HNSW index for high performance vector similarity search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dom_chunks_embedding_hnsw "
        "ON dom_chunks USING hnsw (embedding vector_cosine_ops);"
    )

    # 5. Intents table
    op.create_table(
        "intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_intents_scan_id", "intents", ["scan_id"])

    # 6. Evidence table
    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "intent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("intents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dom_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("rrf_score", sa.Float(), nullable=True),
    )
    op.create_index("ix_evidence_intent_id", "evidence", ["intent_id"])
    op.create_index("ix_evidence_chunk_id", "evidence", ["chunk_id"])

    # 7. Contradictions table
    op.create_table(
        "contradictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity", sa.String(length=255), nullable=False),
        sa.Column("conflict", sa.Text(), nullable=False),
        sa.Column("values", postgresql.JSONB(), nullable=False),
        sa.Column(
            "severity", sa.String(length=50), server_default="HARD_CONTRADICTION", nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_contradictions_scan_id", "contradictions", ["scan_id"])

    # 8. Patches table
    op.create_table(
        "patches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("patch_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="1", nullable=False),
        sa.Column("pr_url", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_patches_scan_id", "patches", ["scan_id"])


def downgrade() -> None:
    op.drop_table("patches")
    op.drop_table("contradictions")
    op.drop_table("evidence")
    op.drop_table("intents")
    op.drop_table("dom_chunks")
    op.drop_table("scans")
    op.drop_table("businesses")
