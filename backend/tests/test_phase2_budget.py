"""Phase 2 Item 3: fenced PG budget reservation never exceeds the limit."""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.budget import LLMBudgetExceededError
from app.jobs.budget_reserve import reserve_scan_llm_call
from app.jobs.queue import claim_next_job, enqueue_scan_job, mark_running
from app.models.database import Organization, Scan
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
    url = resolve_pg_url()
    assert_disposable_url(url)
    try:
        await ensure_database_exists(url)
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    return url


@pytest_asyncio.fixture
async def pg_session(pg_url: str):
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    await reset_public_schema(engine)
    await create_all_with_vector(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_budget_reserve_never_exceeds_limit(
    pg_session: AsyncSession, pg_url: str
) -> None:
    limit = 5
    async with pg_session.begin():
        org_id = uuid.uuid4()
        pg_session.add(Organization(id=org_id, name="Bud", slug=f"b-{org_id.hex[:8]}"))
        result = await enqueue_scan_job(
            pg_session,
            scan_uuid=uuid.uuid4(),
            url="https://budget.example/",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"bud-{uuid.uuid4().hex}",
            fingerprint=uuid.uuid4().hex,
            org_id=org_id,
        )
        scan_id = result.scan.id

    claimed = await claim_next_job(pg_session, worker_id="budget-w")
    assert claimed is not None
    await pg_session.commit()
    async with pg_session.begin():
        assert await mark_running(
            pg_session,
            job_id=claimed.job_id,
            fencing_token=claimed.fencing_token,
            worker_id="budget-w",
        )

    engine = create_async_engine(pg_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _one_reserve() -> int | None:
        async with factory() as session:
            async with session.begin():
                try:
                    return await reserve_scan_llm_call(
                        session,
                        scan_id=scan_id,
                        job_id=claimed.job_id,
                        fencing_token=claimed.fencing_token,
                        worker_id="budget-w",
                        limit=limit,
                        usd_delta=0.01,
                    )
                except LLMBudgetExceededError:
                    return None

    outcomes = await asyncio.gather(*[_one_reserve() for _ in range(20)])
    successes = [o for o in outcomes if o is not None]
    assert len(successes) == limit
    assert max(successes) == limit

    async with factory() as session:
        used = await session.scalar(
            select(Scan.llm_calls_made).where(Scan.id == scan_id)
        )
    assert int(used or 0) == limit
    await engine.dispose()


@pytest.mark.asyncio
async def test_stale_fence_cannot_increment(pg_session: AsyncSession) -> None:
    async with pg_session.begin():
        org_id = uuid.uuid4()
        pg_session.add(Organization(id=org_id, name="Stale", slug=f"s-{org_id.hex[:8]}"))
        result = await enqueue_scan_job(
            pg_session,
            scan_uuid=uuid.uuid4(),
            url="https://stale-budget.example/",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"stale-{uuid.uuid4().hex}",
            fingerprint=uuid.uuid4().hex,
            org_id=org_id,
        )
        scan_id = result.scan.id

    claimed = await claim_next_job(pg_session, worker_id="w1")
    assert claimed is not None
    await pg_session.commit()

    async with pg_session.begin():
        with pytest.raises(LLMBudgetExceededError) as exc:
            await reserve_scan_llm_call(
                pg_session,
                scan_id=scan_id,
                job_id=claimed.job_id,
                fencing_token=claimed.fencing_token + 99,
                worker_id="w1",
                limit=10,
            )
    assert exc.value.reason == "stale_fence"
