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
    # Default max_retries=2 → 3 provider attempts; each consumes one budget unit.
    assert state["calls_made"] == 3


@pytest.mark.asyncio
async def test_401_auth_error_is_not_retried():
    """401/403 is permanent: one attempt, typed LLMAuthError, no retry amplification."""
    from app.core.llm_errors import ErrorClass, LLMAuthError

    class _AuthErr(RuntimeError):
        status_code = 401

    handler = AsyncMock(side_effect=_AuthErr("Error code: 401 - Invalid API Key"))
    client = _client_with_mock(handler)
    with pytest.raises(LLMAuthError) as exc_info:
        await client.create(
            _TinyResponse,
            messages=[{"role": "user", "content": "auth-check"}],
            max_retries=2,
        )
    assert exc_info.value.error_class is ErrorClass.AUTH
    assert handler.await_count == 1
    assert client.calls_made == 1
    assert "test-secret-key-do-not-leak" not in str(exc_info.value)


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


@pytest.mark.asyncio
async def test_shared_budget_guard_across_two_clients():
    from app.core.budget import BudgetGuard

    guard = BudgetGuard(limit=3)
    handler = AsyncMock(return_value=_TinyResponse(answer="ok", confidence=0.5))
    a = LLMClient(
        api_key="k",
        model="groq/test",
        budget_guard=guard,
        instructor_client=_FakeInstructorClient(handler),
    )
    b = LLMClient(
        api_key="k",
        model="groq/test",
        budget_guard=guard,
        instructor_client=_FakeInstructorClient(handler),
    )
    await a.create(_TinyResponse, messages=[{"role": "user", "content": "1"}], max_retries=0)
    await b.create(_TinyResponse, messages=[{"role": "user", "content": "2"}], max_retries=0)
    await a.create(_TinyResponse, messages=[{"role": "user", "content": "3"}], max_retries=0)
    with pytest.raises(BudgetExhausted):
        await b.create(_TinyResponse, messages=[{"role": "user", "content": "4"}], max_retries=0)
    assert guard.used == 3
    assert handler.await_count == 3


@pytest.mark.asyncio
async def test_retries_consume_budget_per_provider_attempt():
    calls = {"n": 0}

    async def flaky(**kwargs: Any) -> _TinyResponse:
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return _TinyResponse(answer="ok", confidence=0.5)

    handler = AsyncMock(side_effect=flaky)
    client = _client_with_mock(handler, max_calls=35)
    result = await client.create(
        _TinyResponse,
        messages=[{"role": "user", "content": "retry"}],
        max_retries=2,
    )
    assert result.answer == "ok"
    assert client.calls_made == 2
    assert handler.await_count == 2


def test_provider_chain_prefers_gemini_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "test-gemini-key")
    client = LLMClient()
    chain = client._get_provider_chain()
    assert len(chain) >= 1
    assert chain[0].name == "gemini"
    assert chain[0].model in ("gemini-2.5-flash", "gemini-3.6-flash")


def test_provider_chain_fallback_order_with_groq_and_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk_test123")
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "test-gemini-key")
    client = LLMClient(model="groq/qwen/qwen3.8-27b")
    chain = client._get_provider_chain()
    assert len(chain) == 2
    assert chain[0].name == "groq"
    assert chain[1].name == "gemini"


def test_provider_chain_only_groq_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk_test123")
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.OPENAI_API_KEY", "")
    client = LLMClient(model="groq/qwen/qwen3.8-27b")
    chain = client._get_provider_chain()
    assert len(chain) == 1
    assert chain[0].name == "groq"


def test_provider_chain_neither_present_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.OPENAI_API_KEY", "")
    client = LLMClient()
    with pytest.raises(RuntimeError, match=r"(?i)either.*key.*is required"):
        client._get_provider_chain()


def test_provider_chain_circuit_breaker_fails_over_remaining_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    LLMClient.reset_tripped_providers()
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk_test123")
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "test-gemini-key")
    client = LLMClient(model="groq/qwen/qwen3.8-27b")
    # Initially healthy: groq first
    initial_chain = client._get_provider_chain()
    assert initial_chain[0].name == "groq"
    assert initial_chain[1].name == "gemini"

    # Trip groq (e.g. 429 rate limit mid-scan)
    client._tripped_providers.add("groq")

    # Subsequent claims automatically put gemini first
    next_chain = client._get_provider_chain()
    assert next_chain[0].name == "gemini"
    assert next_chain[1].name == "groq"

    # Any new LLMClient instance (e.g. created by another engine or stage) also inherits tripped status
    another_client = LLMClient(model="groq/qwen/qwen3.8-27b")
    assert another_client._get_provider_chain()[0].name == "gemini"

    # Clean up
    LLMClient.reset_tripped_providers()
    assert client._get_provider_chain()[0].name == "groq"


def test_provider_chain_dynamic_env_switching(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure changing DEFAULT_LLM_MODEL and FALLBACK_LLM_MODEL switches chain ordering and models without code changes."""
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk_test123")
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "test-gemini-key")

    # Case 1: Primary Gemini, Fallback Groq
    monkeypatch.setattr("app.core.config.settings.DEFAULT_LLM_MODEL", "gemini/gemini-3.6-flash")
    monkeypatch.setattr("app.core.config.settings.FALLBACK_LLM_MODEL", "groq/openai/gpt-oss-120b")
    client1 = LLMClient()
    chain1 = client1._get_provider_chain()
    assert chain1[0].name == "gemini"
    assert chain1[0].model == "gemini-3.6-flash"
    assert chain1[1].name == "groq"
    assert chain1[1].model == "openai/gpt-oss-120b"

    # Case 2: Primary Groq with custom model, Fallback Gemini
    monkeypatch.setattr(
        "app.core.config.settings.DEFAULT_LLM_MODEL", "groq/llama-3.3-70b-versatile"
    )
    monkeypatch.setattr("app.core.config.settings.FALLBACK_LLM_MODEL", "gemini/gemini-2.5-flash")
    client2 = LLMClient()
    chain2 = client2._get_provider_chain()
    assert chain2[0].name == "groq"
    assert chain2[0].model == "llama-3.3-70b-versatile"
    assert chain2[1].name == "gemini"
    assert chain2[1].model == "gemini-2.5-flash"


def test_provider_chain_provider_model_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure GROQ_MODEL, GEMINI_MODEL, and OPENAI_MODEL env variables are respected."""
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "gsk_test123")
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr("app.core.config.settings.OPENAI_API_KEY", "sk-test-openai")

    monkeypatch.setattr("app.core.config.settings.GROQ_MODEL", "custom-groq-model")
    monkeypatch.setattr("app.core.config.settings.GEMINI_MODEL", "custom-gemini-model")
    monkeypatch.setattr("app.core.config.settings.OPENAI_MODEL", "custom-openai-model")

    monkeypatch.setattr("app.core.config.settings.DEFAULT_LLM_MODEL", "groq")
    monkeypatch.setattr("app.core.config.settings.FALLBACK_LLM_MODEL", "gemini")

    client = LLMClient()
    chain = client._get_provider_chain()
    assert chain[0].name == "groq"
    assert chain[0].model == "custom-groq-model"
    assert chain[1].name == "gemini"
    assert chain[1].model == "custom-gemini-model"
    assert chain[2].name == "openai"
    assert chain[2].model == "custom-openai-model"
