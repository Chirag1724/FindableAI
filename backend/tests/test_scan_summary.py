"""Unit tests for AI Website Health Brief v2 (scan_summary) — no PostgreSQL."""

from __future__ import annotations

import json
import uuid
from dataclasses import replace as dc_replace

import pytest

from app.core.llm_errors import ErrorClass, LLMProviderError
from app.orchestration import remediation_lifecycle as rl
from app.orchestration import scan_summary as scan_summary_mod
from app.orchestration.scan_summary import (
    CONTEXT_SCHEMA_VERSION,
    PROMPT_VERSION,
    ScanSnapshot,
    compute_input_hash,
    compute_verdict_and_signals,
    deserialize_scan_snapshot,
    map_remediation_status,
    serialize_scan_snapshot,
    validate_summary_payload,
)
from app.schemas.summary import (
    LlmFactStatement,
    LlmNextStep,
    LlmOverallAssessment,
    LlmSummaryPayload,
    RemediationStatusLabel,
    SummaryCoverage,
    SummaryPriority,
    SummarySignals,
    SummaryVerdict,
)


def _coverage(**kwargs: int | None) -> SummaryCoverage:
    defaults = {
        "evaluations_completed": 10,
        "evaluations_total": 10,
        "findings_included": 1,
        "omitted_count": 0,
    }
    defaults.update(kwargs)
    return SummaryCoverage(**defaults)


def _bare_snapshot(**overrides) -> ScanSnapshot:
    scan_id = overrides.pop("scan_id", uuid.uuid4())
    base = ScanSnapshot(
        scan_id=scan_id,
        url="https://unit.example/",
        status=overrides.pop("status", "completed"),
        outcome=overrides.pop("outcome", "success"),
        facts=overrides.pop("facts", {"F_dom_chunks": {"id": "F_dom_chunks", "value": 0}}),
        allowed_fact_ids=overrides.pop("allowed_fact_ids", frozenset({"F_dom_chunks"})),
        snapshot_numbers=overrides.pop("snapshot_numbers", frozenset({"0"})),
        snapshot_urls=overrides.pop("snapshot_urls", frozenset({"https://unit.example/"})),
        coverage=overrides.pop("coverage", _coverage()),
        omitted=overrides.pop("omitted", ()),
        verdict=SummaryVerdict.INSUFFICIENT_EVIDENCE,
        signals=SummarySignals(),
        remediation_eligible=overrides.pop("remediation_eligible", True),
        dom_chunk_count=overrides.pop("dom_chunk_count", 0),
        pages_crawled=overrides.pop("pages_crawled", 1),
        e_with_evidence=overrides.pop("e_with_evidence", 0),
        e_unknown_count=overrides.pop("e_unknown_count", 0),
        intent_total=overrides.pop("intent_total", 0),
    )
    if overrides:
        base = dc_replace(base, **overrides)
    verdict, signals = compute_verdict_and_signals(base)
    return dc_replace(base, verdict=verdict, signals=signals)


@pytest.mark.parametrize(
    ("state", "eligible", "expected"),
    [
        (rl.STATE_VERIFIED, True, RemediationStatusLabel.DONE),
        (rl.STATE_MUTATING, True, RemediationStatusLabel.IN_PROGRESS),
        (None, True, RemediationStatusLabel.NOT_STARTED),
        (rl.STATE_READY, True, RemediationStatusLabel.NOT_STARTED),
        (rl.STATE_VERIFIED, False, RemediationStatusLabel.UNAVAILABLE),
        (None, False, RemediationStatusLabel.UNAVAILABLE),
    ],
)
def test_map_remediation_status(
    state: str | None,
    eligible: bool,
    expected: RemediationStatusLabel,
) -> None:
    assert map_remediation_status(state, remediation_eligible=eligible) == expected


