"""Scan-scoped LLM call budget (P2-4.2).

One ``BudgetGuard`` per scan. Shared by every ``LLMClient`` / engine that
belongs to that scan. Reservation is atomic and happens *before* any
provider invocation; the lock is never held during network I/O.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMBudgetExceededError(Exception):
    """Raised when a scan's hard LLM call limit would be exceeded.

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
        # Phase 0 compatibility aliases
        self.calls_made = resolved_used
        self.max_calls = resolved_limit

        text = message or (
            f"LLM budget exhausted: {resolved_used}/{resolved_limit} calls used "
            f"(limit={resolved_limit}, remaining={resolved_remaining}, "
            f"attempted={resolved_attempted})"
        )
        super().__init__(text)

    def as_dict(self) -> dict[str, int]:
        return {
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
            "attempted": self.attempted,
        }


# Phase 0 public name — same exception.
BudgetExhausted = LLMBudgetExceededError


class BudgetGuard:
    """Async-safe, scan-scoped hard cap on LLM provider invocations.

    Semantics:
    - ``reserve()`` atomically increments ``used`` when ``used < limit``.
    - Reservation commits immediately (no refund on later cancel/failure).
    - If reservation fails, the provider is never invoked for that attempt.
    - After a successful ``reserve()``, the unit counts even if the provider
      raises or the task is cancelled before/during the provider await.
    """

    def __init__(self, limit: int | None = None) -> None:
        resolved = settings.MAX_LLM_CALLS_PER_SCAN if limit is None else limit
        if not isinstance(resolved, int) or isinstance(resolved, bool):
            raise ValueError("BudgetGuard limit must be an int >= 0")
        if resolved < 0:
            raise ValueError("BudgetGuard limit must be >= 0")
        self._limit = resolved
        self._used = 0
        self._lock = asyncio.Lock()

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(0, self._limit - self._used)

    def snapshot(self) -> Mapping[str, int]:
        """Safe observability snapshot (no secrets)."""
        return {
            "limit": self._limit,
            "used": self._used,
            "remaining": self.remaining,
        }

    def __repr__(self) -> str:
        return f"BudgetGuard(limit={self._limit}, used={self._used})"

    async def reserve(self) -> int:
        """Atomically reserve one provider-call unit.

        Returns the 1-based call number after reservation.
        Raises ``LLMBudgetExceededError`` if the scan has no remaining units.
        The lock is released before the caller awaits the provider.
        """
        async with self._lock:
            if self._used >= self._limit:
                logger.info(
                    "llm_budget_exhausted limit=%s used=%s remaining=0 attempted=%s",
                    self._limit,
                    self._used,
                    self._used + 1,
                )
                raise LLMBudgetExceededError(
                    limit=self._limit,
                    used=self._used,
                    remaining=0,
                    attempted=self._used + 1,
                )
            self._used += 1
            call_number = self._used
            logger.info(
                "llm_budget_reserved call=%s/%s remaining=%s",
                call_number,
                self._limit,
                self.remaining,
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
