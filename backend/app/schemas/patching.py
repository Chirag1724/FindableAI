"""Patch-engine contracts for prioritization (P2-3.1).

Prioritization only — no JSON-LD, diffs, projected scores, or GitHub artifacts.
Reuses ``EvidenceReference``, ``IntentEvaluation``, ``Contradiction``, and
``SchemaOrgReport`` / ``ScoreBreakdown`` from the intelligence layer.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.intelligence import Contradiction, EvidenceReference, IntentEvaluation
from app.schemas.scoring import SchemaOrgReport, ScoreBreakdown


class RemediationKind(StrEnum):
    """Controlled remediation opportunity kinds (auditable patch engine)."""

    INFORMATION_GAP = "INFORMATION_GAP"
    MISSING_SCHEMA = "MISSING_SCHEMA"
    CONTRADICTION = "CONTRADICTION"


class SchemaRemediationTarget(StrEnum):
    """Required Schema.org types the initial patch engine may target."""

    LOCAL_BUSINESS = "LocalBusiness"
    POSTAL_ADDRESS = "PostalAddress"
    OPENING_HOURS = "OpeningHoursSpecification"
    GEO_COORDINATES = "GeoCoordinates"
    MENU = "Menu"
    FAQ_PAGE = "FAQPage"


class RemediationEvidence(BaseModel):
    """Provenance linking an opportunity back to intelligence outputs."""

    intent_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    schema_types: list[str] = Field(default_factory=list)
    evidence_references: list[EvidenceReference] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    dom_paths: list[str] = Field(default_factory=list)
    schema_issues: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RemediationOpportunity(BaseModel):
    """A ranked remediation candidate (no patch payload)."""

    opportunity_id: str = Field(..., min_length=1)
    kind: RemediationKind
    title: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    impact: float = Field(..., ge=0.0, le=100.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    difficulty: int = Field(..., ge=1, le=5)
    priority: float = Field(..., ge=0.0)
    evidence: RemediationEvidence = Field(default_factory=RemediationEvidence)
    schema_target: SchemaRemediationTarget | None = None
    related_intent_ids: list[str] = Field(default_factory=list)
    related_contradiction_ids: list[str] = Field(default_factory=list)
    dedupe_key: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _priority_matches_formula(self) -> RemediationOpportunity:
        expected = (self.impact * self.confidence) / float(self.difficulty)
        if abs(self.priority - expected) > 1e-9:
            raise ValueError(
                f"priority must equal (impact * confidence) / difficulty; "
                f"got {self.priority}, expected {expected}"
            )
        return self


class PatchPrioritizerInput(BaseModel):
    """Typed inputs for deterministic prioritization (no I/O)."""

    intent_evaluations: list[IntentEvaluation] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    score_breakdown: ScoreBreakdown | None = None
    schema_report: SchemaOrgReport | None = None

    @field_validator("intent_evaluations")
    @classmethod
    def _validate_intents(cls, value: list[IntentEvaluation]) -> list[IntentEvaluation]:
        for item in value:
            if not isinstance(item, IntentEvaluation):
                raise TypeError("intent_evaluations must contain IntentEvaluation instances")
        return value

    @field_validator("contradictions")
    @classmethod
    def _validate_contradictions(cls, value: list[Contradiction]) -> list[Contradiction]:
        for item in value:
            if not isinstance(item, Contradiction):
                raise TypeError("contradictions must contain Contradiction instances")
        return value


class PatchPrioritizationResult(BaseModel):
    """Top-N remediation opportunities (N ≤ 3)."""

    opportunities: list[RemediationOpportunity] = Field(default_factory=list, max_length=3)
    total_candidates: int = Field(..., ge=0)
    selected_count: int = Field(..., ge=0, le=3)

    @model_validator(mode="after")
    def _selected_matches_list(self) -> PatchPrioritizationResult:
        if self.selected_count != len(self.opportunities):
            raise ValueError("selected_count must equal len(opportunities)")
        if self.selected_count > self.total_candidates:
            raise ValueError("selected_count cannot exceed total_candidates")
        return self
