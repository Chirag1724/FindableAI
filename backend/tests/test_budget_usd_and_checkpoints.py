"""Budget USD enforcement, durable checkpoint helpers, verification honesty."""

from __future__ import annotations

import asyncio

import pytest

from app.core.budget import BudgetGuard, LLMBudgetExceededError
from app.jobs.checkpoints import (
    checkpoint_compatible,
    empty_checkpoint,
    mark_stage,
    request_stage_fingerprint,
    stage_done,
)
from app.orchestration.remediation_lifecycle import (
    OUTCOME_FIXED,
    VERIFICATION_METHOD_HEURISTIC,
    evaluate_verification_outcome,
    persist_verification_run,
)


@pytest.mark.asyncio
async def test_budget_enforces_estimated_usd(monkeypatch):
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "LLM_ENFORCE_USD_BUDGET", True)
    monkeypatch.setattr(config_mod.settings, "LLM_BUDGET_CAP_USD", 0.00025)
    monkeypatch.setattr(config_mod.settings, "LLM_ESTIMATED_USD_PER_CALL", 0.0001)

    guard = BudgetGuard(limit=100)
    await guard.reserve()  # 0.0001
    await guard.reserve()  # 0.0002
    with pytest.raises(LLMBudgetExceededError) as ei:
        await guard.reserve()  # would be 0.0003 > 0.00025
    assert ei.value.reason == "usd_limit"
    assert guard.used == 2


@pytest.mark.asyncio
async def test_budget_usd_disabled_allows_calls(monkeypatch):
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "LLM_ENFORCE_USD_BUDGET", False)
    monkeypatch.setattr(config_mod.settings, "LLM_BUDGET_CAP_USD", 0.00001)
    monkeypatch.setattr(config_mod.settings, "LLM_ESTIMATED_USD_PER_CALL", 0.001)

    guard = BudgetGuard(limit=3, enforce_usd=False)
    assert await guard.reserve() == 1
    assert await guard.reserve() == 2
    assert await guard.reserve() == 3
    with pytest.raises(LLMBudgetExceededError) as ei:
        await guard.reserve()
    assert ei.value.reason == "call_limit"


@pytest.mark.asyncio
async def test_budget_on_reserve_hook_fires():
    seen: list[tuple[int, float]] = []

    async def hook(used: int, usd: float) -> None:
        seen.append((used, usd))

    guard = BudgetGuard(
        limit=5,
        enforce_usd=False,
        usd_per_call=0.01,
        on_reserve=hook,
    )
    await guard.reserve()
    await guard.reserve()
    assert seen == [(1, 0.01), (2, 0.02)]


@pytest.mark.asyncio
async def test_concurrent_budget_reservations_respect_limit():
    guard = BudgetGuard(limit=20, enforce_usd=False)

    async def worker() -> int:
        ok = 0
        for _ in range(30):
            try:
                await guard.reserve()
                ok += 1
            except LLMBudgetExceededError:
                break
        return ok

    totals = await asyncio.gather(*[worker() for _ in range(8)])
    assert sum(totals) == 20
    assert guard.used == 20


def test_checkpoint_fingerprint_and_compatibility():
    fp = request_stage_fingerprint(
        url="https://Example.com/path/",
        max_pages=3,
        personas=["cto", "developer"],
    )
    cp = empty_checkpoint(fingerprint=fp)
    assert checkpoint_compatible(cp, fingerprint=fp)
    assert not checkpoint_compatible(cp, fingerprint="other")
    assert not stage_done(cp, "chunks")
    cp2 = mark_stage(cp, "chunks", meta={"count": 4})
    assert stage_done(cp2, "chunks")
    # Incompatible extractor version
    bad = dict(cp2)
    bad["versions"] = {**bad["versions"], "extractor": "old"}
    assert not checkpoint_compatible(bad, fingerprint=fp)


def test_heuristic_fixed_is_not_full_verification():
    outcome, _ops, detail = evaluate_verification_outcome(
        original_issue_keywords=["pricing", "refund"],
        patched_content="Our pricing and refund policy is clear.",
        validation_passed=True,
    )
    assert outcome == OUTCOME_FIXED
    assert "heuristic" in detail.lower() or "not a full" in detail.lower()
    assert "fully_verified=false" in detail.lower() or "not a full" in detail.lower()


@pytest.mark.asyncio
async def test_persist_verification_forces_honesty_flags():
    class _Sess:
        def __init__(self) -> None:
            self.added = None

        def add(self, row):
            self.added = row

        async def flush(self):
            return None

    session = _Sess()
    row = await persist_verification_run(
        session,
        scan_id=__import__("uuid").uuid4(),
        remediation_run_id=__import__("uuid").uuid4(),
        evaluated_revision="abc",
        issue_outcome=OUTCOME_FIXED,
        operational_status="ok",
        detail="x",
        verification_method=VERIFICATION_METHOD_HEURISTIC,
        fully_verified=True,  # attempt to lie
        is_full_rescan=True,
    )
    assert row.fully_verified is False
    assert row.is_full_rescan is False
    assert row.verification_method == VERIFICATION_METHOD_HEURISTIC
