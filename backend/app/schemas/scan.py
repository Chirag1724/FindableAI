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
    AUDITED = "audited"
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
        description="Buyer/user personas to simulate for intent queries",
    )
    repo_url: str | None = Field(
        default=None,
        description="Optional connected GitHub repository URL for automated PR generation",
    )
    auto_evaluate: bool = Field(
        default=True,
        description="Whether to automatically proceed to LLM intent & entailment evaluation stage",
    )


class ScanStatusEvent(BaseModel):
    scan_id: str
    status: ScanStatus
    progress_percent: int = Field(ge=0, le=100)
    current_step: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    seq: int | None = Field(
        default=None,
        description="Monotonic per-scan durable event sequence when persisted",
    )
    progress_current: int | None = None
    progress_total: int | None = None


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
    org_id: str | None = Field(
        default=None,
        description="Owning organization UUID when created under an org API key; null for admin/legacy",
    )
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
        description="Total LLM provider call reservations via BudgetGuard (attempts)",
    )
    llm_usd_estimated: float | None = Field(
        default=None,
        description=(
            "Estimated USD spend from BudgetGuard (LLM_ESTIMATED_USD_PER_CALL). "
            "Not a provider invoice; never treat as exact cost."
        ),
    )
    llm_usd_provider_reported: float | None = Field(
        default=None,
        description="Provider-reported USD when available; null if not returned by provider",
    )
    cost_basis: str | None = Field(
        default=None,
        description="estimated | provider_reported | unknown — how cost figures should be read",
    )
    provider_successes: int | None = Field(
        default=None, description="Completed provider invocations that returned a valid response"
    )
    provider_failures: int | None = Field(
        default=None, description="Completed provider invocations that failed after reservation"
    )
    primary_llm_model: str | None = Field(
        default=None, description="Primary model spec used for this scan (no secrets)"
    )
    fallback_provider_used: bool | None = Field(
        default=None, description="True when a failover provider was used for at least one call"
    )
    batches_total: int | None = Field(
        default=None, description="Known NLI batch total; null until established"
    )
    batches_completed: int | None = Field(
        default=None, description="Unique NLI batches completed successfully"
    )
    batches_failed: int | None = Field(
        default=None, description="NLI batches that failed (may later retry)"
    )
    llm_tokens_in: int | None = Field(
        default=None, description="Cumulative prompt tokens when provider reports usage"
    )
    llm_tokens_out: int | None = Field(
        default=None, description="Cumulative completion tokens when provider reports usage"
    )
    job_status: str | None = Field(
        default=None, description="Durable scan_jobs.status when durable jobs are enabled"
    )
    job_attempt_count: int | None = Field(default=None, description="Durable job attempt_count")
    job_max_attempts: int | None = Field(default=None, description="Durable job max_attempts")
    worker_heartbeat_recent: bool | None = Field(
        default=None,
        description=(
            "True when a worker heartbeat was seen within SCAN_JOB_HEARTBEAT_TIMEOUT_SECONDS. "
            "False + job_status=queued means the scan is waiting with no active worker."
        ),
    )
    repo_url: str | None = Field(
        default=None,
        description="Optional connected GitHub repository URL for automated PR generation",
    )
    github_repo_url: str | None = Field(
        default=None,
        description="Alias for repo_url",
    )
    # Durable progress snapshot (authoritative across API/worker processes)
    progress_percent: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Persisted progress percent from the worker; None if unknown",
    )
    progress_stage: str | None = Field(default=None, description="Current durable stage label")
    progress_message: str | None = Field(
        default=None, description="Latest durable progress message"
    )
    progress_current: int | None = Field(
        default=None, description="Completed work units when known"
    )
    progress_total: int | None = Field(default=None, description="Total work units when known")
    progress_seq: int | None = Field(
        default=None, description="Last durable progress event sequence number"
    )
    failed_intent_ids: list[str] = Field(
        default_factory=list,
        description="Intent IDs that did not persist (failed ACT batch); empty on full success",
    )
    failure_reason: str | None = Field(
        default=None,
        description="Public reason when outcome is partial or failed (no secrets)",
    )
    provider_retries: int | None = Field(default=None, description="Same-provider retries")
    provider_failovers: int | None = Field(default=None, description="Provider failovers")
    duplicate_requests_joined: int | None = Field(
        default=None, description="In-flight duplicate requests coalesced"
    )
    cache_hits: int | None = Field(
        default=None, description="Cache hits that skipped a provider call"
    )
    evaluations_valid: int | None = Field(
        default=None, description="Evaluations that passed citation validation"
    )


class ScanJobStatusResponse(BaseModel):
    """Authorized durable job status for a scan (no secrets / raw provider errors)."""

    scan_id: str
    job_id: str | None = None
    job_status: str | None = None
    job_type: str | None = None
    attempt_count: int | None = None
    max_attempts: int | None = None
    fencing_token: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    worker_heartbeat_recent: bool | None = Field(
        default=None,
        description="True when last_heartbeat_at is within the heartbeat timeout window",
    )
    error_code: str | None = None
    error_detail: str | None = Field(
        default=None, description="Sanitized public error detail (never raw provider payloads)"
    )
    failure_category: str | None = None
    llm_calls_checkpoint: int | None = None
    llm_usd_checkpoint: float | None = Field(
        default=None,
        description="Estimated USD checkpoint (not a provider invoice)",
    )
    cost_basis: str = "estimated"
    progress_percent: int | None = None
    progress_stage: str | None = None
    progress_message: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    progress_seq: int | None = None
    batches_total: int | None = None
    batches_completed: int | None = None
    batches_failed: int | None = None
    provider_successes: int | None = None
    provider_failures: int | None = None
    primary_llm_model: str | None = None
    fallback_provider_used: bool | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    correlation_id: str | None = None
