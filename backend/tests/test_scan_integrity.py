"""P0 regression: honest execution modes, fallback provenance, remediation gates."""

from __future__ import annotations

import pytest

from app.orchestration.scan_integrity import (
    ExecutionMode,
    IntegrityInput,
    PatchesSource,
    ResultSource,
    ScanOutcome,
    ScoreSource,
    decide_scan_integrity,
    should_inject_synthetic_contradictions,
    should_inject_synthetic_intents,
)


def test_real_llm_requires_evals_calls_and_no_mocks():
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=30,
            dag_success=True,
            dag_error=None,
            dag_error_reason=None,
            llm_calls_made=31,
            used_synthetic_intents=False,
            used_synthetic_contradictions=False,
            final_evaluation_count=30,
            score_source=ScoreSource.DETERMINISTIC_SCORER,
            patches_source=PatchesSource.ASSEMBLER,
            is_production=False,
        )
    )
    assert d.execution_mode is ExecutionMode.REAL_LLM
    assert d.result_source is ResultSource.REAL_PIPELINE
    assert d.outcome is ScanOutcome.SUCCESS
    assert d.remediation_eligible is True
    assert d.data_source == "live_pipeline"


def test_calls_made_alone_is_not_real_llm():
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=0,
            dag_success=False,
            dag_error="LLM structured call failed",
            dag_error_reason="intent_generation_failed",
            llm_calls_made=3,
            used_synthetic_intents=True,
            used_synthetic_contradictions=False,
            final_evaluation_count=30,
            score_source=ScoreSource.MOCK,
            patches_source=PatchesSource.MOCK,
            is_production=False,
        )
    )
    assert d.execution_mode is not ExecutionMode.REAL_LLM
    assert d.result_source is ResultSource.SYNTHETIC_FALLBACK
    assert d.outcome is ScanOutcome.INCONCLUSIVE
    assert d.remediation_eligible is False
    assert d.data_source == "synthetic_fallback"
    assert any("synthetic" in w.lower() for w in d.warnings)


def test_missing_credentials_path_synthetic_not_success():
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=0,
            dag_success=False,
            dag_error="LLM structured call failed: AuthenticationError",
            dag_error_reason="intent_generation_failed",
            llm_calls_made=0,
            used_synthetic_intents=True,
            used_synthetic_contradictions=True,
            final_evaluation_count=30,
            score_source=ScoreSource.MOCK,
            patches_source=PatchesSource.MOCK,
            is_production=False,
        )
    )
    assert d.execution_mode is ExecutionMode.SYNTHETIC_FALLBACK
    assert d.outcome is not ScanOutcome.SUCCESS
    assert d.remediation_eligible is False


@pytest.mark.parametrize(
    "reason",
    [
        "intent_generation_failed",
        "budget_exhausted",
        "entailment_failed",
        "unexpected_error",
    ],
)
def test_provider_style_failures_never_real_success(reason: str):
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=0,
            dag_success=False,
            dag_error=f"stage failed: {reason}",
            dag_error_reason=reason,
            llm_calls_made=0,
            used_synthetic_intents=True,
            used_synthetic_contradictions=False,
            final_evaluation_count=30,
            score_source=ScoreSource.MOCK,
            patches_source=PatchesSource.NONE,
            is_production=False,
        )
    )
    assert d.execution_mode is ExecutionMode.SYNTHETIC_FALLBACK
    assert d.outcome is ScanOutcome.INCONCLUSIVE
    assert d.remediation_eligible is False


def test_budget_exhaustion_with_partial_real_evals():
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=12,
            dag_success=False,
            dag_error="ACT budget exhausted",
            dag_error_reason="budget_exhausted",
            llm_calls_made=35,
            used_synthetic_intents=False,
            used_synthetic_contradictions=False,
            final_evaluation_count=12,
            score_source=ScoreSource.DETERMINISTIC_SCORER,
            patches_source=PatchesSource.NONE,
            is_production=False,
        )
    )
    assert d.result_source is ResultSource.PARTIAL_REAL
    assert d.outcome is ScanOutcome.PARTIAL
    # Evaluations that exist came from real LLM calls — mode is real_llm, outcome is partial.
    assert d.execution_mode is ExecutionMode.REAL_LLM
    assert d.remediation_eligible is False
    assert d.error_message is not None


def test_zero_intents_inconclusive_not_clean_audit():
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=0,
            dag_success=False,
            dag_error=None,
            dag_error_reason=None,
            llm_calls_made=0,
            used_synthetic_intents=False,
            used_synthetic_contradictions=False,
            final_evaluation_count=0,
            score_source=ScoreSource.NONE,
            patches_source=PatchesSource.NONE,
            is_production=False,
        )
    )
    assert d.result_source is ResultSource.INCONCLUSIVE
    assert d.outcome is ScanOutcome.INCONCLUSIVE
    assert d.remediation_eligible is False
    assert d.execution_mode is not ExecutionMode.REAL_LLM


