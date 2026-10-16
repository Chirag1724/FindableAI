"""Stage checkpoints for safe pipeline resume (fingerprint + version gated)."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import DOMChunk, ScanJob

logger = logging.getLogger(__name__)

CHECKPOINT_SCHEMA_VERSION = 1
EXTRACTOR_VERSION = "dom_chunker_v1"
RETRIEVAL_VERSION = "hybrid_rrf_v1"


def pipeline_version_bundle(*, model: str | None = None) -> dict[str, str]:
    return {
        "checkpoint_schema": str(CHECKPOINT_SCHEMA_VERSION),
        "extractor": EXTRACTOR_VERSION,
        "retrieval": RETRIEVAL_VERSION,
        "model": model or settings.DEFAULT_LLM_MODEL,
        "prompt_bundle": "findable_dag_v1",
    }


def request_stage_fingerprint(
    *,
    url: str,
    max_pages: int,
    personas: list[str] | None,
) -> str:
    payload = {
        "url": (url or "").strip().lower().rstrip("/"),
        "max_pages": int(max_pages),
        "personas": sorted([p.strip().lower() for p in (personas or []) if p]),
        "extractor": EXTRACTOR_VERSION,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def empty_checkpoint(*, fingerprint: str, versions: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "v": CHECKPOINT_SCHEMA_VERSION,
        "fingerprint": fingerprint,
        "versions": versions or pipeline_version_bundle(),
        "stages": {},
        "updated_at": datetime.now(UTC).isoformat(),
    }


def checkpoint_compatible(stored: dict[str, Any] | None, *, fingerprint: str) -> bool:
    if not stored or not isinstance(stored, dict):
        return False
    if int(stored.get("v") or 0) != CHECKPOINT_SCHEMA_VERSION:
        return False
    if stored.get("fingerprint") != fingerprint:
        return False
    versions = stored.get("versions") or {}
    expected = pipeline_version_bundle(model=versions.get("model"))
    for key in ("extractor", "retrieval", "prompt_bundle", "checkpoint_schema"):
        if str(versions.get(key) or "") != str(expected.get(key) or ""):
            return False
    return True


def stage_done(stored: dict[str, Any] | None, stage: str) -> bool:
    if not stored:
        return False
    stages = stored.get("stages") or {}
    entry = stages.get(stage) or {}
    return bool(entry.get("done"))


def mark_stage(
    stored: dict[str, Any],
    stage: str,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stages = dict(stored.get("stages") or {})
    stages[stage] = {"done": True, **(meta or {}), "at": datetime.now(UTC).isoformat()}
    stored = {**stored, "stages": stages, "updated_at": datetime.now(UTC).isoformat()}
    return stored


async def load_job_checkpoint(session: AsyncSession, job_id: uuid.UUID) -> dict[str, Any] | None:
    job = await session.get(ScanJob, job_id)
    if job is None:
        return None
    raw = getattr(job, "checkpoint_json", None)
    return dict(raw) if isinstance(raw, dict) else None


async def save_job_checkpoint(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    fencing_token: int,
    worker_id: str,
    checkpoint: dict[str, Any],
) -> bool:
    """Fenced checkpoint write — stale workers cannot overwrite."""
    result = await session.execute(
        update(ScanJob)
        .where(
            ScanJob.id == job_id,
            ScanJob.fencing_token == fencing_token,
            ScanJob.claimed_by == worker_id,
        )
        .values(checkpoint_json=checkpoint, updated_at=datetime.now(UTC))
    )
    try:
        return bool(getattr(result, "rowcount", 0))
    except Exception:
        return True


async def count_persisted_chunks(session: AsyncSession, scan_id: uuid.UUID) -> int:
    result = await session.scalar(
        select(DOMChunk.id).where(DOMChunk.scan_id == scan_id).limit(1)
    )
    if result is None:
        return 0
    from sqlalchemy import func

    return int(
        await session.scalar(
            select(func.count()).select_from(DOMChunk).where(DOMChunk.scan_id == scan_id)
        )
        or 0
    )


async def best_effort_save_checkpoint(
    *,
    job_id: uuid.UUID,
    fencing_token: int,
    worker_id: str,
    checkpoint: dict[str, Any],
) -> None:
    try:
        from app.db import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            async with session.begin():
                ok = await save_job_checkpoint(
                    session,
                    job_id=job_id,
                    fencing_token=fencing_token,
                    worker_id=worker_id,
                    checkpoint=checkpoint,
                )
                if not ok:
                    logger.warning(
                        "checkpoint_fenced_write_skipped job_id=%s token=%s",
                        job_id,
                        fencing_token,
                    )
    except Exception as exc:
        logger.warning("checkpoint_persist_failed job_id=%s err=%s", job_id, exc)
