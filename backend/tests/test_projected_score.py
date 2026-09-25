"""Unit tests for P2-3.4 projected score."""

from __future__ import annotations

import pytest

from app.engines.jsonld_generator import dumps_jsonld
from app.engines.projected_score import (
    ProjectedScoreCalculator,
    ProjectedScoreError,
    project_score_for_generated,
    project_scores,
)
from app.engines.scorer import ScoreInputs, Scorer
from app.schemas.intelligence import EntailmentStatus, IntentEvaluation
from app.schemas.patching import GeneratedJsonLd, SchemaRemediationTarget
from app.schemas.scoring import ScoreBreakdown


def _eval(status: EntailmentStatus, intent_id: str = "i1") -> IntentEvaluation:
    return IntentEvaluation(
        intent_id=intent_id,
        query="Q?",
        status=status,
        reasoning="fixture",
        evidence=[],
        confidence=0.9,
    )


def _faq_generated() -> GeneratedJsonLd:
    payload = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "Hours?",
                "acceptedAnswer": {"@type": "Answer", "text": "10-10"},
            }
        ],
    }
    return GeneratedJsonLd(
        opportunity_id="missing_schema:FAQPage",
        schema_type=SchemaRemediationTarget.FAQ_PAGE,
        payload=payload,
        json_text=dumps_jsonld(payload),
    )


def _lb_generated() -> GeneratedJsonLd:
    payload = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": "Bistro 2026",
        "telephone": "+91 9876543210",
    }
    return GeneratedJsonLd(
        opportunity_id="missing_schema:LocalBusiness",
        schema_type=SchemaRemediationTarget.LOCAL_BUSINESS,
        payload=payload,
        json_text=dumps_jsonld(payload),
    )


def test_current_score_preserved_and_delta():
    html = "<html><head></head><body></body></html>"
    inputs = ScoreInputs(
        intent_evaluations=[_eval(EntailmentStatus.SUPPORTED)],
        html_documents=[html],
        extracted_fact_count=5,
    )
    current = Scorer().score(inputs)
    result = project_score_for_generated(
        _faq_generated(), score_inputs=inputs, current_breakdown=current
    )
    assert result.current_score == current.f_score
    assert result.delta == pytest.approx(result.projected_score - result.current_score)
    assert 0.0 <= result.projected_score <= 100.0


def test_schema_remediation_can_improve_score():
    html = "<html><head></head><body></body></html>"
    inputs = ScoreInputs(html_documents=[html], extracted_fact_count=1)
    result = project_score_for_generated(_faq_generated(), score_inputs=inputs)
    # Adding a valid required schema type should not decrease S_str-driven F.
    assert result.projected_score >= result.current_score
    assert result.projected_breakdown.s_str >= result.current_breakdown.s_str


def test_no_document_mutation():
    html = "<html><head></head><body>ORIGINAL</body></html>"
    docs = [html]
    inputs = ScoreInputs(html_documents=docs, extracted_fact_count=1)
    project_score_for_generated(_faq_generated(), score_inputs=inputs)
    assert docs[0] == html
    assert "ORIGINAL" in docs[0]
    assert "ld+json" not in docs[0]


def test_uses_existing_scorer(monkeypatch: pytest.MonkeyPatch):
    calls: list[ScoreInputs] = []
    real = Scorer.score

    def spy(self, inputs: ScoreInputs) -> ScoreBreakdown:  # type: ignore[no-untyped-def]
        calls.append(inputs)
        return real(self, inputs)

    monkeypatch.setattr(Scorer, "score", spy)
    inputs = ScoreInputs(
        html_documents=["<html><head></head><body></body></html>"],
        extracted_fact_count=1,
    )
    project_score_for_generated(_faq_generated(), score_inputs=inputs)
    assert len(calls) >= 2  # current (if needed) + projected


def test_independent_top3_projections():
    html = "<html><head></head><body></body></html>"
    inputs = ScoreInputs(html_documents=[html], extracted_fact_count=1)
    batch = project_scores([_faq_generated(), _lb_generated()], score_inputs=inputs)
    assert len(batch.projections) == 2
    ids = {p.opportunity_id for p in batch.projections}
    assert ids == {"missing_schema:FAQPage", "missing_schema:LocalBusiness"}
    # Independent: each has its own delta; not a cumulative chain
    assert all(isinstance(p.projected_breakdown, ScoreBreakdown) for p in batch.projections)


def test_conflict_fails_deterministically():
    gen = _faq_generated()
    html = (
        "<html><head>"
        f'<script type="application/ld+json">{dumps_jsonld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": "Other?", "acceptedAnswer": {"@type": "Answer", "text": "x"}}]})}</script>'
        "</head><body></body></html>"
    )
    inputs = ScoreInputs(html_documents=[html], extracted_fact_count=1)
    with pytest.raises(ProjectedScoreError):
        project_score_for_generated(gen, score_inputs=inputs)


def test_calculator_class():
    inputs = ScoreInputs(
        html_documents=["<html><head></head><body></body></html>"],
        extracted_fact_count=1,
    )
    batch = ProjectedScoreCalculator().project([_faq_generated()], score_inputs=inputs)
    assert batch.projections[0].schema_type == SchemaRemediationTarget.FAQ_PAGE


def test_no_llm(monkeypatch: pytest.MonkeyPatch):
    def boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr("app.core.llm.LLMClient.create", boom)
    inputs = ScoreInputs(
        html_documents=["<html><head></head><body></body></html>"],
        extracted_fact_count=1,
    )
    project_score_for_generated(_faq_generated(), score_inputs=inputs)
