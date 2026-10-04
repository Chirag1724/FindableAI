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


class AuditSummary(BaseModel):
    pages_crawled: int
    dom_chunks_extracted: int
    intents_generated: int
    contradictions_detected: int
    execution_time_seconds: float


class ScanResponse(BaseModel):
    scan_id: str
    target_url: str
    status: ScanStatus
    created_at: datetime
    completed_at: datetime | None = None
    f_score: FScoreBreakdown | None = None
    summary: AuditSummary | None = None
    patches: list[PatchProposal] = Field(default_factory=list)
    intents: list[IntentEvaluation] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    error: str | None = None
    execution_mode: str | None = Field(
        default=None,
        description="Execution mode: 'real_llm' or 'deterministic_fallback'",
    )
    data_source: str = Field(
        default="live_pipeline",
        description="Data provenance: 'live_pipeline' or 'synthetic_fallback'",
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
