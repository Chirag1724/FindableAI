"""GitHub PR engine contracts (P2-3.5 / P2-3.6).

Consumes validated Phase 3.1-3.4 artifacts. Does not recalculate scores or
re-format patches.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.intelligence import EvidenceReference, IntentEvaluation
from app.schemas.patching import (
    FormattedPatch,
    ProjectedScoreResult,
    RemediationOpportunity,
    SchemaRemediationTarget,
)


class PRFileChange(BaseModel):
    """One repository-relative file change for reporting and commit."""

    path: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    opportunity_ids: list[str] = Field(default_factory=list)
    schema_types: list[str] = Field(default_factory=list)


class PRReportData(BaseModel):
    """Authoritative inputs for deterministic PR Markdown (P2-3.6)."""

    scan_id: str = Field(..., min_length=1)
    current_score: float = Field(..., ge=0.0, le=100.0)
    projected_score: float = Field(..., ge=0.0, le=100.0)
    delta: float
    detected_gaps: list[str] = Field(default_factory=list)
    intent_evaluations: list[IntentEvaluation] = Field(default_factory=list)
    evidence_items: list[EvidenceReference] = Field(default_factory=list)
    file_changes: list[PRFileChange] = Field(default_factory=list)
    opportunity_titles: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _delta_matches(self) -> PRReportData:
        expected = self.projected_score - self.current_score
        if abs(self.delta - expected) > 1e-9:
            raise ValueError(
                f"delta must equal projected_score - current_score; "
                f"got {self.delta}, expected {expected}"
            )
        return self


class ValidatedRepoFileUpdate(BaseModel):
    """Normalized, validated full-file update ready for GitHub Contents API."""

    path: str = Field(..., min_length=1)
    content: str
    opportunity_ids: list[str] = Field(default_factory=list)
    schema_types: list[SchemaRemediationTarget] = Field(default_factory=list)


class PREngineRequest(BaseModel):
    """Caller-supplied, validated Phase 3 pipeline outputs for PR creation."""

    source_repo: str = Field(
        ...,
        min_length=3,
        description="Source repository as owner/name",
    )
    target_branch: str = Field(..., min_length=1)
    scan_id: str = Field(..., min_length=1)
    patches: list[FormattedPatch] = Field(default_factory=list)
    projections: list[ProjectedScoreResult] = Field(default_factory=list)
    opportunities: list[RemediationOpportunity] = Field(default_factory=list)
    intent_evaluations: list[IntentEvaluation] = Field(default_factory=list)
    commit_message: str = Field(
        default="feat: apply FindableAI remediation patches",
        min_length=1,
    )
    pr_title: str = Field(
        default="FindableAI: Apply remediation patches",
        min_length=1,
    )

    @field_validator("source_repo")
    @classmethod
    def _validate_repo(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned.count("/") != 1:
            raise ValueError("source_repo must be 'owner/name'")
        owner, name = cleaned.split("/")
        if not owner or not name:
            raise ValueError("source_repo must be 'owner/name'")
        if any(part in ("", ".", "..") for part in (owner, name)):
            raise ValueError("invalid source_repo")
        return cleaned

    @field_validator("patches")
    @classmethod
    def _only_pipeline_patches(cls, value: list[FormattedPatch]) -> list[FormattedPatch]:
        for item in value:
            if not isinstance(item, FormattedPatch):
                raise TypeError("patches must contain FormattedPatch instances")
        return value


class PREngineResult(BaseModel):
    """Structured result of a (possibly idempotent) PR operation."""

    source_repository: str
    fork_repository: str
    target_branch: str
    generated_branch: str
    commit_sha: str
    pr_number: int
    pr_url: str
    changed_files: list[str] = Field(default_factory=list)
    applied_opportunity_ids: list[str] = Field(default_factory=list)
    current_score: float = Field(..., ge=0.0, le=100.0)
    projected_score: float = Field(..., ge=0.0, le=100.0)
    delta: float
    pr_body: str = Field(..., min_length=1)
    reused_existing_pr: bool = False
    markdown_scan_id: str = Field(..., min_length=1)
