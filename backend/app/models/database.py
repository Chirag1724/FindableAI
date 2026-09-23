import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Computed, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # Fallback to Text or custom type representation if pgvector package is not yet initialized
    from sqlalchemy.types import UserDefinedType

    class Vector(UserDefinedType):  # type: ignore[no-redef]
        def __init__(self, dim: int = 1536):
            self.dim = dim

        def get_col_spec(self, **kw):
            return f"vector({self.dim})"


class Base(DeclarativeBase):
    pass


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scans: Mapped[list["Scan"]] = relationship(
        "Scan", back_populates="business", cascade="all, delete-orphan"
    )


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="in_progress", index=True
    )

    # Findability F-Score metrics (0.0 to 100.0)
    f_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    s_ans: Mapped[float | None] = mapped_column(Float, nullable=True)
    s_con: Mapped[float | None] = mapped_column(Float, nullable=True)
    s_str: Mapped[float | None] = mapped_column(Float, nullable=True)
    s_acc: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    business: Mapped[Business | None] = relationship("Business", back_populates="scans")
    dom_chunks: Mapped[list["DOMChunk"]] = relationship(
        "DOMChunk", back_populates="scan", cascade="all, delete-orphan"
    )
    intents: Mapped[list["Intent"]] = relationship(
        "Intent", back_populates="scan", cascade="all, delete-orphan"
    )
    contradictions: Mapped[list["Contradiction"]] = relationship(
        "Contradiction", back_populates="scan", cascade="all, delete-orphan"
    )
    patches: Mapped[list["Patch"]] = relationship(
        "Patch", back_populates="scan", cascade="all, delete-orphan"
    )


class DOMChunk(Base):
    __tablename__ = "dom_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    dom_path: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tag: Mapped[str] = mapped_column(String(50), nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 1536-dimensional vector for hybrid semantic search
    embedding: Mapped[Any | None] = mapped_column(Vector(1536), nullable=True)

    # Full text search tsvector column for BM25 keyword matching
    content_tsv: Mapped[Any | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan: Mapped[Scan] = relationship("Scan", back_populates="dom_chunks")
    evidence_links: Mapped[list["Evidence"]] = relationship(
        "Evidence", back_populates="chunk", cascade="all, delete-orphan"
    )


class Intent(Base):
    __tablename__ = "intents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # SUPPORTED | CONTRADICTED | UNKNOWN
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan: Mapped[Scan] = relationship("Scan", back_populates="intents")
    evidence_items: Mapped[list["Evidence"]] = relationship(
        "Evidence", back_populates="intent", cascade="all, delete-orphan"
    )


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dom_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    rrf_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    intent: Mapped[Intent] = relationship("Intent", back_populates="evidence_items")
    chunk: Mapped[DOMChunk] = relationship("DOMChunk", back_populates="evidence_links")


class Contradiction(Base):
    __tablename__ = "contradictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity: Mapped[str] = mapped_column(String(255), nullable=False)
    conflict: Mapped[str] = mapped_column(Text, nullable=False)
    values: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    severity: Mapped[str] = mapped_column(
        String(50), nullable=False, default="HARD_CONTRADICTION"
    )  # HARD_CONTRADICTION | SOFT_INCONSISTENCY

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan: Mapped[Scan] = relationship("Scan", back_populates="contradictions")


class Patch(Base):
    __tablename__ = "patches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    patch_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # json_ld | meta_tag | content_update
    content: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    pr_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan: Mapped[Scan] = relationship("Scan", back_populates="patches")
