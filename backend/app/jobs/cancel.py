"""Cooperative scan/job cancellation (queued + running).

Cancel is fail-closed and fenced: terminal ``cancelled`` is absorbing; stale
workers cannot overwrite it. Validated partial results are never discarded.
"""

from __future__ import annotations

import contextvars
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.errors import FailureCategory, JobErrorCode, redact_error
from app.jobs.metrics import metrics
from app.jobs.progress import persist_scan_progress
from app.jobs.queue import _dml_rowcount, _utcnow
from app.jobs.states import JobStatus, is_terminal
from app.models.database import Scan as ScanModel
from app.models.database import ScanJob

logger = logging.getLogger(__name__)

CancelCheck = Callable[[], Awaitable[None]]
_cancel_check_var: contextvars.ContextVar[CancelCheck | None] = contextvars.ContextVar(
    "scan_cancel_check", default=None
)

_TERMINAL_SCAN = frozenset({"completed", "failed", "cancelled"})


class ScanCancelled(Exception):
    """Raised inside the worker/pipeline when cooperative cancel is detected."""


def set_cancel_check(check: CancelCheck | None) -> contextvars.Token[CancelCheck | None]:
    return _cancel_check_var.set(check)


def reset_cancel_check(token: contextvars.Token[CancelCheck | None]) -> None:
    _cancel_check_var.reset(token)


async def cooperative_cancel_checkpoint() -> None:
    """Invoke the active cancel check (no-op when unset). Call before provider I/O."""
    check = _cancel_check_var.get()
    if check is not None:
        await check()


@dataclass(frozen=True, slots=True)
class CancelResult:
    scan_id: uuid.UUID
    scan_status: str
    job_status: str | None
    already_cancelled: bool
    conflict: bool
    message: str


async def _latest_job(session: AsyncSession, scan_id: uuid.UUID) -> ScanJob | None:
    job = await session.scalar(
        select(ScanJob)
        .where(ScanJob.scan_id == scan_id)
        .order_by(ScanJob.created_at.desc())
        .limit(1)
    )
    return job if isinstance(job, ScanJob) else None



async def request_scan_cancel(
    session: AsyncSession,
    *,
    scan_id: uuid.UUID,
    actor: str,
    reason: str | None = None,
) -> CancelResult:
    """Cancel a queued job atomically, or flag a running job for cooperative stop.

    Idempotent for already-cancelled scans. Returns ``conflict=True`` for
    completed/failed scans (HTTP 409 at the API layer).
    """
    now = _utcnow()
    scan = await session.get(ScanModel, scan_id)
    if scan is None:
        raise LookupError("scan not found")

    job = await _latest_job(session, scan_id)
    scan_status = str(scan.status or "")
    reason_text = (reason or "cancelled_by_user").strip()[:2000] or "cancelled_by_user"
    actor_text = (actor or "unknown")[:128]

    if scan_status == "cancelled" or (job is not None and job.status == JobStatus.CANCELLED.value):
        return CancelResult(
            scan_id=scan_id,
            scan_status="cancelled",
            job_status=job.status if job else JobStatus.CANCELLED.value,
            already_cancelled=True,
            conflict=False,
            message="already cancelled",
        )

    if scan_status in ("completed", "failed") or (
        job is not None and is_terminal(job.status) and job.status != JobStatus.CANCELLED.value
    ):
        return CancelResult(
            scan_id=scan_id,
            scan_status=scan_status or (job.status if job else "unknown"),
            job_status=job.status if job else None,
            already_cancelled=False,
            conflict=True,
            message="scan already terminal",
        )

    # Path A: atomic queued / retry_scheduled -> cancelled
    if job is not None:
        result = await session.execute(
            update(ScanJob)
            .where(
                ScanJob.id == job.id,
                ScanJob.status.in_(
                    [JobStatus.QUEUED.value, JobStatus.RETRY_SCHEDULED.value]
                ),
            )
            .values(
                status=JobStatus.CANCELLED.value,
                cancel_requested=True,
                finished_at=now,
                updated_at=now,
                lease_expires_at=None,
                claimed_by=None,
                error_code=JobErrorCode.CANCELLED.value,
                failure_category=FailureCategory.CANCELLED.value,
                error_detail=redact_error(reason_text),
            )
        )
        if _dml_rowcount(result) > 0:
            await session.execute(
                update(ScanModel)
                .where(
                    ScanModel.id == scan_id,
                    ScanModel.status.notin_(list(_TERMINAL_SCAN)),
                )
                .values(
                    status="cancelled",
                    cancel_requested=True,
                    cancel_reason=reason_text,
                    cancelled_by=actor_text,
                    completed_at=now,
                    progress_stage="cancelled",
                    progress_message=reason_text,
                    progress_percent=100,
                    progress_updated_at=now,
                    error=reason_text,
                )
            )
            await persist_scan_progress(
                session,
                scan_id=scan_id,
                status="cancelled",
                stage="cancelled",
                message=reason_text,
                percent=100,
                event_type="cancelled",
                event_status="cancelled",
            )
            metrics.incr("scan_jobs_cancelled_queued")
            return CancelResult(
                scan_id=scan_id,
                scan_status="cancelled",
                job_status=JobStatus.CANCELLED.value,
                already_cancelled=False,
                conflict=False,
                message="queued job cancelled",
            )

        # Race: job was claimed meanwhile — fall through to running path.
        await session.refresh(job)

    # Path B: running / claimed — set cancel_requested; worker finalizes.
    if job is not None:
        await session.execute(
            update(ScanJob)
            .where(
                ScanJob.id == job.id,
                ScanJob.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
            )
            .values(cancel_requested=True, updated_at=now)
        )

    await session.execute(
        update(ScanModel)
        .where(
            ScanModel.id == scan_id,
            ScanModel.status.notin_(list(_TERMINAL_SCAN)),
        )
        .values(
            status="cancelling",
            cancel_requested=True,
            cancel_reason=reason_text,
            cancelled_by=actor_text,
            progress_stage="cancelling",
            progress_message=reason_text,
            progress_updated_at=now,
        )
    )
    await persist_scan_progress(
        session,
        scan_id=scan_id,
        status="cancelling",
        stage="cancelling",
        message=reason_text,
        event_type="cancel_requested",
        event_status="cancelling",
    )
    metrics.incr("scan_jobs_cancel_requested")
    refreshed = await _latest_job(session, scan_id)
    return CancelResult(
        scan_id=scan_id,
        scan_status="cancelling",
        job_status=refreshed.status if refreshed else None,
        already_cancelled=False,
        conflict=False,
        message="cancel requested; worker will finalize",
    )


