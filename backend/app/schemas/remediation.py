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
    lifecycle_state: str
    changed_files: list[Any] = Field(default_factory=list)
    validation_results: list[Any] = Field(default_factory=list)
    error: str | None = None
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


class VerifyRemediationRequest(BaseModel):
    remediation_run_id: UUID | None = None
    acceptance_keywords: list[str] = Field(default_factory=list)
