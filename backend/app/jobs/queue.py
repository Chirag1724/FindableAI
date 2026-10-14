"""PostgreSQL-backed durable job enqueue / claim / complete / recover.

Design notes
------------
- At-least-once execution with idempotent side effects.
- Claims use ``FOR UPDATE SKIP LOCKED`` on PostgreSQL; SQLite falls back to
  a compare-and-set update (sufficient for unit tests, not for concurrency proof).
- Transactions never span LLM or GitHub network I/O.
- Stale workers cannot complete a job after a newer fencing_token claim.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.engine import CursorResult, Result
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.jobs.correlation import new_correlation_id
from app.jobs.errors import FailureCategory, JobErrorCode, classify_failure, redact_error
from app.jobs.metrics import metrics
from app.jobs.states import JobStatus, assert_transition, is_terminal
from app.models.database import Scan as ScanModel
from app.models.database import ScanJob

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job_id: uuid.UUID
    scan_id: uuid.UUID
    fencing_token: int
    attempt_count: int
    correlation_id: str
    payload: dict[str, Any]
    llm_calls_checkpoint: int
    llm_usd_checkpoint: float
    checkpoint_json: dict[str, Any] | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    job: ScanJob
    scan: ScanModel
    created: bool
    conflict: bool = False


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _dml_rowcount(result: Result[Any]) -> int:
    """Rowcount from a DML execute result.

    ``AsyncSession.execute`` is typed as ``Result``, which omits ``rowcount``.
    UPDATE/DELETE statements return a ``CursorResult`` at runtime; narrow to
    that public type before reading affected rows.
    """
    if isinstance(result, CursorResult):
        return int(result.rowcount or 0)
    return 0


def request_fingerprint(
    *,
    url: str,
    max_pages: int,
    personas: list[str] | None,
    repo_url: str | None,
) -> str:
    normalized = {
        "url": (url or "").strip().rstrip("/").lower(),
        "max_pages": int(max_pages),
        "personas": sorted(p.strip().lower() for p in (personas or []) if p),
        "repo_url": (repo_url or "").strip().rstrip("/").lower() or None,
    }
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_idempotency_key(
    client_key: str | None,
    *,
    fingerprint: str,
) -> str:
    """Idempotency policy:

    - If ``Idempotency-Key`` header is provided, that key scopes the request
      globally (unique in ``scan_jobs``). Conflicting fingerprints → 409.
    - Otherwise a derived key ``auto:<fingerprint>`` deduplicates identical
      payloads within the uniqueness constraint (same key forever until row
      deleted; operational TTL is advisory via docs / cleanup, not DB expiry).
    """
    if client_key and client_key.strip():
        return f"client:{client_key.strip()[:480]}"
    return f"auto:{fingerprint}"


def compute_backoff_seconds(attempt_count: int) -> float:
    base = float(settings.SCAN_JOB_BACKOFF_BASE_SECONDS)
    cap = float(settings.SCAN_JOB_BACKOFF_MAX_SECONDS)
    exp = min(cap, base * (2 ** max(0, attempt_count - 1)))
    jitter = random.uniform(0.0, min(1.0, exp * 0.2))
    return float(min(cap, exp + jitter))


async def enqueue_scan_job(
    session: AsyncSession,
    *,
    scan_uuid: uuid.UUID,
    url: str,
    max_pages: int,
    personas: list[str] | None,
    repo_url: str | None,
    idempotency_key: str,
    fingerprint: str,
    correlation_id: str | None = None,
) -> EnqueueResult:
    """Persist scan + job atomically. Caller must commit/begin the transaction."""
    existing = await session.scalar(
        select(ScanJob).where(ScanJob.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            scan = await session.get(ScanModel, existing.scan_id)
            assert scan is not None
            return EnqueueResult(job=existing, scan=scan, created=False, conflict=True)
        scan = await session.get(ScanModel, existing.scan_id)
        assert scan is not None

        # Zombie recovery: if the job is non-terminal, verify it has an active,
        # healthy worker. If the heartbeat is stale or the job sat in queue past the
        # heartbeat timeout, treat it as dead, mark the old row failed, and allow a
        # fresh scan to be created and executed.
        now = _utcnow()
        heartbeat_timeout = timedelta(
            seconds=int(getattr(settings, "SCAN_JOB_HEARTBEAT_TIMEOUT_SECONDS", 300))
        )
        is_term = is_terminal(existing.status)

        is_zombie = False
        if not is_term and existing.finished_at is None:
            if existing.status in (JobStatus.CLAIMED.value, JobStatus.RUNNING.value):
                # Worker claimed or running: must have a fresh heartbeat and unexpired lease
                hb = _as_utc(existing.last_heartbeat_at)
                lease = _as_utc(existing.lease_expires_at)
                if hb is None or hb < now - heartbeat_timeout:
                    is_zombie = True
                elif lease is not None and lease < now:
                    is_zombie = True
            elif existing.status in (JobStatus.QUEUED.value, JobStatus.RETRY_SCHEDULED.value):
                # Queued or retry scheduled: check if waiting too long without being claimed
                next_run = _as_utc(existing.next_run_at)
                if (
                    existing.status == JobStatus.RETRY_SCHEDULED.value
                    and next_run is not None
                    and next_run > now
                ):
                    is_zombie = False
                else:
                    ref_time = _as_utc(existing.available_at or existing.created_at)
                    if ref_time is not None and ref_time < now - heartbeat_timeout:
                        is_zombie = True

        if is_zombie:
            metrics.incr("scan_jobs_zombie_recovered")
            logger.warning(
                "scan_job_zombie_recovered job_id=%s old_scan_id=%s new_scan_id=%s status=%s "
                "last_heartbeat=%s available_at=%s correlation_id=%s; superseding with fresh scan",
                existing.id,
                existing.scan_id,
                scan_uuid,
                existing.status,
                existing.last_heartbeat_at,
                existing.available_at,
                existing.correlation_id,
            )
            existing.status = JobStatus.FAILED.value
            existing.error_code = JobErrorCode.EXECUTION_DEADLINE.value
            existing.failure_category = FailureCategory.TIMEOUT.value
            existing.error_detail = redact_error(
                "heartbeat timeout; zombie job superseded by fresh scan"
            )
            existing.finished_at = now
            existing.updated_at = now
            existing.lease_expires_at = None
            existing.idempotency_key = f"{existing.idempotency_key}:zombie:{existing.id.hex}"

            if scan is not None and scan.status in ("in_progress", "pending"):
                scan.status = "failed"
                scan.error = "Scan timed out (worker heartbeat lost)"
                scan.completed_at = now

            cid = correlation_id or new_correlation_id()
            db_scan = ScanModel(
                id=scan_uuid,
                url=url,
                repo_url=repo_url,
                status="in_progress",
            )
            job = ScanJob(
                id=uuid.uuid4(),
                scan_id=scan_uuid,
                job_type="scan_pipeline",
                status=JobStatus.QUEUED.value,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                correlation_id=cid,
                payload={
                    "url": url,
                    "max_pages": max_pages,
                    "personas": personas or ["cto", "developer", "procurement"],
                    "repo_url": repo_url,
                },
                attempt_count=0,
                max_attempts=int(settings.SCAN_JOB_MAX_ATTEMPTS),
                fencing_token=0,
                available_at=now,
            )
            session.add(db_scan)
            session.add(job)
            await session.flush()
            metrics.incr("scan_jobs_enqueued")
            logger.info(
                "scan_job_enqueued job_id=%s scan_id=%s correlation_id=%s status=%s",
                job.id,
                scan_uuid,
                cid,
                job.status,
            )
            return EnqueueResult(job=job, scan=db_scan, created=True, conflict=False)

        metrics.incr("scan_jobs_idempotent_hits")
        logger.info(
            "scan_job_idempotent_hit job_id=%s scan_id=%s correlation_id=%s",
            existing.id,
            existing.scan_id,
            existing.correlation_id,
        )
        return EnqueueResult(job=existing, scan=scan, created=False, conflict=False)

    cid = correlation_id or new_correlation_id()
    db_scan = ScanModel(
        id=scan_uuid,
        url=url,
        repo_url=repo_url,
        status="in_progress",
    )
    job = ScanJob(
        id=uuid.uuid4(),
        scan_id=scan_uuid,
        job_type="scan_pipeline",
        status=JobStatus.QUEUED.value,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        correlation_id=cid,
        payload={
            "url": url,
            "max_pages": max_pages,
            "personas": personas or ["cto", "developer", "procurement"],
            "repo_url": repo_url,
        },
        attempt_count=0,
        max_attempts=int(settings.SCAN_JOB_MAX_ATTEMPTS),
        fencing_token=0,
        available_at=_utcnow(),
        next_run_at=_utcnow(),
        llm_calls_checkpoint=0,
        llm_usd_checkpoint=0.0,
        checkpoint_json=None,
    )
    try:
        # Savepoint so a uniqueness race does not poison the outer transaction.
        async with session.begin_nested():
            session.add(db_scan)
            session.add(job)
            await session.flush()
    except IntegrityError:
        # Concurrent duplicate insert on uq_scan_jobs_idempotency — recover winner.
        existing = await session.scalar(
            select(ScanJob).where(ScanJob.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise
        scan = await session.get(ScanModel, existing.scan_id)
        if scan is None:
            raise
        conflict = existing.request_fingerprint != fingerprint
        metrics.incr("scan_jobs_idempotent_race")
        logger.info(
            "scan_job_idempotent_race job_id=%s conflict=%s correlation_id=%s",
            existing.id,
            conflict,
            existing.correlation_id,
        )
        return EnqueueResult(job=existing, scan=scan, created=False, conflict=conflict)
    metrics.incr("scan_jobs_enqueued")
    logger.info(
        "scan_job_enqueued job_id=%s scan_id=%s correlation_id=%s status=%s",
        job.id,
        scan_uuid,
        cid,
        job.status,
    )
    return EnqueueResult(job=job, scan=db_scan, created=True, conflict=False)


def _claimable_stmt(now: datetime):
    """Build the claim candidate query for ``session.scalars`` / FOR UPDATE SKIP LOCKED."""
    return (
        select(ScanJob)
        .where(
            or_(
                and_(
                    ScanJob.status == JobStatus.QUEUED.value,
                    ScanJob.available_at <= now,
                ),
                and_(
                    ScanJob.status == JobStatus.RETRY_SCHEDULED.value,
                    ScanJob.next_run_at.is_not(None),
                    ScanJob.next_run_at <= now,
                ),
                and_(
                    ScanJob.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
                    ScanJob.lease_expires_at.is_not(None),
                    ScanJob.lease_expires_at < now,
                ),
            )
        )
        .order_by(ScanJob.available_at.asc())
        .limit(1)
    )


async def claim_next_job(
    session: AsyncSession,
    *,
    worker_id: str,
    lease_seconds: int | None = None,
) -> ClaimedJob | None:
    """Atomically claim one available job. Short transaction; no network I/O."""
    now = _utcnow()
    lease_secs = (
        lease_seconds if lease_seconds is not None else int(settings.SCAN_JOB_LEASE_SECONDS)
    )
    lease_until = now + timedelta(seconds=lease_secs)

    dialect = session.bind.dialect.name if session.bind is not None else ""
    stmt = _claimable_stmt(now)
    if dialect == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    # scalars() yields ORM entities; avoids treating Select[tuple[ScanJob]] rows as tuples.
    job = (await session.scalars(stmt)).first()
    if job is None:
        return None

    prior_status = job.status
    if is_terminal(prior_status):
        return None

    # Lease recovery: return abandoned work to queue semantics via re-claim.
    if prior_status in (JobStatus.CLAIMED.value, JobStatus.RUNNING.value):
        assert_transition(prior_status, JobStatus.QUEUED)
        metrics.incr("scan_jobs_lease_recovered")
        logger.warning(
            "scan_job_lease_recovered job_id=%s prior_status=%s prior_worker=%s "
            "fencing_token=%s correlation_id=%s",
            job.id,
            prior_status,
            job.claimed_by,
            job.fencing_token,
            job.correlation_id,
        )

    if prior_status in (JobStatus.CLAIMED.value, JobStatus.RUNNING.value):
        # Lease recovery: logical QUEUED then CLAIMED in one atomic update.
        assert_transition(JobStatus.QUEUED, JobStatus.CLAIMED)
    else:
        assert_transition(prior_status, JobStatus.CLAIMED)

    job.status = JobStatus.CLAIMED.value
    job.claimed_by = worker_id
    job.fencing_token = int(job.fencing_token) + 1
    job.lease_expires_at = lease_until
    job.last_heartbeat_at = now
    job.attempt_count = int(job.attempt_count) + 1
    job.updated_at = now
    if prior_status == JobStatus.RETRY_SCHEDULED.value:
        job.next_run_at = None
    await session.flush()

    metrics.incr("scan_jobs_claimed")
    logger.info(
        "scan_job_claimed job_id=%s scan_id=%s worker=%s attempt=%s fencing_token=%s "
        "correlation_id=%s",
        job.id,
        job.scan_id,
        worker_id,
        job.attempt_count,
        job.fencing_token,
        job.correlation_id,
    )
    return ClaimedJob(
        job_id=job.id,
        scan_id=job.scan_id,
        fencing_token=job.fencing_token,
        attempt_count=job.attempt_count,
        correlation_id=job.correlation_id,
        payload=dict(job.payload or {}),
        llm_calls_checkpoint=int(job.llm_calls_checkpoint or 0),
        llm_usd_checkpoint=float(getattr(job, "llm_usd_checkpoint", 0.0) or 0.0),
        checkpoint_json=(
            {**job.checkpoint_json} if isinstance(job.checkpoint_json, dict) else None
        ),
        idempotency_key=job.idempotency_key,
    )


async def mark_running(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    fencing_token: int,
    worker_id: str,
) -> bool:
    now = _utcnow()
    result = await session.execute(
        update(ScanJob)
        .where(
            ScanJob.id == job_id,
            ScanJob.fencing_token == fencing_token,
            ScanJob.claimed_by == worker_id,
            ScanJob.status == JobStatus.CLAIMED.value,
        )
        .values(
            status=JobStatus.RUNNING.value,
            started_at=now,
            last_heartbeat_at=now,
            updated_at=now,
        )
    )
    return _dml_rowcount(result) > 0


async def heartbeat(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    fencing_token: int,
    worker_id: str,
    lease_seconds: int | None = None,
) -> bool:
    now = _utcnow()
    lease_secs = (
        lease_seconds if lease_seconds is not None else int(settings.SCAN_JOB_LEASE_SECONDS)
    )
    result = await session.execute(
        update(ScanJob)
        .where(
            ScanJob.id == job_id,
            ScanJob.fencing_token == fencing_token,
            ScanJob.claimed_by == worker_id,
            ScanJob.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
        )
        .values(
            lease_expires_at=now + timedelta(seconds=lease_secs),
            last_heartbeat_at=now,
            updated_at=now,
        )
    )
    return _dml_rowcount(result) > 0


async def complete_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    fencing_token: int,
    worker_id: str,
    llm_calls_checkpoint: int | None = None,
) -> bool:
    now = _utcnow()
    values: dict[str, Any] = {
        "status": JobStatus.SUCCEEDED.value,
        "finished_at": now,
        "updated_at": now,
        "lease_expires_at": None,
        "error_code": None,
        "error_detail": None,
        "failure_category": None,
    }
    if llm_calls_checkpoint is not None:
        values["llm_calls_checkpoint"] = llm_calls_checkpoint
    result = await session.execute(
        update(ScanJob)
        .where(
            ScanJob.id == job_id,
            ScanJob.fencing_token == fencing_token,
            ScanJob.claimed_by == worker_id,
            ScanJob.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
        )
        .values(**values)
    )
    ok = _dml_rowcount(result) > 0
    if ok:
        metrics.incr("scan_jobs_succeeded")
        logger.info(
            "scan_job_succeeded job_id=%s fencing_token=%s worker=%s",
            job_id,
            fencing_token,
            worker_id,
        )
    else:
        metrics.incr("scan_jobs_stale_complete")
        logger.warning(
            "scan_job_stale_complete job_id=%s fencing_token=%s worker=%s",
            job_id,
            fencing_token,
            worker_id,
        )
    return ok


async def fail_or_retry_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    fencing_token: int,
    worker_id: str,
    exc: BaseException | str,
    llm_calls_checkpoint: int | None = None,
) -> JobStatus:
    """Classify failure; schedule retry or mark permanent/dead-letter. Fenced."""
    category, code, retryable = classify_failure(exc)
    detail = redact_error(str(exc))
    now = _utcnow()

    job = await session.scalar(
        select(ScanJob).where(
            ScanJob.id == job_id,
            ScanJob.fencing_token == fencing_token,
            ScanJob.claimed_by == worker_id,
        )
    )
    if job is None:
        metrics.incr("scan_jobs_stale_fail")
        logger.warning(
            "scan_job_stale_fail job_id=%s fencing_token=%s worker=%s",
            job_id,
            fencing_token,
            worker_id,
        )
        return JobStatus.FAILED

    if llm_calls_checkpoint is not None:
        job.llm_calls_checkpoint = max(int(job.llm_calls_checkpoint or 0), llm_calls_checkpoint)

    job.error_code = code.value
    job.error_detail = detail
    job.failure_category = category.value
    job.updated_at = now
    job.lease_expires_at = None

    attempts_left = int(job.attempt_count) < int(job.max_attempts)
    if retryable and attempts_left and category != FailureCategory.BUDGET_EXHAUSTED:
        delay = compute_backoff_seconds(int(job.attempt_count))
        job.status = JobStatus.RETRY_SCHEDULED.value
        job.next_run_at = now + timedelta(seconds=delay)
        job.available_at = job.next_run_at
        metrics.incr("scan_jobs_retry_scheduled")
        logger.warning(
            "scan_job_retry_scheduled job_id=%s attempt=%s/%s delay=%.1fs "
            "category=%s code=%s correlation_id=%s",
            job.id,
            job.attempt_count,
            job.max_attempts,
            delay,
            category.value,
            code.value,
            job.correlation_id,
        )
        return JobStatus.RETRY_SCHEDULED

    terminal = JobStatus.DEAD_LETTER if retryable and not attempts_left else JobStatus.FAILED
    if category == FailureCategory.BUDGET_EXHAUSTED:
        terminal = JobStatus.FAILED
        job.error_code = JobErrorCode.BUDGET_EXHAUSTED.value

    job.status = terminal.value
    job.finished_at = now
    metrics.incr("scan_jobs_failed" if terminal == JobStatus.FAILED else "scan_jobs_dead_letter")
    logger.error(
        "scan_job_terminal job_id=%s status=%s category=%s code=%s correlation_id=%s detail=%s",
        job.id,
        terminal.value,
        category.value,
        job.error_code,
        job.correlation_id,
        detail,
    )
    return terminal


async def update_llm_checkpoint(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    fencing_token: int,
    worker_id: str,
    llm_calls: int,
    llm_usd: float | None = None,
) -> bool:
    """Fenced durable budget checkpoint. Returns False if fence mismatch."""
    values: dict[str, Any] = {
        "llm_calls_checkpoint": int(llm_calls),
        "updated_at": _utcnow(),
    }
    if llm_usd is not None:
        values["llm_usd_checkpoint"] = float(llm_usd)
    result = await session.execute(
        update(ScanJob)
        .where(
            ScanJob.id == job_id,
            ScanJob.fencing_token == fencing_token,
            ScanJob.claimed_by == worker_id,
        )
        .values(**values)
    )
    return _dml_rowcount(result) > 0


async def queue_depth(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(select(ScanJob.status, func.count()).group_by(ScanJob.status))
    counts = {status: int(count) for status, count in rows.all()}
    depth = int(counts.get(JobStatus.QUEUED.value, 0)) + int(
        counts.get(JobStatus.RETRY_SCHEDULED.value, 0)
    )
    active = int(counts.get(JobStatus.CLAIMED.value, 0)) + int(
        counts.get(JobStatus.RUNNING.value, 0)
    )
    metrics.set_gauge("scan_jobs_queue_depth", float(depth))
    metrics.set_gauge("scan_jobs_active", float(active))
    metrics.set_gauge(
        "scan_jobs_failed_total",
        float(counts.get(JobStatus.FAILED.value, 0) + counts.get(JobStatus.DEAD_LETTER.value, 0)),
    )
    return {"depth": depth, "active": active, **{f"status_{k}": v for k, v in counts.items()}}


async def recover_expired_leases(session: AsyncSession) -> int:
    """Requeue jobs whose leases expired (also claimed via claim_next_job)."""
    now = _utcnow()
    result = await session.execute(
        update(ScanJob)
        .where(
            ScanJob.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
            ScanJob.lease_expires_at.is_not(None),
            ScanJob.lease_expires_at < now,
        )
        .values(
            status=JobStatus.QUEUED.value,
            claimed_by=None,
            lease_expires_at=None,
            available_at=now,
            next_run_at=now,
            updated_at=now,
            error_code=JobErrorCode.EXECUTION_DEADLINE.value,
            failure_category=FailureCategory.TIMEOUT.value,
            error_detail=redact_error("lease expired; requeued for recovery"),
        )
    )
    count = _dml_rowcount(result)
    if count:
        metrics.incr("scan_jobs_lease_recovered", count)
        logger.warning("scan_jobs_bulk_lease_recovery count=%s", count)
    return count


async def detect_deadline_exceeded(session: AsyncSession) -> int:
    """Mark running jobs that exceeded SCAN_JOB_EXECUTION_DEADLINE_SECONDS."""
    now = _utcnow()
    deadline = timedelta(seconds=int(settings.SCAN_JOB_EXECUTION_DEADLINE_SECONDS))
    cutoff = now - deadline
    result = await session.execute(
        update(ScanJob)
        .where(
            ScanJob.status == JobStatus.RUNNING.value,
            ScanJob.started_at.is_not(None),
            ScanJob.started_at < cutoff,
        )
        .values(
            status=JobStatus.DEAD_LETTER.value,
            finished_at=now,
            updated_at=now,
            lease_expires_at=None,
            error_code=JobErrorCode.EXECUTION_DEADLINE.value,
            failure_category=FailureCategory.TIMEOUT.value,
            error_detail=redact_error("execution deadline exceeded"),
        )
    )
    return _dml_rowcount(result)


async def db_supports_skip_locked(session: AsyncSession) -> bool:
    bind = session.bind
    if bind is None:
        return False
    if bind.dialect.name != "postgresql":
        return False
    try:
        await session.execute(text("SELECT 1 FOR UPDATE SKIP LOCKED"))
        return True
    except Exception:
        return False
