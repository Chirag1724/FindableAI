"""Unit tests for deterministic Patch Prioritizer (P2-3.1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.engines.patch_prioritizer import (
    PatchPrioritizer,
    PatchPrioritizerError,
    _RawOpportunity,
    calculate_priority,
    contradiction_local_id,
    deduplicate_opportunities,
    rank_opportunities,
    select_top_three,
    validate_confidence,
    validate_difficulty,
    validate_impact,
)
from app.schemas.intelligence import (
    Contradiction,
    ContradictionSeverity,
    EntailmentStatus,
    EvidenceReference,
    IntentEvaluation,
)
from app.schemas.patching import (
    PatchPrioritizationResult,
    PatchPrioritizerInput,
    RemediationEvidence,
    RemediationKind,
    RemediationOpportunity,
    SchemaRemediationTarget,
)
from app.schemas.scoring import SchemaOrgReport, SchemaTypeResult, ScoreBreakdown, ScoreWeights


def _eval(
    *,
    intent_id: str,
    status: EntailmentStatus,
    query: str = "Example question?",
    confidence: float = 0.8,
    evidence: list[EvidenceReference] | None = None,
) -> IntentEvaluation:
    return IntentEvaluation(
        intent_id=intent_id,
        query=query,
        status=status,
        reasoning="fixture",
        evidence=evidence or [],
        confidence=confidence,
    )


def _contra(
    *,
    severity: ContradictionSeverity,
    entity: str = "phone:primary",
    cid: str = "c1",
    conflict: str = "conflicting phone values",
) -> Contradiction:
    return Contradiction(
        entity=entity,
        conflict=conflict,
        values=[{"value": "a", "chunk_id": "x"}, {"value": "b", "chunk_id": "y"}],
        severity=severity,
        contradiction_id=cid,
        source_urls=["https://example.com/a", "https://example.com/b"],
        dom_paths=["/html/body/p[1]", "/html/body/p[2]"],
    )


def _schema_type(
    schema_type: str,
    *,
    present: bool,
    valid: bool = False,
    issues: list[str] | None = None,
) -> SchemaTypeResult:
    return SchemaTypeResult(
        schema_type=schema_type,
        present=present,
        valid=valid,
        occurrences=1 if present else 0,
        source_count=1 if present else 0,
        issues=issues or [],
    )


def _schema_report(types: list[SchemaTypeResult]) -> SchemaOrgReport:
    required = [
        "LocalBusiness",
        "PostalAddress",
        "OpeningHoursSpecification",
        "GeoCoordinates",
        "Menu",
        "FAQPage",
    ]
    by_name = {t.schema_type: t for t in types}
    full: list[SchemaTypeResult] = []
    present_valid = 0
    for name in required:
        item = by_name.get(name) or _schema_type(name, present=False)
        full.append(item)
        if item.present and item.valid:
            present_valid += 1
    return SchemaOrgReport(
        total_blocks=0,
        valid_blocks=0,
        invalid_blocks=0,
        malformed_blocks=0,
        required_types=required,
        types=full,
        score=100.0 * present_valid / 6.0,
        issues=[],
    )


def _opp(
    *,
    opportunity_id: str,
    impact: float,
    confidence: float,
    difficulty: int,
    kind: RemediationKind = RemediationKind.MISSING_SCHEMA,
) -> RemediationOpportunity:
    priority = (impact * confidence) / float(difficulty)
    return RemediationOpportunity(
        opportunity_id=opportunity_id,
        kind=kind,
        title=f"Title {opportunity_id}",
        reason=f"Reason {opportunity_id}",
        impact=impact,
        confidence=confidence,
        difficulty=difficulty,
        priority=priority,
        evidence=RemediationEvidence(),
        dedupe_key=f"{kind.value}|{opportunity_id}",
    )


# --- Formula / bounds ---


def test_priority_formula():
    assert calculate_priority(impact=80, confidence=0.9, difficulty=2) == 36.0


def test_difficulty_cannot_be_zero():
    with pytest.raises(PatchPrioritizerError, match="never zero"):
        validate_difficulty(0)
    with pytest.raises(PatchPrioritizerError):
        calculate_priority(impact=50, confidence=0.5, difficulty=0)


def test_impact_bounds():
    assert validate_impact(0) == 0.0
    assert validate_impact(100) == 100.0
    with pytest.raises(PatchPrioritizerError):
        validate_impact(-1)
    with pytest.raises(PatchPrioritizerError):
        validate_impact(101)


def test_confidence_bounds():
    assert validate_confidence(0) == 0.0
    assert validate_confidence(1) == 1.0
    with pytest.raises(PatchPrioritizerError):
        validate_confidence(-0.01)
    with pytest.raises(PatchPrioritizerError):
        validate_confidence(1.01)


def test_invalid_opportunity_priority_rejected():
    with pytest.raises(ValidationError):
        RemediationOpportunity(
            opportunity_id="x",
            kind=RemediationKind.MISSING_SCHEMA,
            title="t",
            reason="r",
            impact=80,
            confidence=0.9,
            difficulty=2,
            priority=99.0,  # wrong
            dedupe_key="MISSING_SCHEMA|x",
        )


# --- Ranking / top-3 ---


def test_top_three_selection():
    opps = [
        _opp(opportunity_id=f"o{i}", impact=10.0 * i, confidence=1.0, difficulty=1)
        for i in range(1, 6)
    ]
    selected = select_top_three(opps)
    assert len(selected) == 3
    assert [o.opportunity_id for o in selected] == ["o5", "o4", "o3"]


def test_descending_priority_order():
    opps = [
        _opp(opportunity_id="low", impact=10, confidence=1.0, difficulty=2),
        _opp(opportunity_id="high", impact=90, confidence=1.0, difficulty=2),
        _opp(opportunity_id="mid", impact=40, confidence=1.0, difficulty=2),
    ]
    ranked = rank_opportunities(opps)
    assert [o.opportunity_id for o in ranked] == ["high", "mid", "low"]


def test_deterministic_tie_breaking():
    # Equal priority/impact/confidence/difficulty → opportunity_id ascending
    a = _opp(opportunity_id="a", impact=50, confidence=1.0, difficulty=2)
    b = _opp(opportunity_id="b", impact=50, confidence=1.0, difficulty=2)
    c = _opp(opportunity_id="c", impact=50, confidence=1.0, difficulty=2)
    ranked = rank_opportunities([c, a, b])
    assert [o.opportunity_id for o in ranked] == ["a", "b", "c"]
    assert rank_opportunities([c, a, b]) == rank_opportunities([b, c, a])


def test_fewer_than_three_opportunities():
    # Mark others present+valid so only FAQ is a gap
    types = []
    for name in [
        "LocalBusiness",
        "PostalAddress",
        "OpeningHoursSpecification",
        "GeoCoordinates",
        "Menu",
        "FAQPage",
    ]:
        if name == "FAQPage":
            types.append(_schema_type(name, present=False))
        else:
            types.append(_schema_type(name, present=True, valid=True))
    report = _schema_report(types)
    result = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(schema_report=report, intent_evaluations=[], contradictions=[])
    )
    assert result.selected_count == 1
    assert result.total_candidates == 1
    assert result.opportunities[0].schema_target == SchemaRemediationTarget.FAQ_PAGE


def test_empty_input():
    result = PatchPrioritizer().prioritize(PatchPrioritizerInput())
    assert result.opportunities == []
    assert result.total_candidates == 0
    assert result.selected_count == 0


# --- Opportunity identification ---


def test_unknown_intent_creates_information_gap():
    result = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(
            intent_evaluations=[
                _eval(
                    intent_id="local_01",
                    status=EntailmentStatus.UNKNOWN,
                    query="Does the business have a physical address?",
                    confidence=0.7,
                )
            ]
        )
    )
    assert result.selected_count == 1
    opp = result.opportunities[0]
    assert opp.kind == RemediationKind.INFORMATION_GAP
    assert "address" in opp.opportunity_id
    assert "123 Main" not in opp.reason  # no invented facts
    assert "local_01" in opp.related_intent_ids


def test_missing_faq_page_schema_opportunity():
    types = [
        _schema_type(n, present=True, valid=True)
        for n in [
            "LocalBusiness",
            "PostalAddress",
            "OpeningHoursSpecification",
            "GeoCoordinates",
            "Menu",
        ]
    ] + [_schema_type("FAQPage", present=False)]
    result = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(schema_report=_schema_report(types))
    )
    assert any(
        o.kind == RemediationKind.MISSING_SCHEMA
        and o.schema_target == SchemaRemediationTarget.FAQ_PAGE
        for o in result.opportunities
    )


def test_missing_local_business_schema_opportunity():
    types = [_schema_type("LocalBusiness", present=False)] + [
        _schema_type(n, present=True, valid=True)
        for n in [
            "PostalAddress",
            "OpeningHoursSpecification",
            "GeoCoordinates",
            "Menu",
            "FAQPage",
        ]
    ]
    result = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(schema_report=_schema_report(types))
    )
    assert result.opportunities[0].schema_target == SchemaRemediationTarget.LOCAL_BUSINESS


def test_contradiction_creates_opportunity():
    result = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(
            contradictions=[
                _contra(severity=ContradictionSeverity.HARD_CONTRADICTION, cid="hours-1")
            ]
        )
    )
    assert result.selected_count == 1
    opp = result.opportunities[0]
    assert opp.kind == RemediationKind.CONTRADICTION
    assert "hours-1" in opp.related_contradiction_ids
    assert opp.evidence.source_urls
    assert opp.evidence.dom_paths


def test_hard_and_soft_contradictions_handled():
    result = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(
            contradictions=[
                _contra(
                    severity=ContradictionSeverity.HARD_CONTRADICTION,
                    cid="hard-1",
                    entity="hours",
                ),
                _contra(
                    severity=ContradictionSeverity.SOFT_INCONSISTENCY,
                    cid="soft-1",
                    entity="price:soup",
                ),
            ]
        )
    )
    kinds_severities = {o.opportunity_id: o.impact for o in result.opportunities}
    assert "contradiction:hard-1" in kinds_severities
    assert "contradiction:soft-1" in kinds_severities
    assert kinds_severities["contradiction:hard-1"] > kinds_severities["contradiction:soft-1"]


def test_duplicate_schema_gaps_deduplicated():
    # Same missing type appearing once in report → one opportunity
    types = [_schema_type("FAQPage", present=False)] + [
        _schema_type(n, present=True, valid=True)
        for n in [
            "LocalBusiness",
            "PostalAddress",
            "OpeningHoursSpecification",
            "GeoCoordinates",
            "Menu",
        ]
    ]
    report = _schema_report(types)
    result = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(schema_report=report, score_breakdown=None)
    )
    faq = [o for o in result.opportunities if o.schema_target == SchemaRemediationTarget.FAQ_PAGE]
    assert len(faq) == 1


def test_multiple_unknown_intents_same_theme_aggregated():
    result = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(
            intent_evaluations=[
                _eval(
                    intent_id="a1",
                    status=EntailmentStatus.UNKNOWN,
                    query="What is your street address?",
                    confidence=0.6,
                ),
                _eval(
                    intent_id="a2",
                    status=EntailmentStatus.UNKNOWN,
                    query="Do you have a physical location?",
                    confidence=0.8,
                ),
                _eval(
                    intent_id="a3",
                    status=EntailmentStatus.UNKNOWN,
                    query="Where are you located?",
                    confidence=0.7,
                ),
            ]
        )
    )
    assert result.total_candidates == 1
    opp = result.opportunities[0]
    assert opp.kind == RemediationKind.INFORMATION_GAP
    assert set(opp.related_intent_ids) == {"a1", "a2", "a3"}
    assert opp.impact > 55.0  # aggregated boost


def test_provenance_preserved():
    evidence = [
        EvidenceReference(chunk_id="chk-1", dom_path="/main/p[1]", url="https://ex.com/page")
    ]
    result = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(
            intent_evaluations=[
                _eval(
                    intent_id="u1",
                    status=EntailmentStatus.UNKNOWN,
                    query="What are your opening hours?",
                    confidence=0.9,
                    evidence=evidence,
                )
            ],
            contradictions=[
                _contra(severity=ContradictionSeverity.HARD_CONTRADICTION, cid="c-prov")
            ],
        )
    )
    info = next(o for o in result.opportunities if o.kind == RemediationKind.INFORMATION_GAP)
    assert any(r.chunk_id == "chk-1" for r in info.evidence.evidence_references)
    assert info.evidence.evidence_references[0].url == "https://ex.com/page"
    contra = next(o for o in result.opportunities if o.kind == RemediationKind.CONTRADICTION)
    assert "https://example.com/a" in contra.evidence.source_urls
    assert "/html/body/p[1]" in contra.evidence.dom_paths


def test_no_fabricated_evidence():
    result = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(
            intent_evaluations=[
                _eval(
                    intent_id="u1",
                    status=EntailmentStatus.UNKNOWN,
                    query="Is parking available?",
                    confidence=0.5,
                    evidence=[],
                )
            ]
        )
    )
    opp = result.opportunities[0]
    assert opp.evidence.evidence_references == []
    assert opp.evidence.source_urls == []
    assert "parking" in opp.reason.lower() or "general" in opp.opportunity_id


def test_invalid_input_rejected():
    with pytest.raises(PatchPrioritizerError):
        PatchPrioritizer().prioritize({"intent_evaluations": [{"bad": True}]})


def test_no_llm_network_database_dependency(monkeypatch: pytest.MonkeyPatch):
    def boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise AssertionError("external I/O must not be called")

    monkeypatch.setattr("app.core.llm.LLMClient.create", boom)
    PatchPrioritizer().prioritize(
        PatchPrioritizerInput(
            intent_evaluations=[
                _eval(intent_id="i1", status=EntailmentStatus.UNKNOWN, query="Hours?")
            ],
            contradictions=[_contra(severity=ContradictionSeverity.SOFT_INCONSISTENCY)],
            schema_report=_schema_report([_schema_type("Menu", present=False)]),
        )
    )


def test_score_breakdown_schema_report_used():
    types = [_schema_type("LocalBusiness", present=False)] + [
        _schema_type(n, present=True, valid=True)
        for n in [
            "PostalAddress",
            "OpeningHoursSpecification",
            "GeoCoordinates",
            "Menu",
            "FAQPage",
        ]
    ]
    report = _schema_report(types)
    breakdown = ScoreBreakdown(
        f_score=40.0,
        s_ans=50.0,
        s_con=50.0,
        s_str=10.0,
        s_acc=50.0,
        weights=ScoreWeights(),
        schema_report=report,
    )
    result = PatchPrioritizer().prioritize(PatchPrioritizerInput(score_breakdown=breakdown))
    assert any(
        o.schema_target == SchemaRemediationTarget.LOCAL_BUSINESS for o in result.opportunities
    )


def test_supported_intents_do_not_create_gaps():
    result = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(
            intent_evaluations=[
                _eval(intent_id="s1", status=EntailmentStatus.SUPPORTED, query="Hours?"),
                _eval(
                    intent_id="p1",
                    status=EntailmentStatus.PARTIALLY_SUPPORTED,
                    query="Address?",
                ),
            ]
        )
    )
    assert result.total_candidates == 0


def test_result_model_contract():
    result = PatchPrioritizer().prioritize(PatchPrioritizerInput())
    assert isinstance(result, PatchPrioritizationResult)
    dumped = result.model_dump()
    assert set(dumped) >= {"opportunities", "total_candidates", "selected_count"}


def test_deterministic_full_pipeline():
    inputs = PatchPrioritizerInput(
        intent_evaluations=[
            _eval(
                intent_id="u1",
                status=EntailmentStatus.UNKNOWN,
                query="Do you have a FAQ about pets?",
            )
        ],
        contradictions=[
            _contra(severity=ContradictionSeverity.HARD_CONTRADICTION, entity="hours", cid="h1")
        ],
        schema_report=_schema_report(
            [_schema_type("FAQPage", present=False)]
            + [
                _schema_type(n, present=True, valid=True)
                for n in [
                    "LocalBusiness",
                    "PostalAddress",
                    "OpeningHoursSpecification",
                    "GeoCoordinates",
                    "Menu",
                ]
            ]
        ),
    )
    a = PatchPrioritizer().prioritize(inputs)
    b = PatchPrioritizer().prioritize(inputs)
    assert a.model_dump() == b.model_dump()
    assert a.selected_count <= 3


def test_dedupe_uses_true_mean_confidence_not_pairwise_average():
    """Pairwise (a+b)/2 then (+c)/2 is wrong; mean of samples must be used."""
    key = "MISSING_SCHEMA|FAQPage"
    raw = [
        _RawOpportunity(
            kind=RemediationKind.MISSING_SCHEMA,
            dedupe_key=key,
            opportunity_id="missing_schema:FAQPage",
            title="t",
            reason="r",
            impact=40.0,
            confidence=0.3,
            difficulty=2,
            schema_target=SchemaRemediationTarget.FAQ_PAGE,
        ),
        _RawOpportunity(
            kind=RemediationKind.MISSING_SCHEMA,
            dedupe_key=key,
            opportunity_id="missing_schema:FAQPage",
            title="t",
            reason="r",
            impact=70.0,
            confidence=0.6,
            difficulty=2,
            schema_target=SchemaRemediationTarget.FAQ_PAGE,
        ),
        _RawOpportunity(
            kind=RemediationKind.MISSING_SCHEMA,
            dedupe_key=key,
            opportunity_id="missing_schema:FAQPage",
            title="t",
            reason="r",
            impact=50.0,
            confidence=0.9,
            difficulty=3,
            schema_target=SchemaRemediationTarget.FAQ_PAGE,
        ),
    ]
    merged = deduplicate_opportunities(raw)
    assert len(merged) == 1
    assert merged[0].impact == 70.0
    assert merged[0].difficulty == 3
    assert merged[0].confidence == pytest.approx(0.6)  # (0.3+0.6+0.9)/3
    # Pairwise running average would have been ((0.3+0.6)/2 + 0.9)/2 = 0.675
    assert merged[0].confidence != pytest.approx(0.675)


def test_idless_contradictions_with_different_values_do_not_merge():
    a = Contradiction(
        entity="phone",
        conflict="home vs mobile mismatch",
        values=[{"value": "111"}, {"value": "222"}],
        severity=ContradictionSeverity.HARD_CONTRADICTION,
        contradiction_id=None,
        source_urls=["https://ex.com/a"],
        dom_paths=["/p[1]"],
    )
    b = Contradiction(
        entity="phone",
        conflict="fax vs desk mismatch",
        values=[{"value": "333"}, {"value": "444"}],
        severity=ContradictionSeverity.HARD_CONTRADICTION,
        contradiction_id=None,
        source_urls=["https://ex.com/b"],
        dom_paths=["/p[2]"],
    )
    assert contradiction_local_id(a) != contradiction_local_id(b)
    result = PatchPrioritizer().prioritize(PatchPrioritizerInput(contradictions=[a, b]))
    assert result.total_candidates == 2
    ids = {o.opportunity_id for o in result.opportunities}
    assert len(ids) == 2


def test_idless_identical_contradictions_dedupe_to_one():
    shared = {
        "entity": "phone",
        "conflict": "same conflict",
        "values": [{"value": "111"}, {"value": "222"}],
        "severity": ContradictionSeverity.HARD_CONTRADICTION,
        "contradiction_id": None,
        "source_urls": ["https://ex.com/a"],
        "dom_paths": ["/p[1]"],
    }
    a = Contradiction(**shared)
    b = Contradiction(**shared)
    assert contradiction_local_id(a) == contradiction_local_id(b)
    result = PatchPrioritizer().prioritize(PatchPrioritizerInput(contradictions=[a, b]))
    assert result.total_candidates == 1