def test_compute_verdict_insufficient_all_unknown_zero_chunks() -> None:
    snap = _bare_snapshot(
        dom_chunk_count=0,
        e_with_evidence=0,
        e_unknown_count=3,
        intent_total=3,
        facts={
            "F_dom_chunks": {"id": "F_dom_chunks", "value": 0},
            "E_unknown_count": {"id": "E_unknown_count", "value": 3},
            "E_intent_total": {"id": "E_intent_total", "value": 3},
        },
    )
    assert snap.verdict == SummaryVerdict.INSUFFICIENT_EVIDENCE
    assert snap.signals.all_intents_unknown is True
    assert snap.signals.zero_dom_chunks is True


def test_compute_verdict_issues_found_contradicted_with_evidence() -> None:
    snap = _bare_snapshot(
        dom_chunk_count=2,
        e_with_evidence=1,
        e_unknown_count=0,
        intent_total=1,
        facts={
            "F_dom_chunks": {"id": "F_dom_chunks", "value": 2},
            "I_hours": {
                "id": "I_hours",
                "kind": "intent",
                "status": "CONTRADICTED",
                "evidence_count": 2,
            },
            "C_total": {"id": "C_total", "value": 0},
            "L_failed_audits": {"id": "L_failed_audits", "value": []},
            "S_overall": {"id": "S_overall", "value": 80.0},
            "S_pillar_ans": {"id": "S_pillar_ans", "value": 80.0},
            "S_pillar_con": {"id": "S_pillar_con", "value": 80.0},
            "S_pillar_str": {"id": "S_pillar_str", "value": 80.0},
            "S_pillar_acc": {"id": "S_pillar_acc", "value": 80.0},
        },
    )
    assert snap.verdict == SummaryVerdict.ISSUES_FOUND


def test_compute_verdict_scan_incomplete_partial_outcome() -> None:
    snap = _bare_snapshot(outcome="partial", dom_chunk_count=1, intent_total=1)
    assert snap.verdict == SummaryVerdict.SCAN_INCOMPLETE


def test_compute_verdict_score_pillar_mismatch() -> None:
    snap = _bare_snapshot(
        dom_chunk_count=1,
        e_with_evidence=1,
        intent_total=1,
        facts={
            "F_dom_chunks": {"id": "F_dom_chunks", "value": 1},
            "I_x": {
                "id": "I_x",
                "kind": "intent",
                "status": "CONTRADICTED",
                "evidence_count": 1,
            },
            "C_total": {"id": "C_total", "value": 0},
            "L_failed_audits": {"id": "L_failed_audits", "value": []},
            "S_overall": {"id": "S_overall", "value": 30.0},
            "S_pillar_ans": {"id": "S_pillar_ans", "value": 0.0},
            "S_pillar_con": {"id": "S_pillar_con", "value": 0.0},
            "S_pillar_str": {"id": "S_pillar_str", "value": 0.0},
            "S_pillar_acc": {"id": "S_pillar_acc", "value": 0.0},
        },
    )
    assert snap.signals.score_pillar_mismatch is True


def _valid_payload(**kwargs) -> LlmSummaryPayload:
    return LlmSummaryPayload(
        overall_assessment=LlmOverallAssessment(
            text=kwargs.get("overall", "Limited evidence from this scan."),
            fact_ids=kwargs.get("oa_ids", ["F_dom_chunks"]),
        ),
        what_the_scan_found=[
            LlmFactStatement(text="Chunk count was recorded.", fact_ids=["F_dom_chunks"]),
        ],
        why_it_matters=[
            LlmFactStatement(
                text="Grounding depends on captured page text.", fact_ids=["F_dom_chunks"]
            ),
        ],
        evidence_gaps=[
            LlmFactStatement(
                text="All intents are UNKNOWN and no DOM chunks were captured.",
                fact_ids=["E_unknown_count", "F_dom_chunks"],
            ),
        ],
        next_steps=[
            LlmNextStep(
                text="Re-run after pages expose readable content.",
                priority=SummaryPriority.MEDIUM,
                fact_ids=["F_dom_chunks"],
            ),
        ],
        limitations="",
    )


