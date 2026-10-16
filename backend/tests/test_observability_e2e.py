"""Targeted tests for durable observability, credentials fail-closed, and job status."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.budget import BudgetGuard, LLMBudgetExceededError
from app.core.config import settings
from app.core.observability import ScanObservability
from app.main import app
from app.orchestration.scan_persistence import observability_from_budget


@pytest.mark.asyncio
async def test_observability_counters_concurrent_safe():
    obs = ScanObservability()
    await obs.init_batches(10)

    async def worker(i: int) -> None:
        await obs.batch_started()
        if i % 3 == 0:
            await obs.batch_failed()
        else:
            await obs.batch_completed()
        await obs.record_provider_success() if i % 2 == 0 else await obs.record_provider_failure()

    await asyncio.gather(*[worker(i) for i in range(10)])
    snap = obs.snapshot()
    assert snap["batches_total"] == 10
    assert snap["batches_started"] == 10
    assert snap["batches_completed"] + snap["batches_failed"] == 10
    assert snap["provider_successes"] + snap["provider_failures"] == 10
    # Unknown totals must not shrink once established.
    await obs.init_batches(5)
    assert obs.snapshot()["batches_total"] == 10


@pytest.mark.asyncio
async def test_budget_exhaustion_records_no_false_success():
    guard = BudgetGuard(limit=2, usd_cap=1.0, usd_per_call=0.01, enforce_usd=True)
    await guard.reserve()
    await guard.reserve()
    with pytest.raises(LLMBudgetExceededError) as exc:
        await guard.reserve()
    assert exc.value.reason == "call_limit"
    assert guard.used == 2
    assert guard.observability.provider_successes == 0


def test_observability_from_budget_labels_estimate():
    guard = BudgetGuard(limit=5, initial_used=2, initial_usd=0.0002)
    fields = observability_from_budget(guard)
    assert fields["cost_basis"] == "estimated"
    assert fields["llm_usd_provider_reported"] is None
    assert abs(float(fields["llm_usd_estimated"]) - 0.0002) < 1e-9


@pytest.mark.asyncio
async def test_create_scan_fails_closed_without_llm_credentials(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_SYNTHETIC_DEMO", False)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/scans",
            json={"url": "https://example.com", "max_pages": 1},
        )
        assert resp.status_code == 503
        detail = resp.json().get("detail", "")
        assert "LLM" in str(detail) or "credential" in str(detail).lower()


@pytest.mark.asyncio
async def test_job_status_unauthorized_when_api_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", "secret-test-key")
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "dummy")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Unknown scan still requires auth when API_KEY set.
        resp = await client.get(f"/api/v1/scans/scan_{uuid.uuid4().hex}/job")
        assert resp.status_code == 401

        resp_ok_auth_missing_scan = await client.get(
            f"/api/v1/scans/scan_{uuid.uuid4().hex}/job",
            headers={"X-API-Key": "secret-test-key"},
        )
        # 404 when durable lookup works; 503 if local DATABASE_URL is unreachable.
        assert resp_ok_auth_missing_scan.status_code in (404, 503)


@pytest.mark.asyncio
async def test_mock_real_separation_synthetic_flag(monkeypatch):
    """ALLOW_SYNTHETIC_DEMO=false must not invent success without credentials."""
    from app.core.llm_credentials import llm_credentials_for_real_scan

    monkeypatch.setattr(settings, "ALLOW_SYNTHETIC_DEMO", False)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(settings, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    ok, reason = llm_credentials_for_real_scan()
    assert ok is False
    assert "ALLOW_SYNTHETIC_DEMO" in reason or "credential" in reason.lower() or "GROQ" in reason
