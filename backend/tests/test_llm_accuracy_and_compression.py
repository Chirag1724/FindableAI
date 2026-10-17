"""Tests for Quote-First attribution, context compression, and query deduplication."""

from __future__ import annotations

import uuid

import pytest

from app.crawler.context_compressor import clean_dom_noise, compress_chunk_for_query
from app.engines.entailment_engine import (
    EntailmentEngine,
    RetrievedEvidence,
    validate_intent_evaluation,
)
from app.schemas.intelligence import (
    EntailmentStatus,
    EvidenceReference,
    IntentCategory,
    IntentEvaluation,
    IntentQuery,
)


def test_clean_dom_noise_strips_svg_and_cookies():
    raw_html = (
        "<div><svg><path d='M10 10'/></svg>Welcome to Acme. "
        "We use cookies to improve your experience. "
        "Accept all cookies now! Pricing starts at $20/month.</div>"
    )
    cleaned = clean_dom_noise(raw_html)
    assert "<svg>" not in cleaned
    assert "M10 10" not in cleaned
    assert "We use cookies" not in cleaned
    assert "Accept all cookies" not in cleaned
    assert "Welcome to Acme." in cleaned
    assert "Pricing starts at $20/month." in cleaned


def test_compress_chunk_for_query_finds_relevant_sentence():
    chunk = (
        "Acme was founded in 2018 in San Francisco. We build enterprise AI software. "
        "Our team has 50 engineers. "
        "All paid plans include a 14-day free trial without a credit card. "
        "Contact support for enterprise licensing. Check out our blog for updates."
    )
    query = "Does Acme have a free trial?"
    compressed = compress_chunk_for_query(chunk, query, max_chars=120)

    assert "14-day free trial" in compressed
    assert "founded in 2018" not in compressed
    assert len(compressed) <= 125


def test_validate_intent_evaluation_preserves_valid_verbatim_quote():
    chunk_id = str(uuid.uuid4())
    chunk_content = "All paid plans include a 14-day free trial with no credit card required."
    evidence = [
        RetrievedEvidence(
            chunk_id=chunk_id,
            url="https://example.com/pricing",
            dom_path="div.pricing",
            content=chunk_content,
            rank=1,
        )
    ]
    intent = IntentQuery(
        intent_id="intent_1",
        query="Is there a free trial?",
        persona="buyer",
        category=IntentCategory.PRICING,
        difficulty="easy",
        expected_evidence_type="pricing_table",
    )
    raw_eval = IntentEvaluation(
        intent_id="intent_1",
        query="Is there a free trial?",
        verbatim_quote="14-day free trial with no credit card required",
        cited_chunk_id=chunk_id,
        status=EntailmentStatus.SUPPORTED,
        reasoning="The pricing page states there is a 14-day free trial.",
        evidence=[EvidenceReference(chunk_id=chunk_id, dom_path="div.pricing")],
        confidence=0.95,
    )

    validated = validate_intent_evaluation(raw_eval, intent=intent, retrieved=evidence)
    assert validated.status == EntailmentStatus.SUPPORTED
    assert validated.verbatim_quote == "14-day free trial with no credit card required"
    assert validated.cited_chunk_id == chunk_id


def test_validate_intent_evaluation_unknown_clears_quote():
    chunk_id = str(uuid.uuid4())
    intent = IntentQuery(
        intent_id="intent_2",
        query="Does it support SSO?",
        persona="cto",
        category=IntentCategory.TRUST,
        difficulty="medium",
        expected_evidence_type="faq",
    )
    raw_eval = IntentEvaluation(
        intent_id="intent_2",
        query="Does it support SSO?",
        verbatim_quote="Some unrelated text",
        cited_chunk_id=chunk_id,
        status=EntailmentStatus.UNKNOWN,
        reasoning="No SSO details found.",
        evidence=[],
        confidence=0.0,
    )

    validated = validate_intent_evaluation(raw_eval, intent=intent, retrieved=[])
    assert validated.status == EntailmentStatus.UNKNOWN
    assert validated.verbatim_quote is None
    assert validated.cited_chunk_id is None


@pytest.mark.asyncio
async def test_evaluate_intents_deduplicates_identical_queries():
    # Setup two intents with identical query text across different personas
    intent_cto = IntentQuery(
        intent_id="intent_cto",
        query="What is the pricing for enterprise?",
        persona="cto",
        category=IntentCategory.PRICING,
        difficulty="medium",
        expected_evidence_type="pricing_table",
    )
    intent_procurement = IntentQuery(
        intent_id="intent_procurement",
        query="what is the pricing for enterprise?",  # identical except casing
        persona="procurement",
        category=IntentCategory.PRICING,
        difficulty="medium",
        expected_evidence_type="pricing_table",
    )

    chunk_id = str(uuid.uuid4())
    dummy_chunks = [
        type(
            "Chunk",
            (),
            {
                "id": chunk_id,
                "url": "https://example.com",
                "dom_path": "main",
                "content": "Enterprise pricing starts at $500/month.",
            },
        )()
    ]

    class MockRetriever:
        async def __call__(self, query: str, scan_id: uuid.UUID, top_k: int):
            return dummy_chunks

    class MockLLM:
        def __init__(self):
            self.calls = 0

        async def create(self, response_model, messages, **kwargs):
            self.calls += 1
            # Return an IntentEvaluationBatch
            from app.schemas.intelligence import IntentEvaluationBatch

            return IntentEvaluationBatch(
                evaluations=[
                    IntentEvaluation(
                        intent_id="intent_cto",
                        query="What is the pricing for enterprise?",
                        verbatim_quote="Enterprise pricing starts at $500/month.",
                        cited_chunk_id=chunk_id,
                        status=EntailmentStatus.SUPPORTED,
                        reasoning="Page specifies $500/month for enterprise.",
                        evidence=[EvidenceReference(chunk_id=chunk_id, dom_path="main")],
                        confidence=0.95,
                    )
                ]
            )

    mock_llm = MockLLM()
    engine = EntailmentEngine(llm_client=mock_llm, retriever=MockRetriever())

    results = await engine.evaluate_intents(
        intents=[intent_cto, intent_procurement],
        scan_id=uuid.uuid4(),
    )

    assert len(results) == 2
    # The LLM should only have been called ONCE for the deduplicated query!
    assert mock_llm.calls == 1

    r_cto, r_procurement = results
    assert r_cto.intent_id == "intent_cto"
    assert r_cto.status == EntailmentStatus.SUPPORTED
    assert r_cto.verbatim_quote == "Enterprise pricing starts at $500/month."

    assert r_procurement.intent_id == "intent_procurement"
    assert r_procurement.status == EntailmentStatus.SUPPORTED
    assert r_procurement.verbatim_quote == "Enterprise pricing starts at $500/month."
    assert r_procurement.persona == "procurement"
