"""Regression tests for Phase 3 audit fixes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.jobs.errors import classify_failure
from app.jobs.states import JobStatus
from app.main import app
from app.orchestration.remediation_lifecycle import (
    STATE_MUTATING,
    STATE_PR_OPEN,
    STATE_PR_PERSIST_FAILED,
    upsert_remediation_run,
)


@pytest.mark.asyncio
async def test_liveness_healthy_without_database(monkeypatch):
    """Liveness must not fail when DB is down (avoids Docker restart loops)."""
    from app.api.v1 import health as health_mod

    class _BoomEngine:
        def connect(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(health_mod, "engine", _BoomEngine())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body.get("database") == "not_checked"


@pytest.mark.asyncio
async def test_ready_not_ready_when_database_down(monkeypatch):
    from app.api.v1 import health as health_mod

    class _BoomCtx:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *args):
            return False

    class _BoomEngine:
        def connect(self):
            return _BoomCtx()

    monkeypatch.setattr(health_mod, "engine", _BoomEngine())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_ready"


@pytest.mark.asyncio
async def test_upsert_skips_remutation_when_pr_persist_failed_has_url(monkeypatch):
    """Crash after GitHub accept but before clean PR_OPEN must not open a second PR."""
    from app.orchestration import remediation_lifecycle as rl

    scan_id = uuid.uuid4()
    existing = MagicMock()
    existing.id = uuid.uuid4()
    existing.scan_id = scan_id
    existing.repo_full_name = "acme/site"
    existing.lifecycle_state = STATE_PR_PERSIST_FAILED
    existing.pr_number = 42
    existing.pr_url = "https://github.com/acme/site/pull/42"
    existing.error = "persist failed"
    existing.state_revision = 1

    monkeypatch.setattr(rl, "get_run_by_idempotency", AsyncMock(return_value=existing))

    class _FakeSession:
        def __init__(self):
            self.added = []

        def add(self, row):
            self.added.append(row)

        async def flush(self):
            return None

        async def execute(self, *_a, **_k):
            class _R:
                rowcount = 1

            return _R()

    session = _FakeSession()
    out = await upsert_remediation_run(
        session,
        scan_id=scan_id,
        idempotency_key="scan:repo:main",
        repo_full_name="acme/site",
        base_branch="main",
        lifecycle_state=STATE_MUTATING,
    )
    assert out is existing
    assert existing.lifecycle_state == STATE_PR_OPEN
    assert session.added == []
    assert existing.error is None


def test_already_failed_scan_is_not_retryable():
    cat, _code, retryable = classify_failure("scan already failed; skipping re-execution")
    assert retryable is False
    assert cat.value == "permanent"


@pytest.mark.asyncio
async def test_worker_marks_failed_prior_scan_without_success(monkeypatch):
    from app.jobs import worker as worker_mod
    from app.jobs.queue import ClaimedJob

    claimed = ClaimedJob(
        job_id=uuid.uuid4(),
        scan_id=uuid.uuid4(),
        fencing_token=3,
        attempt_count=2,
        correlation_id="c1",
        payload={"url": "https://example.com", "max_pages": 1},
        llm_calls_checkpoint=5,
        llm_usd_checkpoint=0.0,
        checkpoint_json=None,
        idempotency_key="k",
    )

    w = worker_mod.ScanJobWorker(worker_id="test-w")
    monkeypatch.setattr(w, "_scan_terminal_outcome", AsyncMock(return_value="failed"))

    fail_mock = AsyncMock(return_value=JobStatus.FAILED)
    complete_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(worker_mod, "fail_or_retry_job", fail_mock)
    monkeypatch.setattr(worker_mod, "complete_job", complete_mock)
    monkeypatch.setattr(worker_mod, "mark_running", AsyncMock(return_value=True))

    class _Begin:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _Sess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def begin(self):
            return _Begin()

        async def get(self, _model, _id):
            # Matching org_id (both None) so org-integrity check does not short-circuit.
            return MagicMock(org_id=None)

    monkeypatch.setattr(worker_mod, "AsyncSessionLocal", lambda: _Sess())

    await w._execute_claimed(claimed)
    assert fail_mock.await_count == 1
    assert complete_mock.await_count == 0


def test_inline_fallback_default_is_false():
    from app.core.config import Settings

    assert Settings.model_fields["SCAN_JOB_INLINE_FALLBACK"].default is False
