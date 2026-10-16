"""API schemas for remediation lifecycle and post-PR verification."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ValidationCheckOut(BaseModel):
    name: str
    status: str
    detail: str = ""
    safety_critical: bool = False


class PatchValidationResponse(BaseModel):
    eligible_for_validated_pr: bool
    checks: list[ValidationCheckOut]


class RemediationRunOut(BaseModel):
    id: UUID
    scan_id: UUID
    idempotency_key: str
    repo_full_name: str
    base_branch: str
    base_sha: str | None = None
    head_branch: str | None = None
    head_sha: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    lifecycle_state: str = Field(
        description=(
            "Durable remediation FSM state. "
            "'verified' means a heuristic post-PR check reported fixed — "
            "not a full website re-scan. Always consult verification_runs.fully_verified."
        ),
    )
    changed_files: list[Any] = Field(default_factory=list)
    validation_results: list[Any] = Field(default_factory=list)
    error: str | None = None
    state_revision: int | None = Field(
        default=None,
        description="Optimistic concurrency token for CAS lifecycle transitions",
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VerificationRunOut(BaseModel):
    id: UUID
    scan_id: UUID
    remediation_run_id: UUID
    evaluated_revision: str | None = None
    issue_outcome: str
    operational_status: str
    detail: str | None = None
    fresh_evidence: list[Any] = Field(default_factory=list)
    created_at: datetime | None = None
    verification_method: str = Field(
        default="heuristic_post_pr",
        description=(
            "How verification was performed. Current implementation is always "
            "'heuristic_post_pr' (keyword/content checks on PR head files), "
            "never a full website re-scan."
        ),
    )
    fully_verified: bool = Field(
        default=False,
        description=(
            "True only for a complete fresh re-scan verification. "
            "Heuristic post-PR checks always leave this false."
        ),
    )
    is_full_rescan: bool = Field(
        default=False,
        description="Whether verification re-ran the full FindableAI scan pipeline",
    )


class VerifyRemediationRequest(BaseModel):
    remediation_run_id: UUID | None = None
    acceptance_keywords: list[str] = Field(default_factory=list)
