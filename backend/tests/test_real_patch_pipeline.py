"""Tests for real-time fact extraction and patch assembly pipeline."""

from __future__ import annotations

from app.engines.fact_extractor import extract_business_facts
from app.engines.patch_assembler import assemble_real_patches
from app.engines.scorer import ScoreInputs, Scorer
from app.schemas.intelligence import (
    Contradiction,
    ContradictionSeverity,
    EntailmentStatus,
    IntentEvaluation,
)


class DummyChunk:
    def __init__(self, content: str, dom_path: str = "/div", chunk_id: str = "c1") -> None:
        self.content = content
        self.dom_path = dom_path
        self.id = chunk_id
        self.url = "https://example.com"


def test_fact_extractor_from_html_and_chunks():
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <meta property="og:site_name" content="Acme Cloud Platform" />
        <title>Home | Acme Cloud</title>
      </head>
      <body>
        <main>
          <h1>Next-Gen Cloud Infrastructure</h1>
          <p>Contact our sales team at <a href="tel:+1-800-555-0199">+1-800-555-0199</a> or email <a href="mailto:support@acmecloud.io">support@acmecloud.io</a>.</p>
          <p>We are located at: 100 Innovation Way, Suite 400, San Francisco, CA 94105</p>
        </main>
      </body>
    </html>
    """
    chunks = [
        DummyChunk("Contact sales at +1-800-555-0199 or support@acmecloud.io"),
        DummyChunk("Open Monday: 09:00 - 18:00 and Friday: 09:00 - 17:00"),
    ]
    intents = [
        IntentEvaluation(
            intent_id="i1",
            query="Does Acme Cloud support enterprise SLAs?",
            status=EntailmentStatus.SUPPORTED,
            reasoning="Acme Cloud guarantees 99.99% uptime with 24/7 dedicated support under enterprise SLA.",
            confidence=0.95,
        )
    ]

    facts = extract_business_facts(
        html, chunks=chunks, url="https://acmecloud.io", intent_evaluations=intents
    )
    assert facts.name == "Acme Cloud Platform"
    assert facts.telephone is not None and "555" in facts.telephone
    assert facts.email == "support@acmecloud.io"
    assert len(facts.opening_hours) >= 1
    assert any(h.day_of_week == "Monday" for h in facts.opening_hours)
    assert len(facts.faq_entries) >= 1
    assert "enterprise SLAs" in facts.faq_entries[0].question


def test_assemble_real_patches_produces_valid_proposals():
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Apex Robotics - Industrial AI Automation</title>
      </head>
      <body>
        <h1>Apex Robotics</h1>
        <p>Call +1 415-555-2670 or visit our headquarters in Silicon Valley.</p>
        <p class="hours">Open Monday: 08:00 - 17:00</p>
      </body>
    </html>
    """
    chunks = [DummyChunk("Apex Robotics industrial automation call +1 415-555-2670")]
    evaluations = [
        IntentEvaluation(
            intent_id="i01",
            query="What robots does Apex Robotics manufacture?",
            status=EntailmentStatus.SUPPORTED,
            reasoning="Apex Robotics builds autonomous articulated arms and mobile industrial robots.",
            confidence=0.92,
        )
    ]
    contradictions = [
        Contradiction(
            contradiction_id="c01",
            entity="operating_hours",
            conflict="Hours conflict between main landing and contact page",
            values=["Monday: 08:00 - 17:00", "Monday: 09:00 - 18:00"],
            severity=ContradictionSeverity.HARD_CONTRADICTION,
            source_urls=["https://apexrobotics.ai"],
        )
    ]
    inputs = ScoreInputs(
        intent_evaluations=evaluations,
        contradictions=contradictions,
        html_documents=[html],
        chunks=chunks,
    )
    score_breakdown = Scorer().score(inputs)

    patches = assemble_real_patches(
        html=html,
        url="https://apexrobotics.ai",
        score_inputs=inputs,
        score_breakdown=score_breakdown,
        chunks=chunks,
        contradictions=contradictions,
    )

    assert len(patches) >= 1
    # Check that proposals have non-mock data
    titles = [p.title for p in patches]
    assert any("Schema.org" in t for t in titles)
    for p in patches:
        assert p.impact_score_delta > 0
        assert p.unified_diff.startswith("---")
        assert (
            "Apex Robotics" in p.dom_anchor.original_snippet
            or "Apex Robotics" in p.dom_anchor.suggested_snippet
            or "hours" in p.dom_anchor.original_snippet
        )
