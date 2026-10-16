"""Deterministic scan execution-integrity decisions (P0 honesty).

Separates:
- execution_mode  — how intelligence was produced
- result_source   — provenance of intent/evaluation artifacts
- outcome         — success / partial / inconclusive / failed
- score_source / patches_source — whether score/patches are real or mock
- remediation_eligible — whether patches may be treated as evidence-backed

Never infer real_llm from llm_calls_made alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ExecutionMode(StrEnum):
    REAL_LLM = "real_llm"
    SYNTHETIC_FALLBACK = "synthetic_fallback"
    DETERMINISTIC = "deterministic"


class ResultSource(StrEnum):
    REAL_PIPELINE = "real_pipeline"
    SYNTHETIC_FALLBACK = "synthetic_fallback"
    PARTIAL_REAL = "partial_real"
    INCONCLUSIVE = "inconclusive"


class ScoreSource(StrEnum):
    DETERMINISTIC_SCORER = "deterministic_scorer"
    MOCK = "mock"
    NONE = "none"


class PatchesSource(StrEnum):
    ASSEMBLER = "assembler"
    MOCK = "mock"
    NONE = "none"


class ScanOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"


# Backward-compatible data_source values already used by API consumers.
DATA_SOURCE_LIVE = "live_pipeline"
DATA_SOURCE_SYNTHETIC = "synthetic_fallback"


@dataclass(frozen=True)
class IntegrityInput:
    """Facts known after DAG + optional synthetic fill + score/patch assembly."""

    dag_evaluation_count: int
    dag_success: bool
    dag_error: str | None
    dag_error_reason: str | None
    llm_calls_made: int
    used_synthetic_intents: bool
    used_synthetic_contradictions: bool
    final_evaluation_count: int
    score_source: ScoreSource
    patches_source: PatchesSource
    is_production: bool
    failed_intent_ids: tuple[str, ...] = ()
    cache_hits: int = 0


@dataclass
class IntegrityDecision:
    execution_mode: ExecutionMode
    data_source: str
    result_source: ResultSource
    score_source: ScoreSource
    patches_source: PatchesSource
    outcome: ScanOutcome
    remediation_eligible: bool
    warnings: list[str] = field(default_factory=list)
    mark_status_failed: bool = False
    error_message: str | None = None


def sanitize_public_error(message: str | None, *, max_len: int = 400) -> str | None:
    """Redact secret-looking substrings from client-facing / SSE error text."""
    if not message:
        return None
    cleaned = " ".join(str(message).split())
    # Strip common secret-looking substrings without inventing redaction infra.
    for token in ("Bearer ", "api_key", "API_KEY", "gsk_", "sk-", "ghp_"):
        if token.lower() in cleaned.lower():
            cleaned = "Provider error (details redacted)"
            break
    if len(cleaned) > max_len:
        return cleaned[: max_len - 3] + "..."
    return cleaned


# Backward-compatible private alias
_sanitize_public_error = sanitize_public_error


def decide_scan_integrity(inp: IntegrityInput) -> IntegrityDecision:
    """Compute honest mode/provenance/outcome from pipeline facts."""
    warnings: list[str] = []
    dag_n = max(0, inp.dag_evaluation_count)
    calls = max(0, inp.llm_calls_made)
    cache_hits = max(0, int(inp.cache_hits or 0))
    llm_evidence = calls > 0 or cache_hits > 0
    final_n = max(0, inp.final_evaluation_count)

    has_real_evals = dag_n > 0 and not inp.used_synthetic_intents
    act_complete = inp.dag_success and not inp.failed_intent_ids
    if inp.failed_intent_ids:
        warnings.append(
            "Partial ACT: failed intent_ids="
            + ",".join(inp.failed_intent_ids[:20])
            + ("..." if len(inp.failed_intent_ids) > 20 else "")
        )
    mock_score = inp.score_source is ScoreSource.MOCK
    mock_patches = inp.patches_source is PatchesSource.MOCK

    # --- execution_mode: never from calls_made alone ---
    # Cache hits skip budget but still prove the real LLM path supplied results.
    if (
        has_real_evals
        and llm_evidence
        and not inp.used_synthetic_intents
        and not mock_score
        and not mock_patches
    ):
        execution_mode = ExecutionMode.REAL_LLM
    elif inp.is_production and not has_real_evals:
        execution_mode = ExecutionMode.DETERMINISTIC
    else:
        execution_mode = ExecutionMode.SYNTHETIC_FALLBACK

    # --- result_source ---
    if inp.used_synthetic_intents:
        result_source = ResultSource.SYNTHETIC_FALLBACK
        warnings.append(
            "Intent evaluations were synthetically generated; not a real-LLM NLI audit."
        )
    elif has_real_evals and act_complete and not mock_score:
        result_source = ResultSource.REAL_PIPELINE
    elif has_real_evals and (not act_complete or mock_score):
        result_source = ResultSource.PARTIAL_REAL
        if not inp.dag_success:
            warnings.append("DAG did not fully succeed; preserved real evaluations are partial.")
        if mock_score:
            warnings.append("F-Score was mock-generated and is not audit-grade.")
    else:
        result_source = ResultSource.INCONCLUSIVE
        warnings.append("No real intent evaluations are available for this scan.")

    if inp.used_synthetic_contradictions:
        warnings.append("Contradiction list includes synthetic fallback entries.")
    if mock_patches:
        warnings.append("Patches are mock/demo artifacts, not evidence-backed remediations.")

    # data_source: keep legacy enum values for existing clients
    if result_source is ResultSource.REAL_PIPELINE:
        data_source = DATA_SOURCE_LIVE
    elif result_source is ResultSource.PARTIAL_REAL:
        data_source = DATA_SOURCE_LIVE
    else:
        data_source = DATA_SOURCE_SYNTHETIC

    # --- remediation_eligible ---
    # Eligible only when a full real audit completed and the real assembler ran
    # (including returning an empty list = "no patches needed").
    remediation_eligible = (
        has_real_evals
        and calls > 0
        and act_complete
        and not inp.used_synthetic_intents
        and not mock_score
        and not mock_patches
        and inp.patches_source is PatchesSource.ASSEMBLER
        and result_source is ResultSource.REAL_PIPELINE
    )

    # --- outcome / failed ---
    mark_failed = False
    error_message = _sanitize_public_error(inp.dag_error)

    if result_source is ResultSource.REAL_PIPELINE and act_complete:
        outcome = ScanOutcome.SUCCESS
    elif result_source is ResultSource.PARTIAL_REAL:
        outcome = ScanOutcome.PARTIAL
    elif result_source is ResultSource.SYNTHETIC_FALLBACK:
        outcome = ScanOutcome.INCONCLUSIVE
    elif final_n == 0 and dag_n == 0:
        outcome = ScanOutcome.INCONCLUSIVE
        if inp.is_production and inp.dag_error:
            mark_failed = True
            outcome = ScanOutcome.FAILED
    else:
        outcome = ScanOutcome.INCONCLUSIVE

    # Production: DAG error with zero real evals → failed
    if inp.is_production and not has_real_evals and inp.dag_error:
        mark_failed = True
        outcome = ScanOutcome.FAILED

    # Zero final evaluations after pipeline → never "success"
    if final_n == 0 and outcome is ScanOutcome.SUCCESS:
        outcome = ScanOutcome.INCONCLUSIVE

    # Mock score cannot yield success
    if mock_score and outcome is ScanOutcome.SUCCESS:
        outcome = ScanOutcome.INCONCLUSIVE

    return IntegrityDecision(
        execution_mode=execution_mode,
        data_source=data_source,
        result_source=result_source,
        score_source=inp.score_source,
        patches_source=inp.patches_source,
        outcome=outcome,
        remediation_eligible=remediation_eligible,
        warnings=warnings,
        mark_status_failed=mark_failed,
        error_message=error_message
        if mark_failed or outcome is not ScanOutcome.SUCCESS
        else (error_message if (inp.dag_error and outcome is ScanOutcome.PARTIAL) else None),
    )


def should_inject_synthetic_intents(
    *,
    is_production: bool,
    dag_evaluation_count: int,
    allow_synthetic_demo: bool = False,
) -> bool:
    """Synthetic intents only when explicitly opted in (never in production)."""
    return allow_synthetic_demo and (not is_production) and dag_evaluation_count <= 0


def should_inject_synthetic_contradictions(
    *,
    is_production: bool,
    contradiction_count: int,
    dag_error: str | None,
    allow_synthetic_demo: bool = False,
) -> bool:
    """Synthetic contradictions only when explicitly opted in (never in production)."""
    return (
        allow_synthetic_demo
        and (not is_production)
        and contradiction_count <= 0
        and bool(dag_error)
    )
