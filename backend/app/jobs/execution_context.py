"""Per-task job ownership context for fenced durable writes during a pipeline run."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobExecutionContext:
    job_id: uuid.UUID
    scan_id: uuid.UUID
    fencing_token: int
    worker_id: str
    correlation_id: str | None = None


_current_job_ctx: ContextVar[JobExecutionContext | None] = ContextVar(
    "findable_job_execution_ctx", default=None
)


def get_job_execution_context() -> JobExecutionContext | None:
    return _current_job_ctx.get()


@contextmanager
def job_execution_context(ctx: JobExecutionContext) -> Iterator[JobExecutionContext]:
    token = _current_job_ctx.set(ctx)
    try:
        yield ctx
    finally:
        _current_job_ctx.reset(token)