def test_validate_drops_unknown_fact_id() -> None:
    snap = _bare_snapshot(
        allowed_fact_ids=frozenset({"F_dom_chunks", "E_unknown_count"}),
        facts={
            "F_dom_chunks": {"id": "F_dom_chunks", "value": 0},
            "E_unknown_count": {"id": "E_unknown_count", "value": 2},
        },
    )
    raw = _valid_payload()
    raw.what_the_scan_found[0].fact_ids = ["phantom_id", "F_dom_chunks"]
    cleaned, _errors = validate_summary_payload(
        raw,
        allowed_fact_ids=snap.allowed_fact_ids,
        snapshot_numbers=snap.snapshot_numbers,
        snapshot_urls=snap.snapshot_urls,
        verdict=snap.verdict,
    )
    assert cleaned is not None
    assert cleaned.what_the_scan_found[0].fact_ids == ["F_dom_chunks"]
    assert "phantom_id" not in cleaned.what_the_scan_found[0].fact_ids


def test_validate_rejects_forbidden_health_language_for_insufficient_evidence() -> None:
    snap = _bare_snapshot(
        e_unknown_count=2,
        intent_total=2,
        allowed_fact_ids=frozenset({"F_dom_chunks", "E_unknown_count"}),
    )
    raw = _valid_payload(overall="Your site looks healthy with no issues.")
    cleaned, errors = validate_summary_payload(
        raw,
        allowed_fact_ids=snap.allowed_fact_ids,
        snapshot_numbers=snap.snapshot_numbers,
        snapshot_urls=snap.snapshot_urls,
        verdict=SummaryVerdict.INSUFFICIENT_EVIDENCE,
    )
    assert cleaned is None
    assert any("forbidden health" in e for e in errors)


def test_validate_rejects_url_not_in_snapshot() -> None:
    snap = _bare_snapshot(snapshot_urls=frozenset({"https://unit.example/"}))
    raw = _valid_payload(
        overall="See https://evil.example/phish for context.",
    )
    cleaned, errors = validate_summary_payload(
        raw,
        allowed_fact_ids=snap.allowed_fact_ids,
        snapshot_numbers=snap.snapshot_numbers,
        snapshot_urls=snap.snapshot_urls,
        verdict=snap.verdict,
    )
    assert cleaned is None
    assert any("URL not in snapshot" in e for e in errors)


def test_validate_rejects_numbers_not_in_snapshot() -> None:
    snap = _bare_snapshot(snapshot_numbers=frozenset({"0", "1"}))
    raw = _valid_payload(overall="We counted 999 separate problems.")
    cleaned, errors = validate_summary_payload(
        raw,
        allowed_fact_ids=snap.allowed_fact_ids,
        snapshot_numbers=snap.snapshot_numbers,
        snapshot_urls=snap.snapshot_urls,
        verdict=snap.verdict,
    )
    assert cleaned is None
    assert any("number 999 not in snapshot" in e for e in errors)


def test_compute_input_hash_changes_when_intent_status_changes() -> None:
    shared_facts = {
        "F_dom_chunks": {"id": "F_dom_chunks", "value": 1},
        "I_hours": {
            "id": "I_hours",
            "kind": "intent",
            "status": "UNKNOWN",
            "evidence_count": 0,
        },
    }
    a = _bare_snapshot(facts=dict(shared_facts), allowed_fact_ids=frozenset(shared_facts))
    shared_facts["I_hours"] = {
        **shared_facts["I_hours"],
        "status": "CONTRADICTED",
        "evidence_count": 2,
    }
    b = _bare_snapshot(facts=dict(shared_facts), allowed_fact_ids=frozenset(shared_facts))
    assert compute_input_hash(a) != compute_input_hash(b)


def test_compute_input_hash_includes_context_schema_version() -> None:
    snap = _bare_snapshot()
    manual = {
        "context_schema_version": CONTEXT_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "facts": {k: snap.facts[k] for k in sorted(snap.facts.keys())},
    }
    import hashlib

    expected = hashlib.sha256(
        json.dumps(
            manual, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
        ).encode("utf-8")
    ).hexdigest()
    assert compute_input_hash(snap) == expected
    assert CONTEXT_SCHEMA_VERSION == "ctx_v2"


