"""Tests for Synthetic Intent Personas resolution and categorization."""

from __future__ import annotations

import pytest

from app.api.v1.scans import _generate_fallback_evaluations
from app.engines.intent_generator import resolve_query_persona, validate_intent_batch
from app.schemas.intelligence import IntentBatch, IntentCategory, IntentQuery


def _make_dummy_query(category: IntentCategory, idx: int) -> IntentQuery:
    return IntentQuery(
        intent_id=f"temp_{idx}",
        category=category,
        query=f"Is {category.value} supported properly question {idx}?",
        difficulty="medium",
        expected_evidence_type="documentation",
    )


def test_resolve_query_persona_defaults():
    # Policy / Trust -> CTO
    assert resolve_query_persona(IntentCategory.POLICY) == "cto"
    assert resolve_query_persona(IntentCategory.TRUST) == "cto"

    # Accessibility / Transactional -> Developer
    assert resolve_query_persona(IntentCategory.ACCESSIBILITY) == "developer"
    assert resolve_query_persona(IntentCategory.TRANSACTIONAL) == "developer"

    # Pricing / Commercial -> Procurement
    assert resolve_query_persona(IntentCategory.PRICING) == "procurement"
    assert resolve_query_persona(IntentCategory.COMMERCIAL) == "procurement"


def test_resolve_query_persona_restricted_active():
    # If only procurement is active, policy maps to procurement
    assert resolve_query_persona(IntentCategory.POLICY, active_personas=["procurement"]) == "procurement"
    # If only developer is active, policy maps to developer
    assert resolve_query_persona(IntentCategory.POLICY, active_personas=["developer"]) == "developer"


def test_validate_intent_batch_assigns_persona():
    queries = []
    idx = 1
    for cat in IntentCategory:
        for _ in range(3):
            queries.append(_make_dummy_query(cat, idx))
            idx += 1

    batch = IntentBatch(business_type="SaaS platform", queries=queries)
    validated = validate_intent_batch(batch, personas=["cto", "developer", "procurement"])

    assert len(validated.queries) == 30
    for q in validated.queries:
        assert q.persona in ("cto", "developer", "procurement")

    # Check that pricing questions were tagged with procurement
    pricing_queries = [q for q in validated.queries if q.category == IntentCategory.PRICING]
    assert all(q.persona == "procurement" for q in pricing_queries)


def test_fallback_evaluations_have_persona():
    evals = _generate_fallback_evaluations(
        "https://example.com",
        [],
        personas=["cto", "developer", "procurement"],
    )
    assert len(evals) == 30
    for ev in evals:
        assert ev.category is not None
        assert ev.persona in ("cto", "developer", "procurement")
