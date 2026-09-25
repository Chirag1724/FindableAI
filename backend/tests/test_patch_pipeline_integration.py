"""Cross-phase integration: P2-3.1 → 3.2 → checker → 3.3 → 3.4."""

from __future__ import annotations

import json

from app.engines.jsonld_generator import JsonLdGenerator
from app.engines.patch_formatter import format_jsonld_patch
from app.engines.patch_prioritizer import PatchPrioritizer
from app.engines.projected_score import project_score_for_generated
from app.engines.scorer import ScoreInputs, analyze_schema_org
from app.schemas.intelligence import EntailmentStatus, EvidenceReference, IntentEvaluation
from app.schemas.patching import (
    BusinessFacts,
    FaqEntry,
    OpeningHoursFact,
    PatchFormatStatus,
    PatchPrioritizerInput,
    SchemaRemediationTarget,
)
from app.schemas.scoring import SchemaOrgReport, SchemaTypeResult


def _schema_report_missing(*missing: str) -> SchemaOrgReport:
    required = [
        "LocalBusiness",
        "PostalAddress",
        "OpeningHoursSpecification",
        "GeoCoordinates",
        "Menu",
        "FAQPage",
    ]
    types = []
    for name in required:
        present = name not in missing
        types.append(
            SchemaTypeResult(
                schema_type=name,
                present=present,
                valid=present,
                occurrences=1 if present else 0,
                source_count=1 if present else 0,
                issues=[],
            )
        )
    return SchemaOrgReport(
        total_blocks=0,
        valid_blocks=0,
        invalid_blocks=0,
        malformed_blocks=0,
        required_types=required,
        types=types,
        score=100.0 * sum(1 for t in types if t.present and t.valid) / 6.0,
        issues=[],
    )


def test_e2e_faq_page_pipeline():
    prioritization = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(schema_report=_schema_report_missing("FAQPage"))
    )
    assert any(
        o.schema_target == SchemaRemediationTarget.FAQ_PAGE for o in prioritization.opportunities
    )

    generation = JsonLdGenerator().generate(
        prioritization,
        facts=BusinessFacts(
            faq_entries=[FaqEntry(question="Are dogs allowed?", answer="Yes, on the patio.")]
        ),
        intent_evaluations=[],
    )
    assert len(generation.generated) >= 1
    faq = next(g for g in generation.generated if g.schema_type == SchemaRemediationTarget.FAQ_PAGE)
    assert faq.opportunity_id.startswith("missing_schema")
    parsed = json.loads(faq.json_text)
    assert parsed["@type"] == "FAQPage"

    report = analyze_schema_org(
        [f'<html><head><script type="application/ld+json">{faq.json_text}</script></head></html>']
    )
    assert next(t for t in report.types if t.schema_type == "FAQPage").valid

    html = "<html><head><title>Bistro</title></head><body></body></html>"
    formatted = format_jsonld_patch(faq, html=html, file_path="index.html")
    assert formatted.status is PatchFormatStatus.APPLIED
    assert "--- a/index.html" in formatted.patch_text
    assert "application/ld+json" in formatted.patched_html

    projection = project_score_for_generated(
        faq,
        score_inputs=ScoreInputs(html_documents=[html], extracted_fact_count=3),
    )
    assert projection.delta == projection.projected_score - projection.current_score
    assert projection.opportunity_id == faq.opportunity_id


def test_e2e_local_business_and_hours():
    prioritization = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(
            schema_report=_schema_report_missing("LocalBusiness", "OpeningHoursSpecification")
        )
    )
    facts = BusinessFacts(
        name="Bistro 2026",
        telephone="+91 9876543210",
        opening_hours=[
            OpeningHoursFact(day_of_week="Monday", opens="10:00", closes="22:00"),
        ],
    )
    generation = JsonLdGenerator().generate(prioritization, facts=facts)
    types = {g.schema_type for g in generation.generated}
    assert SchemaRemediationTarget.LOCAL_BUSINESS in types
    assert SchemaRemediationTarget.OPENING_HOURS in types

    lb = next(
        g for g in generation.generated if g.schema_type == SchemaRemediationTarget.LOCAL_BUSINESS
    )
    hours = next(
        g for g in generation.generated if g.schema_type == SchemaRemediationTarget.OPENING_HOURS
    )

    html = "<html><head></head><body></body></html>"
    for item in (lb, hours):
        formatted = format_jsonld_patch(item, html=html)
        assert formatted.status is PatchFormatStatus.APPLIED
        proj = project_score_for_generated(
            item,
            score_inputs=ScoreInputs(
                html_documents=[html],
                intent_evaluations=[
                    IntentEvaluation(
                        intent_id="i1",
                        query="Open?",
                        status=EntailmentStatus.UNKNOWN,
                        reasoning="x",
                        evidence=[EvidenceReference(chunk_id="c", dom_path="/p", excerpt=None)],
                        confidence=0.5,
                    )
                ],
                extracted_fact_count=2,
            ),
        )
        assert proj.schema_type == item.schema_type
        assert proj.projected_breakdown.s_str >= proj.current_breakdown.s_str
