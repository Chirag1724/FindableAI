"""Durable scan progress snapshots and ordered events (cross-process authoritative).

Progress writes are best-effort: failures are logged and never fail the scan pipeline.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Scan, ScanProgressEvent

logger = logging.getLogger(__name__)


async def persist_scan_progress(
    session: AsyncSession,
    *,
    scan_id: uuid.UUID,
    status: str | None = None,
    stage: str | None = None,
    message: str | None = None,
    percent: int | None = None,
    current: int | None = None,
    total: int | None = None,
    append_event: bool = True,
    event_type: str = "progress",
    event_status: str | None = None,
    job_id: uuid.UUID | None = None,
    fencing_token: int | None = None,
    worker_id: str | None = None,
) -> int | None:
    """Update scan progress columns and optionally append a sequenced event.

    ``status`` updates the coarse ``scans.status`` column (pending/in_progress/
    completed/failed). ``event_status`` (fine-grained pipeline step) is stored
    on the progress event for SSE/UI; defaults to ``status`` when omitted.

    When ``job_id`` / ``fencing_token`` / ``worker_id`` are provided, the write
    is fenced: a stale worker affects 0 rows and returns ``None``.

    Returns the new event sequence number when an event is appended, else None.
    """
    if job_id is not None and fencing_token is not None and worker_id is not None:
        from app.jobs.states import JobStatus
        from app.models.database import ScanJob

        fence_ok = await session.scalar(
            select(ScanJob.id).where(
                ScanJob.id == job_id,
                ScanJob.fencing_token == fencing_token,
                ScanJob.claimed_by == worker_id,
                ScanJob.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
            )
        )
        if fence_ok is None:
            logger.warning(
                "progress_fenced_write_skipped scan_id=%s job_id=%s token=%s worker=%s",
                scan_id,
                job_id,
                fencing_token,
                worker_id,
            )
            return None

    now = datetime.now(UTC)
    clamped_percent: int | None = None
    if percent is not None:
        clamped_percent = max(0, min(100, int(percent)))

    values: dict[str, Any] = {"progress_updated_at": now}
    if status is not None:
        values["status"] = status
    if stage is not None:
        values["progress_stage"] = stage[:100]
    if message is not None:
        values["progress_message"] = message[:2000]
    if clamped_percent is not None:
        values["progress_percent"] = clamped_percent
    if current is not None:
        values["progress_current"] = max(0, int(current))
    if total is not None:
        values["progress_total"] = max(0, int(total))

    await session.execute(update(Scan).where(Scan.id == scan_id).values(**values))

    if not append_event:
        return None

    next_seq = await session.scalar(
        select(func.coalesce(func.max(ScanProgressEvent.seq), 0)).where(
            ScanProgressEvent.scan_id == scan_id
        )
    )
    seq = int(next_seq or 0) + 1
    row_status = event_status if event_status is not None else status
    session.add(
        ScanProgressEvent(
            id=uuid.uuid4(),
            scan_id=scan_id,
            seq=seq,
            event_type=event_type[:64],
            status=row_status,
            stage=(stage[:100] if stage else None),
            message=(message[:2000] if message else None),
            percent=clamped_percent,
            current=(max(0, int(current)) if current is not None else None),
            total=(max(0, int(total)) if total is not None else None),
            created_at=now,
        )
    )
    return seq


async def load_progress_snapshot(
    session: AsyncSession, scan_id: uuid.UUID
) -> dict[str, Any] | None:
    scan = await session.get(Scan, scan_id)
    if scan is None:
        return None
    last_seq = await session.scalar(
        select(func.coalesce(func.max(ScanProgressEvent.seq), 0)).where(
            ScanProgressEvent.scan_id == scan_id
        )
    )
    return {
        "status": scan.status,
        "progress_stage": scan.progress_stage,
        "progress_message": scan.progress_message,
        "progress_percent": scan.progress_percent,
        "progress_current": scan.progress_current,
        "progress_total": scan.progress_total,
        "progress_updated_at": scan.progress_updated_at,
        "progress_seq": int(last_seq or 0),
        "error": scan.error,
        "completed_at": scan.completed_at,
    }


async def list_progress_events_after(
    session: AsyncSession,
    scan_id: uuid.UUID,
    *,
    after_seq: int = 0,
    limit: int = 500,
) -> list[ScanProgressEvent]:
    result = await session.execute(
        select(ScanProgressEvent)
        .where(
            ScanProgressEvent.scan_id == scan_id,
            ScanProgressEvent.seq > int(after_seq),
        )
        .order_by(ScanProgressEvent.seq.asc())
        .limit(max(1, min(int(limit), 2000)))
    )
    return list(result.scalars().all())


async def best_effort_persist_progress(
    *,
    scan_id: uuid.UUID,
    status: str | None = None,
    stage: str | None = None,
    message: str | None = None,
    percent: int | None = None,
    current: int | None = None,
    total: int | None = None,
    event_status: str | None = None,
) -> int | None:
    """Open a short-lived session; never raise to callers."""
    try:
        from app.db import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            async with session.begin():
                return await persist_scan_progress(
                    session,
                    scan_id=scan_id,
                    status=status,
                    stage=stage,
                    message=message,
                    percent=percent,
                    current=current,
                    total=total,
                    event_status=event_status,
                )
    except Exception as exc:
        logger.warning(
            "durable_progress_persist_failed scan_id=%s stage=%s err=%s",
            scan_id,
            stage,
            exc,
        )
        return None
