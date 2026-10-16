"""Final orchestration result schema (P2-4.1)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.orchestration.state import ScanPhase
from app.schemas.github_pr import PREngineResult
from app.schemas.intelligence import Contradiction, IntentEvaluation
from app.schemas.patching import (
    FormattedPatch,
    ProjectedScoreResult,
    RemediationOpportunity,
)
from app.schemas.scoring import SchemaOrgReport, ScoreBreakdown


class OrchestrationResult(BaseModel):
    """Structured STOP output for a completed (or failed) DAG run."""

    scan_id: str = Field(..., min_length=1)
    final_state: ScanPhase
    success: bool
    remediation_available: bool = False
    pr_requested: bool = False
    pr_created: bool = False
    stage_trace: list[str] = Field(default_factory=list)
    intent_count: int = Field(default=0, ge=0)
    evaluation_count: int = Field(default=0, ge=0)
    contradiction_count: int = Field(default=0, ge=0)
    opportunity_count: int = Field(default=0, ge=0)
    patch_count: int = Field(default=0, ge=0)
    llm_calls_made: int | None = None
    llm_calls_remaining: int | None = None
    score: ScoreBreakdown | None = None
    schema_report: SchemaOrgReport | None = None
    evaluations: list[IntentEvaluation] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    opportunities: list[RemediationOpportunity] = Field(default_factory=list)
    patches: list[FormattedPatch] = Field(default_factory=list)
    projected_scores: list[ProjectedScoreResult] = Field(default_factory=list)
    pr_body: str | None = None
    pr_result: PREngineResult | None = None
    error: str | None = None
    error_reason: str | None = None
    failed_intent_ids: list[str] = Field(default_factory=list)
