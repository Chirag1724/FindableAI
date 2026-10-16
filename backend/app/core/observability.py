"""Scan-scoped provider/batch observability counters (concurrency-safe).

Counters are monotonic and never decrease. They accompany BudgetGuard so every
reported provider attempt corresponds to a reserved BudgetGuard unit.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScanObservability:
    """In-memory ledger for one scan execution (shared by all LLMClients)."""

    primary_model: str | None = None
    fallback_provider_used: bool = False
    provider_successes: int = 0
    provider_failures: int = 0
    batches_total: int | None = None
    batches_queued: int = 0
    batches_started: int = 0
    batches_completed: int = 0
    batches_failed: int = 0
    batches_retrying: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def set_primary_model(self, model: str | None) -> None:
        if not model:
            return
        async with self._lock:
            if self.primary_model is None:
                self.primary_model = model

    async def mark_fallback_used(self) -> None:
        async with self._lock:
            self.fallback_provider_used = True

    async def record_provider_success(self, *, tokens_in: int | None = None, tokens_out: int | None = None) -> None:
        async with self._lock:
            self.provider_successes += 1
            if tokens_in is not None:
                self.tokens_in = (self.tokens_in or 0) + max(0, int(tokens_in))
            if tokens_out is not None:
                self.tokens_out = (self.tokens_out or 0) + max(0, int(tokens_out))

    async def record_provider_failure(self) -> None:
        async with self._lock:
            self.provider_failures += 1

    async def init_batches(self, total: int) -> None:
        async with self._lock:
            total_i = max(0, int(total))
            # Unknown stays unknown until established; once set, never shrink.
            if self.batches_total is None or total_i > self.batches_total:
                self.batches_total = total_i
            self.batches_queued = max(self.batches_queued, total_i)

    async def batch_started(self) -> None:
        async with self._lock:
            self.batches_started += 1
            if self.batches_queued > 0:
                self.batches_queued = max(0, self.batches_queued - 1)

    async def batch_completed(self) -> None:
        async with self._lock:
            self.batches_completed += 1
            if self.batches_retrying > 0:
                self.batches_retrying = max(0, self.batches_retrying - 1)

    async def batch_failed(self) -> None:
        async with self._lock:
            self.batches_failed += 1
            if self.batches_retrying > 0:
                self.batches_retrying = max(0, self.batches_retrying - 1)

    async def batch_retrying(self) -> None:
        async with self._lock:
            self.batches_retrying += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "primary_model": self.primary_model,
            "fallback_provider_used": self.fallback_provider_used,
            "provider_successes": self.provider_successes,
            "provider_failures": self.provider_failures,
            "provider_attempts_completed": self.provider_successes + self.provider_failures,
            "batches_total": self.batches_total,
            "batches_queued": self.batches_queued,
            "batches_started": self.batches_started,
            "batches_completed": self.batches_completed,
            "batches_failed": self.batches_failed,
            "batches_retrying": self.batches_retrying,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }


__all__ = ["ScanObservability"]
