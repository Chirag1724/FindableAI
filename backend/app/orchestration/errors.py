"""Typed orchestration errors (P2-4.1)."""

from __future__ import annotations


class OrchestrationError(Exception):
    """Base error for DAG orchestration failures."""

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "orchestration_error"
        super().__init__(message)


class InvalidStateTransitionError(OrchestrationError):
    def __init__(self, message: str, *, from_state: str, to_state: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(message, reason="invalid_transition")


class MissingStageInputError(OrchestrationError):
    def __init__(self, message: str, *, stage: str) -> None:
        self.stage = stage
        super().__init__(message, reason="missing_stage_input")


class StageExecutionError(OrchestrationError):
    def __init__(self, message: str, *, stage: str, reason: str | None = None) -> None:
        self.stage = stage
        super().__init__(message, reason=reason or "stage_execution_error")
