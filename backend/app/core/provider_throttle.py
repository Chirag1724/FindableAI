"""Per-provider async pacing for free-tier RPM/TPM caps.

One ``ProviderThrottle`` per provider name, shared process-wide. Call
``await throttle.acquire(tokens)`` before every outbound LLM request. Pacing is
an *estimate* (prompt chars / 4 + max_tokens, the same quantity Groq calls
"Requested"); HTTP 429 handling in ``LLMClient`` remains the backstop.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


def estimate_request_tokens(messages: list[dict[str, str]], max_tokens: int) -> int:
    """Rough tokens a provider will reserve for a request (prompt + completion cap)."""
    chars = sum(len(str(m.get("content") or "")) for m in messages)
    return int(chars / 4) + 8 * max(1, len(messages)) + max(0, int(max_tokens))


@dataclass
class ProviderThrottle:
    """Sliding 60s window enforcing requests-per-minute and estimated tokens-per-minute."""

    rpm: int = 28
    tpm: int | None = None  # None = no token pacing
    _requests: list[float] = field(default_factory=list, repr=False)
    _tokens: list[tuple[float, int]] = field(default_factory=list, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        self._requests = [t for t in self._requests if t > cutoff]
        self._tokens = [(t, n) for t, n in self._tokens if t > cutoff]

    def _wait_needed(self, now: float, tokens: int) -> float:
        wait = 0.0
        if len(self._requests) >= self.rpm:
            wait = max(wait, 60.0 - (now - self._requests[0]) + 0.15)
        if self.tpm is not None and tokens > 0:
            used = sum(n for _, n in self._tokens)
            if used + tokens > self.tpm and self._tokens:
                # Drop oldest entries until the request fits; wait for the last one dropped.
                remaining = used
                for t, n in self._tokens:
                    remaining -= n
                    if remaining + tokens <= self.tpm:
                        wait = max(wait, 60.0 - (now - t) + 0.15)
                        break
                else:
                    wait = max(wait, 60.0 - (now - self._tokens[-1][0]) + 0.15)
        return max(0.0, wait)

    async def acquire(self, tokens: int = 0) -> float:
        """Block until a request of ``tokens`` fits the window. Returns seconds waited."""
        waited = 0.0
        async with self._lock:
            while True:
                now = time.monotonic()
                self._prune(now)
                wait = self._wait_needed(now, tokens)
                if wait <= 0.0 or (self.tpm is not None and tokens > self.tpm and not self._tokens):
                    # Single oversized request: let the provider decide (429 → classified).
                    self._requests.append(now)
                    if tokens > 0:
                        self._tokens.append((now, int(tokens)))
                    return waited
                logger.info(
                    "provider_throttle waiting=%.1fs rpm=%s tpm=%s est_tokens=%s",
                    wait,
                    self.rpm,
                    self.tpm,
                    tokens,
                )
                # Release the lock while sleeping so other providers are not blocked.
                self._lock.release()
                try:
                    await asyncio.sleep(wait)
                finally:
                    await self._lock.acquire()
                waited += wait

    def record_actual(self, tokens: int) -> None:
        """Replace the latest estimate with the provider-reported usage (best effort)."""
        if not self._tokens or tokens <= 0:
            return
        t, _ = self._tokens[-1]
        self._tokens[-1] = (t, int(tokens))


@dataclass
class DailyQuota:
    """Simple per-provider requests-per-day guard."""

    rpd: int = 1000
    _count: int = field(default=0, repr=False)
    _reset_date: str = field(default="", repr=False)

    def check_and_increment(self) -> bool:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if today != self._reset_date:
            self._count = 0
            self._reset_date = today
        if self._count >= self.rpd:
            return False
        self._count += 1
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.rpd - self._count)


# Process-wide singletons — one per provider. Groq free tier: 30 RPM / 8K TPM
# (per model; one conservative shared budget here). Configurable via settings.
PROVIDER_THROTTLES: dict[str, ProviderThrottle] = {
    "groq": ProviderThrottle(
        rpm=int(getattr(settings, "GROQ_RPM_LIMIT", 28)),
        tpm=int(getattr(settings, "GROQ_TPM_LIMIT", 8000)) or None,
    ),
    "gemini": ProviderThrottle(rpm=14),
    "openai": ProviderThrottle(rpm=500),
}

DAILY_QUOTAS: dict[str, DailyQuota] = {
    "groq": DailyQuota(rpd=1000),
    "gemini": DailyQuota(rpd=1500),
    "openai": DailyQuota(rpd=10000),
}

__all__ = [
    "DAILY_QUOTAS",
    "PROVIDER_THROTTLES",
    "DailyQuota",
    "ProviderThrottle",
    "estimate_request_tokens",
]
