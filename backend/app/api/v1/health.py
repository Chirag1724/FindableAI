import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select, text

from app.core.config import settings
from app.db import AsyncSessionLocal, engine
from app.jobs.metrics import metrics
from app.jobs.states import JobStatus
from app.models.database import ScanJob

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthCheckResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str | None = "unknown"
    queue: str | None = "unknown"
    worker: str | None = "unknown"
    auth: str | None = "unknown"
    environment: str = "development"
    metrics: dict | None = None
    # Aggregate queue observability only (no tenant data / secrets).
    queued_jobs: int | None = None
    oldest_queued_age_seconds: float | None = None
    worker_heartbeat_age_seconds: float | None = None


@router.get("/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """Liveness: process is up. Does not probe DB (avoids restart loops).

    Use ``/ready`` for database and queue dependency checks.
    """
    return HealthCheckResponse(
        status="healthy",
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        database="not_checked",
        queue="not_checked",
        worker="not_checked",
        environment=settings.ENVIRONMENT,
    )


@router.get("/ready", response_model=HealthCheckResponse)
async def readiness_check() -> HealthCheckResponse:
    """Readiness: API + database + durable queue observability (no secrets)."""
    from app.core.auth import is_production_environment, production_api_key_configured

    db_status = "connected"
    queue_status = "unknown"
    worker_status = "unknown"
    overall_status = "healthy"
    snap = metrics.snapshot()
    queued_jobs: int | None = None
    oldest_queued_age_seconds: float | None = None
    worker_heartbeat_age_seconds: float | None = None

    if is_production_environment() and not production_api_key_configured():
        return HealthCheckResponse(
            status="not_ready",
            service=settings.PROJECT_NAME,
            version=settings.VERSION,
            database="not_checked",
            queue="not_checked",
            worker="not_checked",
            auth="misconfigured",
            environment=settings.ENVIRONMENT,
            metrics=snap,
        )
    auth_status = "configured" if production_api_key_configured() else "open_non_production"

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Readiness DB connection failed: %s", exc)
        db_status = "disconnected"
        overall_status = "not_ready"
        return HealthCheckResponse(
            status=overall_status,
            service=settings.PROJECT_NAME,
            version=settings.VERSION,
            database=db_status,
            queue="unavailable",
            worker="unknown",
            auth=auth_status,
            environment=settings.ENVIRONMENT,
            metrics=snap,
        )

    if not settings.DURABLE_SCAN_JOBS:
        queue_status = "disabled"
        worker_status = "n/a"
        return HealthCheckResponse(
            status=overall_status,
            service=settings.PROJECT_NAME,
            version=settings.VERSION,
            database=db_status,
            queue=queue_status,
            worker=worker_status,
            auth=auth_status,
            environment=settings.ENVIRONMENT,
            metrics=snap,
        )

    try:
        async with AsyncSessionLocal() as session:
            now = datetime.now(UTC)
            queued = await session.scalar(
                select(func.count())
                .select_from(ScanJob)
                .where(
                    ScanJob.status.in_([JobStatus.QUEUED.value, JobStatus.RETRY_SCHEDULED.value])
                )
            )
            active = await session.scalar(
                select(func.count())
                .select_from(ScanJob)
                .where(ScanJob.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]))
            )
            oldest_available = await session.scalar(
                select(func.min(ScanJob.available_at)).where(
                    ScanJob.status.in_([JobStatus.QUEUED.value, JobStatus.RETRY_SCHEDULED.value])
                )
            )
            newest_hb = await session.scalar(select(func.max(ScanJob.last_heartbeat_at)))

            queued_jobs = int(queued or 0)
            if oldest_available is not None:
                oa = oldest_available
                if oa.tzinfo is None:
                    oa = oa.replace(tzinfo=UTC)
                oldest_queued_age_seconds = max(0.0, (now - oa).total_seconds())
            if newest_hb is not None:
                hb = newest_hb
                if hb.tzinfo is None:
                    hb = hb.replace(tzinfo=UTC)
                worker_heartbeat_age_seconds = max(0.0, (now - hb).total_seconds())

            hb_timeout = max(30, int(settings.SCAN_JOB_HEARTBEAT_TIMEOUT_SECONDS))
            queue_stale = max(30, int(settings.SCAN_JOB_QUEUE_STALE_SECONDS))
            cutoff = now - timedelta(seconds=hb_timeout)
            recent_hb = await session.scalar(
                select(func.count())
                .select_from(ScanJob)
                .where(
                    ScanJob.last_heartbeat_at.is_not(None),
                    ScanJob.last_heartbeat_at >= cutoff,
                )
            )
            queue_status = "ready"
            stale_queue = (
                queued_jobs > 0
                and oldest_queued_age_seconds is not None
                and oldest_queued_age_seconds >= queue_stale
                and int(recent_hb or 0) == 0
                and int(active or 0) == 0
            )
            if stale_queue or (
                queued_jobs > 0 and int(recent_hb or 0) == 0 and int(active or 0) == 0
            ):
                worker_status = "stale_or_absent"
                overall_status = "degraded"
            elif int(active or 0) > 0 or int(recent_hb or 0) > 0:
                worker_status = "active"
            else:
                worker_status = "idle"
            metrics.set_gauge("scan_jobs_queue_depth", float(queued_jobs))
            metrics.set_gauge("scan_jobs_active", float(active or 0))
            if oldest_queued_age_seconds is not None:
                metrics.set_gauge("scan_jobs_oldest_queued_age_seconds", oldest_queued_age_seconds)
    except Exception as exc:
        logger.warning("Readiness queue probe failed: %s", exc)
        queue_status = "unavailable"
        worker_status = "unknown"
        overall_status = "degraded"

    return HealthCheckResponse(
        status=overall_status,
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        database=db_status,
        queue=queue_status,
        worker=worker_status,
        auth=auth_status,
        environment=settings.ENVIRONMENT,
        metrics=snap,
        queued_jobs=queued_jobs,
        oldest_queued_age_seconds=oldest_queued_age_seconds,
        worker_heartbeat_age_seconds=worker_heartbeat_age_seconds,
    )
