"""API remediation authorization: fail closed before any GitHub mutation."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.scans import SCANS_DB
from app.core.config import settings
from app.main import app
from app.schemas.patch import DOMSelectorAnchor, PatchProposal, PatchType
from app.schemas.scan import ScanResponse, ScanStatus


def _base_scan(**overrides) -> ScanResponse:
    data = dict(
        scan_id="scan_gate_test_0001",
        target_url="https://example.com",
        status=ScanStatus.COMPLETED,
        created_at=datetime.now(UTC),
        repo_url="https://github.com/my-org/my-site",
        github_repo_url="https://github.com/my-org/my-site",
        execution_mode="real_llm",
        data_source="live_pipeline",
        result_source="real_pipeline",
        outcome="success",
        score_source="deterministic_scorer",
        patches_source="assembler",
        remediation_eligible=True,
        intelligence_warnings=[],
        llm_calls_made=10,
        patches=[
            PatchProposal(
                patch_id="patch_gate_ok",
                patch_type=PatchType.SCHEMA_MICRODATA,
                title="Organization JSON-LD",
                rationale="real assembler patch",
                impact_score_delta=2.0,
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
        ],
    )
    data.update(overrides)
    return ScanResponse.model_validate(data)


@pytest.fixture
def scan_in_memory():
    sid = "scan_gate_test_0001"
    SCANS_DB[sid] = _base_scan()
    yield sid
    SCANS_DB.pop(sid, None)


@pytest.mark.asyncio
async def test_remediation_rejected_when_eligible_false(scan_in_memory, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_should_not_be_used")
    SCANS_DB[scan_in_memory].remediation_eligible = False
    create_called = MagicMock()

    class Boom:
        def __init__(self, *a, **k):
            create_called()

    monkeypatch.setattr("app.api.v1.scans.build_pygithub_client_from_token", Boom)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/v1/scans/{scan_in_memory}/patches/apply")
    assert resp.status_code == 400
    assert "not eligible" in resp.json()["detail"].lower()
    create_called.assert_not_called()


@pytest.mark.asyncio
async def test_remediation_rejected_when_eligible_none(scan_in_memory, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_should_not_be_used")
    SCANS_DB[scan_in_memory].remediation_eligible = None
    create_called = MagicMock()

    class Boom:
        def __init__(self, *a, **k):
            create_called()

    monkeypatch.setattr("app.api.v1.scans.build_pygithub_client_from_token", Boom)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/v1/scans/{scan_in_memory}/patches/apply")
    assert resp.status_code == 400
    assert "not eligible" in resp.json()["detail"].lower()
    create_called.assert_not_called()


@pytest.mark.asyncio
async def test_remediation_rejected_when_integrity_missing(monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_should_not_be_used")
    sid = "scan_gate_missing_meta"
    # Pending-like record: no integrity fields decided yet
    SCANS_DB[sid] = ScanResponse(
        scan_id=sid,
        target_url="https://example.com",
        status=ScanStatus.COMPLETED,
        created_at=datetime.now(UTC),
        repo_url="https://github.com/my-org/my-site",
        patches=[
            PatchProposal(
                patch_id="patch_x",
                patch_type=PatchType.SCHEMA_MICRODATA,
                title="x",
                rationale="x",
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
        ],
    )
    create_called = MagicMock()

    class Boom:
        def __init__(self, *a, **k):
            create_called()

    monkeypatch.setattr("app.api.v1.scans.build_pygithub_client_from_token", Boom)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/v1/scans/{sid}/patches/apply")
        assert resp.status_code == 400
        assert "not eligible" in resp.json()["detail"].lower()
        create_called.assert_not_called()
    finally:
        SCANS_DB.pop(sid, None)


@pytest.mark.asyncio
async def test_synthetic_patch_rejected_despite_eligible_true(scan_in_memory, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "ghp_should_not_be_used")
    SCANS_DB[scan_in_memory].remediation_eligible = True
    SCANS_DB[scan_in_memory].patches[0].is_synthetic = True
    create_called = MagicMock()

    class Boom:
        def __init__(self, *a, **k):
            create_called()

    monkeypatch.setattr("app.api.v1.scans.build_pygithub_client_from_token", Boom)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/v1/scans/{scan_in_memory}/patches/apply")
    assert resp.status_code == 400
    assert "synthetic" in resp.json()["detail"].lower()
    create_called.assert_not_called()


@pytest.mark.asyncio
async def test_eligible_scan_reaches_token_validation(scan_in_memory, monkeypatch):
    """Eligibility True + real patch → gate passes; missing token still blocks GitHub."""
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
    create_called = MagicMock()

    class Boom:
        def __init__(self, *a, **k):
            create_called()

    monkeypatch.setattr("app.api.v1.scans.build_pygithub_client_from_token", Boom)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/v1/scans/{scan_in_memory}/patches/apply")
    assert resp.status_code == 400
    assert "GitHub integration token is not configured" in resp.json()["detail"]
    create_called.assert_not_called()


@pytest.mark.asyncio
async def test_hard_failure_sets_fail_closed_integrity(monkeypatch):
    import uuid

    from app.api.v1.scans import _finalize_hard_failure

    sid = "scan_hard_fail_test"
    su = uuid.uuid4()
    SCANS_DB[sid] = ScanResponse(
        scan_id=sid,
        target_url="https://example.com",
        status=ScanStatus.PENDING,
        created_at=datetime.now(UTC),
    )

    class _FailingSession:
        async def __aenter__(self):
            raise RuntimeError("db offline")

        async def __aexit__(self, *a):
            return False

    # Force DB path to fail so we still verify in-memory fail-closed
    monkeypatch.setattr("app.api.v1.scans.AsyncSessionLocal", lambda: _FailingSession())

    await _finalize_hard_failure(sid, su, RuntimeError("Bearer gsk_secret_value boom"))
    record = SCANS_DB[sid]
    assert record.status == ScanStatus.FAILED
    assert record.remediation_eligible is False
    assert record.outcome in ("failed", "partial")
    assert record.error is not None
    assert "gsk_secret" not in (record.error or "")
    SCANS_DB.pop(sid, None)
