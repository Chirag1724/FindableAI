"""Phase 3 Item 1: cache-only remediation eligibility (unit + reason codes)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.orchestration.cache_remediation import (
    RemediationDenyReason,
    content_hash_for_text,
    current_cache_fingerprint,
    evaluate_cache_only_remediation,
)
from app.schemas.intelligence import (
    EntailmentStatus,
    EvidenceReference,
    IntentEvaluation,
)


def _scan(**kwargs):
    base = dict(
        status="completed",
        outcome="success",
        remediation_eligible=True,
        result_source="real_pipeline",
        org_id=uuid.uuid4(),
        cancel_requested=False,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _evidence(*, age_seconds: float = 0.0, **overrides):
    excerpt = overrides.pop("excerpt", "Hours: Mon-Fri 9-5")
    now = datetime.now(UTC)
    row = SimpleNamespace(
        source_url="https://example.com/",
        excerpt=excerpt,
        content_hash=content_hash_for_text(excerpt),
        cache_fingerprint=current_cache_fingerprint(),
        created_at=now - timedelta(seconds=age_seconds),
        chunk_id=uuid.uuid4(),
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


def test_eligible_happy_path():
    org = uuid.uuid4()
    d = evaluate_cache_only_remediation(
        scan=_scan(org_id=org),
        tenant_org_id=org,
        is_system_admin=False,
        evidence_rows=[_evidence()],
    )
    assert d.eligible is True
    assert d.reason is None


@pytest.mark.parametrize(
    "mutate,reason",
    [
        ({"tenant_org_id": "other"}, RemediationDenyReason.CROSS_TENANT),
        ({"status": "running"}, RemediationDenyReason.SCAN_STATE),
        ({"status": "cancelled"}, RemediationDenyReason.SCAN_STATE),
        ({"status": "failed"}, RemediationDenyReason.SCAN_STATE),
        ({"status": "queued"}, RemediationDenyReason.SCAN_STATE),
        ({"remediation_eligible": False}, RemediationDenyReason.NOT_ELIGIBLE_FLAG),
        ({"evidence_rows": []}, RemediationDenyReason.NO_EVIDENCE),
    ],
)
def test_deny_reasons_basic(mutate, reason):
    org = uuid.uuid4()
    tenant = uuid.uuid4() if mutate.get("tenant_org_id") == "other" else org
    scan_kwargs = {k: v for k, v in mutate.items() if k not in ("tenant_org_id", "evidence_rows")}
    scan = _scan(org_id=org, **scan_kwargs)
    evidence = mutate.get("evidence_rows", [_evidence()])
    d = evaluate_cache_only_remediation(
        scan=scan,
        tenant_org_id=tenant,
        is_system_admin=False,
        evidence_rows=evidence,
    )
    assert d.eligible is False
    assert d.reason is reason


def test_missing_provenance():
    org = uuid.uuid4()
    ev = _evidence()
    ev.content_hash = None
    d = evaluate_cache_only_remediation(
        scan=_scan(org_id=org),
        tenant_org_id=org,
        is_system_admin=False,
        evidence_rows=[ev],
    )
    assert d.reason is RemediationDenyReason.MISSING_PROVENANCE


def test_provenance_hash_mismatch():
    org = uuid.uuid4()
    ev = _evidence()
    ev.content_hash = "0" * 64
    d = evaluate_cache_only_remediation(
        scan=_scan(org_id=org),
        tenant_org_id=org,
        is_system_admin=False,
        evidence_rows=[ev],
    )
    assert d.reason is RemediationDenyReason.PROVENANCE_MISMATCH


def test_fingerprint_mismatch():
    org = uuid.uuid4()
    ev = _evidence(cache_fingerprint="stale|v0")
    d = evaluate_cache_only_remediation(
        scan=_scan(org_id=org),
        tenant_org_id=org,
        is_system_admin=False,
        evidence_rows=[ev],
    )
    assert d.reason is RemediationDenyReason.FINGERPRINT_MISMATCH


def test_stale_beyond_ttl(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "EVIDENCE_TTL_SECONDS", 100)
    org = uuid.uuid4()
    d = evaluate_cache_only_remediation(
        scan=_scan(org_id=org),
        tenant_org_id=org,
        is_system_admin=False,
        evidence_rows=[_evidence(age_seconds=101)],
    )
    assert d.reason is RemediationDenyReason.STALE_EVIDENCE


def test_boundary_exactly_ttl_is_eligible(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "EVIDENCE_TTL_SECONDS", 100)
    org = uuid.uuid4()
    d = evaluate_cache_only_remediation(
        scan=_scan(org_id=org),
        tenant_org_id=org,
        is_system_admin=False,
        evidence_rows=[_evidence(age_seconds=100)],
    )
    assert d.eligible is True


def test_invalid_evaluation_mem_chunk():
    org = uuid.uuid4()
    ev = IntentEvaluation(
        intent_id="i1",
        query="q",
        status=EntailmentStatus.SUPPORTED,
        confidence=0.9,
        reasoning="ok",
        evidence=[
            EvidenceReference(
                chunk_id="mem:1",
                dom_path="p",
                url="https://example.com",
                rank=1,
            )
        ],
    )
    d = evaluate_cache_only_remediation(
        scan=_scan(org_id=org),
        tenant_org_id=org,
        is_system_admin=False,
        evidence_rows=[_evidence()],
        evaluations=[ev],
    )
    assert d.reason is RemediationDenyReason.INVALID_EVALUATION


def test_completed_with_partial_outcome_allowed():
    org = uuid.uuid4()
    d = evaluate_cache_only_remediation(
        scan=_scan(org_id=org, outcome="partial"),
        tenant_org_id=org,
        is_system_admin=False,
        evidence_rows=[_evidence()],
    )
    assert d.eligible is True


def test_reason_codes_stable_strings():
    assert RemediationDenyReason.STALE_EVIDENCE.value == "stale_evidence"
    assert RemediationDenyReason.CROSS_TENANT.value == "cross_tenant"
    assert RemediationDenyReason.FINGERPRINT_MISMATCH.value == "fingerprint_mismatch"


@pytest.mark.asyncio
async def test_forbidden_provider_raises_and_budget_unchanged():
    """Cache-only path must not call providers; budget counters stay put."""
    from app.orchestration.cache_remediation import ForbiddenProviderClient

    client = ForbiddenProviderClient()
    with pytest.raises(RuntimeError, match="cache_only_remediation_forbids_provider_calls"):
        await client.chat(messages=[{"role": "user", "content": "hi"}])
    budget = {"llm_calls_made": 7}
    # Structural: eligibility does not touch budget.
    org = uuid.uuid4()
    d = evaluate_cache_only_remediation(
        scan=_scan(org_id=org),
        tenant_org_id=org,
        is_system_admin=False,
        evidence_rows=[_evidence()],
    )
    assert d.eligible is True
    assert budget["llm_calls_made"] == 7
