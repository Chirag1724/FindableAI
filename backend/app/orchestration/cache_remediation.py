"""Single source of truth for cache-only remediation eligibility (Phase 3).

Cache-only means: open a PR / apply patches from already-persisted scan evidence
with ZERO new provider calls and ZERO budget consumption. Live crawl/LLM is
never silently invoked from this path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from app.core.config import settings
from app.jobs.checkpoints import RETRIEVAL_VERSION
from app.schemas.intelligence import EntailmentStatus, IntentEvaluation


class RemediationDenyReason(StrEnum):
    CROSS_TENANT = "cross_tenant"
    SCAN_STATE = "scan_state_ineligible"
    MISSING_PROVENANCE = "missing_provenance"
    PROVENANCE_MISMATCH = "provenance_mismatch"
    STALE_EVIDENCE = "stale_evidence"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    INVALID_EVALUATION = "invalid_evaluation"
    NOT_ELIGIBLE_FLAG = "remediation_flag_false"
    NO_EVIDENCE = "no_validated_evidence"


_TERMINAL_INELIGIBLE = frozenset(
    {
        "cancelled",
        "cancelling",
        "failed",
        "pending",
        "queued",
        "in_progress",
        "crawling",
        "extracting_dom",
        "synthesizing_intents",
        "hybrid_retrieval",
        "nli_evaluation",
        "computing_fscore",
        "generating_patches",
    }
)
_ALLOWED_SCAN_STATUS = frozenset({"completed", "audited"})
_ALLOWED_OUTCOMES = frozenset({"success", "partial", None, ""})


def current_cache_fingerprint() -> str:
    """Fingerprint that must match evidence stamped at capture time."""
    return f"{RETRIEVAL_VERSION}|integrity_v1"


def content_hash_for_text(text: str | None) -> str:
    raw = (text or "").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    eligible: bool
    reason: RemediationDenyReason | None
    detail: str
    evidence_count: int = 0
    oldest_evidence_age_seconds: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "reason": self.reason.value if self.reason else None,
            "detail": self.detail,
            "evidence_count": self.evidence_count,
            "oldest_evidence_age_seconds": self.oldest_evidence_age_seconds,
            "ttl_seconds": int(getattr(settings, "EVIDENCE_TTL_SECONDS", 604800)),
            "cache_fingerprint": current_cache_fingerprint(),
        }


class _EvidenceRow(Protocol):
    source_url: str | None
    excerpt: str | None
    content_hash: str | None
    cache_fingerprint: str | None
    created_at: datetime | None
    chunk_id: Any


class _ScanRow(Protocol):
    status: str | None
    outcome: str | None
    remediation_eligible: bool | None
    result_source: str | None
    org_id: Any
    cancel_requested: bool | None


def evaluate_cache_only_remediation(
    *,
    scan: _ScanRow,
    tenant_org_id: Any | None,
    is_system_admin: bool,
    evidence_rows: list[Any],
    evaluations: list[IntentEvaluation] | None = None,
    now: datetime | None = None,
) -> EligibilityDecision:
    """Return eligibility for cache-only remediation. Fail closed with reason codes."""
    ttl = int(getattr(settings, "EVIDENCE_TTL_SECONDS", 604800) or 604800)
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)

    # Tenant: non-admin must match scan org; NULL org denied to members.
    if not is_system_admin:
        if tenant_org_id is None or getattr(scan, "org_id", None) is None:
            return EligibilityDecision(
                False, RemediationDenyReason.CROSS_TENANT, "scan org missing or principal has no org"
            )
        if scan.org_id != tenant_org_id:
            return EligibilityDecision(
                False, RemediationDenyReason.CROSS_TENANT, "scan belongs to another organization"
            )

    status = str(scan.status or "").lower()
    if status in _TERMINAL_INELIGIBLE or status not in _ALLOWED_SCAN_STATUS:
        # Explicit: completed (and legacy audited) only. Partial live scans that
        # never reached completed stay ineligible even if outcome=partial.
        if status != "completed":
            return EligibilityDecision(
                False,
                RemediationDenyReason.SCAN_STATE,
                f"scan status {status!r} does not permit cache-only remediation",
            )

    if getattr(scan, "cancel_requested", False):
        return EligibilityDecision(
            False, RemediationDenyReason.SCAN_STATE, "scan has cancel_requested set"
        )

    outcome = (getattr(scan, "outcome", None) or "").lower() or None
    if outcome not in _ALLOWED_OUTCOMES and outcome not in ("success", "partial"):
        return EligibilityDecision(
            False, RemediationDenyReason.SCAN_STATE, f"scan outcome {outcome!r} ineligible"
        )

    if scan.remediation_eligible is not True:
        return EligibilityDecision(
            False,
            RemediationDenyReason.NOT_ELIGIBLE_FLAG,
            "scan.remediation_eligible is not True",
        )

    if not evidence_rows:
        return EligibilityDecision(
            False, RemediationDenyReason.NO_EVIDENCE, "no durable evidence rows for scan"
        )

    expected_fp = current_cache_fingerprint()
    oldest_age: float | None = None
    for row in evidence_rows:
        source_url = getattr(row, "source_url", None)
        excerpt = getattr(row, "excerpt", None)
        content_hash = getattr(row, "content_hash", None)
        cache_fp = getattr(row, "cache_fingerprint", None)
        created_at = getattr(row, "created_at", None)
        chunk_id = getattr(row, "chunk_id", None)

        if not source_url or not excerpt or chunk_id is None or created_at is None:
            return EligibilityDecision(
                False,
                RemediationDenyReason.MISSING_PROVENANCE,
                "evidence missing source_url, excerpt, chunk_id, or created_at",
                evidence_count=len(evidence_rows),
            )
        if not content_hash:
            return EligibilityDecision(
                False,
                RemediationDenyReason.MISSING_PROVENANCE,
                "evidence missing content_hash",
                evidence_count=len(evidence_rows),
            )
        expected_hash = content_hash_for_text(excerpt)
        if content_hash != expected_hash:
            return EligibilityDecision(
                False,
                RemediationDenyReason.PROVENANCE_MISMATCH,
                "evidence content_hash does not match excerpt",
                evidence_count=len(evidence_rows),
            )
        if not cache_fp:
            return EligibilityDecision(
                False,
                RemediationDenyReason.MISSING_PROVENANCE,
                "evidence missing cache_fingerprint",
                evidence_count=len(evidence_rows),
            )
        if cache_fp != expected_fp:
            return EligibilityDecision(
                False,
                RemediationDenyReason.FINGERPRINT_MISMATCH,
                f"cache_fingerprint {cache_fp!r} != {expected_fp!r}",
                evidence_count=len(evidence_rows),
            )
        ts = created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        age = (clock - ts).total_seconds()
        oldest_age = age if oldest_age is None else max(oldest_age, age)
        if age > ttl:
            return EligibilityDecision(
                False,
                RemediationDenyReason.STALE_EVIDENCE,
                f"evidence age {age:.0f}s exceeds TTL {ttl}s",
                evidence_count=len(evidence_rows),
                oldest_evidence_age_seconds=oldest_age,
            )

    if evaluations:
        for ev in evaluations:
            # Validated = has durable evidence cites. UNKNOWN/empty without cites
            # cannot authorize remediation.
            if not ev.evidence and ev.status is not EntailmentStatus.UNKNOWN:
                return EligibilityDecision(
                    False,
                    RemediationDenyReason.INVALID_EVALUATION,
                    f"evaluation {ev.intent_id} has no evidence and status {ev.status}",
                    evidence_count=len(evidence_rows),
                    oldest_evidence_age_seconds=oldest_age,
                )
            for cite in ev.evidence or []:
                if not cite.chunk_id or str(cite.chunk_id).startswith("mem:"):
                    return EligibilityDecision(
                        False,
                        RemediationDenyReason.INVALID_EVALUATION,
                        f"evaluation {ev.intent_id} cites non-durable chunk",
                        evidence_count=len(evidence_rows),
                        oldest_evidence_age_seconds=oldest_age,
                    )

    return EligibilityDecision(
        True,
        None,
        "cache-only remediation eligible",
        evidence_count=len(evidence_rows),
        oldest_evidence_age_seconds=oldest_age,
    )


class ForbiddenProviderClient:
    """Provider stub that raises if any outbound call is attempted (cache-only path)."""

    async def chat(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("cache_only_remediation_forbids_provider_calls")

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("cache_only_remediation_forbids_provider_calls")


def evidence_ttl_window(now: datetime | None = None) -> datetime:
    ttl = int(getattr(settings, "EVIDENCE_TTL_SECONDS", 604800) or 604800)
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    return clock - timedelta(seconds=ttl)


async def load_scan_evidence_rows(session: Any, scan_id: Any) -> list[Any]:
    """Load durable Evidence rows for a scan (SQL join via intents)."""
    from sqlalchemy import select

    from app.models.database import Evidence as EvidenceModel
    from app.models.database import Intent as IntentModel

    result = await session.execute(
        select(EvidenceModel)
        .join(IntentModel, EvidenceModel.intent_id == IntentModel.id)
        .where(IntentModel.scan_id == scan_id)
        .order_by(EvidenceModel.created_at.asc())
    )
    return list(result.scalars().all())


async def decide_cache_only_for_scan(
    session: Any,
    *,
    scan: Any,
    tenant_org_id: Any | None,
    is_system_admin: bool,
    evaluations: list[IntentEvaluation] | None = None,
    now: datetime | None = None,
) -> EligibilityDecision:
    """SSOT entry used by apply/validate routes."""
    rows = await load_scan_evidence_rows(session, scan.id)
    return evaluate_cache_only_remediation(
        scan=scan,
        tenant_org_id=tenant_org_id,
        is_system_admin=is_system_admin,
        evidence_rows=rows,
        evaluations=evaluations,
        now=now,
    )


def eligibility_http_exception(decision: EligibilityDecision) -> Any:
    """Map a deny decision to HTTP 409 (state/freshness) or 422 (provenance)."""
    from fastapi import HTTPException, status

    body = decision.as_dict()
    body["hint"] = (
        "Re-run a fresh scan to capture current evidence, then retry remediation. "
        "Cache-only remediation never falls back to live provider calls."
    )
    code = status.HTTP_409_CONFLICT
    if decision.reason in (
        RemediationDenyReason.MISSING_PROVENANCE,
        RemediationDenyReason.PROVENANCE_MISMATCH,
        RemediationDenyReason.FINGERPRINT_MISMATCH,
        RemediationDenyReason.INVALID_EVALUATION,
        RemediationDenyReason.NO_EVIDENCE,
    ):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    if decision.reason is RemediationDenyReason.CROSS_TENANT:
        code = status.HTTP_404_NOT_FOUND
        body = {"detail": "Scan not found", "reason": decision.reason.value}
        return HTTPException(status_code=code, detail=body)
    return HTTPException(status_code=code, detail=body)