def test_production_zero_evals_with_error_marks_failed():
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=0,
            dag_success=False,
            dag_error="LLM structured call failed",
            dag_error_reason="intent_generation_failed",
            llm_calls_made=0,
            used_synthetic_intents=False,
            used_synthetic_contradictions=False,
            final_evaluation_count=0,
            score_source=ScoreSource.NONE,
            patches_source=PatchesSource.NONE,
            is_production=True,
        )
    )
    assert d.mark_status_failed is True
    assert d.outcome is ScanOutcome.FAILED
    assert d.execution_mode is ExecutionMode.DETERMINISTIC
    assert d.remediation_eligible is False


def test_mock_score_blocks_real_llm_and_remediation():
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=30,
            dag_success=True,
            dag_error=None,
            dag_error_reason=None,
            llm_calls_made=31,
            used_synthetic_intents=False,
            used_synthetic_contradictions=False,
            final_evaluation_count=30,
            score_source=ScoreSource.MOCK,
            patches_source=PatchesSource.ASSEMBLER,
            is_production=False,
        )
    )
    assert d.execution_mode is not ExecutionMode.REAL_LLM
    assert d.remediation_eligible is False
    assert d.outcome is not ScanOutcome.SUCCESS


def test_empty_real_assembler_patches_still_eligible():
    """Real audit concluding no patches is a valid remediation conclusion."""
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=30,
            dag_success=True,
            dag_error=None,
            dag_error_reason=None,
            llm_calls_made=31,
            used_synthetic_intents=False,
            used_synthetic_contradictions=False,
            final_evaluation_count=30,
            score_source=ScoreSource.DETERMINISTIC_SCORER,
            patches_source=PatchesSource.ASSEMBLER,
            is_production=True,
        )
    )
    assert d.remediation_eligible is True
    assert d.outcome is ScanOutcome.SUCCESS


def test_synthetic_injection_gates_require_explicit_opt_in():
    # Normal non-prod path: no silent synthetic fill
    assert (
        should_inject_synthetic_intents(
            is_production=False, dag_evaluation_count=0, allow_synthetic_demo=False
        )
        is False
    )
    assert (
        should_inject_synthetic_intents(
            is_production=False, dag_evaluation_count=0, allow_synthetic_demo=True
        )
        is True
    )
    assert (
        should_inject_synthetic_intents(
            is_production=True, dag_evaluation_count=0, allow_synthetic_demo=True
        )
        is False
    )
    assert (
        should_inject_synthetic_intents(
            is_production=False, dag_evaluation_count=5, allow_synthetic_demo=True
        )
        is False
    )
    assert (
        should_inject_synthetic_contradictions(
            is_production=False,
            contradiction_count=0,
            dag_error="x",
            allow_synthetic_demo=False,
        )
        is False
    )
    assert (
        should_inject_synthetic_contradictions(
            is_production=False,
            contradiction_count=0,
            dag_error="x",
            allow_synthetic_demo=True,
        )
        is True
    )
    assert (
        should_inject_synthetic_contradictions(
            is_production=True,
            contradiction_count=0,
            dag_error="x",
            allow_synthetic_demo=True,
        )
        is False
    )


def test_zero_evals_with_calls_is_not_real_success():
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=0,
            dag_success=False,
            dag_error="auth failed",
            dag_error_reason="intent_generation_failed",
            llm_calls_made=2,
            used_synthetic_intents=False,
            used_synthetic_contradictions=False,
            final_evaluation_count=0,
            score_source=ScoreSource.NONE,
            patches_source=PatchesSource.NONE,
            is_production=False,
        )
    )
    assert d.execution_mode is not ExecutionMode.REAL_LLM
    assert d.outcome is not ScanOutcome.SUCCESS
    assert d.remediation_eligible is False


def test_synthetic_inputs_cannot_be_remediation_eligible_even_with_assembler_label():
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=0,
            dag_success=False,
            dag_error=None,
            dag_error_reason=None,
            llm_calls_made=0,
            used_synthetic_intents=True,
            used_synthetic_contradictions=False,
            final_evaluation_count=30,
            score_source=ScoreSource.DETERMINISTIC_SCORER,
            patches_source=PatchesSource.ASSEMBLER,
            is_production=False,
        )
    )
    assert d.remediation_eligible is False
    assert d.result_source is ResultSource.SYNTHETIC_FALLBACK


def test_error_message_redacts_bearer_like_content():
    d = decide_scan_integrity(
        IntegrityInput(
            dag_evaluation_count=0,
            dag_success=False,
            dag_error="Request failed Bearer gsk_secret_value_here",
            dag_error_reason="intent_generation_failed",
            llm_calls_made=0,
            used_synthetic_intents=False,
            used_synthetic_contradictions=False,
            final_evaluation_count=0,
            score_source=ScoreSource.NONE,
            patches_source=PatchesSource.NONE,
            is_production=True,
        )
    )
    assert d.error_message is not None
    assert "gsk_secret" not in d.error_message
