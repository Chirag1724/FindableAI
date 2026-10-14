"""Scan job worker loop — independently runnable from the API process."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import settings
from app.db import AsyncSessionLocal
from app.jobs.correlation import bind_correlation_id
from app.jobs.execution_context import JobExecutionContext, job_execution_context
from app.jobs.metrics import metrics
from app.jobs.queue import (
    ClaimedJob,
    claim_next_job,
    complete_job,
    detect_deadline_exceeded,
    fail_or_retry_job,
    heartbeat,
    mark_running,
    queue_depth,
    recover_expired_leases,
)
from app.jobs.states import JobStatus
from app.models.database import Scan as ScanModel
from app.models.database import ScanJob

logger = logging.getLogger("findable.worker")


def default_worker_id() -> str:
    configured = (settings.SCAN_WORKER_ID or "").strip()
    if configured:
        return configured
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class ScanJobWorker:
    """Polls PostgreSQL for durable scan jobs and executes the pipeline."""

    def __init__(
        self,
        *,
        worker_id: str | None = None,
        poll_interval: float | None = None,
        pipeline: Any | None = None,
    ) -> None:
        self.worker_id = worker_id or default_worker_id()
        self.poll_interval = (
            float(settings.SCAN_JOB_POLL_INTERVAL_SECONDS)
            if poll_interval is None
            else poll_interval
        )
        self._pipeline = pipeline
        self._stopping = asyncio.Event()
        self._current_job_id: uuid.UUID | None = None

    def request_shutdown(self) -> None:
        logger.info("worker_shutdown_requested worker_id=%s", self.worker_id)
        self._stopping.set()

    async def run_forever(self) -> None:
        logger.info(
            "worker_started worker_id=%s poll_interval=%.2f durable=%s",
            self.worker_id,
            self.poll_interval,
            settings.DURABLE_SCAN_JOBS,
        )
        while not self._stopping.is_set():
            try:
                processed = await self.run_once()
            except Exception:
                logger.exception("worker_loop_error worker_id=%s", self.worker_id)
                processed = False
            if not processed:
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_interval)
                except TimeoutError:
                    pass
        logger.info("worker_stopped worker_id=%s", self.worker_id)

    async def run_once(self) -> bool:
        """Claim and execute at most one job. Returns True if work was done."""
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await recover_expired_leases(session)
                await detect_deadline_exceeded(session)
                await queue_depth(session)
                claimed = await claim_next_job(session, worker_id=self.worker_id)

        if claimed is None:
            return False

        await self._execute_claimed(claimed)
        return True

    async def execute_specific_job(self, job_id: uuid.UUID) -> bool:
        """Claim a specific job if it is claimable (inline fallback / tests)."""
        now = datetime.now(UTC)
        claimed: ClaimedJob | None = None
        async with AsyncSessionLocal() as session:
            async with session.begin():
                job = await session.get(ScanJob, job_id)
                if job is None:
                    return False
                lease_expired = (
                    job.status in (JobStatus.CLAIMED.value, JobStatus.RUNNING.value)
                    and job.lease_expires_at is not None
                    and job.lease_expires_at < now
                )
                if (
                    job.status
                    not in (
                        JobStatus.QUEUED.value,
                        JobStatus.RETRY_SCHEDULED.value,
                    )
                    and not lease_expired
                ):
                    return False

                job.status = JobStatus.CLAIMED.value
                job.claimed_by = self.worker_id
                job.fencing_token = int(job.fencing_token) + 1
                job.attempt_count = int(job.attempt_count) + 1
                job.lease_expires_at = now + timedelta(seconds=int(settings.SCAN_JOB_LEASE_SECONDS))
                job.last_heartbeat_at = now
                job.updated_at = now
                job.next_run_at = None
                claimed = ClaimedJob(
                    job_id=job.id,
                    scan_id=job.scan_id,
                    fencing_token=job.fencing_token,
                    attempt_count=job.attempt_count,
                    correlation_id=job.correlation_id,
                    payload=dict(job.payload or {}),
                    llm_calls_checkpoint=int(job.llm_calls_checkpoint or 0),
                    llm_usd_checkpoint=float(getattr(job, "llm_usd_checkpoint", 0.0) or 0.0),
                    checkpoint_json=(
                        {**job.checkpoint_json}
                        if isinstance(job.checkpoint_json, dict)
                        else None
                    ),
                    idempotency_key=job.idempotency_key,
                )

        if claimed is None:
            return False
        await self._execute_claimed(claimed)
        return True

    async def _execute_claimed(self, claimed: ClaimedJob) -> None:
        bind_correlation_id(claimed.correlation_id)
        self._current_job_id = claimed.job_id
        started = datetime.now(UTC)
        metrics.incr("scan_jobs_attempts")

        async with AsyncSessionLocal() as session:
            async with session.begin():
                ok = await mark_running(
                    session,
                    job_id=claimed.job_id,
                    fencing_token=claimed.fencing_token,
                    worker_id=self.worker_id,
                )
        if not ok:
            logger.warning(
                "scan_job_mark_running_failed job_id=%s fencing_token=%s",
                claimed.job_id,
                claimed.fencing_token,
            )
            self._current_job_id = None
            return

        prior_outcome = await self._scan_terminal_outcome(claimed.scan_id)
        if prior_outcome == "completed":
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await complete_job(
                        session,
                        job_id=claimed.job_id,
                        fencing_token=claimed.fencing_token,
                        worker_id=self.worker_id,
                    )
            self._current_job_id = None
            return
        if prior_outcome == "failed":
            # Prior attempt already finalized the scan — do not remutate or
            # mark the job succeeded; record a non-retryable terminal failure.
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await fail_or_retry_job(
                        session,
                        job_id=claimed.job_id,
                        fencing_token=claimed.fencing_token,
                        worker_id=self.worker_id,
                        exc="scan already failed; skipping re-execution",
                        llm_calls_checkpoint=claimed.llm_calls_checkpoint,
                    )
            self._current_job_id = None
            return

        llm_checkpoint = claimed.llm_calls_checkpoint
        try:
            with job_execution_context(
                JobExecutionContext(
                    job_id=claimed.job_id,
                    scan_id=claimed.scan_id,
                    fencing_token=claimed.fencing_token,
                    worker_id=self.worker_id,
                    correlation_id=claimed.correlation_id,
                )
            ):
                llm_checkpoint = await self._execute_pipeline(claimed)
            # Pipeline finished successfully — always persist success even if a
            # shutdown was requested during the run (avoid spurious retries).
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await complete_job(
                        session,
                        job_id=claimed.job_id,
                        fencing_token=claimed.fencing_token,
                        worker_id=self.worker_id,
                        llm_calls_checkpoint=llm_checkpoint,
                    )
            duration = (datetime.now(UTC) - started).total_seconds()
            metrics.set_gauge("scan_job_last_duration_seconds", duration)
            logger.info(
                "scan_job_pipeline_ok job_id=%s scan_id=%s duration=%.2fs "
                "correlation_id=%s llm_calls=%s",
                claimed.job_id,
                claimed.scan_id,
                duration,
                claimed.correlation_id,
                llm_checkpoint,
            )
        except asyncio.CancelledError as exc:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await fail_or_retry_job(
                        session,
                        job_id=claimed.job_id,
                        fencing_token=claimed.fencing_token,
                        worker_id=self.worker_id,
                        exc=exc,
                        llm_calls_checkpoint=llm_checkpoint,
                    )
            raise
        except Exception as exc:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    status = await fail_or_retry_job(
                        session,
                        job_id=claimed.job_id,
                        fencing_token=claimed.fencing_token,
                        worker_id=self.worker_id,
                        exc=exc,
                        llm_calls_checkpoint=llm_checkpoint,
                    )
            logger.error(
                "scan_job_pipeline_failed job_id=%s terminal_or_retry=%s correlation_id=%s",
                claimed.job_id,
                status.value,
                claimed.correlation_id,
            )
        finally:
            self._current_job_id = None

    async def _scan_terminal_outcome(self, scan_id: uuid.UUID) -> str | None:
        """Return ``completed``, ``failed``, or None if the scan is still open."""
        try:
            async with AsyncSessionLocal() as session:
                scan = await session.get(ScanModel, scan_id)
                if scan is None or scan.completed_at is None:
                    return None
                if scan.status == "completed":
                    return "completed"
                if scan.status == "failed":
                    return "failed"
                return None
        except Exception:
            return None

    async def _execute_pipeline(self, claimed: ClaimedJob) -> int:
        payload = claimed.payload or {}
        url = str(payload.get("url") or "")
        max_pages = int(payload.get("max_pages") or 5)
        personas = payload.get("personas") or ["cto", "developer", "procurement"]
        scan_uuid = claimed.scan_id
        scan_id = f"scan_{scan_uuid.hex}"

        initial_used = int(claimed.llm_calls_checkpoint or 0)
        initial_usd = float(claimed.llm_usd_checkpoint or 0.0)
        try:
            async with AsyncSessionLocal() as session:
                scan = await session.get(ScanModel, scan_uuid)
                if scan is not None and scan.llm_calls_made is not None:
                    initial_used = max(initial_used, int(scan.llm_calls_made))
        except Exception:
            pass

        stop_hb = asyncio.Event()

        async def _hb_loop() -> None:
            while not stop_hb.is_set():
                try:
                    await asyncio.wait_for(stop_hb.wait(), timeout=max(5.0, self.poll_interval))
                except TimeoutError:
                    try:
                        async with AsyncSessionLocal() as session:
                            async with session.begin():
                                await heartbeat(
                                    session,
                                    job_id=claimed.job_id,
                                    fencing_token=claimed.fencing_token,
                                    worker_id=self.worker_id,
                                )
                    except Exception:
                        logger.debug("heartbeat_failed job_id=%s", claimed.job_id, exc_info=True)

        hb_task = asyncio.create_task(_hb_loop())
        try:
            if self._pipeline is not None:
                result = await self._pipeline(
                    scan_id,
                    scan_uuid,
                    url,
                    max_pages,
                    personas,
                    initial_llm_calls=initial_used,
                    initial_llm_usd=initial_usd,
                    resume_checkpoint=claimed.checkpoint_json,
                )
            else:
                from app.api.v1.scans import run_scan_pipeline

                result = await run_scan_pipeline(
                    scan_id,
                    scan_uuid,
                    url,
                    max_pages,
                    personas,
                    initial_llm_calls=initial_used,
                    initial_llm_usd=initial_usd,
                    resume_checkpoint=claimed.checkpoint_json,
                )
            if isinstance(result, int):
                return result
            async with AsyncSessionLocal() as session:
                scan = await session.get(ScanModel, scan_uuid)
                if scan and scan.llm_calls_made is not None:
                    return max(initial_used, int(scan.llm_calls_made))
            return initial_used
        finally:
            stop_hb.set()
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass


async def process_job_inline(job_id: uuid.UUID) -> None:
    """Inline fallback after API enqueue (dev/test). Job row is already durable."""
    worker = ScanJobWorker(worker_id=f"inline:{os.getpid()}:{job_id.hex[:8]}")
    await worker.execute_specific_job(job_id)


def install_signal_handlers(worker: ScanJobWorker) -> None:
    loop = asyncio.get_running_loop()

    def _handler() -> None:
        worker.request_shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handler)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *_: worker.request_shutdown())
