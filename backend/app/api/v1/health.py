import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import settings
from app.db import engine

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthCheckResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str | None = "unknown"
    environment: str = "development"


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Production-grade system health check endpoint.
    Performs an active database ping (SELECT 1) to verify storage readiness.
    """
    db_status = "connected"
    overall_status = "healthy"

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Health check DB connection failed: %s", exc)
        db_status = "disconnected"
        overall_status = "degraded"

    return HealthCheckResponse(
        status=overall_status,
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        database=db_status,
        environment=settings.ENVIRONMENT,
    )
