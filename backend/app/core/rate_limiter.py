"""Rate limiter supporting both client-IP sliding window and enterprise token-bucket (Phase 3)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Sliding Window Rate Limiter (IP-based endpoint protection)
# ---------------------------------------------------------------------------

class SlidingWindowRateLimiter:
    """In-memory thread-safe sliding window rate limiter."""

    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(
        self, key: str, max_requests: int, window_seconds: int = 60
    ) -> tuple[bool, int]:
        """Checks if the given key has exceeded max_requests in the trailing window_seconds.

        Returns (allowed: bool, retry_after_seconds: int).
        """
        now = time.monotonic()
        cutoff = now - window_seconds

        async with self._lock:
            timestamps = self._requests[key]
            # Prune timestamps older than window
            valid_timestamps = [t for t in timestamps if t > cutoff]
            self._requests[key] = valid_timestamps

            if len(valid_timestamps) >= max_requests:
                oldest = valid_timestamps[0]
                retry_after = max(1, int(window_seconds - (now - oldest)))
                return False, retry_after

            valid_timestamps.append(now)
            return True, 0


limiter = SlidingWindowRateLimiter()


def rate_limit(max_requests: int, window_seconds: int = 60, bucket: str = "general") -> Callable:
    """FastAPI dependency factory enforcing rate limits per client IP."""

    async def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED or settings.ENVIRONMENT == "test":
            return

        client_ip = request.client.host if request.client else "unknown"
        key = f"{bucket}:{client_ip}"

        allowed, retry_after = await limiter.is_allowed(key, max_requests, window_seconds)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {bucket}. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency


# Standard preconfigured dependencies
rate_limit_scans = rate_limit(
    max_requests=settings.RATE_LIMIT_SCANS_PER_MINUTE,
    window_seconds=60,
    bucket="scans",
)
rate_limit_mutating = rate_limit(
    max_requests=30,
    window_seconds=60,
    bucket="mutating",
)


# ---------------------------------------------------------------------------
# 2. Token-Bucket Rate Limiter (Organization / Scoped API Key Multi-Tenancy)
# ---------------------------------------------------------------------------

@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


class TokenBucket:
    """In-memory thread-safe token bucket rate limiter."""

    def __init__(self, capacity: int, refill_rate_per_sec: float) -> None:
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill_rate = refill_rate_per_sec
        self.last_refill = time.monotonic()
        self.lock = asyncio.Lock()

    def _refill(self, now: float) -> None:
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

    async def consume(self, cost: float = 1.0) -> tuple[bool, int, int]:
        async with self.lock:
            now = time.monotonic()
            self._refill(now)
            if self.tokens >= cost:
                self.tokens -= cost
                remaining = int(self.tokens)
                return True, remaining, 0
            else:
                needed = cost - self.tokens
                reset_sec = max(1, int(needed / self.refill_rate)) if self.refill_rate > 0 else 60
                return False, 0, reset_sec


class RateLimiterRegistry:
    """Registry maintaining token buckets keyed by tenant or API key."""

    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()

    async def check(
        self,
        identifier: str,
        limit_per_min: int,
        cost: int = 1,
    ) -> RateLimitResult:
        if limit_per_min <= 0:
            return RateLimitResult(allowed=True, limit=0, remaining=999, reset_seconds=0)

        bucket_key = f"{identifier}:{limit_per_min}"
        if bucket_key not in self._buckets:
            async with self._lock:
                if bucket_key not in self._buckets:
                    refill_rate = float(limit_per_min) / 60.0
                    self._buckets[bucket_key] = TokenBucket(
                        capacity=limit_per_min, refill_rate_per_sec=refill_rate
                    )

        bucket = self._buckets[bucket_key]
        allowed, remaining, reset_sec = await bucket.consume(cost)
        return RateLimitResult(
            allowed=allowed,
            limit=limit_per_min,
            remaining=remaining,
            reset_seconds=reset_sec,
        )

    def reset_for_test(self) -> None:
        self._buckets.clear()


limiter_registry = RateLimiterRegistry()


async def enforce_rate_limit(
    identifier: str,
    limit_per_min: int,
) -> RateLimitResult:
    """Enforces rate limit for the given identifier; raises HTTP 429 if exceeded."""
    res = await limiter_registry.check(identifier, limit_per_min)
    if not res.allowed:
        logger.warning(
            "rate_limit_exceeded identifier=%s limit=%d reset_sec=%d",
            identifier,
            res.limit,
            res.reset_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {res.limit} requests per minute.",
            headers={
                "Retry-After": str(res.reset_seconds),
                "X-RateLimit-Limit": str(res.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(res.reset_seconds),
            },
        )
    return res
