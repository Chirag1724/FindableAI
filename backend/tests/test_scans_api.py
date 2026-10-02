import pytest
from httpx import ASGITransport, AsyncClient

from app.core.embeddings import (
    EMBEDDING_DIM,
    _deterministic_fallback_embedding,
    get_embedding,
    get_embeddings_batch,
)
from app.main import app


def test_deterministic_fallback_embedding():
    text = "FindableAI Machine Discoverability Optimization"
    vec = _deterministic_fallback_embedding(text)
    assert len(vec) == EMBEDDING_DIM
    # Verify L2 norm is approximately 1.0 (unit vector)
    norm = sum(x * x for x in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-4

    # Verify identical inputs produce identical deterministic embeddings
    vec2 = _deterministic_fallback_embedding(text)
    assert vec == vec2

    # Verify empty text fallback
    empty_vec = _deterministic_fallback_embedding("")
    assert len(empty_vec) == EMBEDDING_DIM
    assert all(x == 0.0 for x in empty_vec)


@pytest.mark.asyncio
async def test_get_embedding_and_batch():
    emb = await get_embedding("Bistro 2026 organic farm-to-table dining")
    assert len(emb) == EMBEDDING_DIM

    batch = await get_embeddings_batch(["Page 1 Menu", "Page 2 Hours", "Page 3 About"])
    assert len(batch) == 3
    for v in batch:
        assert len(v) == EMBEDDING_DIM


@pytest.mark.asyncio
async def test_create_scan_and_get_details():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Trigger scan creation via /api/v1/scans
        resp = await client.post(
            "/api/v1/scans",
            json={"url": "https://example.com", "max_pages": 3},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "scan_id" in data
        scan_id = data["scan_id"]
        assert data["target_url"] == "https://example.com"
        assert data["status"] in ("pending", "crawling", "completed")

        # 2. Fetch scan record via /api/v1/scans/{id}
        get_resp = await client.get(f"/api/v1/scans/{scan_id}")
        assert get_resp.status_code == 200
        scan_data = get_resp.json()
        assert scan_data["scan_id"] == scan_id

        # 3. Test Contract 2 alias route /api/scans/{id}
        alias_resp = await client.get(f"/api/scans/{scan_id}")
        assert alias_resp.status_code == 200
        assert alias_resp.json()["scan_id"] == scan_id


@pytest.mark.asyncio
async def test_scan_subresources_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create scan
        resp = await client.post(
            "/api/v1/scans",
            json={"url": "https://example-test.com", "max_pages": 2},
        )
        assert resp.status_code == 202
        scan_id = resp.json()["scan_id"]

        # Chunks endpoint
        chunks_resp = await client.get(f"/api/v1/scans/{scan_id}/chunks")
        assert chunks_resp.status_code == 200
        assert isinstance(chunks_resp.json(), list)

        # Intents endpoint
        intents_resp = await client.get(f"/api/v1/scans/{scan_id}/intents")
        assert intents_resp.status_code == 200
        intents = intents_resp.json()
        assert len(intents) >= 1
        assert "query" in intents[0]

        # Contradictions endpoint
        contra_resp = await client.get(f"/api/v1/scans/{scan_id}/contradictions")
        assert contra_resp.status_code == 200
        contras = contra_resp.json()
        assert len(contras) >= 1

        # Patches endpoint
        patches_resp = await client.get(f"/api/v1/scans/{scan_id}/patches")
        assert patches_resp.status_code == 200
        patches = patches_resp.json()
        assert len(patches) >= 1
        assert "unified_diff" in patches[0]

        # Apply patch PR endpoint
        apply_resp = await client.post(f"/api/v1/scans/{scan_id}/patches/apply")
        assert apply_resp.status_code == 200
        pr_result = apply_resp.json()
        assert "pr_url" in pr_result
        assert pr_result["pr_number"] == 42


@pytest.mark.asyncio
async def test_scan_ssrf_blocking_in_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Cloud metadata endpoint blocked
        resp = await client.post(
            "/api/v1/scans",
            json={"url": "http://169.254.169.254/latest/meta-data/", "max_pages": 1},
        )
        assert resp.status_code == 400
        assert "Security rejection" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_no_hardcoded_demo_content_regression():
    """
    Regression test ensuring no hardcoded demo content ('Bistro 2026', fake operating hours)
    ever appears in patches, intents, or contradictions for any scanned domain.
    """
    test_url = "https://www.e-cellgehubhimtal.in"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create scan
        resp = await client.post(
            "/api/v1/scans",
            json={"url": test_url, "max_pages": 1},
        )
        assert resp.status_code == 202
        scan_id = resp.json()["scan_id"]

        # 2. Get scan subresources
        patches_resp = await client.get(f"/api/v1/scans/{scan_id}/patches")
        assert patches_resp.status_code == 200
        patches_text = str(patches_resp.json())

        intents_resp = await client.get(f"/api/v1/scans/{scan_id}/intents")
        assert intents_resp.status_code == 200
        intents_text = str(intents_resp.json())

        contra_resp = await client.get(f"/api/v1/scans/{scan_id}/contradictions")
        assert contra_resp.status_code == 200
        contra_text = str(contra_resp.json())

        # Assert no hardcoded Bistro 2026 strings in any response
        assert "Bistro 2026" not in patches_text
        assert "Bistro 2026" not in intents_text
        assert "Bistro 2026" not in contra_text
        assert "Bistro" not in patches_text
        assert "Bistro" not in intents_text
        assert "Bistro" not in contra_text
