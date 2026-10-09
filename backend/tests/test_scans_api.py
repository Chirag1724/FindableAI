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
    """Without valid LLM credentials, subresources stay empty — no silent synthetic fill."""
    import asyncio

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/scans",
            json={"url": "https://example-test.com", "max_pages": 2},
        )
        assert resp.status_code == 202
        scan_id = resp.json()["scan_id"]

        # Wait for background pipeline to settle (no Groq → zero real evals).
        detail = None
        for _ in range(40):
            detail_resp = await client.get(f"/api/v1/scans/{scan_id}")
            assert detail_resp.status_code == 200
            detail = detail_resp.json()
            if detail.get("status") in ("completed", "failed"):
                break
            await asyncio.sleep(0.25)

        assert detail is not None
        assert detail.get("status") in ("completed", "failed")
        # Honest outcome: not a successful real audit without evaluations.
        assert detail.get("remediation_eligible") is not True
        assert detail.get("outcome") in (None, "inconclusive", "failed", "partial")
        assert (detail.get("summary") or {}).get("dag_evaluations_count", 0) in (0, None)

        chunks_resp = await client.get(f"/api/v1/scans/{scan_id}/chunks")
        assert chunks_resp.status_code == 200
        assert isinstance(chunks_resp.json(), list)

        intents_resp = await client.get(f"/api/v1/scans/{scan_id}/intents")
        assert intents_resp.status_code == 200
        intents = intents_resp.json()
        assert isinstance(intents, list)
        # Default ALLOW_SYNTHETIC_DEMO=false → no fabricated intent rows.
        assert len(intents) == 0

        contra_resp = await client.get(f"/api/v1/scans/{scan_id}/contradictions")
        assert contra_resp.status_code == 200
        assert isinstance(contra_resp.json(), list)

        patches_resp = await client.get(f"/api/v1/scans/{scan_id}/patches")
        assert patches_resp.status_code == 200
        patches = patches_resp.json()
        assert isinstance(patches, list)
        assert len(patches) == 0

        apply_resp = await client.post(f"/api/v1/scans/{scan_id}/patches/apply")
        assert apply_resp.status_code == 400
        detail_msg = apply_resp.json()["detail"]
        assert (
            "No GitHub repository configured" in detail_msg or "not eligible" in detail_msg.lower()
        )


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


@pytest.mark.asyncio
async def test_apply_patches_validation_scenarios(monkeypatch):
    from app.core.config import settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Scan with invalid repo URL format
        resp = await client.post(
            "/api/v1/scans",
            json={
                "url": "https://example-test.com",
                "max_pages": 1,
                "repo_url": "invalid-repo-format",
            },
        )
        assert resp.status_code == 202
        scan_id = resp.json()["scan_id"]

        apply_resp = await client.post(f"/api/v1/scans/{scan_id}/patches/apply")
        assert apply_resp.status_code == 400
        assert "Invalid GitHub repository URL format" in apply_resp.json()["detail"]

        # 2. Scan with valid repo URL but missing server GITHUB_TOKEN
        monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
        resp_valid = await client.post(
            "/api/v1/scans",
            json={
                "url": "https://example-test.com",
                "max_pages": 1,
                "repo_url": "https://github.com/my-org/my-site",
            },
        )
        assert resp_valid.status_code == 202
        scan_id_valid = resp_valid.json()["scan_id"]

        # Freeze integrity + patches so this test exercises token validation,
        # not a race with the background synthetic_fallback pipeline.
        from app.api.v1.scans import SCANS_DB
        from app.schemas.patch import DOMSelectorAnchor, PatchProposal, PatchType

        frozen = SCANS_DB[scan_id_valid]
        frozen.execution_mode = "real_llm"
        frozen.result_source = "real_pipeline"
        frozen.outcome = "success"
        frozen.remediation_eligible = True
        frozen.patches = [
            PatchProposal(
                patch_id="patch_test_apply",
                patch_type=PatchType.SCHEMA_MICRODATA,
                title="Test remediation",
                rationale="Deterministic fixture for apply validation",
                impact_score_delta=1.0,
                dom_anchor=DOMSelectorAnchor(
                    css_selector="head",
                    tag_name="head",
                    original_snippet="",
                    suggested_snippet="",
                ),
                unified_diff="--- a/index.html\n+++ b/index.html\n",
                applied=False,
                is_synthetic=False,
            )
        ]

        apply_resp_valid = await client.post(f"/api/v1/scans/{scan_id_valid}/patches/apply")
        assert apply_resp_valid.status_code == 400
        assert "GitHub integration token is not configured" in apply_resp_valid.json()["detail"]

        # 3. Scan with invalid GITHUB_TOKEN (auth failure)
        monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_invalid_mock_token_12345")
        apply_resp_auth = await client.post(f"/api/v1/scans/{scan_id_valid}/patches/apply")
        assert apply_resp_auth.status_code == 400
        assert "GitHub PR creation failed" in apply_resp_auth.json()["detail"]

        # 4. Patches apply-pr endpoint validation
        patches_resp = await client.post(
            "/api/v1/patches/apply-pr",
            json={"patch_id": "p1", "github_repo_url": ""},
        )
        assert patches_resp.status_code == 400
        assert "No GitHub repository configured" in patches_resp.json()["detail"]


@pytest.mark.asyncio
async def test_unknown_scan_returns_404_no_mock_data():
    """
    Ensure the API returns HTTP 404 for non-existent scans instead of
    fabricating mock scans or simulated SSE progressions.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Non-existent scan should return 404 Not Found
        missing_id = "scan_00000000000000000000000000000000"
        resp = await client.get(f"/api/v1/scans/{missing_id}")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

        # Stream endpoint for non-existent scan should also return 404
        stream_resp = await client.get(f"/api/v1/scans/{missing_id}/stream")
        assert stream_resp.status_code == 404

        # Non-existent scan sub-resources should return empty lists, not mocks
        patches_resp = await client.get(f"/api/v1/scans/{missing_id}/patches")
        assert patches_resp.status_code == 200
        assert patches_resp.json() == []

        intents_resp = await client.get(f"/api/v1/scans/{missing_id}/intents")
        assert intents_resp.status_code == 200
        assert intents_resp.json() == []
