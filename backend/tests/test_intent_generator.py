"""Unit tests for IntentGenerator — single LLM call, 30 validated intents."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.llm import LLMClient
from app.engines.intent_generator import (
    IntentGenerationError,
    IntentGenerator,
    generate_intents,
    validate_intent_batch,
)
from app.schemas.intelligence import IntentBatch, IntentCategory, IntentQuery


class _FakeCompletions:
    def __init__(self, handler: AsyncMock) -> None:
        self.create = handler


class _FakeChat:
    def __init__(self, handler: AsyncMock) -> None:
        self.completions = _FakeCompletions(handler)


class _FakeInstructorClient:
    def __init__(self, handler: AsyncMock) -> None:
        self.chat = _FakeChat(handler)


def _llm_with_mock(handler: AsyncMock, *, max_calls: int = 35) -> LLMClient:
    return LLMClient(
        api_key="test-secret-key-do-not-leak",
        model="groq/qwen-2.5-72b-instruct",
        max_calls=max_calls,
        instructor_client=_FakeInstructorClient(handler),
    )


def _make_query(
    category: IntentCategory,
    index: int,
    *,
    query: str | None = None,
    difficulty: str = "medium",
) -> IntentQuery:
    label = category.value
    text = query or f"What should I know about {label} topic number {index}?"
    return IntentQuery(
        intent_id=f"{label}_{index:02d}",
        category=category,
        query=text,
        difficulty=difficulty,  # type: ignore[arg-type]
        expected_evidence_type="FAQ section",
    )


def _valid_batch(*, mutate: dict | None = None) -> IntentBatch:
    queries: list[IntentQuery] = []
    for category in IntentCategory:
        for i in range(1, 4):
            queries.append(_make_query(category, i))
    batch = IntentBatch(business_type="restaurant", queries=queries)
    if not mutate:
        return batch

    updated_queries = list(batch.queries)
    if "queries" in mutate:
        updated_queries = mutate["queries"]
    business_type = mutate.get("business_type", batch.business_type)
    # Bypass Pydantic length constraints when constructing invalid fixtures for
    # validate_intent_batch by using model_construct when needed.
    if len(updated_queries) != 30:
        return IntentBatch.model_construct(
            business_type=business_type,
            queries=updated_queries,
        )
    return IntentBatch(business_type=business_type, queries=updated_queries)


VALID_CONTEXT = (
    "Restaurant with dine-in service, reservations, weekend brunch, "
    "wheelchair-accessible entrance, accepts major cards."
)


@pytest.mark.asyncio
async def test_generate_intents_makes_exactly_one_llm_call():
    batch = _valid_batch()
    handler = AsyncMock(return_value=batch)
    llm = _llm_with_mock(handler)
    generator = IntentGenerator(llm_client=llm)

    result = await generator.generate_intents(business_context=VALID_CONTEXT)

    assert handler.await_count == 1
    assert llm.calls_made == 1
    assert len(result.queries) == 30
    kwargs = handler.await_args.kwargs
    assert kwargs["response_model"] is IntentBatch
    assert kwargs["max_retries"] == 0


@pytest.mark.asyncio
async def test_valid_batch_succeeds_with_all_categories_three_each():
    handler = AsyncMock(return_value=_valid_batch())
    result = await generate_intents(
        business_context=VALID_CONTEXT,
        llm_client=_llm_with_mock(handler),
    )

    assert len(result.queries) == 30
    assert result.business_type == "restaurant"
    counts = {c.value: 0 for c in IntentCategory}
    for q in result.queries:
        counts[q.category.value] += 1
    assert set(counts) == {c.value for c in IntentCategory}
    assert all(v == 3 for v in counts.values())
    # Deterministic ids after validation
    assert result.queries[0].intent_id.endswith("_01")


@pytest.mark.asyncio
async def test_duplicate_queries_rejected_case_insensitive():
    queries = []
    for category in IntentCategory:
        for i in range(1, 4):
            queries.append(_make_query(category, i))
    queries[1] = queries[1].model_copy(
        update={"query": queries[0].query.upper().replace("?", " ?")}
    )
    batch = IntentBatch(business_type="restaurant", queries=queries)

    with pytest.raises(IntentGenerationError, match="Duplicate") as exc_info:
        validate_intent_batch(batch)
    assert exc_info.value.reason == "duplicate_query"


@pytest.mark.asyncio
async def test_invalid_category_distribution_rejected():
    queries = []
    # 4 eligibility, 2 policy, 3 for the rest
    for i in range(1, 5):
        queries.append(_make_query(IntentCategory.ELIGIBILITY, i))
    for i in range(1, 3):
        queries.append(_make_query(IntentCategory.POLICY, i))
    for category in list(IntentCategory)[2:]:
        for i in range(1, 4):
            queries.append(_make_query(category, i))
    assert len(queries) == 30
    batch = IntentBatch(business_type="restaurant", queries=queries)

    with pytest.raises(IntentGenerationError) as exc_info:
        validate_intent_batch(batch)
    assert exc_info.value.reason == "invalid_category_distribution"


@pytest.mark.asyncio
async def test_fewer_than_30_intents_rejected():
    queries = [_make_query(IntentCategory.ELIGIBILITY, 1)]
    batch = IntentBatch.model_construct(business_type="restaurant", queries=queries)
    with pytest.raises(IntentGenerationError) as exc_info:
        validate_intent_batch(batch)
    assert exc_info.value.reason == "invalid_query_count"


@pytest.mark.asyncio
async def test_more_than_30_intents_rejected():
    queries = []
    for category in IntentCategory:
        for i in range(1, 4):
            queries.append(_make_query(category, i))
    queries.append(_make_query(IntentCategory.EDGE_CASES, 4, query="Extra edge case question?"))
    batch = IntentBatch.model_construct(business_type="restaurant", queries=queries)
    with pytest.raises(IntentGenerationError) as exc_info:
        validate_intent_batch(batch)
    assert exc_info.value.reason == "invalid_query_count"


@pytest.mark.asyncio
async def test_empty_questions_rejected():
    queries = []
    for category in IntentCategory:
        for i in range(1, 4):
            queries.append(_make_query(category, i))
    queries[0] = queries[0].model_copy(update={"query": "   "})
    # Construct without re-validating empty query via IntentQuery
    batch = IntentBatch.model_construct(business_type="restaurant", queries=queries)
    with pytest.raises(IntentGenerationError) as exc_info:
        validate_intent_batch(batch)
    assert exc_info.value.reason == "empty_query"


@pytest.mark.asyncio
async def test_answer_like_output_rejected():
    queries = []
    for category in IntentCategory:
        for i in range(1, 4):
            queries.append(_make_query(category, i))
    queries[0] = queries[0].model_copy(update={"query": "Yes, we offer gluten-free options?"})
    batch = IntentBatch(business_type="restaurant", queries=queries)
    with pytest.raises(IntentGenerationError) as exc_info:
        validate_intent_batch(batch)
    assert exc_info.value.reason == "answer_like_query"


@pytest.mark.asyncio
async def test_llm_provider_errors_propagate_as_intent_generation_error():
    handler = AsyncMock(side_effect=RuntimeError("upstream timeout"))
    llm = _llm_with_mock(handler)
    generator = IntentGenerator(llm_client=llm)

    with pytest.raises(IntentGenerationError) as exc_info:
        await generator.generate_intents(business_context=VALID_CONTEXT)

    assert exc_info.value.reason == "llm_failure"
    assert handler.await_count == 1
    assert "test-secret-key-do-not-leak" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_business_context_validation():
    handler = AsyncMock(return_value=_valid_batch())
    llm = _llm_with_mock(handler)
    generator = IntentGenerator(llm_client=llm)

    with pytest.raises(IntentGenerationError) as exc_info:
        await generator.generate_intents(business_context="   short   ")
    assert exc_info.value.reason == "invalid_business_context"
    assert handler.await_count == 0
    assert llm.calls_made == 0


@pytest.mark.asyncio
async def test_validation_failure_does_not_trigger_second_llm_call():
    queries = []
    for category in IntentCategory:
        for i in range(1, 4):
            queries.append(_make_query(category, i))
    queries[5] = queries[5].model_copy(update={"query": queries[4].query})
    bad_batch = IntentBatch(business_type="cafe", queries=queries)

    handler = AsyncMock(return_value=bad_batch)
    llm = _llm_with_mock(handler)
    generator = IntentGenerator(llm_client=llm)

    with pytest.raises(IntentGenerationError) as exc_info:
        await generator.generate_intents(business_context=VALID_CONTEXT)

    assert exc_info.value.reason == "duplicate_query"
    assert handler.await_count == 1
    assert llm.calls_made == 1


@pytest.mark.asyncio
async def test_missing_category_rejected():
    queries = []
    # Skip EDGE_CASES; double up ELIGIBILITY to keep length 30
    for i in range(1, 7):
        queries.append(
            _make_query(
                IntentCategory.ELIGIBILITY,
                i,
                query=f"Eligibility unique question number {i}?",
            )
        )
    for category in list(IntentCategory)[1:-1]:
        for i in range(1, 4):
            queries.append(_make_query(category, i))
    assert len(queries) == 30
    batch = IntentBatch(business_type="restaurant", queries=queries)
    with pytest.raises(IntentGenerationError) as exc_info:
        validate_intent_batch(batch)
    assert exc_info.value.reason in {
        "missing_categories",
        "invalid_category_distribution",
    }
