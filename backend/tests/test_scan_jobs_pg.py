"""PostgreSQL integration tests for durable jobs (SKIP LOCKED / concurrency).

Requires an **explicit opt-in** and a **disposable** PostgreSQL + pgvector database.

  FINDABLE_PG_INTEGRATION=1 \\
  FINDABLE_PG_DATABASE_URL='postgresql+asyncpg://findable:findable_secret@127.0.0.1:55432/findable_itest' \\
  pytest tests/test_scan_jobs_pg.py -q

Safety policy:
- Skips unless ``FINDABLE_PG_INTEGRATION`` is truthy.
- Refuses sqlite URLs.
- Refuses non-loopback hosts unless ``FINDABLE_PG_ALLOW_REMOTE=1`` (fail closed).
- Prefer ``FINDABLE_PG_DATABASE_URL`` over app ``DATABASE_URL`` so local/prod
  app settings are not reused by accident.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.jobs.queue import claim_next_job, enqueue_scan_job, request_fingerprint
from app.jobs.states import JobStatus
from app.models.database import ScanJob
from tests.pg_disposable import (
    PG_SKIP_REASON,
    assert_disposable_url,
    create_all_with_vector,
    ensure_database_exists,
    integration_enabled,
    reset_public_schema,
    resolve_pg_url,
    run_alembic_downgrade,
    run_alembic_upgrade,
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
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    await engine.dispose()
    return url


@pytest_asyncio.fixture
async def pg_session(pg_url: str):
    """Function-scoped session on a reset disposable schema (ORM create_all)."""
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    try:
        await reset_public_schema(engine)
        await create_all_with_vector(engine)
    except Exception as exc:
        await engine.dispose()
        pytest.fail(f"Failed to prepare disposable schema with pgvector: {exc}")

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_pg_two_workers_cannot_claim_same_job(pg_session: AsyncSession, pg_url: str):
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
        engine = create_async_engine(pg_url, pool_pre_ping=True)
        try:
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with factory() as s:
                async with s.begin():
                    return await claim_next_job(s, worker_id=worker, lease_seconds=60)
        finally:
            await engine.dispose()

    c1, c2 = await asyncio.gather(_claim("pg-w1"), _claim("pg-w2"))
    claimed = [c for c in (c1, c2) if c is not None]
    assert len(claimed) == 1

    job = await pg_session.get(ScanJob, claimed[0].job_id)
    assert job is not None
    assert job.status == JobStatus.CLAIMED.value


@pytest.mark.asyncio
async def test_pg_migration_head_reachable(pg_url: str):
    """From a clean schema, Alembic upgrade head must create durable job columns."""
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    try:
        await reset_public_schema(engine)
        # Intentionally do NOT create_all — migrations are the source of truth.
        # Test full cycle: upgrade head -> rollback to base -> re-apply to head cleanly.
        run_alembic_upgrade(pg_url)
        run_alembic_downgrade(pg_url, "base")
        run_alembic_upgrade(pg_url)

        async with engine.connect() as conn:
            ext = await conn.scalar(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            assert ext == 1

            fencing = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'scan_jobs' AND column_name = 'fencing_token'"
                )
            )
            assert fencing.first() is not None

            # 0006 progress/checkpoint columns must exist at head.
            checkpoint = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'scan_jobs' AND column_name = 'checkpoint_json'"
                )
            )
            assert checkpoint.first() is not None

            progress = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'scan_progress_events'"
                )
            )
            assert progress.first() is not None

            # 0007 same-scan evidence trigger + intents.persona must exist at head.
            trigger = await conn.scalar(
                text(
                    "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_evidence_same_scan' "
                    "AND NOT tgisinternal"
                )
            )
            assert trigger == 1

            persona = await conn.scalar(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'intents' AND column_name = 'persona'"
                )
            )
            assert persona == 1

            rev = await conn.scalar(text("SELECT version_num FROM alembic_version"))
            assert rev == "0012_scan_jobs_org_id"
    finally:
        await engine.dispose()


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
