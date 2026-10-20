"""Thread-safe round-robin API key pool with automatic 429 rate-limit cooldown.

Allows concurrent LLM requests to load-balance across multiple keys, tripling
the free-tier token bandwidth (TPM/RPM) and providing transparent failover.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time

from app.core.llm_credentials import provider_api_keys

logger = logging.getLogger(__name__)


def _hash_key(key: str) -> str:
    """Safe key identifier for logs (first 8 chars of sha256)."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8] if key else "none"


class KeyPool:
    """Rotates across multiple API keys per provider with active cooldown tracking."""

    def __init__(self) -> None:
        self._indices: dict[str, int] = {}
        self._cooldowns: dict[str, float] = {}  # key -> monotonic expiry
        self._lock = asyncio.Lock()
        self._thread_lock = threading.Lock()

    def _get_configured_keys(self, provider: str) -> list[str]:
        return provider_api_keys(provider)

    async def get_next_key(self, provider: str, explicit_key: str | None = None) -> str | None:
        """Select the next available key for provider using round-robin.

        If explicit_key is provided and not in cooldown, returns it.
        Otherwise picks the next healthy key from the provider's key pool.
        """
        p = (provider or "").strip().lower()
        now = time.monotonic()

        # If caller injected an explicit key, use it unless rate-limited
        if explicit_key:
            cooldown = self._cooldowns.get(explicit_key, 0.0)
            if now >= cooldown:
                return explicit_key

        keys = self._get_configured_keys(p)
        if not keys:
            return explicit_key

        if len(keys) == 1:
            return keys[0]

        async with self._lock:
            # Clean expired cooldowns
            expired = [k for k, exp in self._cooldowns.items() if now >= exp]
            for k in expired:
                del self._cooldowns[k]

            # Find healthy keys
            healthy = [k for k in keys if k not in self._cooldowns]
            if not healthy:
                # All keys in cooldown: pick the one closest to expiry
                healthy = [min(keys, key=lambda k: self._cooldowns.get(k, 0.0))]

            idx = self._indices.get(p, 0) % len(healthy)
            chosen = healthy[idx]
            self._indices[p] = (idx + 1) % len(healthy)
            return chosen

    async def mark_rate_limited(
        self,
        provider: str,
        key: str,
        retry_after: float = 20.0,
    ) -> None:
        """Put a key into temporary cooldown so subsequent calls use remaining keys."""
        if not key:
            return
        cooldown_sec = max(5.0, min(120.0, float(retry_after or 20.0)))
        async with self._lock:
            self._cooldowns[key] = time.monotonic() + cooldown_sec
        logger.warning(
            "key_pool_rate_limited provider=%s key_id=%s cooldown=%.1fs",
            provider,
            _hash_key(key),
            cooldown_sec,
        )

    def get_next_key_sync(self, provider: str, explicit_key: str | None = None) -> str | None:
        """Synchronously select the next available key for provider using round-robin."""
        p = (provider or "").strip().lower()
        now = time.monotonic()

        if explicit_key:
            cooldown = self._cooldowns.get(explicit_key, 0.0)
            if now >= cooldown:
                return explicit_key

        keys = self._get_configured_keys(p)
        if not keys:
            return explicit_key

        if len(keys) == 1:
            return keys[0]

        with self._thread_lock:
            expired = [k for k, exp in self._cooldowns.items() if now >= exp]
            for k in expired:
                del self._cooldowns[k]

            healthy = [k for k in keys if k not in self._cooldowns]
            if not healthy:
                healthy = [min(keys, key=lambda k: self._cooldowns.get(k, 0.0))]

            idx = self._indices.get(p, 0) % len(healthy)
            chosen = healthy[idx]
            self._indices[p] = (idx + 1) % len(healthy)
            return chosen

    def mark_rate_limited_sync(
        self,
        provider: str,
        key: str,
        retry_after: float = 20.0,
    ) -> None:
        """Put a key into temporary cooldown (synchronously)."""
        if not key:
            return
        cooldown_sec = max(5.0, min(120.0, float(retry_after or 20.0)))
        with self._thread_lock:
            self._cooldowns[key] = time.monotonic() + cooldown_sec
        logger.warning(
            "key_pool_rate_limited provider=%s key_id=%s cooldown=%.1fs",
            provider,
            _hash_key(key),
            cooldown_sec,
        )

    def has_alternative_key(self, provider: str, current_key: str) -> bool:
        """Check if another healthy key exists in the pool for instant failover."""
        keys = self._get_configured_keys(provider)
        if len(keys) <= 1:
            return False
        now = time.monotonic()
        other_healthy = [k for k in keys if k != current_key and now >= self._cooldowns.get(k, 0.0)]
        return len(other_healthy) > 0


# Process-wide singleton key pool
KEY_POOL = KeyPool()

__all__ = ["KEY_POOL", "KeyPool", "_hash_key"]