def test_prompt_version_constant_is_v2() -> None:
    assert PROMPT_VERSION == "v2"
    assert scan_summary_mod.PROMPT_VERSION == "v2"


def test_serialize_deserialize_snapshot_roundtrip() -> None:
    snap = _bare_snapshot(
        dom_chunk_count=2,
        e_with_evidence=1,
        e_unknown_count=1,
        intent_total=2,
        facts={
            "F_dom_chunks": {"id": "F_dom_chunks", "value": 2},
            "E_unknown_count": {"id": "E_unknown_count", "value": 1},
            "I_hours": {
                "id": "I_hours",
                "kind": "intent",
                "status": "UNKNOWN",
                "evidence_count": 0,
            },
        },
        allowed_fact_ids=frozenset({"F_dom_chunks", "E_unknown_count", "I_hours"}),
    )
    stored = serialize_scan_snapshot(snap)
    assert stored["context_schema_version"] == CONTEXT_SCHEMA_VERSION
    assert stored["prompt_version"] == PROMPT_VERSION
    assert stored["input_hash"] == compute_input_hash(snap)

    class _Scan:
        id = snap.scan_id
        url = snap.url
        status = snap.status
        outcome = snap.outcome
        remediation_eligible = snap.remediation_eligible
        pages_crawled = snap.pages_crawled

    restored = deserialize_scan_snapshot(stored, _Scan())  # type: ignore[arg-type]
    assert restored is not None
    assert restored.verdict == snap.verdict
    assert restored.facts == snap.facts
    assert compute_input_hash(restored) == compute_input_hash(snap)


def test_deserialize_rejects_schema_mismatch() -> None:
    snap = _bare_snapshot()
    stored = serialize_scan_snapshot(snap)
    stored["context_schema_version"] = "ctx_v0"

    class _Scan:
        id = snap.scan_id
        url = snap.url
        status = snap.status
        outcome = snap.outcome
        remediation_eligible = True
        pages_crawled = 1

    assert deserialize_scan_snapshot(stored, _Scan()) is None  # type: ignore[arg-type]


def test_summary_api_keys_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_summary_mod.settings, "GEMINI_API_KEY_AI_SUMMARY", "key-a")
    monkeypatch.setattr(scan_summary_mod.settings, "GEMINI_API_KEY_AI_SUMMARY1", "key-b")
    monkeypatch.setattr(scan_summary_mod.settings, "GEMINI_API_KEY", "key-c")
    monkeypatch.setattr(scan_summary_mod.settings, "GROQ_API_KEY", "key-d")
    assert scan_summary_mod._summary_api_keys() == ["key-a", "key-b", "key-c", "key-d"]


def test_is_output_truncation_error_detects_max_tokens() -> None:
    exc = LLMProviderError(
        "The output is incomplete due to a max_tokens length limit.",
        provider="gemini",
        model="gemini-2.5-flash",
        error_class=ErrorClass.CONTEXT_LENGTH,
    )
    assert scan_summary_mod._is_output_truncation_error(exc) is True
    assert scan_summary_mod._is_retryable_provider_error(exc) is False


def test_default_summary_model_is_gemini_35_flash_lite() -> None:
    from app.core.config import settings as app_settings

    assert "gemini-3.5-flash-lite" in app_settings.SUMMARY_LLM_MODEL
    assert int(app_settings.SUMMARY_MAX_OUTPUT_TOKENS) >= 8192


def test_no_longer_available_model_classified_not_found() -> None:
    from app.core.llm_errors import ErrorClass, classify_provider_error

    msg = (
        "Error code: 404 - This model models/gemini-2.5-flash is no longer "
        "available to new users. Please update your code to use models/gemini-3.8-flash"
    )
    ce = classify_provider_error(None, msg)
    assert ce.error_class is ErrorClass.NOT_FOUND


