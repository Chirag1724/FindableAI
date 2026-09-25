"""State-machine unit tests for P2-4.1."""

from __future__ import annotations

import pytest

from app.orchestration.errors import InvalidStateTransitionError
from app.orchestration.state import LEGAL_TRANSITIONS, ScanContext, ScanPhase, transition


def test_initial_context_state_is_observe():
    ctx = ScanContext(scan_id="s1", business_context="x" * 40)
    assert ctx.state is ScanPhase.OBSERVE


def test_legal_happy_path_transitions():
    current = ScanPhase.OBSERVE
    for nxt in (
        ScanPhase.PLAN,
        ScanPhase.ACT,
        ScanPhase.VERIFY,
        ScanPhase.REFLECT,
        ScanPhase.STOP,
    ):
        current = transition(current, nxt)
    assert current is ScanPhase.STOP


def test_context_advance_happy_path():
    ctx = ScanContext(scan_id="s1", business_context="x" * 40)
    ctx.advance(ScanPhase.PLAN)
    ctx.advance(ScanPhase.ACT)
    ctx.advance(ScanPhase.VERIFY)
    ctx.advance(ScanPhase.REFLECT)
    ctx.advance(ScanPhase.STOP)
    assert ctx.state is ScanPhase.STOP


@pytest.mark.parametrize(
    ("start", "bad"),
    [
        (ScanPhase.OBSERVE, ScanPhase.VERIFY),
        (ScanPhase.PLAN, ScanPhase.STOP),
        (ScanPhase.ACT, ScanPhase.OBSERVE),
        (ScanPhase.REFLECT, ScanPhase.ACT),
        (ScanPhase.VERIFY, ScanPhase.PLAN),
        (ScanPhase.STOP, ScanPhase.OBSERVE),
    ],
)
def test_invalid_transitions_raise(start: ScanPhase, bad: ScanPhase):
    with pytest.raises(InvalidStateTransitionError) as exc:
        transition(start, bad)
    assert exc.value.from_state == start.value
    assert exc.value.to_state == bad.value
    assert bad not in LEGAL_TRANSITIONS[start]


def test_stop_has_no_outgoing_edges():
    assert LEGAL_TRANSITIONS[ScanPhase.STOP] == frozenset()
