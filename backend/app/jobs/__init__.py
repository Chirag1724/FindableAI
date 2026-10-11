"""Durable scan job queue (PostgreSQL-backed)."""

from app.jobs.errors import FailureCategory, classify_failure
from app.jobs.states import JobStatus, assert_transition, can_transition

__all__ = [
    "FailureCategory",
    "JobStatus",
    "assert_transition",
    "can_transition",
    "classify_failure",
]
