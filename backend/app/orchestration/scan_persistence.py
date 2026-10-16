"""Durable scan-integrity persistence and cold-hydration helpers (P1).

Legacy rows (no integrity_version / no execution_mode) hydrate as inconclusive
and never as verified real_llm or remediation_eligible=true.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

INTEGRITY_VERSION = 1

LEGACY_WARNING = (
    "Legacy scan record: integrity provenance was not persisted; "
    "not treated as a verified real_llm audit."
)


@dataclass
class PersistedIntegrity:
    """Integrity contract fields stored on / restored from the Scan row."""

    execution_mode: str
    result_source: str
    outcome: str
    score_source: str | None
    patches_source: str | None
    remediation_eligible: bool
    intelligence_warnings: list[str] = field(default_factory=list)
    llm_calls_made: int | None = 0
    dag_evaluations_count: int | None = None
    synthetic_intents_count: int | None = None
    pages_crawled: int | None = None
    dom_chunks_extracted: int | None = None
    data_source: str | None = None
    error: str | None = None
    integrity_version: int | None = INTEGRITY_VERSION
    is_legacy: bool = False


def apply_integrity_to_scan_row(
    db_scan: Any,
    *,
    execution_mode: str,
    result_source: str,
    outcome: str,
    score_source: str | None,
    patches_source: str | None,
    remediation_eligible: bool,
    intelligence_warnings: list[str] | None,
    llm_calls_made: int | None,
    dag_evaluations_count: int | None,
    synthetic_intents_count: int | None,
    pages_crawled: int | None,
    dom_chunks_extracted: int | None,
    data_source: str | None,
    error: str | None,
) -> None:
    """Write integrity fields onto a SQLAlchemy Scan instance."""
    db_scan.integrity_version = INTEGRITY_VERSION
    db_scan.execution_mode = execution_mode
    db_scan.result_source = result_source
    db_scan.outcome = outcome
    db_scan.score_source = score_source
    db_scan.patches_source = patches_source
    db_scan.remediation_eligible = bool(remediation_eligible)
    db_scan.intelligence_warnings = list(intelligence_warnings or [])
    db_scan.llm_calls_made = llm_calls_made
    db_scan.dag_evaluations_count = dag_evaluations_count
    db_scan.synthetic_intents_count = synthetic_intents_count
    db_scan.pages_crawled = pages_crawled
    db_scan.dom_chunks_extracted = dom_chunks_extracted
    db_scan.data_source = data_source
    if error is not None:
        db_scan.error = error


def apply_observability_to_scan_row(
    db_scan: Any,
    *,
    llm_usd_estimated: float | None = None,
    provider_successes: int | None = None,
    provider_failures: int | None = None,
    primary_llm_model: str | None = None,
    fallback_provider_used: bool | None = None,
    batches_total: int | None = None,
    batches_completed: int | None = None,
    batches_failed: int | None = None,
    llm_tokens_in: int | None = None,
    llm_tokens_out: int | None = None,
) -> None:
    """Write non-secret provider/batch/cost observability onto a Scan row."""
    if llm_usd_estimated is not None:
        db_scan.llm_usd_estimated = float(llm_usd_estimated)
    if provider_successes is not None:
        db_scan.provider_successes = int(provider_successes)
    if provider_failures is not None:
        db_scan.provider_failures = int(provider_failures)
    if primary_llm_model is not None:
        db_scan.primary_llm_model = str(primary_llm_model)[:128]
    if fallback_provider_used is not None:
        db_scan.fallback_provider_used = bool(fallback_provider_used)
    if batches_total is not None:
        db_scan.batches_total = int(batches_total)
    if batches_completed is not None:
        db_scan.batches_completed = int(batches_completed)
    if batches_failed is not None:
        db_scan.batches_failed = int(batches_failed)
    if llm_tokens_in is not None:
        db_scan.llm_tokens_in = int(llm_tokens_in)
    if llm_tokens_out is not None:
        db_scan.llm_tokens_out = int(llm_tokens_out)


def observability_from_budget(budget_guard: Any) -> dict[str, Any]:
    """Safe dict for ScanResponse / row persistence from a BudgetGuard."""
    if budget_guard is None:
        return {}
    snap = budget_guard.snapshot() if hasattr(budget_guard, "snapshot") else {}
    return {
        "llm_usd_estimated": float(snap.get("usd_used") or 0.0),
        "llm_usd_provider_reported": None,
        "cost_basis": "estimated",
        "provider_successes": int(snap.get("provider_successes") or 0),
        "provider_failures": int(snap.get("provider_failures") or 0),
        "primary_llm_model": snap.get("primary_model"),
        "fallback_provider_used": bool(snap.get("fallback_provider_used") or False),
        "batches_total": snap.get("batches_total"),
        "batches_completed": int(snap.get("batches_completed") or 0),
        "batches_failed": int(snap.get("batches_failed") or 0),
        "llm_tokens_in": snap.get("tokens_in"),
        "llm_tokens_out": snap.get("tokens_out"),
    }


def _has_persisted_integrity(db_scan: Any) -> bool:
    version = getattr(db_scan, "integrity_version", None)
    if version is not None and int(version) >= 1:
        return True
    # Rows written with columns but missing version still count if mode was set.
    mode = getattr(db_scan, "execution_mode", None)
    return isinstance(mode, str) and bool(mode.strip())


def unpack_integrity_from_scan_row(db_scan: Any) -> PersistedIntegrity:
    """Restore integrity for API hydration. Safe defaults for legacy rows."""
    if not _has_persisted_integrity(db_scan):
        return PersistedIntegrity(
            execution_mode="unknown",
            result_source="inconclusive",
            outcome="inconclusive",
            score_source="none",
            patches_source="none",
            remediation_eligible=False,
            intelligence_warnings=[LEGACY_WARNING],
            llm_calls_made=getattr(db_scan, "llm_calls_made", None),
            dag_evaluations_count=None,
            synthetic_intents_count=None,
            pages_crawled=getattr(db_scan, "pages_crawled", None),
            dom_chunks_extracted=getattr(db_scan, "dom_chunks_extracted", None),
            data_source="synthetic_fallback",
            error=getattr(db_scan, "error", None),
            integrity_version=None,
            is_legacy=True,
        )

    warnings_raw = getattr(db_scan, "intelligence_warnings", None) or []
    if isinstance(warnings_raw, str):
        warnings_list = [warnings_raw]
    elif isinstance(warnings_raw, list):
        warnings_list = [str(w) for w in warnings_raw]
    else:
        warnings_list = []

    remediation = getattr(db_scan, "remediation_eligible", None)
    # Missing remediation flag on a "new" row → never default True
    remediation_eligible = bool(remediation) if remediation is not None else False

    execution_mode = getattr(db_scan, "execution_mode", None) or "unknown"
    result_source = getattr(db_scan, "result_source", None) or "inconclusive"
    outcome = getattr(db_scan, "outcome", None) or "inconclusive"

    # Hard safety: never allow real_llm + remediation from unknown/empty provenance
    if execution_mode == "real_llm" and result_source in (None, "", "inconclusive", "unknown"):
        execution_mode = "unknown"
        result_source = "inconclusive"
        outcome = "inconclusive"
        remediation_eligible = False
        warnings_list = [
            *warnings_list,
            "Persisted integrity inconsistent; demoted from real_llm.",
        ]

    if execution_mode != "real_llm":
        remediation_eligible = False

    return PersistedIntegrity(
        execution_mode=str(execution_mode),
        result_source=str(result_source),
        outcome=str(outcome),
        score_source=getattr(db_scan, "score_source", None),
        patches_source=getattr(db_scan, "patches_source", None),
        remediation_eligible=remediation_eligible,
        intelligence_warnings=warnings_list,
        llm_calls_made=getattr(db_scan, "llm_calls_made", None),
        dag_evaluations_count=getattr(db_scan, "dag_evaluations_count", None),
        synthetic_intents_count=getattr(db_scan, "synthetic_intents_count", None),
        pages_crawled=getattr(db_scan, "pages_crawled", None),
        dom_chunks_extracted=getattr(db_scan, "dom_chunks_extracted", None),
        data_source=getattr(db_scan, "data_source", None),
        error=getattr(db_scan, "error", None),
        integrity_version=getattr(db_scan, "integrity_version", None),
        is_legacy=False,
    )
