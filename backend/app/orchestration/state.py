"""Scan phase state machine and scan-scoped context (P2-4.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.orchestration.errors import InvalidStateTransitionError
from app.schemas.github_pr import PREngineResult
from app.schemas.intelligence import Contradiction, IntentBatch, IntentEvaluation
from app.schemas.patching import (
    BusinessFacts,
    FormattedPatch,
    GeneratedJsonLd,
    JsonLdSkip,
    PatchPrioritizationResult,
    ProjectedScoreResult,
    RemediationOpportunity,
)
from app.schemas.scoring import SchemaOrgReport, ScoreBreakdown


class ScanPhase(StrEnum):
    OBSERVE = "OBSERVE"
    PLAN = "PLAN"
    ACT = "ACT"
    VERIFY = "VERIFY"
    REFLECT = "REFLECT"
    STOP = "STOP"


LEGAL_TRANSITIONS: dict[ScanPhase, frozenset[ScanPhase]] = {
    ScanPhase.OBSERVE: frozenset({ScanPhase.PLAN}),
    ScanPhase.PLAN: frozenset({ScanPhase.ACT}),
    ScanPhase.ACT: frozenset({ScanPhase.VERIFY}),
    ScanPhase.VERIFY: frozenset({ScanPhase.REFLECT}),
    ScanPhase.REFLECT: frozenset({ScanPhase.STOP}),
    ScanPhase.STOP: frozenset(),
}


def transition(current: ScanPhase, nxt: ScanPhase) -> ScanPhase:
    """Authoritative legal transition. Rejects invalid edges."""
    allowed = LEGAL_TRANSITIONS.get(current, frozenset())
    if nxt not in allowed:
        raise InvalidStateTransitionError(
            f"illegal transition {current.value} -> {nxt.value}",
            from_state=current.value,
            to_state=nxt.value,
        )
    return nxt


@dataclass
class OrchestrationChunk:
    """Evidence chunk satisfying contradiction EvidenceChunk + scorer TextChunk."""

    id: str
    url: str
    dom_path: str
    content: str
    tag: str = "p"
    word_count: int = 0


@dataclass
class ScanContext:
    """Scan-scoped runtime bag. No secrets/tokens."""

    scan_id: str
    business_context: str
    chunks: list[OrchestrationChunk] = field(default_factory=list)
    html_documents: list[str] = field(default_factory=list)
    business_facts: BusinessFacts = field(default_factory=BusinessFacts)
    state: ScanPhase = ScanPhase.OBSERVE
    completed_stages: list[str] = field(default_factory=list)

    intents: IntentBatch | None = None
    evaluations: list[IntentEvaluation] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    schema_report: SchemaOrgReport | None = None
    score: ScoreBreakdown | None = None

    prioritization: PatchPrioritizationResult | None = None
    opportunities: list[RemediationOpportunity] = field(default_factory=list)
    generated_jsonld: list[GeneratedJsonLd] = field(default_factory=list)
    jsonld_skipped: list[JsonLdSkip] = field(default_factory=list)
    patches: list[FormattedPatch] = field(default_factory=list)
    projected_scores: list[ProjectedScoreResult] = field(default_factory=list)
    pr_body: str | None = None
    pr_result: PREngineResult | None = None

    create_pr: bool = False
    source_repo: str | None = None
    target_branch: str = "main"
    html_file_path: str = "index.html"
    remediation_available: bool = False
    stage_trace: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    def advance(self, nxt: ScanPhase) -> None:
        self.state = transition(self.state, nxt)
