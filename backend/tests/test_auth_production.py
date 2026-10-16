"""Production authentication fail-closed behavior."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import auth as auth_mod
from app.core.config import settings
from app.main import app


def test_assert_production_security_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "API_KEY", "")
    with pytest.raises(RuntimeError, match="API_KEY"):
        auth_mod.assert_production_security_config()


def test_assert_production_security_ok_with_key(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "API_KEY", "prod-secret")
    auth_mod.assert_production_security_config()


def test_non_production_allows_empty_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "API_KEY", "")
    auth_mod.assert_production_security_config()


@pytest.mark.asyncio
async def test_production_empty_key_rejects_mutating_requests(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "API_KEY", "")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/scans",
            json={"url": "https://example.com", "max_pages": 1},
        )
        assert resp.status_code == 503
        assert "API_KEY" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ready_not_ready_when_production_missing_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "API_KEY", "")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "not_ready"
        assert data["auth"] == "misconfigured"


@pytest.mark.asyncio
async def test_valid_and_invalid_credentials_cover_scans(monkeypatch):
    secret = "unit-test-api-key"
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "API_KEY", secret)
    monkeypatch.setattr(settings, "DURABLE_SCAN_JOBS", False)
    monkeypatch.setattr(settings, "ALLOW_SYNTHETIC_DEMO", False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.post(
            "/api/v1/scans",
            json={"url": "https://example.com", "max_pages": 1},
        )
        assert missing.status_code == 401

        invalid = await client.post(
            "/api/v1/scans",
            json={"url": "https://example.com", "max_pages": 1},
            headers={"X-API-Key": "nope"},
        )
        assert invalid.status_code == 401

        # Valid key may still fail SSRF/DB depending on env; auth must pass first.
        # Use allow path: non-prod + example.com is public.
        valid = await client.post(
            "/api/v1/scans",
            json={"url": "https://example.com", "max_pages": 1},
            headers={"X-API-Key": secret},
        )
        assert valid.status_code in (202, 400, 503)
        assert valid.status_code != 401
