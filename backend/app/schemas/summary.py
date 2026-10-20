"""API contracts for the on-demand AI Website Health Brief."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SummaryStatus(StrEnum):
    NONE = "none"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class SummaryPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SummaryVerdict(StrEnum):
    SCAN_INCOMPLETE = "scan_incomplete"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ISSUES_FOUND = "issues_found"
    NO_CONFIRMED_ISSUES = "no_confirmed_issues"


class RemediationStatusLabel(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    UNAVAILABLE = "unavailable"


class SummaryCoverage(BaseModel):
    evaluations_completed: int | None = None
    evaluations_total: int | None = None
    findings_included: int = 0
    omitted_count: int = 0


class FactStatement(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    fact_ids: list[str] = Field(..., min_length=1)


class NextStepStatement(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    priority: SummaryPriority
    fact_ids: list[str] = Field(..., min_length=1)


class OverallAssessment(BaseModel):
    text: str = Field(..., min_length=1, max_length=400)
    fact_ids: list[str] = Field(default_factory=list)


class SummarySignals(BaseModel):
    all_intents_unknown: bool = False
    zero_dom_chunks: bool = False
    single_page_crawl: bool = False
    score_pillar_mismatch: bool = False
    lighthouse_available: bool = False
    remediation_unavailable_reason: str | None = None
    weighted_pillar_sum: float | None = None
    overall_score: float | None = None


class SummaryResponse(BaseModel):
    """GET/POST response for /scans/{id}/summary."""

    status: SummaryStatus
    verdict: SummaryVerdict | None = None
    overall_assessment: OverallAssessment | None = None
    what_the_scan_found: list[FactStatement] = Field(default_factory=list)
    why_it_matters: list[FactStatement] = Field(default_factory=list)
    evidence_gaps: list[FactStatement] = Field(default_factory=list)
    next_steps: list[NextStepStatement] = Field(default_factory=list)
    limitations: str = ""
    signals: SummarySignals | None = None
    omitted: list[str] = Field(default_factory=list)
    coverage: SummaryCoverage | None = None
    remediation_status: RemediationStatusLabel | None = None
    remediation_reason: str | None = None
    generated_at: datetime | None = None
    model: str | None = None
    cached: bool = False
    reason: str | None = None
    message: str | None = None
    retry_after: int | None = None
    # Legacy fields kept optional for older clients during transition
    headline: str | None = None
    overview: str | None = None
    items: list[Any] = Field(default_factory=list)


class LlmFactStatement(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    fact_ids: list[str] = Field(..., min_length=1)

    @field_validator("fact_ids")
    @classmethod
    def _ids(cls, value: list[str]) -> list[str]:
        cleaned = [str(v).strip() for v in value if str(v).strip()]
        if not cleaned:
            raise ValueError("fact_ids required")
        return cleaned


class LlmNextStep(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    priority: SummaryPriority = SummaryPriority.MEDIUM
    fact_ids: list[str] = Field(..., min_length=1)

    @field_validator("priority", mode="before")
    @classmethod
    def _prio(cls, value: Any) -> Any:
        if value is None or value == "":
            return SummaryPriority.MEDIUM
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("fact_ids")
    @classmethod
    def _ids(cls, value: list[str]) -> list[str]:
        cleaned = [str(v).strip() for v in value if str(v).strip()]
        if not cleaned:
            raise ValueError("fact_ids required")
        return cleaned


class LlmOverallAssessment(BaseModel):
    text: str = Field(..., min_length=1, max_length=400)
    fact_ids: list[str] = Field(default_factory=list)


def _coerce_statement_list(value: Any) -> Any:
    """Lite models often return a single object instead of a one-item array."""
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return value


class LlmSummaryPayload(BaseModel):
    """Structured LLM response — verdict is server-attached, not model-produced."""

    overall_assessment: LlmOverallAssessment
    what_the_scan_found: list[LlmFactStatement] = Field(default_factory=list, max_length=6)
    why_it_matters: list[LlmFactStatement] = Field(default_factory=list, max_length=6)
    evidence_gaps: list[LlmFactStatement] = Field(default_factory=list, max_length=6)
    next_steps: list[LlmNextStep] = Field(default_factory=list, max_length=6)
    limitations: str = Field(default="", max_length=1000)

    @field_validator(
        "what_the_scan_found",
        "why_it_matters",
        "evidence_gaps",
        "next_steps",
        mode="before",
    )
    @classmethod
    def _lists(cls, value: Any) -> Any:
        return _coerce_statement_list(value)

    @field_validator("limitations", mode="before")
    @classmethod
    def _limitations(cls, value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, dict):
            # Some models wrap limitations as {"text": "..."}.
            text = value.get("text")
            return text if isinstance(text, str) else ""
        return value


class SummaryReason(StrEnum):
    SCAN_QUEUED = "scan_queued"
    SCAN_RUNNING = "scan_running"
    SCAN_FAILED = "scan_failed"
    SCAN_CANCELLED = "scan_cancelled"
    SCAN_INELIGIBLE = "scan_ineligible"
    SUMMARY_GENERATING = "summary_generating"
    SUMMARY_RATE_LIMITED = "summary_rate_limited"
    SUMMARY_GENERATION_FAILED = "summary_generation_failed"
    PROVIDER_AUTH_ERROR = "provider_auth_error"
    PROVIDER_MODEL_REJECTED = "provider_model_rejected"


def http_detail(
    *,
    reason: str,
    message: str,
    retry_after: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"reason": reason, "message": message}
    if retry_after is not None:
        body["retry_after"] = retry_after
    if extra:
        body.update(extra)
    return body


__all__ = [
    "FactStatement",
    "LlmFactStatement",
    "LlmNextStep",
    "LlmOverallAssessment",
    "LlmSummaryPayload",
    "NextStepStatement",
    "OverallAssessment",
    "RemediationStatusLabel",
    "SummaryCoverage",
    "SummaryPriority",
    "SummaryReason",
    "SummaryResponse",
    "SummarySignals",
    "SummaryStatus",
    "SummaryVerdict",
    "http_detail",
]
