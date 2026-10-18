import time
from unittest.mock import patch

import pytest

from app.core.key_pool import KeyPool, _hash_key
from app.core.provider_throttle import get_provider_throttle


def test_hash_key():
    assert _hash_key("") == "none"
    assert len(_hash_key("gsk_test1234567890")) == 8


@pytest.mark.asyncio
async def test_key_pool_round_robin():
    pool = KeyPool()
    keys = ["gsk_key_alpha", "gsk_key_beta", "gsk_key_gamma"]

    with patch.object(pool, "_get_configured_keys", return_value=keys):
        # Async rotation
        k1 = await pool.get_next_key("groq")
        k2 = await pool.get_next_key("groq")
        k3 = await pool.get_next_key("groq")
        k4 = await pool.get_next_key("groq")

        assert [k1, k2, k3, k4] == [
            "gsk_key_alpha",
            "gsk_key_beta",
            "gsk_key_gamma",
            "gsk_key_alpha",
        ]

        # Sync rotation
        s1 = pool.get_next_key_sync("groq")
        s2 = pool.get_next_key_sync("groq")
        assert [s1, s2] == ["gsk_key_beta", "gsk_key_gamma"]


@pytest.mark.asyncio
async def test_key_pool_single_key_fallback():
    pool = KeyPool()
    with patch.object(pool, "_get_configured_keys", return_value=["gsk_single"]):
        assert await pool.get_next_key("groq") == "gsk_single"
        assert pool.get_next_key_sync("groq") == "gsk_single"
        assert not pool.has_alternative_key("groq", "gsk_single")


@pytest.mark.asyncio
async def test_key_pool_cooldown_and_failover():
    pool = KeyPool()
    keys = ["gsk_key_1", "gsk_key_2"]

    with patch.object(pool, "_get_configured_keys", return_value=keys):
        assert pool.has_alternative_key("groq", "gsk_key_1")

        # Mark key 1 rate-limited for 10 seconds
        await pool.mark_rate_limited("groq", "gsk_key_1", retry_after=10.0)

        # Rotation should only yield key 2
        for _ in range(3):
            assert await pool.get_next_key("groq") == "gsk_key_2"
            assert pool.get_next_key_sync("groq") == "gsk_key_2"

        # Key 1 has no alternatives now since it's the only remaining healthy key
        assert not pool.has_alternative_key("groq", "gsk_key_2")

        # Once key 1 cooldown is cleared, both keys are healthy again
        pool._cooldowns.clear()
        assert pool.has_alternative_key("groq", "gsk_key_1")


def test_key_pool_all_in_cooldown_recovers_safely():
    pool = KeyPool()
    keys = ["gsk_key_1", "gsk_key_2"]

    with patch.object(pool, "_get_configured_keys", return_value=keys):
        now = time.monotonic()
        # Key 1 expires in 5s, Key 2 expires in 20s
        pool._cooldowns["gsk_key_1"] = now + 5.0
        pool._cooldowns["gsk_key_2"] = now + 20.0

        # Should choose key 1 because it's closest to expiry
        chosen = pool.get_next_key_sync("groq")
        assert chosen == "gsk_key_1"


def test_isolated_groq_throttles():
    key1 = "gsk_first_unique_key_123"
    key2 = "gsk_second_unique_key_456"

    t1 = get_provider_throttle("groq", key1)
    t2 = get_provider_throttle("groq", key2)

    assert t1 is not None
    assert t2 is not None
    # Each key gets its own throttle instance
    assert t1 is not t2
    # Same key gets the same throttle instance
    assert get_provider_throttle("groq", key1) is t1
