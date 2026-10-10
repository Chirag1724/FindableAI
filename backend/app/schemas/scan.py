from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from .fscore import FScoreBreakdown
from .intelligence import Contradiction, IntentEvaluation
from .patch import PatchProposal


class ScanStatus(StrEnum):
    PENDING = "pending"
    CRAWLING = "crawling"
    EXTRACTING_DOM = "extracting_dom"
    SYNTHESIZING_INTENTS = "synthesizing_intents"
    HYBRID_RETRIEVAL = "hybrid_retrieval"
    NLI_EVALUATION = "nli_evaluation"
    COMPUTING_FSCORE = "computing_fscore"
    GENERATING_PATCHES = "generating_patches"
    COMPLETED = "completed"
    FAILED = "failed"


class ScanRequest(BaseModel):
    url: str = Field(..., description="Target webpage URL to audit for machine discoverability")
    max_pages: int = Field(default=5, ge=1, le=25, description="Max depth of page crawling")
    personas: list[str] | None = Field(
        default=["cto", "developer", "procurement"],
        description="Buyer/user personas to simulate for synthetic search queries",
    )
    repo_url: str | None = Field(
        default=None,
        description="Optional connected GitHub repository URL for automated PR generation",
    )


class ScanStatusEvent(BaseModel):
    scan_id: str
    status: ScanStatus
    progress_percent: int = Field(ge=0, le=100)
    current_step: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CrawledPageDetail(BaseModel):
    url: str
    status_code: int = 200
    chunks_count: int = 0
    load_time_ms: int = 0
    is_spa: bool = False
    title: str | None = None


class AuditSummary(BaseModel):
    pages_crawled: int
    dom_chunks_extracted: int
    intents_generated: int
    contradictions_detected: int
    execution_time_seconds: float
    max_pages_requested: int | None = None
    crawled_pages: list[CrawledPageDetail] = Field(
        default_factory=list, description="Details of each URL crawled during scan"
    )
    # Integrity / coverage (additive; optional for older clients)
    dag_evaluations_count: int | None = Field(
        default=None,
        description="Intent evaluations produced by the DAG before any synthetic fill",
    )
    synthetic_intents_count: int | None = Field(
        default=None,
        description="Count of synthetically injected intent evaluations (0 if none)",
    )


class ScanResponse(BaseModel):
    scan_id: str
    target_url: str
    status: ScanStatus
    created_at: datetime
    completed_at: datetime | None = None
    f_score: FScoreBreakdown | None = None
    summary: AuditSummary | None = None
    crawled_pages: list[CrawledPageDetail] = Field(
        default_factory=list, description="Details of each URL crawled during scan"
    )
    patches: list[PatchProposal] = Field(default_factory=list)
    intents: list[IntentEvaluation] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    error: str | None = None
    execution_mode: str | None = Field(
        default=None,
        description=(
            "How intelligence ran: 'real_llm' only when DAG evaluations exist, "
            "LLM calls were made, and no synthetic/mock intelligence was substituted. "
            "Otherwise 'synthetic_fallback' or 'deterministic'."
        ),
    )
    data_source: str | None = Field(
        default=None,
        description=(
            "Provenance once integrity is decided: 'live_pipeline' or 'synthetic_fallback'. "
            "None/unset until the scan finishes — never imply live pipeline before that."
        ),
    )
    result_source: str | None = Field(
        default=None,
        description=(
            "Intent/evaluation provenance: real_pipeline | partial_real | "
            "synthetic_fallback | inconclusive"
        ),
    )
    outcome: str | None = Field(
        default=None,
        description="Scan outcome: success | partial | inconclusive | failed",
    )
    score_source: str | None = Field(
        default=None,
        description="F-Score provenance: deterministic_scorer | mock | none",
    )
    patches_source: str | None = Field(
        default=None,
        description="Patch provenance: assembler | mock | none",
    )
    remediation_eligible: bool | None = Field(
        default=None,
        description=(
            "True only when patches (including an empty real assembler result) "
            "may be treated as evidence-backed remediation from a real_llm audit"
        ),
    )
    intelligence_warnings: list[str] = Field(
        default_factory=list,
        description="Human-readable integrity warnings for API/UI consumers",
    )
    llm_calls_made: int | None = Field(
        default=0,
        description="Total LLM provider calls consumed via BudgetGuard",
    )
    repo_url: str | None = Field(
        default=None,
        description="Optional connected GitHub repository URL for automated PR generation",
    )
    github_repo_url: str | None = Field(
        default=None,
        description="Alias for repo_url",
    )
