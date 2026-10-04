import asyncio
import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.core.config import settings


class SlidingWindowRateLimiter:
    """
    In-memory thread-safe sliding window rate limiter.
    Zero external dependencies required (Standard Library first).
    """

    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str, max_requests: int, window_seconds: int = 60) -> tuple[bool, int]:
        """
        Checks if the given key has exceeded max_requests in the trailing window_seconds.
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
    """
    FastAPI dependency factory enforcing rate limits per client IP.
    """
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
