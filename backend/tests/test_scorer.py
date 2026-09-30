"""Unit tests for deterministic F-score calculator and Schema.org checker."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.engines.scorer import (
    ScoreInputs,
    Scorer,
    ScorerError,
    adapt_score_breakdown_to_api,
    analyze_schema_org,
    calculate_accessibility,
    calculate_answerability,
    calculate_consistency,
    calculate_f_score,
    calculate_structure,
    derive_grade,
    provisional_score_weights,
)
from app.schemas.intelligence import (
    Contradiction,
    ContradictionSeverity,
    EntailmentStatus,
    IntentEvaluation,
)
from app.schemas.scoring import ContradictionSeverityWeights, ScoreWeights


@dataclass
class FakeChunk:
    content: str
    tag: str = "p"
    word_count: int = 10


def _eval(status: EntailmentStatus, intent_id: str = "i1") -> IntentEvaluation:
    return IntentEvaluation(
        intent_id=intent_id,
        query="Example question?",
        status=status,
        reasoning="fixture",
        evidence=[],
        confidence=0.9,
    )


def _contra(
    *,
    severity: ContradictionSeverity,
    entity: str = "phone:primary",
    cid: str = "c1",
) -> Contradiction:
    return Contradiction(
        entity=entity,
        conflict="conflict",
        values=[{"value": "a", "chunk_id": "x"}, {"value": "b", "chunk_id": "y"}],
        severity=severity,
        contradiction_id=cid,
    )


# --- F-score mechanics ---


def test_all_components_100_yields_f_100():
    assert calculate_f_score(s_ans=100, s_con=100, s_str=100, s_acc=100) == 100.0


def test_all_components_0_yields_f_0():
    assert calculate_f_score(s_ans=0, s_con=0, s_str=0, s_acc=0) == 0.0


def test_custom_weights():
    weights = ScoreWeights(w_ans=1.0, w_con=0.0, w_str=0.0, w_acc=0.0)
    assert calculate_f_score(s_ans=40, s_con=100, s_str=100, s_acc=100, weights=weights) == 40.0


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        ScoreWeights(w_ans=0.5, w_con=0.5, w_str=0.5, w_acc=0.0)


def test_negative_weights_rejected():
    with pytest.raises(ValueError):
        ScoreWeights(w_ans=-0.1, w_con=0.5, w_str=0.3, w_acc=0.3)


def test_out_of_range_component_rejected():
    with pytest.raises(ScorerError):
        calculate_f_score(s_ans=120, s_con=50, s_str=50, s_acc=50)


def test_floating_point_weight_tolerance():
    # Construct via model with exact sum; aggregation is stable.
    w = provisional_score_weights()
    a = calculate_f_score(s_ans=33.3, s_con=33.3, s_str=33.3, s_acc=33.3, weights=w)
    b = calculate_f_score(s_ans=33.3, s_con=33.3, s_str=33.3, s_acc=33.3, weights=w)
    assert a == b


def test_deterministic_repeated_calculation():
    inputs = ScoreInputs(
        intent_evaluations=[_eval(EntailmentStatus.SUPPORTED)],
        contradictions=[],
        html_documents=[],
        chunks=[FakeChunk("Call +91 9876543210 open Monday")],
        extracted_fact_count=5,
    )
    scorer = Scorer()
    assert scorer.score(inputs).model_dump() == scorer.score(inputs).model_dump()


# --- S_ans ---


def test_s_ans_all_supported():
    score, _ = calculate_answerability(
        [_eval(EntailmentStatus.SUPPORTED, f"i{i}") for i in range(3)]
    )
    assert score == 100.0


def test_s_ans_all_unknown():
    score, _ = calculate_answerability([_eval(EntailmentStatus.UNKNOWN)])
    assert score == 0.0


def test_s_ans_all_contradicted():
    score, _ = calculate_answerability([_eval(EntailmentStatus.CONTRADICTED)])
    assert score == 0.0


def test_s_ans_partial():
    score, _ = calculate_answerability([_eval(EntailmentStatus.PARTIALLY_SUPPORTED)])
    assert score == 50.0


def test_s_ans_mixed():
    score, diag = calculate_answerability(
        [
            _eval(EntailmentStatus.SUPPORTED, "a"),
            _eval(EntailmentStatus.PARTIALLY_SUPPORTED, "b"),
            _eval(EntailmentStatus.UNKNOWN, "c"),
            _eval(EntailmentStatus.CONTRADICTED, "d"),
        ]
    )
    assert score == 37.5
    assert diag["evaluated"] == 4


def test_s_ans_empty():
    score, diag = calculate_answerability([])
    assert score == 0.0
    assert diag["evaluated"] == 0


# --- S_con ---


def test_s_con_zero_contradictions():
    score, _ = calculate_consistency([], fact_count=10)
    assert score == 100.0


def test_s_con_hard_penalty():
    score, diag = calculate_consistency(
        [_contra(severity=ContradictionSeverity.HARD_CONTRADICTION)],
        fact_count=10,
        severity_weights=ContradictionSeverityWeights(hard=1.0, soft=0.5),
    )
    assert score == 90.0
    assert diag["hard"] == 1


def test_s_con_soft_penalty():
    score, _ = calculate_consistency(
        [_contra(severity=ContradictionSeverity.SOFT_INCONSISTENCY)],
        fact_count=10,
        severity_weights=ContradictionSeverityWeights(hard=1.0, soft=0.5),
    )
    assert score == 95.0


def test_s_con_bounded():
    score, _ = calculate_consistency(
        [
            _contra(severity=ContradictionSeverity.HARD_CONTRADICTION, cid=f"c{i}", entity=f"e{i}")
            for i in range(50)
        ],
        fact_count=2,
    )
    assert 0.0 <= score <= 100.0
    assert score == 0.0


def test_s_con_duplicate_contradictions_not_double_counted():
    c = _contra(severity=ContradictionSeverity.HARD_CONTRADICTION, cid="same")
    score_one, _ = calculate_consistency([c], fact_count=10)
    score_dup, diag = calculate_consistency([c, c], fact_count=10)
    assert score_one == score_dup
    assert diag["contradictions"] == 1


# --- Schema.org ---


def _html_with_jsonld(payload: str) -> str:
    return f'<html><head><script type="application/ld+json">{payload}</script></head><body></body></html>'


def test_schema_local_business():
    html = _html_with_jsonld(
        '{"@type":"Restaurant","name":"Bistro","address":{"@type":"PostalAddress","streetAddress":"1 Main"}}'
    )
    report = analyze_schema_org([html])
    lb = next(t for t in report.types if t.schema_type == "LocalBusiness")
    assert lb.present and lb.valid


def test_schema_postal_address():
    html = _html_with_jsonld(
        '{"@type":"PostalAddress","streetAddress":"1 Main","addressLocality":"Bengaluru"}'
    )
    report = analyze_schema_org([html])
    pa = next(t for t in report.types if t.schema_type == "PostalAddress")
    assert pa.present and pa.valid


def test_schema_opening_hours():
    html = _html_with_jsonld(
        '{"@type":"OpeningHoursSpecification","dayOfWeek":"Monday","opens":"10:00","closes":"22:00"}'
    )
    report = analyze_schema_org([html])
    oh = next(t for t in report.types if t.schema_type == "OpeningHoursSpecification")
    assert oh.present and oh.valid


def test_schema_geo():
    html = _html_with_jsonld('{"@type":"GeoCoordinates","latitude":12.97,"longitude":77.59}')
    report = analyze_schema_org([html])
    geo = next(t for t in report.types if t.schema_type == "GeoCoordinates")
    assert geo.present and geo.valid


def test_schema_menu():
    html = _html_with_jsonld('{"@type":"Menu","name":"Dinner","hasMenuItem":[{"name":"Soup"}]}')
    report = analyze_schema_org([html])
    menu = next(t for t in report.types if t.schema_type == "Menu")
    assert menu.present and menu.valid


def test_schema_faq():
    html = _html_with_jsonld(
        '{"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"Hours?","acceptedAnswer":{"@type":"Answer","text":"10-10"}}]}'
    )
    report = analyze_schema_org([html])
    faq = next(t for t in report.types if t.schema_type == "FAQPage")
    assert faq.present and faq.valid


def test_schema_multiple_blocks_and_array():
    html = """
    <html><head>
    <script type="application/ld+json">{"@type":"LocalBusiness","name":"A","telephone":"1"}</script>
    <script type="application/ld+json">[{"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"Q"}]}]</script>
    </head></html>
    """
    report = analyze_schema_org([html])
    assert report.total_blocks == 2
    assert next(t for t in report.types if t.schema_type == "LocalBusiness").present
    assert next(t for t in report.types if t.schema_type == "FAQPage").present


def test_schema_graph_and_type_array():
    html = _html_with_jsonld(
        '{"@graph":[{"@type":["LocalBusiness","Restaurant"],"name":"B","address":"x"},'
        '{"@type":"GeoCoordinates","latitude":1,"longitude":2}]}'
    )
    report = analyze_schema_org([html])
    assert next(t for t in report.types if t.schema_type == "LocalBusiness").present
    assert next(t for t in report.types if t.schema_type == "GeoCoordinates").valid


def test_schema_malformed_json():
    html = _html_with_jsonld("{not-json")
    report = analyze_schema_org([html])
    assert report.malformed_blocks == 1
    assert "INVALID_JSON" in report.issues


def test_schema_absent():
    report = analyze_schema_org(["<html><body>No schema</body></html>"])
    assert report.total_blocks == 0
    assert report.score == 0.0
    assert all(not t.present for t in report.types)


def test_schema_mixed_valid_and_malformed():
    html = """
    <html><head>
    <script type="application/ld+json">{bad</script>
    <script type="application/ld+json">{"@type":"GeoCoordinates","latitude":1,"longitude":2}</script>
    </head></html>
    """
    report = analyze_schema_org([html])
    assert report.malformed_blocks == 1
    assert next(t for t in report.types if t.schema_type == "GeoCoordinates").valid


def test_schema_nested_entities():
    html = _html_with_jsonld(
        '{"@type":"Restaurant","name":"B","address":{"@type":"PostalAddress","streetAddress":"1 Main"},'
        '"geo":{"@type":"GeoCoordinates","latitude":1,"longitude":2}}'
    )
    report = analyze_schema_org([html])
    assert next(t for t in report.types if t.schema_type == "PostalAddress").present
    assert next(t for t in report.types if t.schema_type == "GeoCoordinates").present


# --- S_str ---


def test_s_str_all_six_present():
    parts = [
        '{"@type":"LocalBusiness","name":"N","telephone":"1"}',
        '{"@type":"PostalAddress","streetAddress":"1"}',
        '{"@type":"OpeningHoursSpecification","opens":"10:00","closes":"22:00"}',
        '{"@type":"GeoCoordinates","latitude":1,"longitude":2}',
        '{"@type":"Menu","name":"M","hasMenuItem":[]}',
        '{"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"Q"}]}',
    ]
    html = (
        "<html><head>"
        + "".join(f'<script type="application/ld+json">{p}</script>' for p in parts)
        + "</head></html>"
    )
    report = analyze_schema_org([html])
    score, diag = calculate_structure(report)
    assert score == 100.0
    assert diag["structurally_valid"] == 6


def test_s_str_none_present():
    report = analyze_schema_org(["<html></html>"])
    score, _ = calculate_structure(report)
    assert score == 0.0


def test_s_str_partial_and_invalid_do_not_count_as_valid():
    html = _html_with_jsonld('{"@type":"LocalBusiness"}')  # missing name/location
    report = analyze_schema_org([html])
    lb = next(t for t in report.types if t.schema_type == "LocalBusiness")
    assert lb.present
    assert lb.valid is False
    score, diag = calculate_structure(report)
    assert score == 0.0
    assert diag["present"] == 1
    assert diag["structurally_valid"] == 0


def test_s_str_equal_weight_one_of_six():
    html = _html_with_jsonld('{"@type":"GeoCoordinates","latitude":1,"longitude":2}')
    report = analyze_schema_org([html])
    score, _ = calculate_structure(report)
    assert abs(score - (100.0 / 6.0)) < 1e-9


# --- S_acc ---


def test_s_acc_fully_extractable():
    chunks = [
        FakeChunk("Welcome to Bistro. Call +91 9876543210", "h1", 6),
        FakeChunk("Email hello@bistro.com Address 12 MG Road", "p", 6),
        FakeChunk("Open Monday 10 AM price ₹500", "p", 6),
    ]
    score, diag = calculate_accessibility(chunks)
    # field_ratio=1, text_ratio=1, heading_ratio=1/3 → 100*(7/9)
    assert score == pytest.approx(100.0 * (1.0 + 1.0 + (1.0 / 3.0)) / 3.0)
    assert diag["critical_fields_found"] >= 4
    assert diag["heading_support"] == pytest.approx(1.0 / 3.0)


def test_s_acc_partial():
    chunks = [FakeChunk("Welcome only", "p", 2)]
    score, diag = calculate_accessibility(chunks)
    assert 0.0 < score < 80.0
    assert diag["critical_fields_found"] < diag["critical_fields_total"]


def test_s_acc_missing_critical():
    chunks = [FakeChunk("....", "div", 0)]
    score, _ = calculate_accessibility(chunks)
    assert score < 50.0


def test_s_acc_empty():
    score, diag = calculate_accessibility([])
    assert score == 0.0
    assert diag["chunk_count"] == 0


def test_s_acc_only_supported_signals():
    _, diag = calculate_accessibility([FakeChunk("x", "p", 1)])
    assert set(diag) >= {
        "critical_fields_found",
        "text_extractability",
        "heading_support",
        "chunk_count",
    }


# --- Integration ---


def test_complete_score_breakdown_scanresult_fields():
    html = _html_with_jsonld(
        '{"@type":"LocalBusiness","name":"N","telephone":"1",'
        '"address":{"@type":"PostalAddress","streetAddress":"1"}}'
    )
    result = Scorer().score(
        ScoreInputs(
            intent_evaluations=[
                _eval(EntailmentStatus.SUPPORTED, "a"),
                _eval(EntailmentStatus.UNKNOWN, "b"),
            ],
            contradictions=[],
            html_documents=[html],
            chunks=[FakeChunk("Call +91 9999999999 open Monday", "h2", 5)],
            extracted_fact_count=4,
        )
    )
    assert 0.0 <= result.f_score <= 100.0
    for field in ("f_score", "s_ans", "s_con", "s_str", "s_acc"):
        assert hasattr(result, field)
    assert result.schema_report.required_types
    assert "weights_note" in result.diagnostics


def test_scorer_does_not_invoke_llm(monkeypatch: pytest.MonkeyPatch):
    def boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr("app.core.llm.LLMClient.create", boom)
    Scorer().score(
        ScoreInputs(intent_evaluations=[], contradictions=[], html_documents=[], chunks=[])
    )


# --- Phase E hardening regressions ---


@dataclass
class EvidenceLikeChunk:
    id: str
    url: str
    dom_path: str
    content: str
    tag: str = "p"
    word_count: int = 10


def test_s_con_prefers_explicit_extracted_fact_count():
    result = Scorer().score(
        ScoreInputs(
            contradictions=[_contra(severity=ContradictionSeverity.HARD_CONTRADICTION)],
            extracted_fact_count=10,
            chunks=[
                EvidenceLikeChunk(
                    id="c1",
                    url="https://ex.com",
                    dom_path="/p[1]",
                    content="Call +91 9876543210 and also +91 9123456789",
                )
            ],
        )
    )
    assert result.diagnostics["s_con"]["fact_count"] == 10
    assert result.diagnostics["s_con"]["fact_count_source"] == "explicit"
    assert result.diagnostics["s_con"]["insufficient_denominator"] is False
    assert result.s_con == 90.0


def test_s_con_derives_fact_count_via_extract_facts():
    result = Scorer().score(
        ScoreInputs(
            contradictions=[_contra(severity=ContradictionSeverity.HARD_CONTRADICTION)],
            chunks=[
                EvidenceLikeChunk(
                    id="c1",
                    url="https://ex.com/a",
                    dom_path="/p[1]",
                    content="Call +91 9876543210",
                ),
                EvidenceLikeChunk(
                    id="c2",
                    url="https://ex.com/b",
                    dom_path="/p[2]",
                    content="Email hello@bistro.com",
                ),
            ],
        )
    )
    diag = result.diagnostics["s_con"]
    assert diag["fact_count_source"] == "extract_facts"
    assert diag["fact_count"] >= 2
    assert diag["insufficient_denominator"] is False
    assert result.s_con < 100.0


def test_s_con_insufficient_denominator_without_entity_proxy():
    """Contradiction entity uniqueness must not substitute for extracted facts."""
    result = Scorer().score(
        ScoreInputs(
            contradictions=[
                _contra(
                    severity=ContradictionSeverity.HARD_CONTRADICTION,
                    entity=f"phone:{i}",
                    cid=f"c{i}",
                )
                for i in range(5)
            ],
            chunks=[FakeChunk("plain text without evidence ids")],
        )
    )
    diag = result.diagnostics["s_con"]
    assert diag["insufficient_denominator"] is True
    assert diag["fact_count_source"] == "insufficient"
    assert diag["fallback"] == "s_con_0_without_fact_denominator"
    assert result.s_con == 0.0


def test_schema_source_count_tracks_distinct_html_documents():
    doc_a = _html_with_jsonld('{"@type":"Restaurant","name":"A","telephone":"1"}')
    doc_b = _html_with_jsonld('{"@type":"Restaurant","name":"B","telephone":"2"}')
    doc_c = _html_with_jsonld('{"@type":"GeoCoordinates","latitude":1,"longitude":2}')
    report = analyze_schema_org([doc_a, doc_b, doc_c])
    lb = next(t for t in report.types if t.schema_type == "LocalBusiness")
    geo = next(t for t in report.types if t.schema_type == "GeoCoordinates")
    assert lb.occurrences == 2
    assert lb.source_count == 2
    assert geo.occurrences == 1
    assert geo.source_count == 1


def test_schema_plain_json_object_is_not_valid_schema_block():
    html = _html_with_jsonld('{"foo":"bar"}')
    report = analyze_schema_org([html])
    assert report.total_blocks == 1
    assert report.valid_blocks == 0
    assert report.invalid_blocks == 1
    assert report.malformed_blocks == 0
    assert "INVALID_TYPE:no_schema_entities" in report.issues


def test_schema_malformed_preserved_alongside_non_schema_json():
    html = """
    <html><head>
    <script type="application/ld+json">{bad</script>
    <script type="application/ld+json">{"foo":"bar"}</script>
    <script type="application/ld+json">{"@type":"GeoCoordinates","latitude":1,"longitude":2}</script>
    </head></html>
    """
    report = analyze_schema_org([html])
    assert report.malformed_blocks == 1
    assert report.invalid_blocks == 1
    assert report.valid_blocks == 1
    assert "INVALID_JSON" in report.issues
    assert "INVALID_TYPE:no_schema_entities" in report.issues


def test_s_acc_heading_ratio_is_heading_over_total_chunks():
    chunks = [
        FakeChunk("Welcome", "h1", 1),
        FakeChunk("body", "p", 1),
        FakeChunk("body", "p", 1),
        FakeChunk("body", "p", 1),
        FakeChunk("body", "p", 1),
        FakeChunk("body", "p", 1),
        FakeChunk("body", "p", 1),
        FakeChunk("body", "p", 1),
        FakeChunk("body", "p", 1),
        FakeChunk("body", "p", 1),
    ]
    _, diag = calculate_accessibility(chunks)
    assert diag["heading_chunks"] == 1
    assert diag["chunk_count"] == 10
    assert diag["heading_support"] == pytest.approx(0.1)
    # Old 15%-saturation formula would have yielded ~0.666; ensure it is gone.
    assert diag["heading_support"] < 0.2


def test_s_acc_heading_ratio_deterministic():
    chunks = [FakeChunk("H", "h2", 1), FakeChunk("P", "p", 1), FakeChunk("P", "p", 1)]
    a = calculate_accessibility(chunks)
    b = calculate_accessibility(chunks)
    assert a == b
    assert a[1]["heading_support"] == pytest.approx(1.0 / 3.0)


# --- S-Tier Grading & API Adapter Tests ---


def test_derive_grade_s_tier_and_thresholds():
    # S tier requires >= 95.0 and zero contradictions
    assert derive_grade(98.0, contradiction_count=0) == "S"
    assert derive_grade(95.0, contradiction_count=0) == "S"
    # >= 95.0 with contradictions falls back to A+
    assert derive_grade(96.0, contradiction_count=1) == "A+"

    # Standard tiers
    assert derive_grade(92.0) == "A+"
    assert derive_grade(87.0) == "A"
    assert derive_grade(82.0) == "B+"
    assert derive_grade(75.0) == "B"
    assert derive_grade(67.0) == "C+"
    assert derive_grade(62.0) == "C"
    assert derive_grade(57.0) == "D+"
    assert derive_grade(52.0) == "D"
    assert derive_grade(35.0) == "F"


def test_adapt_score_breakdown_to_api():
    html = """
    <html><head>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"LocalBusiness","name":"Cafe"}</script>
    </head><body><h1>Welcome to Cafe</h1><p>Call +1 555-123-4567 Monday open</p></body></html>
    """
    inputs = ScoreInputs(
        intent_evaluations=[
            _eval(EntailmentStatus.SUPPORTED, "i1"),
            _eval(EntailmentStatus.SUPPORTED, "i2"),
        ],
        contradictions=[],
        html_documents=[html],
        chunks=[FakeChunk("Call +1 555-123-4567 Monday open", "h1", 6)],
        extracted_fact_count=5,
    )
    score_breakdown = Scorer().score(inputs)
    api_breakdown = adapt_score_breakdown_to_api(score_breakdown)

    assert api_breakdown.overall_score == round(score_breakdown.f_score, 1)
    assert api_breakdown.coverage.score == round(score_breakdown.s_ans, 1)
    assert api_breakdown.coverage.weight == 0.40
    assert api_breakdown.contradiction_penalty.weight == 0.30
    # Penalty is 100 - s_con (with s_con=100 -> penalty=0)
    assert api_breakdown.contradiction_penalty.score == 0.0
    assert api_breakdown.structural_clarity.weight == 0.20
    assert api_breakdown.entailment.weight == 0.10
    assert api_breakdown.grade in ("S", "A+", "A", "B+", "B", "C+", "C", "D+", "D", "F")


def test_derive_grade_guardrails():
    # 1. Answerability Floor: even with high overall F (e.g. 74.0), s_ans < 30 caps at D
    assert derive_grade(74.0, s_ans=25.0) == "D"
    assert derive_grade(92.0, s_ans=10.0) == "D"
    # Normal s_ans allows normal grade
    assert derive_grade(74.0, s_ans=75.0) == "B"

    # 2. Contradiction Ceiling: 2+ hard contradictions caps grade at C
    assert derive_grade(88.0, hard_contradictions=2) == "C"
    assert derive_grade(94.0, hard_contradictions=3) == "C"
    # 1 hard contradiction drops S to A+, but doesn't cap at C
    assert derive_grade(88.0, contradiction_count=1, hard_contradictions=1) == "A"