async def job_cancel_requested(session: AsyncSession, job_id: uuid.UUID) -> bool:
    job = await session.get(ScanJob, job_id)
    if job is None:
        return False
    if job.cancel_requested or job.status == JobStatus.CANCELLED.value:
        return True
    scan = await session.get(ScanModel, job.scan_id)
    return bool(scan and (scan.cancel_requested or scan.status in ("cancelling", "cancelled")))


async def finalize_job_cancelled(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    fencing_token: int,
    worker_id: str,
    reason: str | None = None,
) -> bool:
    """Fenced transition of an active job + scan to terminal cancelled."""
    now = _utcnow()
    reason_text = (reason or "cancelled").strip()[:2000] or "cancelled"
    result = await session.execute(
        update(ScanJob)
        .where(
            ScanJob.id == job_id,
            ScanJob.fencing_token == fencing_token,
            ScanJob.claimed_by == worker_id,
            ScanJob.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
            ScanJob.status.notin_(
                [
                    JobStatus.CANCELLED.value,
                    JobStatus.SUCCEEDED.value,
                    JobStatus.FAILED.value,
                    JobStatus.DEAD_LETTER.value,
                ]
            ),
        )
        .values(
            status=JobStatus.CANCELLED.value,
            cancel_requested=True,
            finished_at=now,
            updated_at=now,
            lease_expires_at=None,
            error_code=JobErrorCode.CANCELLED.value,
            failure_category=FailureCategory.CANCELLED.value,
            error_detail=redact_error(reason_text),
        )
    )
    ok = _dml_rowcount(result) > 0
    if not ok:
        metrics.incr("scan_jobs_stale_cancel_finalize")
        logger.warning(
            "scan_job_stale_cancel_finalize job_id=%s fencing_token=%s worker=%s",
            job_id,
            fencing_token,
            worker_id,
        )
        return False

    job = await session.get(ScanJob, job_id)
    if job is None:
        return True
    await session.execute(
        update(ScanModel)
        .where(
            ScanModel.id == job.scan_id,
            ScanModel.status.notin_(["completed", "failed", "cancelled"]),
        )
        .values(
            status="cancelled",
            cancel_requested=True,
            completed_at=now,
            progress_stage="cancelled",
            progress_message=reason_text,
            progress_percent=100,
            progress_updated_at=now,
            error=reason_text,
        )
    )
    await persist_scan_progress(
        session,
        scan_id=job.scan_id,
        status="cancelled",
        stage="cancelled",
        message=reason_text,
        percent=100,
        event_type="cancelled",
        event_status="cancelled",
    )
    metrics.incr("scan_jobs_cancelled_running")
    logger.info(
        "scan_job_cancelled job_id=%s fencing_token=%s worker=%s",
        job_id,
        fencing_token,
        worker_id,
    )
    return True


def cancel_result_payload(result: CancelResult) -> dict[str, Any]:
    return {
        "scan_id": f"scan_{result.scan_id.hex}",
        "status": result.scan_status,
        "job_status": result.job_status,
        "already_cancelled": result.already_cancelled,
        "message": result.message,
    }
