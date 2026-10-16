"""Durable SSE replay contract: events after last_event_id only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.scans import _worker_heartbeat_recent
from app.core.config import settings
from app.jobs.progress import list_progress_events_after, persist_scan_progress
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
async def test_progress_replay_skips_events_at_or_before_cursor(session: AsyncSession):
    """GATE Phase 6: reconnect with last_event_id=N must not re-deliver seq <= N."""
    scan_id = uuid.uuid4()
    session.add(Scan(id=scan_id, url="https://example.com/sse", status="in_progress"))
    await session.commit()

    async with session.begin():
        for i, stage in enumerate(("crawling", "plan", "act"), start=1):
            seq = await persist_scan_progress(
                session,
                scan_id=scan_id,
                status="in_progress",
                stage=stage,
                message=f"step {i}",
                percent=10 * i,
                current=i,
                total=3,
            )
            assert seq == i

    after_one = await list_progress_events_after(session, scan_id, after_seq=1, limit=50)
    assert [r.seq for r in after_one] == [2, 3]
    assert all(r.message != "step 1" for r in after_one)

    after_two = await list_progress_events_after(session, scan_id, after_seq=2, limit=50)
    assert [r.seq for r in after_two] == [3]

    after_all = await list_progress_events_after(session, scan_id, after_seq=3, limit=50)
    assert after_all == []


def test_worker_heartbeat_recent_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SCAN_JOB_HEARTBEAT_TIMEOUT_SECONDS", 60)
    assert _worker_heartbeat_recent(None) is False
    assert _worker_heartbeat_recent(datetime.now(UTC) - timedelta(seconds=10)) is True
    assert _worker_heartbeat_recent(datetime.now(UTC) - timedelta(minutes=10)) is False