def test_llm_summary_payload_coerces_single_object_lists() -> None:
    """gemini-3.5-flash-lite often returns one object instead of a one-item array."""
    from app.schemas.summary import LlmSummaryPayload

    payload = LlmSummaryPayload.model_validate(
        {
            "overall_assessment": {
                "text": "Evidence was limited for site checks.",
                "fact_ids": ["E_unknown_count"],
            },
            "what_the_scan_found": {
                "text": "Many checks UNKNOWN.",
                "fact_ids": ["E_unknown_count"],
            },
            "why_it_matters": {
                "text": "Insufficient evidence blocks confidence.",
                "fact_ids": ["E_unknown_count"],
            },
            "evidence_gaps": {
                "text": "Unknown checks and sparse DOM.",
                "fact_ids": ["E_unknown_count", "F_dom_chunks"],
            },
            "next_steps": {
                "text": "Re-scan with more pages.",
                "priority": "medium",
                "fact_ids": ["F_dom_chunks"],
            },
            "limitations": {"text": "Partial coverage."},
        }
    )
    assert len(payload.what_the_scan_found) == 1
    assert len(payload.why_it_matters) == 1
    assert len(payload.evidence_gaps) == 1
    assert len(payload.next_steps) == 1
    assert payload.limitations == "Partial coverage."


def test_ensure_evidence_gaps_fills_insufficient_verdict() -> None:
    snap = _bare_snapshot(
        e_unknown_count=3,
        dom_chunk_count=0,
        intent_total=3,
        facts={
            "E_unknown_count": {"id": "E_unknown_count", "value": 3},
            "F_dom_chunks": {"id": "F_dom_chunks", "value": 0},
        },
        allowed_fact_ids=frozenset({"E_unknown_count", "F_dom_chunks"}),
    )
    empty = LlmSummaryPayload(
        overall_assessment=LlmOverallAssessment(
            text="Evidence was too limited to confirm site claims.",
            fact_ids=["E_unknown_count"],
        ),
        evidence_gaps=[],
    )
    filled = scan_summary_mod._ensure_evidence_gaps(empty, snap)
    assert filled.evidence_gaps
    assert "E_unknown_count" in filled.evidence_gaps[0].fact_ids


def test_prompt_version_and_filtering_for_scope() -> None:
    from app.schemas.summary import SummaryScope

    assert scan_summary_mod._prompt_version_for_scope(SummaryScope.INTELLIGENCE) == "v2"
    assert scan_summary_mod._prompt_version_for_scope(SummaryScope.LIGHTHOUSE) == "lh_v2"

    facts = {
        "scan_meta": {"id": "scan_meta", "url": "https://example.com"},
        "I_intent_1": {"id": "I_intent_1", "query": "pricing"},
        "C_contra_1": {"id": "C_contra_1", "desc": "mismatch"},
        "L_chatgpt_score": {"id": "L_chatgpt_score", "score": 85},
        "F_pages": {"id": "F_pages", "value": 5},
    }

    intel_facts = scan_summary_mod._filter_facts_for_scope(facts, "intelligence")
    assert "I_intent_1" in intel_facts
    assert "C_contra_1" in intel_facts
    assert "L_chatgpt_score" not in intel_facts
    assert "F_pages" in intel_facts

    lh_facts = scan_summary_mod._filter_facts_for_scope(facts, "lighthouse")
    assert "I_intent_1" not in lh_facts
    assert "C_contra_1" not in lh_facts
    assert "L_chatgpt_score" in lh_facts
    assert "F_pages" in lh_facts
    assert "scan_meta" in lh_facts


def test_system_prompt_differs_by_scope() -> None:
    from app.schemas.summary import SummaryScope, SummaryVerdict

    intel_prompt = scan_summary_mod._system_prompt(
        verdict=SummaryVerdict.ISSUES_FOUND,
        scope=SummaryScope.INTELLIGENCE,
    )
    lh_prompt = scan_summary_mod._system_prompt(
        verdict=SummaryVerdict.ISSUES_FOUND,
        scope=SummaryScope.LIGHTHOUSE,
    )

    assert "Search Intelligence" in intel_prompt
    assert "AI Bot Readiness" in lh_prompt
    assert intel_prompt != lh_prompt
