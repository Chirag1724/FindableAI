"""Per-provider async rate limiter for free-tier RPM/RPD caps.

One ``ProviderThrottle`` per provider name, shared process-wide.
Call ``await throttle.acquire()`` before every outbound LLM request.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class ProviderThrottle:
    """Sliding-window token bucket enforcing requests-per-minute."""

    rpm: int = 28
    _timestamps: list[float] = field(default_factory=list, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            cutoff = now - 60.0
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            if len(self._timestamps) >= self.rpm:
                wait = 60.0 - (now - self._timestamps[0]) + 0.15
                logger.info(
                    "provider_throttle waiting=%.1fs rpm=%s",
                    wait,
                    self.rpm,
                )
                # Release lock while sleeping so other providers aren't blocked.
                self._lock.release()
                try:
                    await asyncio.sleep(wait)
                finally:
                    await self._lock.acquire()
                now = time.monotonic()
                self._timestamps = [t for t in self._timestamps if t > now - 60.0]
            self._timestamps.append(now)


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


# Process-wide singletons — one per provider.
PROVIDER_THROTTLES: dict[str, ProviderThrottle] = {
    "groq": ProviderThrottle(rpm=28),
    "gemini": ProviderThrottle(rpm=14),
    "openai": ProviderThrottle(rpm=500),
}

DAILY_QUOTAS: dict[str, DailyQuota] = {
    "groq": DailyQuota(rpd=1000),
    "gemini": DailyQuota(rpd=1500),
    "openai": DailyQuota(rpd=10000),
}
