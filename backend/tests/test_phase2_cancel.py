"""Phase 2 Item 2: cancel queued/running jobs (Postgres-backed concurrency tests)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.jobs.cancel import finalize_job_cancelled, request_scan_cancel
from app.jobs.queue import claim_next_job, complete_job, enqueue_scan_job, recover_expired_leases
from app.jobs.states import JobStatus
from app.models.database import Organization, Scan, ScanJob, ScanProgressEvent
from tests.pg_disposable import (
    PG_SKIP_REASON,
    assert_disposable_url,
    create_all_with_vector,
    ensure_database_exists,
    integration_enabled,
    reset_public_schema,
    resolve_pg_url,
)

pytestmark = pytest.mark.skipif(not integration_enabled(), reason=PG_SKIP_REASON)


@pytest_asyncio.fixture
async def pg_url() -> str:
    if not integration_enabled():
        pytest.skip("FINDABLE_PG_INTEGRATION not enabled")
    url = resolve_pg_url()
    assert_disposable_url(url)
    try:
        await ensure_database_exists(url)
    except Exception as exc:
        pytest.skip(f"PostgreSQL admin/bootstrap unavailable: {exc}")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text

            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    await engine.dispose()
    return url


@pytest_asyncio.fixture
async def pg_session(pg_url: str):
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    try:
        await reset_public_schema(engine)
        await create_all_with_vector(engine)
    except Exception as exc:
        await engine.dispose()
        pytest.fail(f"Failed to prepare disposable schema: {exc}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_org(session: AsyncSession) -> uuid.UUID:
    org_id = uuid.uuid4()
    session.add(Organization(id=org_id, name="Cancel Org", slug=f"c-{org_id.hex[:8]}"))
    await session.flush()
    return org_id


@pytest.mark.asyncio
async def test_cancel_queued_job_atomic(pg_session: AsyncSession) -> None:
    async with pg_session.begin():
        org_id = await _seed_org(pg_session)
        result = await enqueue_scan_job(
            pg_session,
            scan_uuid=uuid.uuid4(),
            url="https://cancel-queued.example/",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"cancel-q-{uuid.uuid4().hex}",
            fingerprint=uuid.uuid4().hex,
            org_id=org_id,
        )
        scan_id = result.scan.id
        job_id = result.job.id
        out = await request_scan_cancel(
            pg_session, scan_id=scan_id, actor="org:test", reason="stop"
        )
        again = await request_scan_cancel(
            pg_session, scan_id=scan_id, actor="org:test", reason="again"
        )

    assert out.scan_status == "cancelled"
    assert out.job_status == JobStatus.CANCELLED.value
    assert out.conflict is False
    assert again.already_cancelled is True

    job = await pg_session.get(ScanJob, job_id)
    scan = await pg_session.get(Scan, scan_id)
    assert job is not None and job.status == JobStatus.CANCELLED.value
    assert scan is not None and scan.status == "cancelled"
    assert scan.cancel_requested is True

    events = (
        await pg_session.execute(
            select(ScanProgressEvent).where(ScanProgressEvent.scan_id == scan_id)
        )
    ).scalars().all()
    assert any(e.event_type == "cancelled" or e.status == "cancelled" for e in events)


@pytest.mark.asyncio
async def test_cancel_completed_conflict(pg_session: AsyncSession) -> None:
    scan_id = uuid.uuid4()
    async with pg_session.begin():
        org_id = await _seed_org(pg_session)
        pg_session.add(
            Scan(
                id=scan_id,
                org_id=org_id,
                url="https://done.example/",
                status="completed",
                completed_at=datetime.now(UTC),
            )
        )
        pg_session.add(
            ScanJob(
                id=uuid.uuid4(),
                scan_id=scan_id,
                org_id=org_id,
                status=JobStatus.SUCCEEDED.value,
                idempotency_key=f"done-{uuid.uuid4().hex}",
                request_fingerprint=uuid.uuid4().hex,
                correlation_id=uuid.uuid4().hex[:16],
            )
        )
        out = await request_scan_cancel(
            pg_session, scan_id=scan_id, actor="org:test", reason="late"
        )
    assert out.conflict is True


@pytest.mark.asyncio
async def test_cancel_running_flag_and_stale_complete_rejected(
    pg_session: AsyncSession,
) -> None:
    async with pg_session.begin():
        org_id = await _seed_org(pg_session)
        result = await enqueue_scan_job(
            pg_session,
            scan_uuid=uuid.uuid4(),
            url="https://cancel-running.example/",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"cancel-r-{uuid.uuid4().hex}",
            fingerprint=uuid.uuid4().hex,
            org_id=org_id,
        )
        scan_id = result.scan.id

    claimed = await claim_next_job(pg_session, worker_id="w-cancel")
    assert claimed is not None
    await pg_session.commit()

    async with pg_session.begin():
        out = await request_scan_cancel(
            pg_session, scan_id=scan_id, actor="org:test", reason="stop-run"
        )
        assert out.scan_status == "cancelling"
        job = await pg_session.get(ScanJob, claimed.job_id)
        assert job is not None and job.cancel_requested is True
        finalized = await finalize_job_cancelled(
            pg_session,
            job_id=claimed.job_id,
            fencing_token=claimed.fencing_token,
            worker_id="w-cancel",
            reason="stop-run",
        )
        assert finalized is True
        ok = await complete_job(
            pg_session,
            job_id=claimed.job_id,
            fencing_token=claimed.fencing_token,
            worker_id="w-cancel",
        )
        assert ok is False

    job2 = await pg_session.get(ScanJob, claimed.job_id)
    scan2 = await pg_session.get(Scan, scan_id)
    assert job2 is not None and job2.status == JobStatus.CANCELLED.value
    assert scan2 is not None and scan2.status == "cancelled"


@pytest.mark.asyncio
async def test_recovery_does_not_resurrect_cancelled(pg_session: AsyncSession) -> None:
    async with pg_session.begin():
        org_id = await _seed_org(pg_session)
        result = await enqueue_scan_job(
            pg_session,
            scan_uuid=uuid.uuid4(),
            url="https://cancel-recover.example/",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"cancel-rec-{uuid.uuid4().hex}",
            fingerprint=uuid.uuid4().hex,
            org_id=org_id,
        )
        scan_id = result.scan.id

    claimed = await claim_next_job(pg_session, worker_id="w-dead")
    assert claimed is not None
    await pg_session.commit()

    async with pg_session.begin():
        await request_scan_cancel(
            pg_session, scan_id=scan_id, actor="org:test", reason="abandon"
        )
        job = await pg_session.get(ScanJob, claimed.job_id)
        assert job is not None
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=30)
        await recover_expired_leases(pg_session)

    job2 = await pg_session.get(ScanJob, claimed.job_id)
    assert job2 is not None
    assert job2.status == JobStatus.CANCELLED.value
