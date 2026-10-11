import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
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
    repo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="in_progress", index=True
    )

    # Findability F-Score metrics (0.0 to 100.0)
    f_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    s_ans: Mapped[float | None] = mapped_column(Float, nullable=True)
    s_con: Mapped[float | None] = mapped_column(Float, nullable=True)
    s_str: Mapped[float | None] = mapped_column(Float, nullable=True)
    s_acc: Mapped[float | None] = mapped_column(Float, nullable=True)

    # P1: durable scan-integrity contract (nullable for legacy rows)
    integrity_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    result_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)
    score_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    patches_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    remediation_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    intelligence_warnings: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    data_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_calls_made: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dag_evaluations_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    synthetic_intents_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pages_crawled: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dom_chunks_extracted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    remediation_runs: Mapped[list["RemediationRun"]] = relationship(
        "RemediationRun", back_populates="scan", cascade="all, delete-orphan"
    )
    verification_runs: Mapped[list["VerificationRun"]] = relationship(
        "VerificationRun", back_populates="scan", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["ScanJob"]] = relationship(
        "ScanJob", back_populates="scan", cascade="all, delete-orphan"
    )


class ScanJob(Base):
    """PostgreSQL-backed durable scan execution job (Phase 3)."""

    __tablename__ = "scan_jobs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_scan_jobs_idempotency"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False, default="scan_pipeline")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    llm_calls_checkpoint: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan: Mapped[Scan] = relationship("Scan", back_populates="jobs")


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
    persona: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
    # Same chunk may be cited again in a later observation_phase (e.g. post-PR verify).
    __table_args__ = (
        UniqueConstraint(
            "intent_id",
            "chunk_id",
            "observation_phase",
            name="uq_evidence_intent_chunk_phase",
        ),
    )

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
    # Phase 2 provenance (nullable columns remain readable for pre-0003 rows)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    dom_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    observation_phase: Mapped[str] = mapped_column(
        String(50), nullable=False, default="scan", server_default="scan"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

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
    values: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
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


class RemediationRun(Base):
    """Recoverable GitHub PR lifecycle state (Phase 2 Stage 5)."""

    __tablename__ = "remediation_runs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_remediation_runs_idempotency"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    base_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    head_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    changed_files: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    validation_results: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan: Mapped[Scan] = relationship("Scan", back_populates="remediation_runs")
    verification_runs: Mapped[list["VerificationRun"]] = relationship(
        "VerificationRun", back_populates="remediation_run", cascade="all, delete-orphan"
    )


class VerificationRun(Base):
    """Post-PR verification against a specific revision (Phase 2 Stage 6)."""

    __tablename__ = "verification_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    remediation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("remediation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluated_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issue_outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    operational_status: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    fresh_evidence: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scan: Mapped[Scan] = relationship("Scan", back_populates="verification_runs")
    remediation_run: Mapped[RemediationRun] = relationship(
        "RemediationRun", back_populates="verification_runs"
    )
