"""Scan-scoped LLM call budget (P2-4.2) with optional estimated-USD ceiling.

One ``BudgetGuard`` per scan. Shared by every ``LLMClient`` / engine that
belongs to that scan. Reservation is atomic and happens *before* any
provider invocation; the lock is never held during network I/O.

USD accounting uses ``LLM_ESTIMATED_USD_PER_CALL`` (not provider invoices).
When ``LLM_ENFORCE_USD_BUDGET`` is true, estimated spend is a hard stop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    from app.core.observability import ScanObservability

logger = logging.getLogger(__name__)

ReserveHook = Callable[[int, float], Awaitable[None]]

# Process-scoped completed-response cache so a live rerun of the same prompts
# can skip budget/provider without depending on a still-alive BudgetGuard.
# Inflight coalescing stays scan-scoped (per BudgetGuard).
_PROCESS_RESPONSE_CACHE: dict[str, Any] = {}
_PROCESS_RESPONSE_CACHE_MAX = 256


def clear_process_response_cache() -> None:
    """Drop process cache entries (tests / explicit reset)."""
    _PROCESS_RESPONSE_CACHE.clear()


def _store_process_response_cache(key: str, value: Any) -> None:
    _PROCESS_RESPONSE_CACHE[key] = value
    while len(_PROCESS_RESPONSE_CACHE) > _PROCESS_RESPONSE_CACHE_MAX:
        _PROCESS_RESPONSE_CACHE.pop(next(iter(_PROCESS_RESPONSE_CACHE)), None)


class LLMBudgetExceededError(Exception):
    """Raised when a scan's hard LLM call (or estimated USD) limit would be exceeded.

    Raised *before* the provider is invoked. Contains no secrets.
    """

    def __init__(
        self,
        calls_made: int | None = None,
        max_calls: int | None = None,
        *,
        limit: int | None = None,
        used: int | None = None,
        remaining: int | None = None,
        attempted: int | None = None,
        message: str | None = None,
        reason: str = "call_limit",
        usd_used: float | None = None,
        usd_cap: float | None = None,
    ) -> None:
        resolved_limit = limit if limit is not None else (max_calls if max_calls is not None else 0)
        resolved_used = used if used is not None else (calls_made if calls_made is not None else 0)
        if remaining is not None:
            resolved_remaining = remaining
        else:
            resolved_remaining = max(0, resolved_limit - resolved_used)
        resolved_attempted = attempted if attempted is not None else resolved_used + 1

        self.limit = resolved_limit
        self.used = resolved_used
        self.remaining = resolved_remaining
        self.attempted = resolved_attempted
        self.reason = reason
        self.usd_used = float(usd_used or 0.0)
        self.usd_cap = float(usd_cap or 0.0)
        # Phase 0 compatibility aliases
        self.calls_made = resolved_used
        self.max_calls = resolved_limit

        text = message or (
            f"LLM budget exhausted ({reason}): {resolved_used}/{resolved_limit} calls used "
            f"(limit={resolved_limit}, remaining={resolved_remaining}, "
            f"attempted={resolved_attempted}, usd_used={self.usd_used:.6f}, "
            f"usd_cap={self.usd_cap:.6f})"
        )
        super().__init__(text)

    def as_dict(self) -> dict[str, int | float | str]:
        return {
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
            "attempted": self.attempted,
            "reason": self.reason,
            "usd_used": self.usd_used,
            "usd_cap": self.usd_cap,
        }


# Phase 0 public name — same exception.
BudgetExhausted = LLMBudgetExceededError


class BudgetGuard:
    """Async-safe, scan-scoped hard cap on LLM provider invocations.

    Semantics:
    - ``reserve()`` atomically increments ``used`` when ``used < limit``.
    - Optionally enforces estimated USD via ``LLM_ENFORCE_USD_BUDGET``.
    - Reservation commits immediately (no refund on later cancel/failure).
    - If reservation fails, the provider is never invoked for that attempt.
    - After a successful ``reserve()``, the unit counts even if the provider
      raises or the task is cancelled before/during the provider await.
    - Optional ``on_reserve`` hook persists durable checkpoints *after* the
      in-memory reservation (never holds the lock during DB I/O).
    """

    def __init__(
        self,
        limit: int | None = None,
        *,
        initial_used: int = 0,
        initial_usd: float = 0.0,
        usd_cap: float | None = None,
        usd_per_call: float | None = None,
        enforce_usd: bool | None = None,
        on_reserve: ReserveHook | None = None,
        observability: ScanObservability | None = None,
    ) -> None:
        from app.core.observability import ScanObservability as _ScanObservability

        resolved = settings.MAX_LLM_CALLS_PER_SCAN if limit is None else limit
        if not isinstance(resolved, int) or isinstance(resolved, bool):
            raise ValueError("BudgetGuard limit must be an int >= 0")
        if resolved < 0:
            raise ValueError("BudgetGuard limit must be >= 0")
        if not isinstance(initial_used, int) or isinstance(initial_used, bool) or initial_used < 0:
            raise ValueError("BudgetGuard initial_used must be an int >= 0")
        if initial_usd < 0:
            raise ValueError("initial_usd must be >= 0")
        self._limit = resolved
        self._used = initial_used
        self._usd_used = float(initial_usd)
        self._usd_cap = float(settings.LLM_BUDGET_CAP_USD if usd_cap is None else usd_cap)
        self._usd_per_call = float(
            settings.LLM_ESTIMATED_USD_PER_CALL if usd_per_call is None else usd_per_call
        )
        self._enforce_usd = (
            bool(settings.LLM_ENFORCE_USD_BUDGET) if enforce_usd is None else bool(enforce_usd)
        )
        self._on_reserve = on_reserve
        self.observability = observability or _ScanObservability()
        self._lock = asyncio.Lock()
        # Scan-scoped duplicate-request guard: identical in-flight provider requests
        # (same model/schema/messages) share one future instead of two calls.
        self.inflight: dict[str, asyncio.Future[Any]] = {}
        self._inflight_lock = asyncio.Lock()
        # Completed identical requests reuse the prior result and skip budget.
        # Shared across scans in this process so a live rerun can cache-hit.
        self.response_cache = _PROCESS_RESPONSE_CACHE

    def restore_used(self, used: int) -> None:
        """Raise the used counter to at least ``used`` (never decreases)."""
        if not isinstance(used, int) or isinstance(used, bool) or used < 0:
            raise ValueError("used must be an int >= 0")
        if used > self._used:
            self._used = used

    def restore_usd(self, usd: float) -> None:
        """Raise estimated USD used to at least ``usd`` (never decreases)."""
        if usd < 0:
            raise ValueError("usd must be >= 0")
        if usd > self._usd_used:
            self._usd_used = float(usd)

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(0, self._limit - self._used)

    @property
    def usd_used(self) -> float:
        return self._usd_used

    @property
    def usd_cap(self) -> float:
        return self._usd_cap

    @property
    def enforce_usd(self) -> bool:
        return self._enforce_usd

    def snapshot(self) -> Mapping[str, int | float | bool | str | None]:
        """Safe observability snapshot (no secrets)."""
        base: dict[str, int | float | bool | str | None] = {
            "limit": self._limit,
            "used": self._used,
            "remaining": self.remaining,
            "usd_used": self._usd_used,
            "usd_cap": self._usd_cap,
            "usd_per_call": self._usd_per_call,
            "enforce_usd": self._enforce_usd,
            "cost_basis": "estimated",
        }
        base.update(self.observability.snapshot())
        return base

    def __repr__(self) -> str:
        return (
            f"BudgetGuard(limit={self._limit}, used={self._used}, "
            f"usd_used={self._usd_used:.6f}, enforce_usd={self._enforce_usd})"
        )

    async def reserve(self) -> int:
        """Atomically reserve one provider-call unit (and estimated USD).

        Returns the 1-based call number after reservation.
        Raises ``LLMBudgetExceededError`` if the scan has no remaining units.
        The lock is released before durable hooks and provider awaits.
        """
        async with self._lock:
            if self._used >= self._limit:
                logger.info(
                    "llm_budget_exhausted reason=call_limit limit=%s used=%s remaining=0 attempted=%s",
                    self._limit,
                    self._used,
                    self._used + 1,
                )
                raise LLMBudgetExceededError(
                    limit=self._limit,
                    used=self._used,
                    remaining=0,
                    attempted=self._used + 1,
                    reason="call_limit",
                    usd_used=self._usd_used,
                    usd_cap=self._usd_cap,
                )
            projected_usd = self._usd_used + self._usd_per_call
            if self._enforce_usd and projected_usd > self._usd_cap + 1e-12:
                logger.info(
                    "llm_budget_exhausted reason=usd_limit usd_used=%s usd_cap=%s per_call=%s",
                    self._usd_used,
                    self._usd_cap,
                    self._usd_per_call,
                )
                raise LLMBudgetExceededError(
                    limit=self._limit,
                    used=self._used,
                    remaining=self.remaining,
                    attempted=self._used + 1,
                    reason="usd_limit",
                    usd_used=self._usd_used,
                    usd_cap=self._usd_cap,
                    message=(
                        f"LLM estimated USD budget exhausted: "
                        f"{self._usd_used:.6f}/{self._usd_cap:.6f} "
                        f"(per_call={self._usd_per_call:.6f})"
                    ),
                )
            self._used += 1
            self._usd_used = projected_usd
            call_number = self._used
            usd_snapshot = self._usd_used
            logger.info(
                "llm_budget_reserved call=%s/%s remaining=%s usd_used=%.6f",
                call_number,
                self._limit,
                self.remaining,
                usd_snapshot,
            )

        if self._on_reserve is not None:
            try:
                await self._on_reserve(call_number, usd_snapshot)
            except Exception:
                logger.warning(
                    "llm_budget_durable_checkpoint_failed call=%s",
                    call_number,
                    exc_info=True,
                )
        return call_number


def default_scan_budget(*, limit: int | None = None) -> BudgetGuard:
    """Factory for a fresh scan-scoped guard (never a process singleton)."""
    return BudgetGuard(limit=limit)


__all__ = [
    "BudgetExhausted",
    "BudgetGuard",
    "LLMBudgetExceededError",
    "default_scan_budget",
]
