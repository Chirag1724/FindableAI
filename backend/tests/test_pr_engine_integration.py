"""Mocked end-to-end: Phase 3.1-3.4 -> Markdown -> PR Engine."""

from __future__ import annotations

from app.engines.jsonld_generator import JsonLdGenerator
from app.engines.patch_formatter import format_jsonld_patch
from app.engines.patch_prioritizer import PatchPrioritizer
from app.engines.projected_score import project_score_for_generated
from app.engines.scorer import ScoreInputs
from app.github.client import FakeGitHubClient
from app.github.pr_engine import GitHubPRService
from app.schemas.github_pr import PREngineRequest
from app.schemas.intelligence import EntailmentStatus, EvidenceReference, IntentEvaluation
from app.schemas.patching import (
    BusinessFacts,
    FaqEntry,
    PatchFormatStatus,
    PatchPrioritizerInput,
    SchemaRemediationTarget,
)
from app.schemas.scoring import SchemaOrgReport, SchemaTypeResult


def _schema_missing_faq() -> SchemaOrgReport:
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
        present = name != "FAQPage"
        types.append(
            SchemaTypeResult(
                schema_type=name,
                present=present,
                valid=present,
                occurrences=1 if present else 0,
                source_count=1 if present else 0,
            )
        )
    return SchemaOrgReport(
        total_blocks=0,
        valid_blocks=0,
        invalid_blocks=0,
        malformed_blocks=0,
        required_types=required,
        types=types,
        score=100.0 * 5 / 6,
        issues=[],
    )


def test_pipeline_to_mocked_pr():
    html = "<html><head><title>Bistro</title></head><body></body></html>"
    intents = [
        IntentEvaluation(
            intent_id="faq_01",
            query="Are dogs allowed?",
            status=EntailmentStatus.SUPPORTED,
            reasoning="supported",
            evidence=[
                EvidenceReference(
                    chunk_id="chk-1",
                    dom_path="/main/p[2]",
                    url="https://example.com/",
                    excerpt="Yes, leashed dogs on the patio.",
                )
            ],
            confidence=0.9,
        )
    ]

    prioritization = PatchPrioritizer().prioritize(
        PatchPrioritizerInput(schema_report=_schema_missing_faq(), intent_evaluations=intents)
    )
    generation = JsonLdGenerator().generate(
        prioritization,
        facts=BusinessFacts(
            faq_entries=[
                FaqEntry(question="Are dogs allowed?", answer="Yes, leashed dogs on the patio.")
            ]
        ),
        intent_evaluations=intents,
    )
    assert generation.generated
    faq = next(g for g in generation.generated if g.schema_type == SchemaRemediationTarget.FAQ_PAGE)

    formatted = format_jsonld_patch(faq, html=html, file_path="index.html")
    assert formatted.status is PatchFormatStatus.APPLIED

    projection = project_score_for_generated(
        faq,
        score_inputs=ScoreInputs(html_documents=[html], extracted_fact_count=2),
    )

    client = FakeGitHubClient(login="bot-user")
    client.seed_repo("acme/demo-site", files={"index.html": html})
    service = GitHubPRService(client)

    result = service.create_remediation_pr(
        PREngineRequest(
            source_repo="acme/demo-site",
            target_branch="main",
            scan_id="scan-e2e",
            patches=[formatted],
            projections=[projection],
            opportunities=list(prioritization.opportunities),
            intent_evaluations=intents,
        )
    )

    assert result.changed_files == ["index.html"]
    assert result.applied_opportunity_ids == [faq.opportunity_id]
    assert abs(result.delta - (result.projected_score - result.current_score)) < 1e-9
    assert f"{result.current_score:.1f}" in result.pr_body
    assert f"{result.projected_score:.1f}" in result.pr_body
    assert "index.html" in result.pr_body
    assert (
        "faq_01" in result.pr_body or "UNKNOWN" in result.pr_body or "SUPPORTED" in result.pr_body
    )
    assert "chk-1" in result.pr_body or "Evidence" in result.pr_body
    assert any(c.startswith("create_pull:") for c in client.calls)
    assert not any("api.github.com" in c for c in client.calls)
    # Only the validated HTML file was touched
    branch = result.generated_branch
    paths = set(client._repos["bot-user/demo-site"].files[branch].keys())
    assert paths == {"index.html"}
