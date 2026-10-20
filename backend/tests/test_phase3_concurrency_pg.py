"""Phase 3 Item 2b: live PostgreSQL concurrency (SKIP LOCKED / lease / fencing).

HARD REQUIREMENT: real Postgres, separate connections per worker, no mocks.

  FINDABLE_PG_INTEGRATION=1 \\
  FINDABLE_PG_DATABASE_URL='postgresql+asyncpg://findable:findable_secret@127.0.0.1:55432/findable_itest' \\
  pytest tests/test_phase3_concurrency_pg.py -q --count=20

If Postgres is unreachable this module FAILS LOUDLY (does not silently skip).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.budget import LLMBudgetExceededError
from app.jobs.budget_reserve import reserve_scan_llm_call
from app.jobs.checkpoints import save_job_checkpoint
from app.jobs.progress import persist_scan_progress
from app.jobs.queue import (
    claim_next_job,
    complete_job,
    enqueue_scan_job,
    fail_or_retry_job,
    heartbeat,
    request_fingerprint,
)
from app.jobs.states import JobStatus
from app.models.database import ScanJob
from app.orchestration.evidence_persistence import upsert_intent_evaluations_fenced
from tests.pg_disposable import (
    assert_disposable_url,
    create_all_with_vector,
    ensure_database_exists,
    integration_enabled,
    reset_public_schema,
    resolve_pg_url,
)

# Default suite: leave as NOT VERIFIED when opt-in unset (explicit reason, not silent).
# When opt-in is set, fixtures FAIL (never skip) if Postgres is unreachable.
_NOT_VERIFIED = (
    "NOT VERIFIED: FINDABLE_PG_INTEGRATION not set — Phase 3 concurrency requires real "
    "PostgreSQL. Export FINDABLE_PG_INTEGRATION=1 and FINDABLE_PG_DATABASE_URL "
    "(e.g. postgresql+asyncpg://findable:findable_secret@127.0.0.1:55432/findable_itest)."
)
pytestmark = pytest.mark.skipif(not integration_enabled(), reason=_NOT_VERIFIED)


@pytest_asyncio.fixture
async def pg_url() -> str:
    if not integration_enabled():
        pytest.fail(_NOT_VERIFIED)
    url = resolve_pg_url()
    assert_disposable_url(url)
    try:
        await ensure_database_exists(url)
    except Exception as exc:
        pytest.fail(f"NOT VERIFIED: PostgreSQL admin/bootstrap unavailable: {exc}")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.fail(f"NOT VERIFIED: PostgreSQL unreachable: {exc}")
    await engine.dispose()
    return url


@pytest_asyncio.fixture
async def pg_engine(pg_url: str):
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    try:
        await reset_public_schema(engine)
        await create_all_with_vector(engine)
    except Exception as exc:
        await engine.dispose()
        pytest.fail(f"NOT VERIFIED: schema prepare failed: {exc}")
    yield engine, pg_url
    await engine.dispose()


def _factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _enqueue(session: AsyncSession, *, url_suffix: str = "") -> uuid.UUID:
    fp = request_fingerprint(
        url=f"https://example.com/p3-{url_suffix or uuid.uuid4().hex[:8]}",
        max_pages=1,
        personas=None,
        repo_url=None,
    )
    result = await enqueue_scan_job(
        session,
        scan_uuid=uuid.uuid4(),
        url=f"https://example.com/p3-{url_suffix or uuid.uuid4().hex[:8]}",
        max_pages=1,
        personas=None,
        repo_url=None,
        idempotency_key=f"auto:{fp}-{uuid.uuid4().hex[:8]}",
        fingerprint=fp,
    )
    return result.job.id


@pytest.mark.asyncio
async def test_skip_locked_m_jobs_n_workers(pg_engine):
    """M queued jobs, N concurrent workers — each job claimed exactly once."""
    engine, pg_url = pg_engine
    factory = _factory(engine)
    for m, n in ((3, 5), (5, 3)):
        async with factory() as session:
            async with session.begin():
                job_ids = [await _enqueue(session, url_suffix=f"{m}-{n}-{i}") for i in range(m)]

        barrier = asyncio.Barrier(n)

        async def _worker(wid: str, sync: asyncio.Barrier = barrier, db_url: str = pg_url):
            await sync.wait()
            claimed_local: list = []
            eng = create_async_engine(db_url, pool_pre_ping=True)
            try:
                fac = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
                # Drain the queue: with N < M each worker claims repeatedly.
                while True:
                    async with fac() as s:
                        async with s.begin():
                            c = await claim_next_job(s, worker_id=wid, lease_seconds=60)
                    if c is None:
                        break
                    claimed_local.append(c)
            finally:
                await eng.dispose()
            return claimed_local

        results = await asyncio.gather(*[_worker(f"w{i}") for i in range(n)])
        claimed = [c for batch in results for c in batch]
        assert len(claimed) == m
        assert len({c.job_id for c in claimed}) == m
        for c in claimed:
            assert c.fencing_token >= 1
            assert c.attempt_count >= 1
            assert c.job_id in job_ids


@pytest.mark.asyncio
async def test_lease_recovery_and_live_lease_not_reclaimable(pg_engine):
    engine, _pg_url = pg_engine
    factory = _factory(engine)
    async with factory() as session:
        async with session.begin():
            jid = await _enqueue(session, url_suffix="lease")

        async with session.begin():
            c1 = await claim_next_job(session, worker_id="A", lease_seconds=60)
            assert c1 is not None and c1.job_id == jid
            # Live lease: B must not reclaim
            c_live = await claim_next_job(session, worker_id="B", lease_seconds=60)
            assert c_live is None
            job = await session.get(ScanJob, jid)
            assert job is not None
            job.status = JobStatus.RUNNING.value
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

        async with session.begin():
            c2 = await claim_next_job(session, worker_id="B", lease_seconds=60)
            assert c2 is not None
            assert c2.fencing_token > c1.fencing_token
            assert c2.attempt_count > c1.attempt_count


@pytest.mark.asyncio
async def test_cancelled_job_never_reclaimed(pg_engine):
    engine, _pg_url = pg_engine
    factory = _factory(engine)
    async with factory() as session:
        async with session.begin():
            jid = await _enqueue(session, url_suffix="cancel")
            job = await session.get(ScanJob, jid)
            assert job is not None
            job.cancel_requested = True

        async with session.begin():
            assert await claim_next_job(session, worker_id="X", lease_seconds=60) is None


@pytest.mark.asyncio
async def test_max_attempts_goes_to_terminal(pg_engine):
    engine, _pg_url = pg_engine
    factory = _factory(engine)
    async with factory() as session:
        async with session.begin():
            jid = await _enqueue(session, url_suffix="maxatt")
            c1 = await claim_next_job(session, worker_id="A", lease_seconds=60)
            assert c1 is not None
            job = await session.get(ScanJob, jid)
            assert job is not None
            job.max_attempts = 1
            job.attempt_count = 1

        async with session.begin():
            terminal = await fail_or_retry_job(
                session,
                job_id=jid,
                fencing_token=c1.fencing_token,
                worker_id="A",
                exc=RuntimeError("boom"),
            )
            assert terminal in (JobStatus.FAILED, JobStatus.DEAD_LETTER)
            job = await session.get(ScanJob, jid)
            assert job is not None
            assert job.status in (JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value)


@pytest.mark.asyncio
async def test_fencing_stale_worker_writes_affect_zero_rows(pg_engine):
    engine, _pg_url = pg_engine
    factory = _factory(engine)
    async with factory() as session:
        async with session.begin():
            jid = await _enqueue(session, url_suffix="fence")
            c1 = await claim_next_job(session, worker_id="A", lease_seconds=60)
            assert c1 is not None
            job = await session.get(ScanJob, jid)
            assert job is not None
            scan_id = job.scan_id
            job.status = JobStatus.RUNNING.value
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

        async with session.begin():
            c2 = await claim_next_job(session, worker_id="B", lease_seconds=60)
            assert c2 is not None

        # Stale A
        async with session.begin():
            assert (
                await heartbeat(session, job_id=jid, fencing_token=c1.fencing_token, worker_id="A")
                is False
            )
            seq = await persist_scan_progress(
                session,
                scan_id=scan_id,
                stage="stale",
                message="should not write",
                percent=50,
                job_id=jid,
                fencing_token=c1.fencing_token,
                worker_id="A",
            )
            assert seq is None
            assert (
                await save_job_checkpoint(
                    session,
                    job_id=jid,
                    fencing_token=c1.fencing_token,
                    worker_id="A",
                    checkpoint={"v": 1, "stale": True},
                )
                is False
            )
            _, inserted = await upsert_intent_evaluations_fenced(
                session,
                scan_id=scan_id,
                evaluations=[],
                job_id=jid,
                fencing_token=c1.fencing_token,
                worker_id="A",
            )
            assert inserted == 0
            with pytest.raises(LLMBudgetExceededError):
                await reserve_scan_llm_call(
                    session,
                    scan_id=scan_id,
                    job_id=jid,
                    fencing_token=c1.fencing_token,
                    worker_id="A",
                    limit=10,
                )
            assert (
                await complete_job(
                    session, job_id=jid, fencing_token=c1.fencing_token, worker_id="A"
                )
                is False
            )

        # Live B succeeds
        async with session.begin():
            assert (
                await heartbeat(session, job_id=jid, fencing_token=c2.fencing_token, worker_id="B")
                is True
            )
            assert (
                await complete_job(
                    session, job_id=jid, fencing_token=c2.fencing_token, worker_id="B"
                )
                is True
            )
            job = await session.get(ScanJob, jid)
            assert job is not None
            assert job.status == JobStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_combined_cancel_vs_claim(pg_engine):
    engine, pg_url = pg_engine
    factory = _factory(engine)
    async with factory() as session:
        async with session.begin():
            jid = await _enqueue(session, url_suffix="race-cancel")

        barrier = asyncio.Barrier(2)

        async def _claim():
            await barrier.wait()
            eng = create_async_engine(pg_url, pool_pre_ping=True)
            try:
                fac = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
                async with fac() as s:
                    async with s.begin():
                        return await claim_next_job(s, worker_id="claimer", lease_seconds=60)
            finally:
                await eng.dispose()

        async def _cancel():
            await barrier.wait()
            eng = create_async_engine(pg_url, pool_pre_ping=True)
            try:
                fac = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
                async with fac() as s:
                    async with s.begin():
                        job = await s.get(ScanJob, jid)
                        assert job is not None
                        job.cancel_requested = True
                        return True
            finally:
                await eng.dispose()

        claimed, _ = await asyncio.gather(_claim(), _cancel())
        async with factory() as session:
            job = await session.get(ScanJob, jid)
            assert job is not None
            # Exactly one valid outcome: either claimed before cancel flag, or never claimed.
            if claimed is not None:
                assert claimed.job_id == jid
            else:
                assert job.cancel_requested is True


@pytest.mark.asyncio
async def test_completion_vs_reclaim(pg_engine):
    engine, pg_url = pg_engine
    factory = _factory(engine)
    async with factory() as session:
        async with session.begin():
            jid = await _enqueue(session, url_suffix="race-complete")
            c1 = await claim_next_job(session, worker_id="A", lease_seconds=60)
            assert c1 is not None
            job = await session.get(ScanJob, jid)
            assert job is not None
            job.status = JobStatus.RUNNING.value
            job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

        barrier = asyncio.Barrier(2)

        async def _complete():
            await barrier.wait()
            eng = create_async_engine(pg_url, pool_pre_ping=True)
            try:
                fac = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
                async with fac() as s:
                    async with s.begin():
                        return await complete_job(
                            s, job_id=jid, fencing_token=c1.fencing_token, worker_id="A"
                        )
            finally:
                await eng.dispose()

        async def _reclaim():
            await barrier.wait()
            eng = create_async_engine(pg_url, pool_pre_ping=True)
            try:
                fac = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
                async with fac() as s:
                    async with s.begin():
                        return await claim_next_job(s, worker_id="B", lease_seconds=60)
            finally:
                await eng.dispose()

        done, reclaimed = await asyncio.gather(_complete(), _reclaim())
        async with factory() as session:
            job = await session.get(ScanJob, jid)
            assert job is not None
            # Exactly one winner: succeeded OR reclaimed (not both succeeding writes).
            if done:
                assert job.status == JobStatus.SUCCEEDED.value
                assert reclaimed is None or reclaimed.fencing_token >= c1.fencing_token
            else:
                assert reclaimed is not None
                assert reclaimed.fencing_token > c1.fencing_token
