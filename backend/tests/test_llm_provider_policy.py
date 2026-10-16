"""Phase 5 GATE: fake-provider recovery policy (429/401/failover/race/cache).

Exercises the real multi-provider path (not the injected-instructor shortcut)
so classification, trip, failover counts, and budget reservation stay honest.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.core.budget import BudgetGuard, LLMBudgetExceededError, clear_process_response_cache
from app.core.llm import LLMClient, ProviderEndpoint
from app.core.llm_errors import ErrorClass, LLMAuthError

# Unthrottled fake endpoint names (not in PROVIDER_THROTTLES).
_GROQ = "fake_groq"
_GEMINI = "fake_gemini"


class _Tiny(BaseModel):
    answer: str


class _HttpErr(RuntimeError):
    def __init__(self, message: str, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(message)


class _FakeCompletions:
    def __init__(self, handler: AsyncMock) -> None:
        self.create = handler
        self.create_with_completion = None


class _FakeChat:
    def __init__(self, handler: AsyncMock) -> None:
        self.completions = _FakeCompletions(handler)


class _FakeInstructor:
    def __init__(self, handler: AsyncMock) -> None:
        self.chat = _FakeChat(handler)


def _ep(name: str, model: str = "test-model") -> ProviderEndpoint:
    return ProviderEndpoint(
        name=name,
        model=model,
        api_key=f"test-key-{name}",
        base_url=f"https://{name}.example/v1",
        mode=None,
    )


def _chain_client(
    handlers: dict[str, AsyncMock],
    *,
    budget: BudgetGuard | None = None,
    max_calls: int = 35,
) -> LLMClient:
    """LLMClient on the real provider path with stubbed chain + clients."""
    guard = budget or BudgetGuard(limit=max_calls)
    client = LLMClient(model="groq/test", budget_guard=guard, instructor_client=None)
    endpoints = [_ep(name) for name in handlers]

    def fake_chain(requested_model: str | None = None) -> list[ProviderEndpoint]:
        healthy = [e for e in endpoints if not client._is_tripped(e.name)]
        tripped = [e for e in endpoints if client._is_tripped(e.name)]
        return healthy + tripped

    def fake_get_client(endpoint: ProviderEndpoint) -> Any:
        return _FakeInstructor(handlers[endpoint.name])

    client._get_provider_chain = fake_chain  # type: ignore[method-assign]
    client._get_provider_client = fake_get_client  # type: ignore[method-assign]
    return client


@pytest.fixture(autouse=True)
def _reset_trips_and_fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    LLMClient.reset_tripped_providers()
    monkeypatch.setattr("app.core.llm._backoff_seconds", lambda *a, **k: 0.0)

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    yield
    LLMClient.reset_tripped_providers()


@pytest.mark.asyncio
async def test_401_is_terminal_single_attempt_no_retry() -> None:
    handler = AsyncMock(side_effect=_HttpErr("Error code: 401 - Invalid API Key", 401))
    client = _chain_client({_GROQ: handler})
    with pytest.raises(LLMAuthError) as exc:
        await client.create(_Tiny, messages=[{"role": "user", "content": "x"}], max_retries=3)
    assert exc.value.error_class is ErrorClass.AUTH
    assert handler.await_count == 1
    assert client.calls_made == 1
    assert client._budget.observability.provider_retries == 0


@pytest.mark.asyncio
async def test_429_bounded_retry_then_success() -> None:
    calls = {"n": 0}

    async def flaky(**kwargs: Any) -> _Tiny:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _HttpErr("Rate limit reached. Please try again in 0.1s", 429)
        return _Tiny(answer="ok")

    handler = AsyncMock(side_effect=flaky)
    client = _chain_client({_GROQ: handler})
    result = await client.create(
        _Tiny, messages=[{"role": "user", "content": "retry-me"}], max_retries=3
    )
    assert result.answer == "ok"
    assert handler.await_count == 3
    assert client.calls_made == 3
    assert client._budget.observability.provider_retries == 2
    assert client._budget.observability.provider_successes == 1
    assert client._budget.observability.provider_failures == 2


@pytest.mark.asyncio
async def test_429_exhausted_failsover_and_counts() -> None:
    primary = AsyncMock(side_effect=_HttpErr("Rate limit reached. Please try again in 0.1s", 429))
    fallback = AsyncMock(return_value=_Tiny(answer="from-fallback"))
    client = _chain_client({_GROQ: primary, _GEMINI: fallback})
    # Policy: RATE_LIMIT max_retries=2 → 3 attempts on primary, then failover.
    result = await client.create(
        _Tiny, messages=[{"role": "user", "content": "failover"}], max_retries=5
    )
    assert result.answer == "from-fallback"
    assert primary.await_count == 3
    assert fallback.await_count == 1
    assert client.calls_made == 4
    assert client._budget.observability.provider_failovers == 1
    assert client._budget.observability.fallback_provider_used is True
    assert client._is_tripped(_GROQ) is True


@pytest.mark.asyncio
async def test_cache_hit_skips_budget() -> None:
    clear_process_response_cache()
    handler = AsyncMock(return_value=_Tiny(answer="cached"))
    client = _chain_client({_GROQ: handler}, max_calls=10)
    msgs = [{"role": "user", "content": "same-payload"}]
    a = await client.create(_Tiny, messages=msgs, max_retries=0)
    b = await client.create(_Tiny, messages=msgs, max_retries=0)
    assert a.answer == b.answer == "cached"
    assert handler.await_count == 1
    assert client.calls_made == 1
    assert client._budget.observability.cache_hits == 1


@pytest.mark.asyncio
async def test_concurrent_budget_race_never_exceeds_limit() -> None:
    guard = BudgetGuard(limit=10)
    provider_ok = 0
    lock = asyncio.Lock()

    async def provider(**kwargs: Any) -> _Tiny:
        nonlocal provider_ok
        await asyncio.sleep(0.005)  # no-op via fixture monkeypatch
        async with lock:
            provider_ok += 1
        return _Tiny(answer="ok")

    client = _chain_client({_GROQ: AsyncMock(side_effect=provider)}, budget=guard)

    async def one(i: int) -> str:
        try:
            await client.create(
                _Tiny, messages=[{"role": "user", "content": f"race-{i}"}], max_retries=0
            )
            return "ok"
        except LLMBudgetExceededError:
            return "budget"

    results = await asyncio.gather(*[one(i) for i in range(25)])
    assert results.count("ok") == 10
    assert results.count("budget") == 15
    assert provider_ok == 10
    assert guard.used == 10
