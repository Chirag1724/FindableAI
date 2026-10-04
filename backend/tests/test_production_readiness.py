import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.rate_limiter import SlidingWindowRateLimiter
from app.main import app


@pytest.mark.asyncio
async def test_security_headers_and_request_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        headers = resp.headers
        assert "x-request-id" in headers
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("x-frame-options") == "DENY"
        assert headers.get("x-xss-protection") == "1; mode=block"
        assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_health_check_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert data["service"] == settings.PROJECT_NAME
        assert data["version"] == settings.VERSION
        assert "database" in data


@pytest.mark.asyncio
async def test_api_key_auth_enforcement(monkeypatch):
    test_secret = "test-prod-secret-key-12345"
    monkeypatch.setattr(settings, "API_KEY", test_secret)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated request without API key should receive 401
        unauth_resp = await client.post(
            "/api/v1/scans",
            json={"url": "https://example.com", "max_pages": 1},
        )
        assert unauth_resp.status_code == 401
        assert "Missing API Key" in unauth_resp.json()["detail"]

        # 2. Incorrect API key receives 401
        bad_key_resp = await client.post(
            "/api/v1/scans",
            json={"url": "https://example.com", "max_pages": 1},
            headers={"X-API-Key": "wrong-key"},
        )
        assert bad_key_resp.status_code == 401
        assert "Invalid API Key" in bad_key_resp.json()["detail"]

        # 3. Valid API key via X-API-Key header succeeds
        auth_resp = await client.post(
            "/api/v1/scans",
            json={"url": "https://example.com", "max_pages": 1},
            headers={"X-API-Key": test_secret},
        )
        assert auth_resp.status_code == 202

        # 4. Valid API key via Authorization Bearer header succeeds
        bearer_resp = await client.post(
            "/api/v1/scans",
            json={"url": "https://example.com", "max_pages": 1},
            headers={"Authorization": f"Bearer {test_secret}"},
        )
        assert bearer_resp.status_code == 202


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter():
    limiter = SlidingWindowRateLimiter()
    key = "test-client-ip"

    # Allow up to 3 requests in a 10s window
    allowed1, retry1 = await limiter.is_allowed(key, max_requests=3, window_seconds=10)
    assert allowed1 is True
    assert retry1 == 0

    allowed2, retry2 = await limiter.is_allowed(key, max_requests=3, window_seconds=10)
    assert allowed2 is True
    assert retry2 == 0

    allowed3, retry3 = await limiter.is_allowed(key, max_requests=3, window_seconds=10)
    assert allowed3 is True
    assert retry3 == 0

    # 4th request must be rejected
    allowed4, retry4 = await limiter.is_allowed(key, max_requests=3, window_seconds=10)
    assert allowed4 is False
    assert retry4 > 0
