"""Persisted remediation / PR lifecycle + post-PR verification (Stages 5-6)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.models.database import RemediationRun, VerificationRun

logger = logging.getLogger(__name__)

STATE_VALIDATING = "validating"
STATE_VALIDATION_FAILED = "validation_failed"
STATE_READY = "ready"
STATE_MUTATING = "mutating"
STATE_PR_OPEN = "pr_open"
STATE_PR_PERSIST_FAILED = "pr_persist_failed"
STATE_VERIFYING = "verifying"
STATE_VERIFIED = "verified"
STATE_BLOCKED = "blocked"
STATE_FAILED = "failed"

OUTCOME_FIXED = "fixed"
OUTCOME_UNRESOLVED = "unresolved"
OUTCOME_INCONCLUSIVE = "inconclusive"

OPS_OK = "ok"
OPS_ERROR = "error"
OPS_TIMEOUT = "timeout"
OPS_SKIPPED = "skipped"


def make_idempotency_key(scan_id: str, repo: str, branch: str) -> str:
    return f"{scan_id}|{repo}|{branch}"


async def get_run_by_idempotency(session: Any, key: str) -> RemediationRun | None:
    result = await session.execute(
        select(RemediationRun).where(RemediationRun.idempotency_key == key)
    )
    row = result.scalars().first()
    return row if isinstance(row, RemediationRun) else None


async def get_runs_for_scan(session: Any, scan_id: uuid.UUID) -> list[RemediationRun]:
    result = await session.execute(
        select(RemediationRun)
        .where(RemediationRun.scan_id == scan_id)
        .order_by(RemediationRun.created_at.desc())
    )
    return list(result.scalars().all())


async def upsert_remediation_run(
    session: Any,
    *,
    scan_id: uuid.UUID,
    idempotency_key: str,
    repo_full_name: str,
    base_branch: str,
    lifecycle_state: str,
    base_sha: str | None = None,
    head_branch: str | None = None,
    head_sha: str | None = None,
    pr_number: int | None = None,
    pr_url: str | None = None,
    changed_files: list[Any] | None = None,
    validation_results: list[Any] | None = None,
    error: str | None = None,
) -> RemediationRun:
    existing = await get_run_by_idempotency(session, idempotency_key)
    now = datetime.now(UTC)
    if existing is not None:
        # Idempotent recovery: do not reopen mutation if PR already recorded.
        if (
            existing.lifecycle_state == STATE_PR_OPEN
            and existing.pr_number is not None
            and lifecycle_state == STATE_MUTATING
        ):
            return existing
        existing.lifecycle_state = lifecycle_state
        existing.updated_at = now
        if base_sha is not None:
            existing.base_sha = base_sha
        if head_branch is not None:
            existing.head_branch = head_branch
        if head_sha is not None:
            existing.head_sha = head_sha
        if pr_number is not None:
            existing.pr_number = pr_number
        if pr_url is not None:
            existing.pr_url = pr_url
        if changed_files is not None:
            existing.changed_files = changed_files
        if validation_results is not None:
            existing.validation_results = validation_results
        if error is not None:
            existing.error = error
        return existing

    row = RemediationRun(
        id=uuid.uuid4(),
        scan_id=scan_id,
        idempotency_key=idempotency_key,
        repo_full_name=repo_full_name,
        base_branch=base_branch,
        base_sha=base_sha,
        head_branch=head_branch,
        head_sha=head_sha,
        pr_number=pr_number,
        pr_url=pr_url,
        lifecycle_state=lifecycle_state,
        changed_files=changed_files or [],
        validation_results=validation_results or [],
        error=error,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row


def evaluate_verification_outcome(
    *,
    original_issue_keywords: Sequence[str] | None,
    patched_content: str | None,
    validation_passed: bool,
    operational_error: str | None = None,
) -> tuple[str, str, str]:
    """Return (issue_outcome, operational_status, detail).

    Never marks fixed solely because a PR opened or syntax passed.
    """
    if operational_error:
        return OUTCOME_INCONCLUSIVE, OPS_ERROR, operational_error
    if patched_content is None:
        return OUTCOME_INCONCLUSIVE, OPS_SKIPPED, "patched content unavailable"
    if not validation_passed:
        return (
            OUTCOME_UNRESOLVED,
            OPS_OK,
            "deterministic checks failed on patched revision",
        )

    keywords = [k.lower() for k in (original_issue_keywords or []) if k and str(k).strip()]
    if not keywords:
        return (
            OUTCOME_INCONCLUSIVE,
            OPS_OK,
            "no acceptance keywords; cannot confirm issue-level fix",
        )

    text = patched_content.lower()
    hits = [k for k in keywords if k in text]
    if len(hits) >= max(1, (len(keywords) + 1) // 2):
        return (
            OUTCOME_FIXED,
            OPS_OK,
            f"fresh content contains acceptance terms: {hits[:5]}",
        )
    return (
        OUTCOME_UNRESOLVED,
        OPS_OK,
        "patched revision lacks required acceptance terms",
    )


async def persist_verification_run(
    session: Any,
    *,
    scan_id: uuid.UUID,
    remediation_run_id: uuid.UUID,
    evaluated_revision: str | None,
    issue_outcome: str,
    operational_status: str,
    detail: str,
    fresh_evidence: list[Any] | None = None,
) -> VerificationRun:
    row = VerificationRun(
        id=uuid.uuid4(),
        scan_id=scan_id,
        remediation_run_id=remediation_run_id,
        evaluated_revision=evaluated_revision,
        issue_outcome=issue_outcome,
        operational_status=operational_status,
        detail=detail,
        fresh_evidence=fresh_evidence or [],
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row


async def list_verifications_for_scan(
    session: Any, scan_id: uuid.UUID
) -> list[VerificationRun]:
    result = await session.execute(
        select(VerificationRun)
        .where(VerificationRun.scan_id == scan_id)
        .order_by(VerificationRun.created_at.desc())
    )
    return list(result.scalars().all())
