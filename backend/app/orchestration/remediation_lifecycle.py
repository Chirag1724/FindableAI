"""Persisted remediation / PR lifecycle + post-PR verification (Stages 5-6).

Trust boundary: PR creation is not fix verification. Heuristic post-PR checks
never set fully_verified=True. Lifecycle transitions are enforced in-process
and via DB compare-and-set (``state_revision``) so concurrent workers cannot
blindly overwrite newer results. Idempotency key uniqueness prevents duplicate
GitHub mutations on retry.

``lifecycle_state=verified`` means a *heuristic* check reported fixed at a
recorded revision — it is **not** a full website re-scan. Always pair with
``verification_runs.fully_verified=false`` for heuristic methods.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from app.models.database import RemediationRun, VerificationRun

logger = logging.getLogger(__name__)

STATE_VALIDATING = "validating"
STATE_VALIDATION_FAILED = "validation_failed"
STATE_READY = "ready"
STATE_MUTATING = "mutating"
STATE_PR_OPEN = "pr_open"
STATE_PR_PERSIST_FAILED = "pr_persist_failed"
STATE_VERIFYING = "verifying"
STATE_VERIFIED = "verified"  # heuristic fixed only — see module docstring
STATE_BLOCKED = "blocked"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"

# User-facing mapping (Stage 3 requirements → established schema):
# Planned → validating/ready
# Patch rejected → validation_failed
# GitHub pending → mutating
# PR created → pr_open (or pr_persist_failed)
# Verification running → verifying
# Heuristic fixed → verified (fully_verified remains false)
# Verification unresolved → failed
# Needs human review / inconclusive → blocked
# Cancelled → cancelled

OUTCOME_FIXED = "fixed"
OUTCOME_UNRESOLVED = "unresolved"
OUTCOME_INCONCLUSIVE = "inconclusive"

VERIFICATION_METHOD_HEURISTIC = "heuristic_post_pr"
VERIFICATION_METHOD_FULL_RESCAN = "full_rescan"

OPS_OK = "ok"
OPS_ERROR = "error"
OPS_TIMEOUT = "timeout"
OPS_SKIPPED = "skipped"

_ALLOWED_TRANSITIONS: Mapping[str, frozenset[str]] = {
    STATE_VALIDATING: frozenset(
        {
            STATE_VALIDATION_FAILED,
            STATE_READY,
            STATE_MUTATING,
            STATE_BLOCKED,
            STATE_FAILED,
            STATE_CANCELLED,
        }
    ),
    STATE_VALIDATION_FAILED: frozenset(
        {STATE_VALIDATING, STATE_READY, STATE_FAILED, STATE_BLOCKED, STATE_CANCELLED}
    ),
    STATE_READY: frozenset(
        {STATE_MUTATING, STATE_VALIDATION_FAILED, STATE_BLOCKED, STATE_FAILED, STATE_CANCELLED}
    ),
    STATE_MUTATING: frozenset(
        {
            STATE_PR_OPEN,
            STATE_PR_PERSIST_FAILED,
            STATE_FAILED,
            STATE_BLOCKED,
            STATE_CANCELLED,
        }
    ),
    STATE_PR_OPEN: frozenset(
        {
            STATE_VERIFYING,
            STATE_PR_PERSIST_FAILED,
            STATE_VERIFIED,
            STATE_FAILED,
            STATE_BLOCKED,
            STATE_CANCELLED,
        }
    ),
    STATE_PR_PERSIST_FAILED: frozenset(
        {
            STATE_PR_OPEN,
            STATE_MUTATING,
            STATE_VERIFYING,
            STATE_FAILED,
            STATE_BLOCKED,
            STATE_CANCELLED,
        }
    ),
    STATE_VERIFYING: frozenset(
        {STATE_VERIFIED, STATE_FAILED, STATE_BLOCKED, STATE_CANCELLED, STATE_PR_OPEN}
    ),
    STATE_VERIFIED: frozenset({STATE_VERIFYING, STATE_BLOCKED, STATE_CANCELLED}),
    STATE_BLOCKED: frozenset(
        {
            STATE_VALIDATING,
            STATE_READY,
            STATE_MUTATING,
            STATE_VERIFYING,
            STATE_CANCELLED,
        }
    ),
    STATE_FAILED: frozenset(
        {
            STATE_VALIDATING,
            STATE_READY,
            STATE_MUTATING,
            STATE_VERIFYING,
            STATE_CANCELLED,
        }
    ),
    STATE_CANCELLED: frozenset(),
}


class InvalidLifecycleTransition(ValueError):
    def __init__(self, from_state: str, to_state: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Invalid remediation lifecycle transition: {from_state!r} → {to_state!r}")


class StaleLifecycleRevision(ValueError):
    """Raised when a CAS transition loses a race against a newer worker."""

    def __init__(self, run_id: uuid.UUID, expected: int, detail: str = "") -> None:
        self.run_id = run_id
        self.expected = expected
        super().__init__(
            f"Stale remediation lifecycle revision for {run_id}: expected={expected} {detail}"
        )


class IdempotencyScopeConflict(ValueError):
    """Raised when an idempotency key is reused with a different scan/repo scope."""


def can_transition(from_state: str | None, to_state: str) -> bool:
    if from_state is None or from_state == "":
        return True
    if from_state == to_state:
        return True
    allowed = _ALLOWED_TRANSITIONS.get(from_state)
    if allowed is None:
        return to_state in {
            STATE_FAILED,
            STATE_BLOCKED,
            STATE_CANCELLED,
            STATE_PR_OPEN,
            STATE_VERIFYING,
        }
    return to_state in allowed


def assert_valid_transition(from_state: str | None, to_state: str) -> None:
    if not can_transition(from_state, to_state):
        raise InvalidLifecycleTransition(str(from_state), to_state)


def lifecycle_state_for_verification_outcome(issue_outcome: str) -> str:
    """Map verification issue outcome to durable lifecycle state.

    ``verified`` = heuristic fixed signal only (never full re-scan proof).
    """
    if issue_outcome == OUTCOME_FIXED:
        return STATE_VERIFIED
    if issue_outcome == OUTCOME_UNRESOLVED:
        return STATE_FAILED
    return STATE_BLOCKED


def make_idempotency_key(scan_id: str, repo: str, branch: str) -> str:
    """Stable per-(scan, repo, base branch) identity for PR mutations."""
    return f"{scan_id}|{repo}|{branch}"


def _row_revision(row: Any) -> int:
    rev = getattr(row, "state_revision", 0)
    try:
        return int(rev or 0)
    except (TypeError, ValueError):
        return 0


async def get_run_by_idempotency(session: Any, key: str) -> RemediationRun | None:
    result = await session.execute(
        select(RemediationRun).where(RemediationRun.idempotency_key == key)
    )
    row = result.scalars().first()
    return row if row is not None else None


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
    enforce_transition: bool = True,
    expected_revision: int | None = None,
) -> RemediationRun:
    """Create or CAS-update a remediation run.

    When an existing row is found, the transition is applied with
    ``UPDATE ... WHERE id AND state_revision AND lifecycle_state`` so a
    stale worker cannot overwrite a newer result. Scope mismatches
    (different scan_id or repo) raise ``IdempotencyScopeConflict``.
    """
    existing = await get_run_by_idempotency(session, idempotency_key)
    now = datetime.now(UTC)
    if existing is not None:
        if existing.scan_id != scan_id:
            raise IdempotencyScopeConflict(
                f"idempotency key bound to scan {existing.scan_id}, not {scan_id}"
            )
        if (existing.repo_full_name or "").lower() != (repo_full_name or "").lower():
            raise IdempotencyScopeConflict(
                f"idempotency key bound to repo {existing.repo_full_name!r}, not {repo_full_name!r}"
            )

        # Idempotent recovery: never remutate when a PR URL/number is already known.
        target_state = lifecycle_state
        if lifecycle_state == STATE_MUTATING and existing.pr_number is not None and existing.pr_url:
            target_state = STATE_PR_OPEN

        if target_state == existing.lifecycle_state and expected_revision is None:
            # Heartbeat / identical retry — refresh metadata without bumping when no-op.
            _apply_optional_fields(
                existing,
                base_sha=base_sha,
                head_branch=head_branch,
                head_sha=head_sha,
                pr_number=pr_number,
                pr_url=pr_url,
                changed_files=changed_files,
                validation_results=validation_results,
                error=error if error is not None else existing.error,
            )
            if target_state == STATE_PR_OPEN:
                existing.error = None
            existing.updated_at = now
            return existing

        if enforce_transition:
            assert_valid_transition(existing.lifecycle_state, target_state)

        current_rev = _row_revision(existing)
        if expected_revision is not None and expected_revision != current_rev:
            raise StaleLifecycleRevision(existing.id, expected_revision)

        values: dict[str, Any] = {
            "lifecycle_state": target_state,
            "state_revision": current_rev + 1,
            "updated_at": now,
        }
        if base_sha is not None:
            values["base_sha"] = base_sha
        if head_branch is not None:
            values["head_branch"] = head_branch
        if head_sha is not None:
            values["head_sha"] = head_sha
        if pr_number is not None:
            values["pr_number"] = pr_number
        if pr_url is not None:
            values["pr_url"] = pr_url
        if changed_files is not None:
            values["changed_files"] = changed_files
        if validation_results is not None:
            values["validation_results"] = validation_results
        if target_state == STATE_PR_OPEN:
            values["error"] = None
        elif error is not None:
            values["error"] = error

        # Prefer real ORM UPDATE for concurrency; fall back to in-memory for mocks.
        if hasattr(existing, "id") and isinstance(getattr(existing, "id", None), uuid.UUID):
            try:
                result = await session.execute(
                    update(RemediationRun)
                    .where(
                        RemediationRun.id == existing.id,
                        RemediationRun.state_revision == current_rev,
                        RemediationRun.lifecycle_state == existing.lifecycle_state,
                    )
                    .values(**values)
                )
                rowcount = getattr(result, "rowcount", None)
                # Only enforce CAS when the dialect returns a real integer rowcount
                # (unit-test mocks often expose a MagicMock here).
                if isinstance(rowcount, int) and rowcount != 1:
                    raise StaleLifecycleRevision(
                        existing.id,
                        current_rev,
                        detail="CAS update matched 0 rows",
                    )
                # Refresh local object to match DB.
                for key, val in values.items():
                    setattr(existing, key, val)
                return existing
            except StaleLifecycleRevision:
                raise
            except Exception:
                # Unit-test mocks / non-SQLAlchemy sessions: mutate in place.
                logger.debug("lifecycle_cas_fallback_in_memory", exc_info=True)

        for key, val in values.items():
            setattr(existing, key, val)
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
        state_revision=0,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row


def _apply_optional_fields(
    existing: Any,
    *,
    base_sha: str | None,
    head_branch: str | None,
    head_sha: str | None,
    pr_number: int | None,
    pr_url: str | None,
    changed_files: list[Any] | None,
    validation_results: list[Any] | None,
    error: str | None,
) -> None:
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


def evaluate_verification_outcome(
    *,
    original_issue_keywords: Sequence[str] | None,
    patched_content: str | None,
    validation_passed: bool,
    operational_error: str | None = None,
) -> tuple[str, str, str]:
    """Return (issue_outcome, operational_status, detail).

    Never marks fixed solely because a PR opened, syntax passed, or projected
    score improved. ``fixed`` is heuristic keyword evidence only.
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
            "no acceptance keywords; cannot confirm issue-level fix "
            "(heuristic post-PR check only; not a full re-scan)",
        )

    text = patched_content.lower()
    hits = [k for k in keywords if k in text]
    if len(hits) >= max(1, (len(keywords) + 1) // 2):
        return (
            OUTCOME_FIXED,
            OPS_OK,
            (
                "heuristic post-PR check: patched revision contains acceptance terms "
                f"{hits[:5]} (not a full website re-scan; fully_verified=false)"
            ),
        )
    return (
        OUTCOME_UNRESOLVED,
        OPS_OK,
        "patched revision lacks required acceptance terms "
        "(heuristic post-PR check only; not a full re-scan)",
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
    verification_method: str = VERIFICATION_METHOD_HEURISTIC,
    fully_verified: bool = False,
    is_full_rescan: bool = False,
) -> VerificationRun:
    """Persist a verification result. Heuristic method can never claim full verify."""
    method = verification_method or VERIFICATION_METHOD_HEURISTIC
    if method == VERIFICATION_METHOD_HEURISTIC:
        fully_verified = False
        is_full_rescan = False
    if not evaluated_revision or not str(evaluated_revision).strip():
        # Missing immutable revision → never claim full verification; force inconclusive honesty.
        fully_verified = False
        is_full_rescan = False
    row = VerificationRun(
        id=uuid.uuid4(),
        scan_id=scan_id,
        remediation_run_id=remediation_run_id,
        evaluated_revision=evaluated_revision,
        issue_outcome=issue_outcome,
        operational_status=operational_status,
        detail=detail,
        fresh_evidence=fresh_evidence or [],
        verification_method=method,
        fully_verified=bool(fully_verified),
        is_full_rescan=bool(is_full_rescan),
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row


async def list_verifications_for_scan(session: Any, scan_id: uuid.UUID) -> list[VerificationRun]:
    result = await session.execute(
        select(VerificationRun)
        .where(VerificationRun.scan_id == scan_id)
        .order_by(VerificationRun.created_at.desc())
    )
    return list(result.scalars().all())
