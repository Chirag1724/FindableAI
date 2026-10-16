"""Unit tests for durable scan job lifecycle, retries, idempotency, fencing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.budget import BudgetGuard, LLMBudgetExceededError
from app.jobs.errors import FailureCategory, JobErrorCode, classify_failure, redact_error
from app.jobs.queue import (
    claim_next_job,
    complete_job,
    compute_backoff_seconds,
    enqueue_scan_job,
    fail_or_retry_job,
    recover_expired_leases,
    request_fingerprint,
    resolve_idempotency_key,
    update_llm_checkpoint,
)
from app.jobs.states import JobStatus, assert_transition, can_transition, is_terminal
from app.models import database as db_mod


class _TestBase(DeclarativeBase):
    pass


class _Scan(_TestBase):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    repo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="in_progress")
    llm_calls_made: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    jobs: Mapped[list[_ScanJob]] = relationship(back_populates="scan")


class _ScanJob(_TestBase):
    __tablename__ = "scan_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"))
    job_type: Mapped[str] = mapped_column(String(50), default="scan_pipeline")
    status: Mapped[str] = mapped_column(String(50), default="queued")
    idempotency_key: Mapped[str] = mapped_column(String(512), unique=True)
    request_fingerprint: Mapped[str] = mapped_column(String(128))
    correlation_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    fencing_token: Mapped[int] = mapped_column(Integer, default=0)
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    llm_calls_checkpoint: Mapped[int] = mapped_column(Integer, default=0)
    llm_usd_checkpoint: Mapped[float] = mapped_column(Float, default=0.0)
    checkpoint_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    scan: Mapped[_Scan] = relationship(back_populates="jobs")


@pytest_asyncio.fixture
async def session(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(db_mod, "Scan", _Scan)
    monkeypatch.setattr(db_mod, "ScanJob", _ScanJob)
    import app.jobs.queue as queue_mod

    monkeypatch.setattr(queue_mod, "ScanModel", _Scan)
    monkeypatch.setattr(queue_mod, "ScanJob", _ScanJob)

    async with factory() as s:
        yield s
    await engine.dispose()


# --- state machine ---


@pytest.mark.parametrize(
    ("cur", "nxt", "ok"),
    [
        (JobStatus.QUEUED, JobStatus.CLAIMED, True),
        (JobStatus.CLAIMED, JobStatus.RUNNING, True),
        (JobStatus.RUNNING, JobStatus.SUCCEEDED, True),
        (JobStatus.RUNNING, JobStatus.RETRY_SCHEDULED, True),
        (JobStatus.RETRY_SCHEDULED, JobStatus.CLAIMED, True),
        (JobStatus.SUCCEEDED, JobStatus.QUEUED, False),
        (JobStatus.FAILED, JobStatus.RUNNING, False),
        (JobStatus.QUEUED, JobStatus.SUCCEEDED, False),
    ],
)
def test_job_transitions(cur, nxt, ok):
    assert can_transition(cur, nxt) is ok
    if ok:
        assert_transition(cur, nxt)
    else:
        with pytest.raises(ValueError):
            assert_transition(cur, nxt)


def test_terminal_statuses():
    assert is_terminal(JobStatus.SUCCEEDED)
    assert is_terminal(JobStatus.DEAD_LETTER)
    assert not is_terminal(JobStatus.RUNNING)


# --- failure classification / redaction ---


def test_classify_retryable_timeout():
    cat, code, retryable = classify_failure(TimeoutError("connection timed out"))
    assert retryable is True
    assert cat in (FailureCategory.TIMEOUT, FailureCategory.RETRYABLE)
    assert code in (JobErrorCode.PROVIDER_TIMEOUT, JobErrorCode.RETRYABLE)


def test_classify_permanent_auth():
    cat, code, retryable = classify_failure("401 Unauthorized: invalid api key")
    assert retryable is False
    assert cat == FailureCategory.PERMANENT
    assert code == JobErrorCode.PROVIDER_AUTH


def test_classify_budget():
    cat, code, retryable = classify_failure("LLM budget exhausted: 60/60")
    assert retryable is False
    assert cat == FailureCategory.BUDGET_EXHAUSTED
    assert code == JobErrorCode.BUDGET_EXHAUSTED


def test_redact_secrets():
    text = redact_error("Authorization: Bearer gsk_SECRETvalue123 and token=abc")
    assert "gsk_SECRETvalue123" not in text
    assert "REDACTED" in text


def test_backoff_bounded():
    delays = [compute_backoff_seconds(i) for i in range(1, 8)]
    assert all(d >= 0 for d in delays)
    assert max(delays) <= 300.0 + 1.0


# --- budget restore ---


def test_budget_restore_never_decreases():
    g = BudgetGuard(limit=60, initial_used=10)
    assert g.used == 10
    g.restore_used(25)
    assert g.used == 25
    g.restore_used(20)
    assert g.used == 25


@pytest.mark.asyncio
async def test_budget_preserved_across_simulated_restart():
    g1 = BudgetGuard(limit=10, initial_used=0)
    await g1.reserve()
    await g1.reserve()
    checkpoint = g1.used
    g2 = BudgetGuard(limit=10, initial_used=checkpoint)
    assert g2.remaining == 8
    with pytest.raises(LLMBudgetExceededError):
        for _ in range(20):
            await g2.reserve()


# --- idempotency helpers ---


def test_fingerprint_stable():
    a = request_fingerprint(
        url="https://Example.com/Path/",
        max_pages=3,
        personas=["cto", "developer"],
        repo_url=None,
    )
    b = request_fingerprint(
        url="https://example.com/path",
        max_pages=3,
        personas=["developer", "cto"],
        repo_url=None,
    )
    assert a == b


def test_idempotency_key_policy():
    fp = "abc123"
    assert resolve_idempotency_key(None, fingerprint=fp) == f"auto:{fp}"
    assert resolve_idempotency_key(" my-key ", fingerprint=fp) == "client:my-key"


# --- queue / fencing (SQLite) ---


@pytest.mark.asyncio
async def test_enqueue_claim_complete(session: AsyncSession):
    scan_id = uuid.uuid4()
    fp = request_fingerprint(
        url="https://example.com", max_pages=2, personas=["cto"], repo_url=None
    )
    async with session.begin():
        result = await enqueue_scan_job(
            session,
            scan_uuid=scan_id,
            url="https://example.com",
            max_pages=2,
            personas=["cto"],
            repo_url=None,
            idempotency_key=f"auto:{fp}",
            fingerprint=fp,
            correlation_id="corr-1",
        )
        assert result.created is True

    async with session.begin():
        claimed = await claim_next_job(session, worker_id="w1", lease_seconds=30)
        assert claimed is not None
        assert claimed.scan_id == scan_id
        token = claimed.fencing_token

    async with session.begin():
        ok = await complete_job(session, job_id=claimed.job_id, fencing_token=token, worker_id="w1")
        assert ok is True

    job = await session.get(_ScanJob, claimed.job_id)
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_idempotent_enqueue(session: AsyncSession):
    scan_id = uuid.uuid4()
    fp = request_fingerprint(url="https://example.com/a", max_pages=1, personas=None, repo_url=None)
    key = "client:k1"
    async with session.begin():
        r1 = await enqueue_scan_job(
            session,
            scan_uuid=scan_id,
            url="https://example.com/a",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp,
        )
    async with session.begin():
        r2 = await enqueue_scan_job(
            session,
            scan_uuid=uuid.uuid4(),
            url="https://example.com/a",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp,
        )
    assert r1.created is True
    assert r2.created is False
    assert r2.conflict is False
    assert r1.job.id == r2.job.id


@pytest.mark.asyncio
async def test_dead_letter_allows_fresh_scan(session: AsyncSession):
    """Terminal dead_letter must release the auto idempotency key for a retry."""
    old_scan_id = uuid.uuid4()
    fp = request_fingerprint(
        url="https://example.com/dead-letter-retry", max_pages=1, personas=None, repo_url=None
    )
    key = f"auto:{fp}"
    async with session.begin():
        r1 = await enqueue_scan_job(
            session,
            scan_uuid=old_scan_id,
            url="https://example.com/dead-letter-retry",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp,
        )
    assert r1.created is True

    async with session.begin():
        job1 = await session.get(_ScanJob, r1.job.id)
        assert job1 is not None
        job1.status = JobStatus.DEAD_LETTER.value
        job1.finished_at = datetime.now(UTC)
        job1.error_code = JobErrorCode.EXECUTION_DEADLINE.value
        job1.error_detail = "parked as dead_letter"

    new_scan_id = uuid.uuid4()
    async with session.begin():
        r2 = await enqueue_scan_job(
            session,
            scan_uuid=new_scan_id,
            url="https://example.com/dead-letter-retry",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp,
        )
    assert r2.created is True
    assert r2.job.id != r1.job.id
    assert r2.scan.id == new_scan_id
    assert r2.job.status == JobStatus.QUEUED.value

    async with session.begin():
        old_j = await session.get(_ScanJob, r1.job.id)
        assert old_j is not None
        assert old_j.status == JobStatus.DEAD_LETTER.value
        assert ":done:" in (old_j.idempotency_key or "")


@pytest.mark.asyncio
async def test_zombie_stale_heartbeat_allows_fresh_scan(session: AsyncSession):
    """A running job with a stale heartbeat must NOT block a new scan of the same URL."""
    old_scan_id = uuid.uuid4()
    fp = request_fingerprint(url="https://example.com/zombie-hb", max_pages=1, personas=None, repo_url=None)
    key = "client:zombie-hb"
    async with session.begin():
        r1 = await enqueue_scan_job(
            session,
            scan_uuid=old_scan_id,
            url="https://example.com/zombie-hb",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp,
        )
    assert r1.created is True

    # Simulate worker crash mid-execution: status running, stale heartbeat 10 minutes ago,
    # but lease_expires_at still has time remaining (simulates long lease window).
    now = datetime.now(UTC)
    async with session.begin():
        job1 = await session.get(_ScanJob, r1.job.id)
        assert job1 is not None
        job1.status = JobStatus.RUNNING.value
        job1.last_heartbeat_at = now - timedelta(minutes=10)
        job1.lease_expires_at = now + timedelta(minutes=5)
        job1.started_at = now - timedelta(minutes=10)

    # Retrying the same URL / key must supersede the zombie with a fresh scan
    new_scan_id = uuid.uuid4()
    async with session.begin():
        r2 = await enqueue_scan_job(
            session,
            scan_uuid=new_scan_id,
            url="https://example.com/zombie-hb",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp,
        )
    assert r2.created is True
    assert r2.conflict is False
    assert r2.job.id != r1.job.id
    assert r2.scan.id == new_scan_id
    assert r2.job.status == JobStatus.QUEUED.value

    # Verify old zombie job and old scan were finalized as failed
    async with session.begin():
        old_j = await session.get(_ScanJob, r1.job.id)
        assert old_j is not None
        assert old_j.status == JobStatus.FAILED.value
        assert old_j.error_code == JobErrorCode.EXECUTION_DEADLINE.value
        assert "heartbeat timeout" in (old_j.error_detail or "")

        old_s = await session.get(_Scan, old_scan_id)
        assert old_s is not None
        assert old_s.status == "failed"


@pytest.mark.asyncio
async def test_healthy_running_job_recent_heartbeat_deduplicates(session: AsyncSession):
    """An actively running job with a fresh heartbeat MUST deduplicate and return created=False."""
    scan_id = uuid.uuid4()
    fp = request_fingerprint(url="https://example.com/healthy-hb", max_pages=1, personas=None, repo_url=None)
    key = "client:healthy-hb"
    async with session.begin():
        r1 = await enqueue_scan_job(
            session,
            scan_uuid=scan_id,
            url="https://example.com/healthy-hb",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp,
        )

    # Worker active with fresh heartbeat (5 seconds ago)
    now = datetime.now(UTC)
    async with session.begin():
        job1 = await session.get(_ScanJob, r1.job.id)
        assert job1 is not None
        job1.status = JobStatus.RUNNING.value
        job1.last_heartbeat_at = now - timedelta(seconds=5)
        job1.lease_expires_at = now + timedelta(minutes=5)

    async with session.begin():
        r2 = await enqueue_scan_job(
            session,
            scan_uuid=uuid.uuid4(),
            url="https://example.com/healthy-hb",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp,
        )
    assert r2.created is False
    assert r2.conflict is False
    assert r2.job.id == r1.job.id


@pytest.mark.asyncio
async def test_zombie_queued_job_past_timeout_allows_fresh_scan(session: AsyncSession):
    """A queued job left unhandled past the timeout must NOT block a new scan."""
    old_scan_id = uuid.uuid4()
    fp = request_fingerprint(url="https://example.com/zombie-q", max_pages=1, personas=None, repo_url=None)
    key = "client:zombie-q"
    async with session.begin():
        r1 = await enqueue_scan_job(
            session,
            scan_uuid=old_scan_id,
            url="https://example.com/zombie-q",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp,
        )

    # Simulate sitting in queue for 10 minutes without any worker
    now = datetime.now(UTC)
    async with session.begin():
        job1 = await session.get(_ScanJob, r1.job.id)
        assert job1 is not None
        job1.available_at = now - timedelta(minutes=10)
        job1.created_at = now - timedelta(minutes=10)

    new_scan_id = uuid.uuid4()
    async with session.begin():
        r2 = await enqueue_scan_job(
            session,
            scan_uuid=new_scan_id,
            url="https://example.com/zombie-q",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp,
        )
    assert r2.created is True
    assert r2.job.id != r1.job.id



@pytest.mark.asyncio
async def test_idempotency_conflict(session: AsyncSession):
    fp1 = request_fingerprint(
        url="https://example.com/1", max_pages=1, personas=None, repo_url=None
    )
    fp2 = request_fingerprint(
        url="https://example.com/2", max_pages=1, personas=None, repo_url=None
    )
    key = "client:same"
    async with session.begin():
        await enqueue_scan_job(
            session,
            scan_uuid=uuid.uuid4(),
            url="https://example.com/1",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp1,
        )
    async with session.begin():
        r = await enqueue_scan_job(
            session,
            scan_uuid=uuid.uuid4(),
            url="https://example.com/2",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=key,
            fingerprint=fp2,
        )
    assert r.conflict is True


@pytest.mark.asyncio
async def test_stale_worker_cannot_complete(session: AsyncSession):
    fp = request_fingerprint(
        url="https://example.com/stale", max_pages=1, personas=None, repo_url=None
    )
    async with session.begin():
        await enqueue_scan_job(
            session,
            scan_uuid=uuid.uuid4(),
            url="https://example.com/stale",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"auto:{fp}",
            fingerprint=fp,
        )
    async with session.begin():
        c1 = await claim_next_job(session, worker_id="w1", lease_seconds=1)
        assert c1 is not None
        job = await session.get(_ScanJob, c1.job_id)
        assert job is not None
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=5)
        job.status = JobStatus.RUNNING.value

    async with session.begin():
        c2 = await claim_next_job(session, worker_id="w2", lease_seconds=30)
        assert c2 is not None
        assert c2.fencing_token > c1.fencing_token

    async with session.begin():
        stale_ok = await complete_job(
            session,
            job_id=c1.job_id,
            fencing_token=c1.fencing_token,
            worker_id="w1",
        )
        assert stale_ok is False

    async with session.begin():
        fresh_ok = await complete_job(
            session,
            job_id=c2.job_id,
            fencing_token=c2.fencing_token,
            worker_id="w2",
        )
        assert fresh_ok is True


@pytest.mark.asyncio
async def test_retry_then_dead_letter(session: AsyncSession, monkeypatch):
    monkeypatch.setattr("app.jobs.queue.settings.SCAN_JOB_BACKOFF_BASE_SECONDS", 0.01)
    monkeypatch.setattr("app.jobs.queue.settings.SCAN_JOB_BACKOFF_MAX_SECONDS", 0.05)

    fp = request_fingerprint(
        url="https://example.com/retry", max_pages=1, personas=None, repo_url=None
    )
    async with session.begin():
        await enqueue_scan_job(
            session,
            scan_uuid=uuid.uuid4(),
            url="https://example.com/retry",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"auto:{fp}",
            fingerprint=fp,
        )

    statuses = []
    for worker in ("w1", "w2"):
        async with session.begin():
            claimed = await claim_next_job(session, worker_id=worker, lease_seconds=30)
            assert claimed is not None
            job = await session.get(_ScanJob, claimed.job_id)
            assert job is not None
            job.max_attempts = 2
        async with session.begin():
            st = await fail_or_retry_job(
                session,
                job_id=claimed.job_id,
                fencing_token=claimed.fencing_token,
                worker_id=worker,
                exc=TimeoutError("provider timed out"),
            )
            statuses.append(st)
            if st == JobStatus.RETRY_SCHEDULED:
                job = await session.get(_ScanJob, claimed.job_id)
                assert job is not None
                job.next_run_at = datetime.now(UTC) - timedelta(seconds=1)
                job.available_at = job.next_run_at
                job.status = JobStatus.QUEUED.value

    assert JobStatus.RETRY_SCHEDULED in statuses
    assert statuses[-1] in (JobStatus.DEAD_LETTER, JobStatus.FAILED)


@pytest.mark.asyncio
async def test_kill_mid_scan_lease_recovery_preserves_checkpoint(session: AsyncSession):
    """GATE Phase 6: worker dies mid-scan → lease recovery → reclaim with checkpoint intact."""
    fp = request_fingerprint(
        url="https://example.com/kill-mid", max_pages=1, personas=None, repo_url=None
    )
    scan_id = uuid.uuid4()
    async with session.begin():
        await enqueue_scan_job(
            session,
            scan_uuid=scan_id,
            url="https://example.com/kill-mid",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"auto:{fp}",
            fingerprint=fp,
        )

    async with session.begin():
        claimed = await claim_next_job(session, worker_id="worker-killed", lease_seconds=60)
        assert claimed is not None
        assert claimed.fencing_token >= 1

    async with session.begin():
        ok = await update_llm_checkpoint(
            session,
            job_id=claimed.job_id,
            fencing_token=claimed.fencing_token,
            worker_id="worker-killed",
            llm_calls=16,
            llm_usd=0.0016,
        )
        assert ok is True
        job = await session.get(_ScanJob, claimed.job_id)
        assert job is not None
        job.status = JobStatus.RUNNING.value
        job.llm_calls_checkpoint = 16
        job.checkpoint_json = {"stage": "act", "batches_done": 1}
        # Simulate hard kill: lease expires, no more heartbeats.
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=5)
        job.last_heartbeat_at = datetime.now(UTC) - timedelta(minutes=2)

    async with session.begin():
        recovered = await recover_expired_leases(session)
        assert recovered == 1
        job = await session.get(_ScanJob, claimed.job_id)
        assert job is not None
        assert job.status == JobStatus.QUEUED.value
        assert job.claimed_by is None
        assert job.llm_calls_checkpoint == 16
        assert (job.checkpoint_json or {}).get("stage") == "act"

    async with session.begin():
        reclaimed = await claim_next_job(session, worker_id="worker-restarted", lease_seconds=60)
        assert reclaimed is not None
        assert reclaimed.job_id == claimed.job_id
        assert reclaimed.fencing_token > claimed.fencing_token
        assert reclaimed.llm_calls_checkpoint == 16

    # Stale worker cannot complete after fencing bump.
    async with session.begin():
        stale = await complete_job(
            session,
            job_id=claimed.job_id,
            fencing_token=claimed.fencing_token,
            worker_id="worker-killed",
        )
        assert stale is False
    async with session.begin():
        fresh = await complete_job(
            session,
            job_id=reclaimed.job_id,
            fencing_token=reclaimed.fencing_token,
            worker_id="worker-restarted",
            llm_calls_checkpoint=18,
        )
        assert fresh is True
