"""P2-4.2 BudgetGuard — scan-scoped hard LLM call cap tests."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from pydantic import BaseModel

from app.core.budget import (
    BudgetExhausted,
    BudgetGuard,
    LLMBudgetExceededError,
    default_scan_budget,
)
from app.core.config import settings
from app.core.llm import LLMClient
from app.orchestration.dag import FindableAIDAG, ObservationInput
from app.orchestration.state import OrchestrationChunk, ScanPhase
from app.schemas.intelligence import (
    EntailmentStatus,
    IntentBatch,
    IntentCategory,
    IntentEvaluation,
    IntentQuery,
)
from app.schemas.patching import PatchPrioritizationResult
from app.schemas.scoring import SchemaOrgReport, SchemaTypeResult, ScoreBreakdown, ScoreWeights


class _Tiny(BaseModel):
    answer: str


class _FakeCompletions:
    def __init__(self, handler: AsyncMock) -> None:
        self.create = handler


class _FakeChat:
    def __init__(self, handler: AsyncMock) -> None:
        self.completions = _FakeCompletions(handler)


class _FakeInstructor:
    def __init__(self, handler: AsyncMock) -> None:
        self.chat = _FakeChat(handler)


def _client(
    handler: AsyncMock,
    *,
    budget: BudgetGuard | None = None,
    max_calls: int | None = None,
) -> LLMClient:
    kwargs: dict[str, Any] = {
        "api_key": "test-secret-key",
        "model": "groq/test",
        "instructor_client": _FakeInstructor(handler),
    }
    if budget is not None:
        kwargs["budget_guard"] = budget
    if max_calls is not None:
        kwargs["max_calls"] = max_calls
    return LLMClient(**kwargs)


# ---------------------------------------------------------------------------
# BudgetGuard unit tests
# ---------------------------------------------------------------------------


def test_initial_state():
    guard = BudgetGuard(limit=35)
    assert guard.used == 0
    assert guard.remaining == 35
    assert guard.limit == 35
    snap = guard.snapshot()
    assert snap["limit"] == 35
    assert snap["used"] == 0
    assert snap["remaining"] == 35
    assert "usd_used" in snap
    assert "enforce_usd" in snap


@pytest.mark.asyncio
async def test_single_reservation():
    guard = BudgetGuard(limit=35)
    n = await guard.reserve()
    assert n == 1
    assert guard.used == 1
    assert guard.remaining == 34


@pytest.mark.asyncio
async def test_exactly_35_reservations():
    guard = BudgetGuard(limit=35)
    for i in range(35):
        assert await guard.reserve() == i + 1
    assert guard.used == 35
    assert guard.remaining == 0


@pytest.mark.asyncio
async def test_36th_reservation_rejected_before_provider():
    events: list[str] = []
    guard = BudgetGuard(limit=35)

    async def provider(**kwargs: Any) -> _Tiny:
        events.append("provider")
        return _Tiny(answer="ok")

    handler = AsyncMock(side_effect=provider)
    client = _client(handler, budget=guard)

    for _ in range(35):
        await client.create(_Tiny, messages=[{"role": "user", "content": "x"}], max_retries=0)

    assert guard.used == 35
    assert handler.await_count == 35
    assert events.count("provider") == 35

    with pytest.raises(LLMBudgetExceededError) as exc:
        await client.create(_Tiny, messages=[{"role": "user", "content": "36"}], max_retries=0)

    assert exc.value.limit == 35
    assert exc.value.used == 35
    assert exc.value.remaining == 0
    assert exc.value.attempted == 36
    assert handler.await_count == 35  # no 36th provider call
    assert events.count("provider") == 35
    assert isinstance(exc.value, BudgetExhausted)


@pytest.mark.asyncio
async def test_reservation_before_provider_ordering():
    events: list[str] = []
    guard = BudgetGuard(limit=2)

    async def provider(**kwargs: Any) -> _Tiny:
        events.append("provider")
        # At provider time, reservation must already have incremented used.
        assert guard.used >= 1
        return _Tiny(answer="ok")

    original_reserve = guard.reserve

    async def traced_reserve() -> int:
        events.append("reserve")
        return int(await original_reserve())

    guard.reserve = traced_reserve  # type: ignore[method-assign]
    client = _client(AsyncMock(side_effect=provider), budget=guard)
    await client.create(_Tiny, messages=[{"role": "user", "content": "x"}], max_retries=0)
    assert events == ["reserve", "provider"]


@pytest.mark.asyncio
async def test_concurrent_40_attempts_limit_35():
    guard = BudgetGuard(limit=35)
    provider_ok = 0
    budget_fail = 0
    lock = asyncio.Lock()

    async def provider(**kwargs: Any) -> _Tiny:
        nonlocal provider_ok
        await asyncio.sleep(0.005)
        async with lock:
            provider_ok += 1
        return _Tiny(answer="ok")

    client = _client(AsyncMock(side_effect=provider), budget=guard)

    async def one(i: int) -> str:
        nonlocal budget_fail
        try:
            # Distinct payloads: identical in-flight requests are intentionally
            # coalesced by LLMClient (see test_identical_inflight_requests_are_coalesced).
            await client.create(_Tiny, messages=[{"role": "user", "content": f"x{i}"}], max_retries=0)
            return "ok"
        except LLMBudgetExceededError:
            async with lock:
                budget_fail += 1
            return "budget"

    results = await asyncio.gather(*[one(i) for i in range(40)])
    assert results.count("ok") == 35
    assert results.count("budget") == 5
    assert provider_ok == 35
    assert budget_fail == 5
    assert guard.used == 35
    assert guard.used <= 35


@pytest.mark.asyncio
async def test_identical_inflight_requests_are_coalesced():
    """Duplicate-request guard: identical concurrent requests cost one budget unit."""
    guard = BudgetGuard(limit=35)
    provider_calls = 0

    async def provider(**kwargs: Any) -> _Tiny:
        nonlocal provider_calls
        provider_calls += 1
        await asyncio.sleep(0.01)
        return _Tiny(answer="ok")

    client = _client(AsyncMock(side_effect=provider), budget=guard)
    results = await asyncio.gather(
        *[
            client.create(_Tiny, messages=[{"role": "user", "content": "same"}], max_retries=0)
            for _ in range(8)
        ]
    )
    assert all(r.answer == "ok" for r in results)
    assert provider_calls == 1
    assert guard.used == 1
    assert guard.observability.duplicate_requests_joined == 7
    assert client._budget.inflight == {}  # cleaned up after completion


@pytest.mark.asyncio
async def test_shared_budget_across_clients():
    guard = BudgetGuard(limit=35)
    handler = AsyncMock(return_value=_Tiny(answer="ok"))
    a = _client(handler, budget=guard)
    b = _client(handler, budget=guard)

    for _ in range(20):
        await a.create(_Tiny, messages=[{"role": "user", "content": "a"}], max_retries=0)
    for _ in range(15):
        await b.create(_Tiny, messages=[{"role": "user", "content": "b"}], max_retries=0)

    assert guard.used == 35
    with pytest.raises(LLMBudgetExceededError):
        await a.create(_Tiny, messages=[{"role": "user", "content": "overflow"}], max_retries=0)
    assert handler.await_count == 35


@pytest.mark.asyncio
async def test_shared_budget_intent_plus_nli_style():
    """1 intent + 30 NLI + 4 extra = 35; 36th fails."""
    guard = BudgetGuard(limit=35)
    handler = AsyncMock(return_value=_Tiny(answer="ok"))
    intent_client = _client(handler, budget=guard)
    nli_client = _client(handler, budget=guard)

    await intent_client.create(
        _Tiny, messages=[{"role": "user", "content": "intent"}], max_retries=0
    )
    for i in range(30):
        await nli_client.create(
            _Tiny, messages=[{"role": "user", "content": f"nli-{i}"}], max_retries=0
        )
    for i in range(4):
        await nli_client.create(
            _Tiny, messages=[{"role": "user", "content": f"extra-{i}"}], max_retries=0
        )
    assert guard.used == 35
    with pytest.raises(LLMBudgetExceededError):
        await intent_client.create(
            _Tiny, messages=[{"role": "user", "content": "too-many"}], max_retries=0
        )
    assert handler.await_count == 35


@pytest.mark.asyncio
async def test_retry_accounting_each_attempt_consumes_budget():
    """max_retries=2 => up to 3 provider attempts => 3 budget units."""
    events: list[str] = []
    guard = BudgetGuard(limit=35)
    calls = {"n": 0}

    async def flaky(**kwargs: Any) -> _Tiny:
        calls["n"] += 1
        events.append(f"provider-{calls['n']}")
        if calls["n"] < 3:
            raise RuntimeError(f"transient-{calls['n']}")
        return _Tiny(answer="ok")

    client = _client(AsyncMock(side_effect=flaky), budget=guard)
    result = await client.create(
        _Tiny,
        messages=[{"role": "user", "content": "retry"}],
        max_retries=2,
    )
    assert result.answer == "ok"
    assert guard.used == 3
    assert events == ["provider-1", "provider-2", "provider-3"]


@pytest.mark.asyncio
async def test_retry_at_budget_boundary_does_not_call_provider():
    guard = BudgetGuard(limit=1)
    handler = AsyncMock(side_effect=RuntimeError("fail-once"))
    client = _client(handler, budget=guard)

    # First attempt reserves + provider fails; retry reserve is rejected (limit=1).
    with pytest.raises(LLMBudgetExceededError):
        await client.create(_Tiny, messages=[{"role": "user", "content": "x"}], max_retries=2)

    assert guard.used == 1
    assert handler.await_count == 1

    with pytest.raises(LLMBudgetExceededError):
        await client.create(_Tiny, messages=[{"role": "user", "content": "y"}], max_retries=2)
    assert handler.await_count == 1


@pytest.mark.asyncio
async def test_provider_failure_still_counts():
    guard = BudgetGuard(limit=5)
    handler = AsyncMock(side_effect=RuntimeError("upstream boom"))
    client = _client(handler, budget=guard)

    with pytest.raises(RuntimeError) as exc:
        await client.create(_Tiny, messages=[{"role": "user", "content": "x"}], max_retries=0)

    assert "upstream boom" in str(exc.value) or "LLM structured call failed" in str(exc.value)
    assert guard.used == 1
    assert not isinstance(exc.value, LLMBudgetExceededError)


@pytest.mark.asyncio
async def test_budget_failure_vs_provider_failure_distinguishable():
    guard = BudgetGuard(limit=1)
    handler = AsyncMock(return_value=_Tiny(answer="ok"))
    client = _client(handler, budget=guard)
    await client.create(_Tiny, messages=[{"role": "user", "content": "1"}], max_retries=0)

    with pytest.raises(LLMBudgetExceededError):
        await client.create(_Tiny, messages=[{"role": "user", "content": "2"}], max_retries=0)

    guard2 = BudgetGuard(limit=1)
    bad = AsyncMock(side_effect=RuntimeError("provider down"))
    client2 = _client(bad, budget=guard2)
    with pytest.raises(RuntimeError) as exc:
        await client2.create(_Tiny, messages=[{"role": "user", "content": "x"}], max_retries=0)
    assert not isinstance(exc.value, LLMBudgetExceededError)


@pytest.mark.asyncio
async def test_per_scan_isolation():
    a = BudgetGuard(limit=35)
    b = BudgetGuard(limit=35)
    handler = AsyncMock(return_value=_Tiny(answer="ok"))
    client_a = _client(handler, budget=a)
    client_b = _client(handler, budget=b)

    for _ in range(35):
        await client_a.create(_Tiny, messages=[{"role": "user", "content": "a"}], max_retries=0)
    with pytest.raises(LLMBudgetExceededError):
        await client_a.create(_Tiny, messages=[{"role": "user", "content": "a"}], max_retries=0)

    for _ in range(35):
        await client_b.create(_Tiny, messages=[{"role": "user", "content": "b"}], max_retries=0)
    assert b.used == 35
    assert a.used == 35


@pytest.mark.asyncio
async def test_limit_zero_rejects_first_call():
    guard = BudgetGuard(limit=0)
    handler = AsyncMock(return_value=_Tiny(answer="ok"))
    client = _client(handler, budget=guard)
    with pytest.raises(LLMBudgetExceededError):
        await client.create(_Tiny, messages=[{"role": "user", "content": "x"}], max_retries=0)
    assert handler.await_count == 0
    assert guard.used == 0


@pytest.mark.asyncio
async def test_limit_one():
    guard = BudgetGuard(limit=1)
    handler = AsyncMock(return_value=_Tiny(answer="ok"))
    client = _client(handler, budget=guard)
    await client.create(_Tiny, messages=[{"role": "user", "content": "x"}], max_retries=0)
    with pytest.raises(LLMBudgetExceededError):
        await client.create(_Tiny, messages=[{"role": "user", "content": "y"}], max_retries=0)
    assert handler.await_count == 1


def test_negative_limit_rejected():
    with pytest.raises(ValueError):
        BudgetGuard(limit=-1)


def test_default_scan_budget_is_fresh():
    a = default_scan_budget()
    b = default_scan_budget()
    assert a is not b
    assert a.limit == settings.MAX_LLM_CALLS_PER_SCAN
    assert a.used == 0


def test_exception_has_no_secrets():
    err = LLMBudgetExceededError(limit=35, used=35, remaining=0, attempted=36)
    assert "api_key" not in str(err)
    assert "token" not in str(err).lower() or "attempted" in str(err)


# ---------------------------------------------------------------------------
# DAG integration
# ---------------------------------------------------------------------------


def _intent_batch() -> IntentBatch:
    queries = []
    for cat in IntentCategory:
        for j in range(1, 4):
            queries.append(
                IntentQuery(
                    intent_id=f"{cat.value}_{j:02d}",
                    category=cat,
                    query=f"Q {cat.value} {j}?",
                    difficulty="easy",
                    expected_evidence_type="page text",
                )
            )
    return IntentBatch(business_type="restaurant", queries=queries)


def _eval(iid: str) -> IntentEvaluation:
    return IntentEvaluation(
        intent_id=iid,
        query="Q?",
        status=EntailmentStatus.UNKNOWN,
        reasoning="fixture",
        evidence=[],
        confidence=0.0,
    )


def _score() -> ScoreBreakdown:
    required = [
        "LocalBusiness",
        "PostalAddress",
        "OpeningHoursSpecification",
        "GeoCoordinates",
        "Menu",
        "FAQPage",
    ]
    report = SchemaOrgReport(
        total_blocks=0,
        valid_blocks=0,
        invalid_blocks=0,
        malformed_blocks=0,
        required_types=required,
        types=[
            SchemaTypeResult(
                schema_type=n, present=False, valid=False, occurrences=0, source_count=0
            )
            for n in required
        ],
        score=0.0,
        issues=[],
    )
    return ScoreBreakdown(
        f_score=40.0,
        s_ans=40.0,
        s_con=100.0,
        s_str=0.0,
        s_acc=50.0,
        weights=ScoreWeights(),
        schema_report=report,
    )


class _CountingIntent:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.calls = 0

    async def generate_intents(self, *, business_context: str) -> IntentBatch:
        self.calls += 1
        await self.llm.create(
            _Tiny,
            messages=[{"role": "user", "content": "intent"}],
            max_retries=0,
        )
        return _intent_batch()


class _CountingNLI:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.calls = 0

    async def evaluate_intents(self, *, intents: Any, scan_id: UUID) -> list[IntentEvaluation]:
        out = []
        for q in intents:
            self.calls += 1
            await self.llm.create(
                _Tiny,
                messages=[{"role": "user", "content": q.intent_id}],
                max_retries=0,
            )
            out.append(_eval(q.intent_id))
        return out


class _FakeContra:
    async def detect_contradictions(self, *, chunks: Any) -> list:
        return []


class _FakeScorer:
    def score(self, inputs: Any) -> ScoreBreakdown:
        return _score()


class _FakePrio:
    def prioritize(self, inputs: Any) -> PatchPrioritizationResult:
        return PatchPrioritizationResult(opportunities=[], total_candidates=0, selected_count=0)


def _obs() -> ObservationInput:
    return ObservationInput(
        scan_id="33333333-3333-3333-3333-333333333333",
        business_context="Neighborhood bistro with lunch specials and patio seating available.",
        chunks=[
            OrchestrationChunk(
                id="c1",
                url="https://ex.com",
                dom_path="/p[1]",
                content="Hello",
                tag="p",
                word_count=1,
            )
        ],
        html_documents=["<html><head></head><body>Hi</body></html>"],
        create_pr=False,
    )


@pytest.mark.asyncio
async def test_dag_shares_one_budget_across_stages():
    guard = BudgetGuard(limit=35)
    handler = AsyncMock(return_value=_Tiny(answer="ok"))
    llm = _client(handler, budget=guard)
    intent = _CountingIntent(llm)
    nli = _CountingNLI(llm)

    dag = FindableAIDAG(
        llm_client=llm,
        budget_guard=guard,
        intent_generator=intent,  # type: ignore[arg-type]
        entailment_engine=nli,  # type: ignore[arg-type]
        contradiction_detector=_FakeContra(),  # type: ignore[arg-type]
        scorer=_FakeScorer(),  # type: ignore[arg-type]
        patch_prioritizer=_FakePrio(),  # type: ignore[arg-type]
    )
    result = await dag.run(_obs())
    assert result.success is True
    assert result.final_state is ScanPhase.STOP
    # 1 intent + 30 NLI = 31
    assert guard.used == 31
    assert intent.calls == 1
    assert nli.calls == 30
    assert dag.budget_guard is guard
    assert result.llm_calls_made == 31


@pytest.mark.asyncio
async def test_dag_budget_exhaustion_no_false_success():
    """Force ACT to exhaust budget mid-pipeline."""
    guard = BudgetGuard(limit=5)  # 1 intent + 4 NLI, then fail
    handler = AsyncMock(return_value=_Tiny(answer="ok"))
    llm = _client(handler, budget=guard)
    intent = _CountingIntent(llm)
    nli = _CountingNLI(llm)
    contra = _FakeContra()
    contra_called = {"n": 0}

    async def detect(*, chunks: Any) -> list:
        contra_called["n"] += 1
        return []

    contra.detect_contradictions = detect  # type: ignore[method-assign]

    dag = FindableAIDAG(
        llm_client=llm,
        budget_guard=guard,
        intent_generator=intent,  # type: ignore[arg-type]
        entailment_engine=nli,  # type: ignore[arg-type]
        contradiction_detector=contra,  # type: ignore[arg-type]
        scorer=_FakeScorer(),  # type: ignore[arg-type]
        patch_prioritizer=_FakePrio(),  # type: ignore[arg-type]
    )
    result = await dag.run(_obs())
    assert result.success is False
    assert result.error_reason == "budget_exhausted"
    assert result.final_state is ScanPhase.ACT
    assert "verify" not in result.stage_trace
    assert contra_called["n"] == 0
    assert guard.used == 5
    assert handler.await_count == 5  # no call past budget


@pytest.mark.asyncio
async def test_lock_not_held_during_provider_io():
    """Two concurrent creates must overlap in provider await (lock released)."""
    guard = BudgetGuard(limit=2)
    in_provider = 0
    max_concurrent = 0
    gate = asyncio.Event()
    started = 0

    async def slow(**kwargs: Any) -> _Tiny:
        nonlocal in_provider, max_concurrent, started
        in_provider += 1
        started += 1
        max_concurrent = max(max_concurrent, in_provider)
        if started >= 2:
            gate.set()
        await gate.wait()
        await asyncio.sleep(0.01)
        in_provider -= 1
        return _Tiny(answer="ok")

    client = _client(AsyncMock(side_effect=slow), budget=guard)
    await asyncio.gather(
        client.create(_Tiny, messages=[{"role": "user", "content": "1"}], max_retries=0),
        client.create(_Tiny, messages=[{"role": "user", "content": "2"}], max_retries=0),
    )
    assert max_concurrent == 2
    assert guard.used == 2
