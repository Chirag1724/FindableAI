import pytest
from httpx import ASGITransport, AsyncClient

from app.core.embeddings import (
    EMBEDDING_DIM,
    _deterministic_fallback_embedding,
    get_embedding,
    get_embeddings_batch,
)
from app.main import app


@pytest.fixture(autouse=True)
def disable_rate_limits(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")


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


def _apply_fixture_scan(
    *,
    scan_id: str,
    repo_url: str | None = "https://github.com/my-org/my-site",
    with_evidence: bool = True,
    chunk_id: str | None = None,
):
    """In-memory eligible scan for apply/validation tests (no background pipeline)."""
    import uuid
    from datetime import UTC, datetime

    from app.api.v1.scans import SCANS_DB
    from app.schemas.intelligence import (
        EntailmentStatus,
        EvidenceReference,
        IntentCategory,
        IntentEvaluation,
    )
    from app.schemas.patch import DOMSelectorAnchor, PatchProposal, PatchType
    from app.schemas.scan import ScanResponse, ScanStatus

    cid = chunk_id or str(uuid.uuid4())
    intents: list[IntentEvaluation] = []
    if with_evidence:
        intents = [
            IntentEvaluation(
                intent_id="intent_apply_fixture",
                query="What are the business hours?",
                status=EntailmentStatus.SUPPORTED,
                reasoning="Hours are stated in the cited DOM chunk.",
                confidence=0.9,
                category=IntentCategory.AVAILABILITY,
                evidence=[
                    EvidenceReference(
                        chunk_id=cid,
                        dom_path="main > section.hours",
                        url="https://example-test.com/hours",
                        rank=1,
                        excerpt="Open Monday to Friday 9am-5pm",
                    )
                ],
            )
        ]

    SCANS_DB[scan_id] = ScanResponse(
        scan_id=scan_id,
        target_url="https://example-test.com",
        status=ScanStatus.COMPLETED,
        created_at=datetime.now(UTC),
        repo_url=repo_url,
        github_repo_url=repo_url,
        execution_mode="real_llm",
        data_source="live_pipeline",
        result_source="real_pipeline",
        outcome="success",
        score_source="deterministic_scorer",
        patches_source="assembler",
        remediation_eligible=True,
        intelligence_warnings=[],
        llm_calls_made=10,
        intents=intents,
        patches=[
            PatchProposal(
                patch_id="patch_test_apply",
                patch_type=PatchType.SCHEMA_MICRODATA,
                title="Test remediation",
                rationale="Deterministic fixture for apply validation",
                impact_score_delta=1.0,
                target_file="index.html",
                dom_anchor=DOMSelectorAnchor(
                    css_selector="head",
                    tag_name="head",
                    original_snippet="",
                    suggested_snippet="",
                ),
                unified_diff="--- a/index.html\n+++ b/index.html\n+<!-- findableai -->\n",
                applied=False,
                is_synthetic=False,
            )
        ],
    )
    return cid


@pytest.mark.asyncio
async def test_apply_patches_validation_scenarios(monkeypatch):
    """Offline apply-path checks: repo format, missing token, auth failure after validation."""
    import uuid
    from unittest.mock import AsyncMock

    from app.api.v1.scans import SCANS_DB
    from app.core.config import settings
    from app.github.client import FakeGitHubClient, GitHubClientError

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Invalid repo URL format (no live scan / LLM)
        bad_id = f"scan_{uuid.uuid4().hex}"
        _apply_fixture_scan(scan_id=bad_id, repo_url="invalid-repo-format", with_evidence=False)
        apply_resp = await client.post(f"/api/v1/scans/{bad_id}/patches/apply")
        assert apply_resp.status_code == 400
        assert "Invalid GitHub repository URL format" in apply_resp.json()["detail"]

        # 2. Missing server GITHUB_TOKEN (checked before patch validation)
        monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
        missing_token_id = f"scan_{uuid.uuid4().hex}"
        _apply_fixture_scan(scan_id=missing_token_id, with_evidence=False)
        apply_resp_valid = await client.post(f"/api/v1/scans/{missing_token_id}/patches/apply")
        assert apply_resp_valid.status_code == 400
        assert "GitHub integration token is not configured" in apply_resp_valid.json()["detail"]

        # 3. Token present: validation must pass (durable evidence + live HTML), then PR auth fails
        chunk_uuid = uuid.uuid4()
        auth_scan_id = f"scan_{uuid.uuid4().hex}"
        _apply_fixture_scan(
            scan_id=auth_scan_id,
            with_evidence=True,
            chunk_id=str(chunk_uuid),
        )
        monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_invalid_mock_token_12345")

        async def _chunk_map(_session, _scan_id):
            return {chunk_uuid: object()}

        monkeypatch.setattr("app.api.v1.scans.load_chunk_id_map", _chunk_map)

        html = (
            "<!DOCTYPE html><html><head><title>Site</title>"
            '<script type="application/ld+json">{"@type":"Organization","name":"Acme"}</script>'
            "</head><body><p>Open Monday to Friday 9am-5pm</p></body></html>"
        )
        fake_gh = FakeGitHubClient(login="bot-user")
        fake_gh.seed_repo(
            "my-org/my-site",
            files={"index.html": html},
            allow_push=True,
        )
        monkeypatch.setattr(
            "app.api.v1.scans.build_pygithub_client_from_token",
            lambda _token: fake_gh,
        )

        def _auth_fail(self, _request):
            raise GitHubClientError("Bad credentials", reason="auth_failure")

        monkeypatch.setattr(
            "app.api.v1.scans.GitHubPRService.create_remediation_pr",
            _auth_fail,
        )
        # Avoid remediation_runs DB writes interfering with offline CI
        monkeypatch.setattr(
            "app.api.v1.scans.upsert_remediation_run",
            AsyncMock(side_effect=RuntimeError("offline db")),
        )

        apply_resp_auth = await client.post(f"/api/v1/scans/{auth_scan_id}/patches/apply")
        assert apply_resp_auth.status_code == 400
        detail = apply_resp_auth.json()["detail"]
        assert isinstance(detail, str)
        assert "GitHub PR creation failed" in detail
        assert "validation_failed" not in str(detail).lower()

        # 4. Patches apply-pr endpoint validation
        patches_resp = await client.post(
            "/api/v1/patches/apply-pr",
            json={"patch_id": "p1", "github_repo_url": ""},
        )
        assert patches_resp.status_code == 400
        assert "No GitHub repository configured" in patches_resp.json()["detail"]

    for key in (bad_id, missing_token_id, auth_scan_id):
        SCANS_DB.pop(key, None)


@pytest.mark.asyncio
async def test_apply_blocked_without_durable_evidence(monkeypatch):
    """Missing durable evidence citations must block validated PR creation."""
    import uuid

    from app.api.v1.scans import SCANS_DB
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    scan_id = f"scan_{uuid.uuid4().hex}"
    _apply_fixture_scan(scan_id=scan_id, with_evidence=False)
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_should_not_reach_github")
    create_called = False

    def _boom(_token):
        nonlocal create_called
        create_called = True
        raise AssertionError("GitHub client must not be built when evidence grounding fails")

    monkeypatch.setattr("app.api.v1.scans.build_pygithub_client_from_token", _boom)

    async def _empty_chunks(_session, _scan_id):
        return {}

    monkeypatch.setattr("app.api.v1.scans.load_chunk_id_map", _empty_chunks)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/v1/scans/{scan_id}/patches/apply")
    SCANS_DB.pop(scan_id, None)

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert detail.get("lifecycle_state") == "validation_failed"
    checks = detail.get("checks") or []
    assert any(
        c.get("name") == "evidence_grounding" and c.get("status") == "failed" for c in checks
    )
    assert create_called is False


@pytest.mark.asyncio
async def test_apply_blocked_when_live_file_validation_fails(monkeypatch):
    """Failed/inconclusive safety-critical checks on fetched file content block PR creation."""
    import uuid
    from unittest.mock import AsyncMock

    from app.api.v1.scans import SCANS_DB
    from app.core.config import settings
    from app.github.client import FakeGitHubClient

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    chunk_uuid = uuid.uuid4()
    scan_id = f"scan_{uuid.uuid4().hex}"
    _apply_fixture_scan(scan_id=scan_id, with_evidence=True, chunk_id=str(chunk_uuid))
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_test_token_not_live")

    async def _chunk_map(_session, _scan_id):
        return {chunk_uuid: object()}

    monkeypatch.setattr("app.api.v1.scans.load_chunk_id_map", _chunk_map)

    fake_gh = FakeGitHubClient(login="bot-user")
    # Invalid JSON-LD is a safety-critical fail on the live file path.
    bad_html = (
        "<!DOCTYPE html><html><head>"
        '<script type="application/ld+json">{not-valid-json</script>'
        "</head><body>ok</body></html>"
    )
    fake_gh.seed_repo("my-org/my-site", files={"index.html": bad_html})
    monkeypatch.setattr(
        "app.api.v1.scans.build_pygithub_client_from_token",
        lambda _token: fake_gh,
    )
    pr_called = False

    def _should_not_pr(self, _request):
        nonlocal pr_called
        pr_called = True
        raise AssertionError("PR must not be created after live file validation failure")

    monkeypatch.setattr("app.api.v1.scans.GitHubPRService.create_remediation_pr", _should_not_pr)
    monkeypatch.setattr(
        "app.api.v1.scans.upsert_remediation_run",
        AsyncMock(side_effect=RuntimeError("offline db")),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/v1/scans/{scan_id}/patches/apply")
    SCANS_DB.pop(scan_id, None)

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert "Live file validation blocked PR" in detail.get("message", "")
    checks = detail.get("checks") or []
    assert any(
        c.get("name") == "jsonld_syntax"
        and c.get("status") in ("failed", "inconclusive")
        and c.get("safety_critical")
        for c in checks
    )
    assert pr_called is False


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


@pytest.mark.asyncio
async def test_three_stage_decoupled_pipeline_endpoints(monkeypatch):
    """
    Validates the 3-stage decoupled pipeline contract:
    Stage 1: Crawl & Technical Audit (POST /api/v1/scans with auto_evaluate=false)
    Stage 2: AI Intent & Claim Evaluation (POST /api/v1/scans/{id}/evaluate)
    Stage 3: Remediation & Patch Generation (POST /api/v1/scans/{id}/remediate)
    """
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    import app.api.v1.scans as scans_module
    from app.api.v1.scans import CHUNKS_DB, HTML_DB, SCANS_DB, SCORE_BREAKDOWN_DB, SCORE_INPUTS_DB
    from app.crawler.dom_chunker import ChunkData
    from app.engines.scorer import ScoreInputs, Scorer
    from app.schemas.scan import ScanResponse, ScanStatus

    monkeypatch.setattr(scans_module, "run_stage_evaluate", AsyncMock(return_value=True))

    import uuid

    scan_raw_uuid = uuid.uuid4()
    test_scan_id = f"scan_{scan_raw_uuid.hex}"
    test_scan = ScanResponse(
        scan_id=test_scan_id,
        target_url="https://findableai-demo.test",
        status=ScanStatus.AUDITED,
        created_at=datetime.now(UTC),
    )
    SCANS_DB[test_scan_id] = test_scan
    SCANS_DB[str(scan_raw_uuid)] = test_scan
    fake_chunk = ChunkData(
        url="https://findableai-demo.test",
        dom_path="body > main",
        content="FindableAI optimizes discoverability for modern AI search engines.",
        tag="main",
        word_count=8,
    )
    CHUNKS_DB[test_scan_id] = [fake_chunk]
    HTML_DB[test_scan_id] = ["<html><body><main>FindableAI content</main></body></html>"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Stage 2: Trigger evaluation on audited scan
        eval_resp = await client.post(
            f"/api/v1/scans/{test_scan_id}/evaluate",
            json={"personas": ["cto"]},
        )
        assert eval_resp.status_code == 202
        eval_data = eval_resp.json()
        assert eval_data["scan_id"] == test_scan_id
        assert eval_data["status"] == "synthesizing_intents"

        # Mock score inputs for Stage 3 remediation
        score_inputs = ScoreInputs(
            intent_evaluations=[],
            contradictions=[],
            html_documents=HTML_DB[test_scan_id],
            chunks=[fake_chunk],
        )
        SCORE_INPUTS_DB[test_scan_id] = score_inputs
        SCORE_BREAKDOWN_DB[test_scan_id] = Scorer().score(score_inputs)

        # Stage 3: Trigger on-demand remediation
        rem_resp = await client.post(f"/api/v1/scans/{test_scan_id}/remediate")
        assert rem_resp.status_code == 200
        assert isinstance(rem_resp.json(), list)
