from datetime import UTC, datetime
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.scans import SCANS_DB
from app.main import app
from app.schemas.scan import ScanResponse, ScanStatus


@pytest.mark.asyncio
async def test_get_lighthouse_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/scans/scan_nonexistent123/lighthouse")
        assert resp.status_code == 404
        data = resp.json()
        assert "not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_get_lighthouse_for_existing_scan():
    # Pre-populate SCANS_DB with a test scan
    scan_id = "scan_test_lighthouse_001"
    SCANS_DB[scan_id] = ScanResponse(
        scan_id=scan_id,
        target_url="https://example.com",
        status=ScanStatus.COMPLETED,
        created_at=datetime.now(UTC),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/scans/{scan_id}/lighthouse")
        assert resp.status_code == 200
        data = resp.json()

        assert data["scan_id"] == scan_id
        assert "computed_at" in data

        # Check engines
        assert "engines" in data
        assert "chatgpt" in data["engines"]
        assert "gemini" in data["engines"]
        assert "perplexity" in data["engines"]
        assert "claude" in data["engines"]
        assert 0 <= data["engines"]["chatgpt"]["score"] <= 100

        # Check governance
        assert "crawler_governance" in data
        gov = data["crawler_governance"]
        assert "ai_visibility_index" in gov
        assert "scraping_risk" in gov
        assert "bot_matrix" in gov
        assert len(gov["bot_matrix"]) == 9

        # Check audits
        assert "audits" in data
        assert "opportunities" in data["audits"]
        assert "diagnostics" in data["audits"]
        assert "passed" in data["audits"]
