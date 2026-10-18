"""Fenced PostgreSQL atomic LLM budget reservation (Phase 2 Item 3).

A request counts when reserved immediately before dispatch. Concurrent workers
cannot exceed ``limit`` because the increment is a single guarded UPDATE.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.budget import LLMBudgetExceededError
from app.jobs.states import JobStatus
from app.models.database import Scan as ScanModel
from app.models.database import ScanJob

logger = logging.getLogger(__name__)


async def reserve_scan_llm_call(
    session: AsyncSession,
    *,
    scan_id: uuid.UUID,
    job_id: uuid.UUID,
    fencing_token: int,
    worker_id: str,
    limit: int,
    usd_delta: float = 0.0,
) -> int:
    """Atomically increment ``scans.llm_calls_made`` under job fencing.

    Returns the new 1-based used count. Raises ``LLMBudgetExceededError`` when
    the cap is reached or the worker fence is stale/cancelled.
    """
    if limit < 0:
        raise ValueError("limit must be >= 0")

    job = await session.scalar(
        select(ScanJob).where(
            ScanJob.id == job_id,
            ScanJob.fencing_token == fencing_token,
            ScanJob.claimed_by == worker_id,
            ScanJob.status.in_([JobStatus.CLAIMED.value, JobStatus.RUNNING.value]),
            ScanJob.cancel_requested.is_(False),
        )
    )
    if job is None:
        logger.warning(
            "budget_reserve_stale_fence job_id=%s fencing_token=%s worker=%s",
            job_id,
            fencing_token,
            worker_id,
        )
        raise LLMBudgetExceededError(
            limit=limit,
            used=limit,
            remaining=0,
            attempted=limit + 1,
            reason="stale_fence",
            message="stale or cancelled worker cannot reserve LLM budget",
        )

    used_expr = func.coalesce(ScanModel.llm_calls_made, 0)
    usd_expr = func.coalesce(ScanModel.llm_usd_estimated, 0.0)
    result = await session.execute(
        update(ScanModel)
        .where(
            ScanModel.id == scan_id,
            used_expr < limit,
            ScanModel.status.notin_(["cancelled", "completed", "failed"]),
        )
        .values(
            llm_calls_made=used_expr + 1,
            llm_usd_estimated=usd_expr + float(usd_delta or 0.0),
        )
        .returning(ScanModel.llm_calls_made)
    )
    new_used = result.scalar_one_or_none()
    if new_used is None:
        current = await session.scalar(
            select(func.coalesce(ScanModel.llm_calls_made, 0)).where(ScanModel.id == scan_id)
        )
        used_now = int(current or 0)
        raise LLMBudgetExceededError(
            limit=limit,
            used=used_now,
            remaining=max(0, limit - used_now),
            attempted=used_now + 1,
            reason="call_limit",
            usd_used=0.0,
            usd_cap=0.0,
        )

    job.llm_calls_checkpoint = max(int(job.llm_calls_checkpoint or 0), int(new_used))
    if usd_delta:
        job.llm_usd_checkpoint = float(job.llm_usd_checkpoint or 0.0) + float(usd_delta)
    return int(new_used)
