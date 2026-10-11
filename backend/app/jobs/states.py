"""Explicit scan-job lifecycle states and validated transitions."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"


TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.DEAD_LETTER,
    }
)

# Valid directed edges. Recovery of abandoned leases re-enters QUEUED.
_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.CLAIMED, JobStatus.CANCELLED}),
    JobStatus.CLAIMED: frozenset(
        {JobStatus.RUNNING, JobStatus.QUEUED, JobStatus.CANCELLED, JobStatus.FAILED}
    ),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.SUCCEEDED,
            JobStatus.RETRY_SCHEDULED,
            JobStatus.FAILED,
            JobStatus.DEAD_LETTER,
            JobStatus.QUEUED,  # lease recovery
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.RETRY_SCHEDULED: frozenset(
        {JobStatus.QUEUED, JobStatus.CLAIMED, JobStatus.CANCELLED}
    ),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
    JobStatus.DEAD_LETTER: frozenset(),
}


def can_transition(current: str | JobStatus, new: str | JobStatus) -> bool:
    cur = JobStatus(current)
    nxt = JobStatus(new)
    if cur == nxt:
        return True
    return nxt in _TRANSITIONS.get(cur, frozenset())


def assert_transition(current: str | JobStatus, new: str | JobStatus) -> None:
    if not can_transition(current, new):
        raise ValueError(f"invalid job transition: {current!s} -> {new!s}")


def is_terminal(status: str | JobStatus) -> bool:
    return JobStatus(status) in TERMINAL_STATUSES
