"""Each provider uses only its own key; foreign prefixes are rejected, never sent."""

from __future__ import annotations

import pytest

from app.core.llm import LLMClient
from app.core.llm_credentials import (
    credential_for_provider,
    key_issuer,
    key_matches_provider,
    llm_credentials_for_real_scan,
)


def test_known_prefixes() -> None:
    assert key_issuer("gsk_abc") == "groq"
    assert key_issuer("xai-abc") == "xai"
    assert key_issuer("sk-or-v1-abc") == "openrouter"
    assert key_issuer("sk-ant-abc") == "anthropic"
    assert key_issuer("sk-abc") == "openai"
    assert key_issuer("AIzaSyAbc") == "gemini"
    assert key_issuer("test-gemini-key") is None  # unknown prefix, accepted as-is


def test_xai_key_rejected_for_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    ok, reason = key_matches_provider("groq", "xai-not-a-groq-key")
    assert ok is False
    assert "xai" in reason
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "xai-not-a-groq-key")
    # Neither the explicit override nor the configured key is usable for Groq.
    assert credential_for_provider("groq", explicit_key="xai-not-a-groq-key") is None
    assert credential_for_provider("groq") is None


def test_gsk_key_accepted_for_groq_rejected_for_openai() -> None:
    assert key_matches_provider("groq", "gsk_test123") == (True, "ok")
    ok, reason = key_matches_provider("openai", "gsk_test123")
    assert ok is False
    assert "groq" in reason


def test_unknown_prefix_placeholder_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test fixtures use non-issuer prefixes so they still build a Groq endpoint.
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "test-placeholder-groq-key")
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.OPENAI_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.NVIDIA_API_KEY", "")
    client = LLMClient()
    chain = client._get_provider_chain()
    assert chain[0].name == "groq"
    assert chain[0].api_key == "test-placeholder-groq-key"


def test_xai_in_groq_env_disables_groq_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "xai-not-for-groq")
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.OPENAI_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.NVIDIA_API_KEY", "")
    client = LLMClient()
    with pytest.raises(RuntimeError, match=r"(?i)either.*key.*is required"):
        client._get_provider_chain()


def test_llm_credentials_for_real_scan_mentions_rejected_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.config.settings.GROQ_API_KEY", "xai-wrong")
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.OPENAI_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.NVIDIA_API_KEY", "")
    monkeypatch.setattr("app.core.config.settings.ANTHROPIC_API_KEY", "")
    ok, reason = llm_credentials_for_real_scan()
    assert ok is False
    assert "xai" in reason.lower() or "Rejected" in reason
    assert "xai-wrong" not in reason  # never echo the key
