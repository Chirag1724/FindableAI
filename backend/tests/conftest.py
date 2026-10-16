"""Shared pytest fixtures for FindableAI backend tests."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.llm_credentials import configured_llm_providers


@pytest.fixture(autouse=True)
def ensure_test_llm_credential_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ordinary tests use a non-secret placeholder key so create_scan is not 503.

    Real provider calls still fail closed without a valid key / with mocked clients.
    Tests that assert missing-credential behavior must clear keys explicitly.
    """
    if configured_llm_providers():
        return
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-placeholder-groq-key")
