"""Unit tests for LLMClient budget guard and structured responses."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, ValidationError

from app.core.llm import BudgetExhausted, LLMClient
from app.schemas.intelligence import EntailmentStatus, IntentEvaluation


class _TinyResponse(BaseModel):
    answer: str
    confidence: float


class _FakeCompletions:
    def __init__(self, handler: AsyncMock) -> None:
        self.create = handler


class _FakeChat:
    def __init__(self, handler: AsyncMock) -> None:
        self.completions = _FakeCompletions(handler)


class _FakeInstructorClient:
    def __init__(self, handler: AsyncMock) -> None:
        self.chat = _FakeChat(handler)


def _client_with_mock(
    handler: AsyncMock,
    *,
    max_calls: int = 35,
    api_key: str = "test-secret-key-do-not-leak",
) -> LLMClient:
    return LLMClient(
        api_key=api_key,
        model="groq/qwen-2.5-72b-instruct",
        max_calls=max_calls,
        instructor_client=_FakeInstructorClient(handler),
    )


@pytest.mark.asyncio
async def test_structured_call_returns_validated_pydantic_model():
    handler = AsyncMock(return_value=_TinyResponse(answer="supported", confidence=0.91))
    client = _client_with_mock(handler)

    result = await client.create(
        _TinyResponse,
        messages=[{"role": "user", "content": "Classify this claim."}],
    )

    assert isinstance(result, _TinyResponse)
    assert result.answer == "supported"
    assert result.confidence == 0.91
    assert client.calls_made == 1
    handler.assert_awaited_once()
    kwargs = handler.await_args.kwargs
    assert kwargs["response_model"] is _TinyResponse
    assert kwargs["model"] == "groq/qwen-2.5-72b-instruct"
    assert kwargs["api_key"] == "test-secret-key-do-not-leak"


@pytest.mark.asyncio
async def test_pydantic_response_validation_for_intent_evaluation():
    payload = IntentEvaluation(
        intent_id="eligibility_01",
        query="Do you have gluten-free options?",
        status=EntailmentStatus.SUPPORTED,
        reasoning="Menu section lists a dedicated gluten-free fryer.",
        evidence=[],
        confidence=0.87,
    )
    handler = AsyncMock(return_value=payload)
    client = _client_with_mock(handler)

    result = await client.create(
        IntentEvaluation,
        messages=[{"role": "user", "content": "Evaluate intent."}],
    )

    assert result.status is EntailmentStatus.SUPPORTED
    assert 0.0 <= result.confidence <= 1.0

    with pytest.raises(ValidationError):
        IntentEvaluation(
            intent_id="bad",
            query="q",
            status=EntailmentStatus.UNKNOWN,
            reasoning="r",
            evidence=[],
            confidence=1.5,
        )


@pytest.mark.asyncio
async def test_budget_increments_on_each_call():
    handler = AsyncMock(
        side_effect=[
            _TinyResponse(answer="a", confidence=0.1),
            _TinyResponse(answer="b", confidence=0.2),
            _TinyResponse(answer="c", confidence=0.3),
        ]
    )
    client = _client_with_mock(handler, max_calls=35)

    assert client.calls_made == 0
    await client.create(_TinyResponse, messages=[{"role": "user", "content": "1"}])
    assert client.calls_made == 1
    await client.create(_TinyResponse, messages=[{"role": "user", "content": "2"}])
    assert client.calls_made == 2
    await client.create(_TinyResponse, messages=[{"role": "user", "content": "3"}])
    assert client.calls_made == 3
    assert client.remaining_calls == 32


@pytest.mark.asyncio
async def test_call_at_35th_limit_succeeds_and_36th_raises_budget_exhausted():
    handler = AsyncMock(return_value=_TinyResponse(answer="ok", confidence=0.5))
    client = _client_with_mock(handler, max_calls=35)

    for i in range(35):
        result = await client.create(
            _TinyResponse,
            messages=[{"role": "user", "content": f"call-{i + 1}"}],
        )
        assert result.answer == "ok"

    assert client.calls_made == 35
    assert client.remaining_calls == 0
    assert handler.await_count == 35

    with pytest.raises(BudgetExhausted) as exc_info:
        await client.create(
            _TinyResponse,
            messages=[{"role": "user", "content": "call-36"}],
        )

    assert exc_info.value.calls_made == 35
    assert exc_info.value.max_calls == 35
    assert handler.await_count == 35  # rejected before provider call
    assert "test-secret-key-do-not-leak" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_key_never_exposed_in_errors_or_repr():
    secret = "gsk_super_secret_provider_key_xyz"
    handler = AsyncMock(side_effect=RuntimeError(f"upstream auth failed for key={secret}"))
    client = _client_with_mock(handler, api_key=secret)

    with pytest.raises(RuntimeError) as exc_info:
        await client.create(
            _TinyResponse,
            messages=[{"role": "user", "content": "boom"}],
        )

    err = str(exc_info.value)
    assert secret not in err
    assert "***REDACTED***" in err
    assert secret not in repr(client)
    assert secret not in str(client.budget_state())
    state = client.budget_state()
    assert "api_key" not in state
    assert state["calls_made"] == 1


@pytest.mark.asyncio
async def test_budget_reservation_is_async_safe():
    """Concurrent callers must not exceed max_calls."""
    import asyncio

    handler = AsyncMock(return_value=_TinyResponse(answer="ok", confidence=0.4))

    async def slow_create(**kwargs: Any) -> _TinyResponse:
        await asyncio.sleep(0.01)
        return _TinyResponse(answer="ok", confidence=0.4)

    handler.side_effect = slow_create
    client = _client_with_mock(handler, max_calls=5)

    results = await asyncio.gather(
        *[
            client.create(_TinyResponse, messages=[{"role": "user", "content": str(i)}])
            for i in range(5)
        ]
    )
    assert len(results) == 5
    assert client.calls_made == 5

    with pytest.raises(BudgetExhausted):
        await client.create(
            _TinyResponse,
            messages=[{"role": "user", "content": "overflow"}],
        )
