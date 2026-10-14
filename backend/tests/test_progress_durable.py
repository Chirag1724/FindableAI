"""Durable progress snapshot + sequenced events (SQLite in-memory)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.jobs.progress import (
    list_progress_events_after,
    load_progress_snapshot,
    persist_scan_progress,
)
from app.models.database import Base, Scan, ScanProgressEvent


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    def _create(sync_conn):
        Base.metadata.create_all(
            sync_conn,
            tables=[Scan.__table__, ScanProgressEvent.__table__],
        )

    async with engine.begin() as conn:
        await conn.run_sync(_create)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_progress_sequence_and_snapshot(session: AsyncSession):
    scan_id = uuid.uuid4()
    session.add(
        Scan(
            id=scan_id,
            url="https://example.com",
            status="in_progress",
        )
    )
    await session.commit()

    async with session.begin():
        seq1 = await persist_scan_progress(
            session,
            scan_id=scan_id,
            status="in_progress",
            stage="crawl",
            message="crawling",
            percent=15,
            current=1,
            total=5,
        )
        seq2 = await persist_scan_progress(
            session,
            scan_id=scan_id,
            status="in_progress",
            stage="nli",
            message="evaluating",
            percent=85,
            current=10,
            total=30,
        )

    assert seq1 == 1
    assert seq2 == 2

    snap = await load_progress_snapshot(session, scan_id)
    assert snap is not None
    assert snap["progress_percent"] == 85
    assert snap["progress_stage"] == "nli"
    assert snap["progress_seq"] == 2
    assert snap["progress_current"] == 10
    assert snap["progress_total"] == 30

    after = await list_progress_events_after(session, scan_id, after_seq=1)
    assert len(after) == 1
    assert after[0].seq == 2
    assert after[0].stage == "nli"


@pytest.mark.asyncio
async def test_progress_does_not_fabricate_percent(session: AsyncSession):
    scan_id = uuid.uuid4()
    session.add(Scan(id=scan_id, url="https://example.com", status="in_progress"))
    await session.commit()
    snap = await load_progress_snapshot(session, scan_id)
    assert snap is not None
    assert snap["progress_percent"] is None
