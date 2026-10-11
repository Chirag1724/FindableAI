"""PostgreSQL integration tests for durable jobs (SKIP LOCKED / concurrency).

Requires disposable Postgres. Skips when DATABASE_URL is sqlite or unreachable.

  FINDABLE_PG_INTEGRATION=1 pytest tests/test_scan_jobs_pg.py -q
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.jobs.queue import claim_next_job, enqueue_scan_job, request_fingerprint
from app.jobs.states import JobStatus
from app.models.database import Base, ScanJob

pytestmark = pytest.mark.skipif(
    os.environ.get("FINDABLE_PG_INTEGRATION", "").lower() not in ("1", "true", "yes")
    or "sqlite" in settings.DATABASE_URL,
    reason="Set FINDABLE_PG_INTEGRATION=1 with a disposable PostgreSQL DATABASE_URL",
)


@pytest.fixture
async def pg_session():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL unavailable: {exc}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_pg_two_workers_cannot_claim_same_job(pg_session: AsyncSession):
    fp = request_fingerprint(
        url="https://example.com/pg-claim", max_pages=1, personas=None, repo_url=None
    )
    async with pg_session.begin():
        await enqueue_scan_job(
            pg_session,
            scan_uuid=uuid.uuid4(),
            url="https://example.com/pg-claim",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"auto:{fp}-{uuid.uuid4().hex[:8]}",
            fingerprint=fp,
        )

    async def _claim(worker: str):
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as s:
            async with s.begin():
                return await claim_next_job(s, worker_id=worker, lease_seconds=60)
        await engine.dispose()

    c1, c2 = await asyncio.gather(_claim("pg-w1"), _claim("pg-w2"))
    claimed = [c for c in (c1, c2) if c is not None]
    assert len(claimed) == 1

    job = await pg_session.get(ScanJob, claimed[0].job_id)
    assert job is not None
    assert job.status == JobStatus.CLAIMED.value


@pytest.mark.asyncio
async def test_pg_migration_head_reachable(pg_session: AsyncSession):
    """Smoke: scan_jobs table exists after metadata create (Alembic 0005 equivalent)."""
    result = await pg_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'scan_jobs' AND column_name = 'fencing_token'"
        )
    )
    assert result.first() is not None


@pytest.mark.asyncio
async def test_pg_lease_recovery_and_fencing(pg_session: AsyncSession):
    from datetime import UTC, datetime, timedelta

    from app.jobs.queue import complete_job

    fp = request_fingerprint(
        url="https://example.com/pg-lease", max_pages=1, personas=None, repo_url=None
    )
    async with pg_session.begin():
        await enqueue_scan_job(
            pg_session,
            scan_uuid=uuid.uuid4(),
            url="https://example.com/pg-lease",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"auto:{fp}-{uuid.uuid4().hex[:8]}",
            fingerprint=fp,
        )

    async with pg_session.begin():
        c1 = await claim_next_job(pg_session, worker_id="lease-w1", lease_seconds=1)
        assert c1 is not None
        job = await pg_session.get(ScanJob, c1.job_id)
        assert job is not None
        job.status = JobStatus.RUNNING.value
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=5)

    async with pg_session.begin():
        c2 = await claim_next_job(pg_session, worker_id="lease-w2", lease_seconds=60)
        assert c2 is not None
        assert c2.fencing_token > c1.fencing_token

    async with pg_session.begin():
        assert (
            await complete_job(
                pg_session,
                job_id=c1.job_id,
                fencing_token=c1.fencing_token,
                worker_id="lease-w1",
            )
            is False
        )
        assert (
            await complete_job(
                pg_session,
                job_id=c2.job_id,
                fencing_token=c2.fencing_token,
                worker_id="lease-w2",
            )
            is True
        )
