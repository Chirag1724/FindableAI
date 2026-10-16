"""Budget controls for remediation-adjacent LLM usage.

Apply / verify / GitHub mutation paths are deterministic and must not invoke
providers. Any optional LLM re-evaluation during remediation must reserve
against a scan-scoped ``BudgetGuard`` first — exhaustion blocks the call and
must never trigger a GitHub mutation.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.budget import BudgetGuard, LLMBudgetExceededError, default_scan_budget
from app.core.config import settings

logger = logging.getLogger(__name__)


def budget_guard_from_scan_usage(
    *,
    llm_calls_made: int | None,
    usd_used: float | None = None,
) -> BudgetGuard:
    """Restore a scan-scoped guard from persisted usage counters."""
    used = int(llm_calls_made or 0)
    usd = float(usd_used or 0.0)
    guard = default_scan_budget(limit=settings.MAX_LLM_CALLS_PER_SCAN)
    guard.restore_used(used)
    if usd > 0:
        guard.restore_usd(usd)
    return guard


async def reserve_remediation_llm_call(guard: BudgetGuard) -> int:
    """Reserve one provider call for remediation-adjacent LLM work.

    Raises ``LLMBudgetExceededError`` before any provider invocation.
    """
    return await guard.reserve()


def assert_github_mutation_not_tied_to_llm_budget(
    *,
    would_call_llm: bool,
    guard: BudgetGuard | None,
) -> None:
    """Fail closed: never open a PR as a side-effect of an LLM budget path.

    GitHub apply is allowed without a reservation when ``would_call_llm`` is
    False (deterministic patch apply). If an LLM call is required first,
    the caller must reserve successfully before mutation.
    """
    if not would_call_llm:
        return
    if guard is None:
        raise LLMBudgetExceededError(
            limit=0,
            used=0,
            remaining=0,
            attempted=1,
            reason="call_limit",
            message="Remediation LLM required but no BudgetGuard was provided",
        )
    if guard.remaining <= 0:
        raise LLMBudgetExceededError(
            limit=guard.limit,
            used=guard.used,
            remaining=0,
            attempted=guard.used + 1,
            reason="call_limit",
            usd_used=guard.usd_used,
            usd_cap=guard.usd_cap,
            message="Remediation LLM budget exhausted; GitHub mutation blocked",
        )


def scan_budget_exhausted(scan_row: Any) -> bool:
    """True when persisted scan LLM usage has hit the configured cap."""
    used = int(getattr(scan_row, "llm_calls_made", 0) or 0)
    return used >= int(settings.MAX_LLM_CALLS_PER_SCAN)
