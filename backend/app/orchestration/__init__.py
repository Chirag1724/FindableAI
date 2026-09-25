"""Orchestration package — P2-4.1 DAG state machine."""

from app.orchestration.dag import FindableAIDAG, ObservationInput, run_scan
from app.orchestration.errors import (
    InvalidStateTransitionError,
    MissingStageInputError,
    OrchestrationError,
    StageExecutionError,
)
from app.orchestration.result import OrchestrationResult
from app.orchestration.state import LEGAL_TRANSITIONS, ScanContext, ScanPhase, transition

__all__ = [
    "LEGAL_TRANSITIONS",
    "FindableAIDAG",
    "InvalidStateTransitionError",
    "MissingStageInputError",
    "ObservationInput",
    "OrchestrationError",
    "OrchestrationResult",
    "ScanContext",
    "ScanPhase",
    "StageExecutionError",
    "run_scan",
    "transition",
]
