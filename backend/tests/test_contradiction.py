"""Unit tests for hybrid contradiction detection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.core.llm import BudgetExhausted, LLMClient
from app.engines.contradiction import (
    ContradictionDetectionError,
    ContradictionDetector,
    SemanticConflictJudgment,
    detect_contradictions,
    extract_facts,
    find_deterministic_conflicts,
    normalize_hours_interval,
    normalize_phone,
    normalize_price,
)
from app.schemas.intelligence import ContradictionSeverity


@dataclass(frozen=True)
class FakeChunk:
    id: str
    url: str
    dom_path: str
    content: str


class _FakeCompletions:
    def __init__(self, handler: AsyncMock) -> None:
        self.create = handler


class _FakeChat:
    def __init__(self, handler: AsyncMock) -> None:
        self.completions = _FakeCompletions(handler)


class _FakeInstructorClient:
    def __init__(self, handler: AsyncMock) -> None:
        self.chat = _FakeChat(handler)


def _llm(handler: AsyncMock | None = None, *, max_calls: int = 35) -> LLMClient:
    return LLMClient(
        api_key="test-secret-key-do-not-leak",
        model="groq/qwen-2.5-72b-instruct",
        max_calls=max_calls,
        instructor_client=_FakeInstructorClient(handler or AsyncMock()),
    )


@pytest.mark.asyncio
async def test_conflicting_phones_hard_contradiction_without_llm():
    handler = AsyncMock()
    chunks = [
        FakeChunk(
            "chunk-a",
            "https://example.com/contact",
            "main > section.contact",
            "Primary contact: +91 99999 11111",
        ),
        FakeChunk(
            "chunk-b",
            "https://example.com/footer",
            "footer > p.phone",
            "Main phone +91-88888-22222",
        ),
    ]
    results = await ContradictionDetector(llm_client=_llm(handler)).detect_contradictions(
        chunks=chunks
    )
    assert len(results) == 1
    assert results[0].severity is ContradictionSeverity.HARD_CONTRADICTION
    assert results[0].entity.startswith("phone:")
    assert {v["chunk_id"] for v in results[0].values} == {"chunk-a", "chunk-b"}
    assert handler.await_count == 0


@pytest.mark.asyncio
async def test_conflicting_emails_hard_contradiction():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p.email", "Primary contact email: hello@bistro.com"),
        FakeChunk("b", "https://ex.com/b", "p.email", "Main contact: info@bistro.com"),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert len(results) == 1
    assert results[0].severity is ContradictionSeverity.HARD_CONTRADICTION
    assert results[0].entity == "email:primary"


@pytest.mark.asyncio
async def test_conflicting_prices_same_entity_hard():
    chunks = [
        FakeChunk("a", "https://ex.com/menu", "tr.item", "Vegan Burger ₹500"),
        FakeChunk("b", "https://ex.com/specials", "div.deal", "Vegan Burger ₹700"),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert len(results) == 1
    assert results[0].severity is ContradictionSeverity.HARD_CONTRADICTION
    assert results[0].entity == "price:burger"


@pytest.mark.asyncio
async def test_conflicting_opening_hours_hard():
    chunks = [
        FakeChunk(
            "chunk-a",
            "https://example.com/hours",
            "main > section.hours",
            "Monday: 10 AM - 10 PM",
        ),
        FakeChunk(
            "chunk-b",
            "https://example.com/contact",
            "main > section.contact",
            "Monday: 10 AM - 9 PM",
        ),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert len(results) == 1
    assert results[0].entity == "opening_hours:monday"
    assert results[0].severity is ContradictionSeverity.HARD_CONTRADICTION
    assert results[0].dom_paths == [
        "main > section.contact",
        "main > section.hours",
    ] or set(results[0].dom_paths) == {
        "main > section.hours",
        "main > section.contact",
    }


@pytest.mark.asyncio
async def test_equivalent_12h_24h_hours_no_contradiction():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Monday: 10 AM - 10 PM"),
        FakeChunk("b", "https://ex.com/b", "p", "Monday: 10:00 - 22:00"),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []


@pytest.mark.asyncio
async def test_equivalent_phone_formatting_no_contradiction():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Call +91 98765 43210"),
        FakeChunk("b", "https://ex.com/b", "p", "Call +91-98765-43210"),
        FakeChunk("c", "https://ex.com/c", "p", "Call +919876543210"),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []
    assert normalize_phone("+91 98765 43210") == normalize_phone("+919876543210")


@pytest.mark.asyncio
async def test_equivalent_price_formatting_no_contradiction():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Lunch special ₹1,000"),
        FakeChunk("b", "https://ex.com/b", "p", "Lunch special Rs. 1000"),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []


@pytest.mark.asyncio
async def test_different_currencies_not_merged():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Entry $50"),
        FakeChunk("b", "https://ex.com/b", "p", "Entry ₹50"),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []
    assert normalize_price("$", "50") != normalize_price("₹", "50")


@pytest.mark.asyncio
async def test_different_products_not_compared():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Pasta ₹500"),
        FakeChunk("b", "https://ex.com/b", "p", "Pizza ₹700"),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []


@pytest.mark.asyncio
async def test_different_phone_contexts_not_compared():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Reservations phone +91 1111111111"),
        FakeChunk("b", "https://ex.com/b", "p", "Support phone +91 2222222222"),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []


@pytest.mark.asyncio
async def test_coordinate_precision_normalization():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Location 12.9715987, 77.5945627"),
        FakeChunk("b", "https://ex.com/b", "p", "Location 12.97160, 77.59456"),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []


@pytest.mark.asyncio
async def test_address_formatting_normalization():
    chunks = [
        FakeChunk(
            "a",
            "https://ex.com/a",
            "p",
            "Address: 12 MG Road,  Bangalore",
        ),
        FakeChunk(
            "b",
            "https://ex.com/b",
            "p",
            "Address: 12 MG Road, Bangalore",
        ),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []


@pytest.mark.asyncio
async def test_ten_digit_vs_plus91_phone_no_contradiction():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Call 9876543210"),
        FakeChunk("b", "https://ex.com/b", "p", "Call +91 98765 43210"),
        FakeChunk("c", "https://ex.com/c", "p", "Call 919876543210"),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []
    assert normalize_phone("9876543210") == normalize_phone("+91 98765 43210")
    assert normalize_phone("9876543210") == normalize_phone("919876543210")


@pytest.mark.asyncio
async def test_reservations_email_vs_support_email_no_contradiction():
    chunks = [
        FakeChunk(
            "a",
            "https://ex.com/a",
            "p",
            "Reservations email: reservations@bistro.com",
        ),
        FakeChunk(
            "b",
            "https://ex.com/b",
            "p",
            "Support email: support@bistro.com",
        ),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []


@pytest.mark.asyncio
async def test_abbreviated_vs_extended_address_no_hard_contradiction():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Address: 12 MG Road"),
        FakeChunk(
            "b",
            "https://ex.com/b",
            "p",
            "Address: 12 MG Road, Bengaluru, Karnataka 560001",
        ),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []


@pytest.mark.asyncio
async def test_genuinely_different_primary_addresses_hard_contradiction():
    chunks = [
        FakeChunk(
            "a",
            "https://ex.com/a",
            "p",
            "Address: 12 MG Road, Bengaluru",
        ),
        FakeChunk(
            "b",
            "https://ex.com/b",
            "p",
            "Address: 45 Brigade Road, Bengaluru",
        ),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert len(results) == 1
    assert results[0].severity is ContradictionSeverity.HARD_CONTRADICTION
    assert results[0].entity == "address:primary"


@pytest.mark.asyncio
async def test_semantic_soft_inconsistency():
    handler = AsyncMock(
        return_value=SemanticConflictJudgment(
            contradictory=True,
            severity=ContradictionSeverity.SOFT_INCONSISTENCY,
            confidence=0.7,
            rationale="Pets policy wording conflicts across pages.",
        )
    )
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Pets allowed on the patio."),
        FakeChunk("b", "https://ex.com/b", "p", "No pets permitted indoors or outdoors."),
    ]
    results = await ContradictionDetector(llm_client=_llm(handler)).detect_contradictions(
        chunks=chunks
    )
    assert len(results) == 1
    assert results[0].severity is ContradictionSeverity.SOFT_INCONSISTENCY
    assert handler.await_count == 1
    assert handler.await_args.kwargs["max_retries"] == 0
    assert {v["chunk_id"] for v in results[0].values} == {"a", "b"}


@pytest.mark.asyncio
async def test_semantic_ambiguity_not_forced_to_hard_or_any():
    handler = AsyncMock(
        return_value=SemanticConflictJudgment(
            contradictory=False,
            severity=None,
            confidence=0.4,
            rationale="Reservations recommended vs required are compatible.",
        )
    )
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Reservations required on weekends."),
        FakeChunk("b", "https://ex.com/b", "p", "Walk-ins welcome on weekdays."),
    ]
    # These cues are opposing globally; LLM says not contradictory for insufficient overlap.
    results = await ContradictionDetector(llm_client=_llm(handler)).detect_contradictions(
        chunks=chunks
    )
    assert results == []
    assert handler.await_count == 1


@pytest.mark.asyncio
async def test_insufficient_semantic_evidence_no_contradiction():
    handler = AsyncMock(
        return_value=SemanticConflictJudgment(
            contradictory=False,
            confidence=0.2,
            rationale="Insufficient evidence.",
        )
    )
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Free parking available."),
        FakeChunk("b", "https://ex.com/b", "p", "Paid parking after 8 PM."),
    ]
    results = await ContradictionDetector(llm_client=_llm(handler)).detect_contradictions(
        chunks=chunks
    )
    assert results == []


@pytest.mark.asyncio
async def test_source_ids_must_belong_to_input_and_metadata_rebuilt():
    handler = AsyncMock(
        return_value=SemanticConflictJudgment(
            contradictory=True,
            severity=ContradictionSeverity.SOFT_INCONSISTENCY,
            confidence=0.8,
            rationale="Conflict",
        )
    )
    chunks = [
        FakeChunk("chunk-a", "https://real.example/a", "main > a", "Pets allowed here."),
        FakeChunk("chunk-b", "https://real.example/b", "main > b", "Pets not permitted here."),
    ]
    results = await ContradictionDetector(llm_client=_llm(handler)).detect_contradictions(
        chunks=chunks
    )
    assert results[0].source_urls == [
        "https://real.example/a",
        "https://real.example/b",
    ] or set(results[0].source_urls) == {
        "https://real.example/a",
        "https://real.example/b",
    }
    assert set(results[0].dom_paths) == {"main > a", "main > b"}


@pytest.mark.asyncio
async def test_duplicate_contradictions_removed_and_ordered():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Monday: 10 AM - 10 PM"),
        FakeChunk("b", "https://ex.com/b", "p", "Monday: 10 AM - 9 PM"),
        FakeChunk("c", "https://ex.com/c", "p", "Monday: 10:00 AM - 9:00 PM"),
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    # a-b, a-c, b-c but b and c equivalent → only conflicts involving a
    assert len(results) == 2
    ids = [c.contradiction_id for c in results]
    assert ids == sorted(ids)
    assert len(set(ids)) == 2


@pytest.mark.asyncio
async def test_self_comparison_does_not_generate_contradiction():
    chunks = [
        FakeChunk(
            "only",
            "https://ex.com",
            "p",
            "Monday: 10 AM - 10 PM and also Monday: 10 AM - 9 PM",
        )
    ]
    results = await detect_contradictions(chunks=chunks, llm_client=_llm())
    assert results == []


@pytest.mark.asyncio
async def test_llm_not_called_for_deterministic_conflicts():
    handler = AsyncMock()
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Monday: 10 AM - 10 PM"),
        FakeChunk("b", "https://ex.com/b", "p", "Monday: 10 AM - 9 PM"),
    ]
    await ContradictionDetector(llm_client=_llm(handler)).detect_contradictions(chunks=chunks)
    assert handler.await_count == 0


@pytest.mark.asyncio
async def test_llm_only_for_semantic_and_shared_client_budget():
    handler = AsyncMock(
        return_value=SemanticConflictJudgment(
            contradictory=True,
            severity=ContradictionSeverity.SOFT_INCONSISTENCY,
            confidence=0.6,
            rationale="soft",
        )
    )
    llm = _llm(handler, max_calls=1)
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Pets allowed."),
        FakeChunk("b", "https://ex.com/b", "p", "No pets allowed."),
        FakeChunk("c", "https://ex.com/c", "p", "Free parking out front."),
        FakeChunk("d", "https://ex.com/d", "p", "Paid parking in the garage."),
    ]
    with pytest.raises(BudgetExhausted):
        await ContradictionDetector(llm_client=llm).detect_contradictions(chunks=chunks)
    assert llm.calls_made == 1
    assert handler.await_count == 1


@pytest.mark.asyncio
async def test_provider_failure_becomes_contradiction_detection_error():
    handler = AsyncMock(side_effect=RuntimeError("provider down"))
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Pets allowed."),
        FakeChunk("b", "https://ex.com/b", "p", "Pets not permitted."),
    ]
    with pytest.raises(ContradictionDetectionError) as exc_info:
        await ContradictionDetector(llm_client=_llm(handler)).detect_contradictions(chunks=chunks)
    assert exc_info.value.reason == "semantic_classification_failure"
    assert "test-secret-key-do-not-leak" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_invalid_structured_output_rejected_no_repair():
    handler = AsyncMock(
        return_value=SemanticConflictJudgment(
            contradictory=True,
            severity=None,
            confidence=0.9,
            rationale="bad",
        )
    )
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Free parking."),
        FakeChunk("b", "https://ex.com/b", "p", "Paid parking."),
    ]
    with pytest.raises(ContradictionDetectionError) as exc_info:
        await ContradictionDetector(llm_client=_llm(handler)).detect_contradictions(chunks=chunks)
    assert exc_info.value.reason == "invalid_llm_output"
    assert handler.await_count == 1


@pytest.mark.asyncio
async def test_semantic_evaluations_concurrent_and_deterministic():
    started: list[float] = []
    finished: list[float] = []
    loop = asyncio.get_running_loop()

    async def side_effect(**kwargs):  # type: ignore[no-untyped-def]
        started.append(loop.time())
        await asyncio.sleep(0.04)
        finished.append(loop.time())
        return SemanticConflictJudgment(
            contradictory=True,
            severity=ContradictionSeverity.SOFT_INCONSISTENCY,
            confidence=0.55,
            rationale="soft conflict",
        )

    handler = AsyncMock(side_effect=side_effect)
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Pets allowed."),
        FakeChunk("b", "https://ex.com/b", "p", "No pets allowed."),
        FakeChunk("c", "https://ex.com/c", "p", "Free parking."),
        FakeChunk("d", "https://ex.com/d", "p", "Paid parking."),
    ]
    results = await ContradictionDetector(llm_client=_llm(handler)).detect_contradictions(
        chunks=chunks
    )
    assert len(results) == 2
    assert handler.await_count == 2
    assert started[1] < finished[0]
    assert [r.contradiction_id for r in results] == sorted(
        r.contradiction_id for r in results if r.contradiction_id
    )


def test_hours_normalization_helpers():
    assert normalize_hours_interval("Monday", "10 AM", "10 PM") == normalize_hours_interval(
        "Mon", "10:00", "22:00"
    )


def test_extract_facts_counts():
    chunks = [
        FakeChunk("a", "https://ex.com/a", "p", "Call +91 9999999999 or email a@x.com"),
    ]
    facts = extract_facts(chunks)
    assert any(f.fact_type.value == "phone" for f in facts)
    assert any(f.fact_type.value == "email" for f in facts)
    assert find_deterministic_conflicts(facts) == []
