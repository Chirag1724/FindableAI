"""Shared pytest fixtures for FindableAI backend tests."""

from __future__ import annotations

import os

import pytest

from app.core.config import settings

_PLACEHOLDER_KEY = "test-placeholder-groq-key"


def _flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


@pytest.fixture(autouse=True)
def isolate_tests_from_real_providers_and_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must never spend real provider quota or enqueue real durable jobs.

    - Real provider keys from the developer's ``.env`` are replaced by a non-secret
      placeholder so ``create_scan`` is not 503 but no live request can authenticate.
      Set ``FINDABLE_LIVE_LLM=1`` to opt a run into real credentials.
    - ``DURABLE_SCAN_JOBS`` defaults to False so API tests do not insert ``scan_jobs``
      rows into the developer's PostgreSQL (a running worker would then execute them).
      PG integration tests (``FINDABLE_PG_INTEGRATION=1``) use their disposable DB and
      keep the durable path. Tests may still override either setting explicitly.
    """
    if not _flag("FINDABLE_LIVE_LLM"):
        for name in (
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "NVIDIA_API_KEY",
            "ANTHROPIC_API_KEY",
        ):
            monkeypatch.setattr(settings, name, "")
        monkeypatch.setattr(settings, "GROQ_API_KEY", _PLACEHOLDER_KEY)
    if not _flag("FINDABLE_PG_INTEGRATION"):
        monkeypatch.setattr(settings, "DURABLE_SCAN_JOBS", False)
