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


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
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
async def readiness_check():
    """Readiness: API + database + durable queue observability (no secrets)."""
    from app.core.auth import is_production_environment, production_api_key_configured

    db_status = "connected"
    queue_status = "unknown"
    worker_status = "unknown"
    overall_status = "healthy"
    snap = metrics.snapshot()

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
            # Recent worker heartbeat within the heartbeat timeout indicates workers alive.
            # (Workers heartbeat every ~5s while running a job; a 2x-lease window would
            # hide a dead worker for 20 minutes.)
            cutoff = datetime.now(UTC) - timedelta(
                seconds=max(30, int(settings.SCAN_JOB_HEARTBEAT_TIMEOUT_SECONDS))
            )
            recent_hb = await session.scalar(
                select(func.count())
                .select_from(ScanJob)
                .where(
                    ScanJob.last_heartbeat_at.is_not(None),
                    ScanJob.last_heartbeat_at >= cutoff,
                )
            )
            queue_status = "ready"
            if int(queued or 0) > 0 and int(recent_hb or 0) == 0 and int(active or 0) == 0:
                # Work waiting but no recent worker activity.
                worker_status = "stale_or_absent"
                if settings.ENVIRONMENT.lower() == "production":
                    overall_status = "degraded"
            elif int(active or 0) > 0 or int(recent_hb or 0) > 0:
                worker_status = "active"
            else:
                worker_status = "idle"
            metrics.set_gauge("scan_jobs_queue_depth", float(queued or 0))
            metrics.set_gauge("scan_jobs_active", float(active or 0))
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
    )
