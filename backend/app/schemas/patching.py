"""Patch-engine contracts for prioritization (P2-3.1).

Prioritization only — no JSON-LD, diffs, projected scores, or GitHub artifacts.
Reuses ``EvidenceReference``, ``IntentEvaluation``, ``Contradiction``, and
``SchemaOrgReport`` / ``ScoreBreakdown`` from the intelligence layer.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

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


# ---------------------------------------------------------------------------
# P2-3.2 / P2-3.3 / P2-3.4 — generation, formatting, projected score
# ---------------------------------------------------------------------------

SCHEMA_ORG_CONTEXT = "https://schema.org"


class FaqEntry(BaseModel):
    """Evidence-backed FAQ pair (never invent answers)."""

    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    source_intent_id: str | None = None


class OpeningHoursFact(BaseModel):
    day_of_week: str = Field(..., min_length=1)
    opens: str = Field(..., min_length=1)
    closes: str = Field(..., min_length=1)


class MenuItemFact(BaseModel):
    name: str = Field(..., min_length=1)
    price: str | None = None


class BusinessFacts(BaseModel):
    """Trusted, evidence-backed facts supplied to the JSON-LD generator.

    The generator never invents values. Omit fields that lack evidence.
    """

    name: str | None = None
    telephone: str | None = None
    email: str | None = None
    street_address: str | None = None
    address_locality: str | None = None
    address_region: str | None = None
    postal_code: str | None = None
    address_country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    opening_hours: list[OpeningHoursFact] = Field(default_factory=list)
    menu_name: str | None = None
    menu_items: list[MenuItemFact] = Field(default_factory=list)
    faq_entries: list[FaqEntry] = Field(default_factory=list)


class GeneratedJsonLd(BaseModel):
    """One controlled Schema.org JSON-LD document for a remediation opportunity."""

    opportunity_id: str = Field(..., min_length=1)
    schema_type: SchemaRemediationTarget
    payload: dict[str, Any]
    json_text: str = Field(..., min_length=1)
    related_intent_ids: list[str] = Field(default_factory=list)
    related_contradiction_ids: list[str] = Field(default_factory=list)
    evidence_notes: list[str] = Field(default_factory=list)


class JsonLdSkip(BaseModel):
    """Deterministic skip when evidence is insufficient or kind is unsupported."""

    opportunity_id: str = Field(..., min_length=1)
    schema_type: SchemaRemediationTarget | None = None
    reason: str = Field(..., min_length=1)


class JsonLdGenerationResult(BaseModel):
    generated: list[GeneratedJsonLd] = Field(default_factory=list)
    skipped: list[JsonLdSkip] = Field(default_factory=list)


class PatchFormatStatus(StrEnum):
    APPLIED = "applied"
    NOOP = "noop"
    CONFLICT = "conflict"
    ERROR = "error"


class FormattedPatch(BaseModel):
    opportunity_id: str = Field(..., min_length=1)
    schema_type: SchemaRemediationTarget
    file_path: str = Field(..., min_length=1)
    patch_text: str = Field(default="")
    changed_lines: int = Field(default=0, ge=0)
    insertion_location: str = Field(default="")
    is_noop: bool = False
    status: PatchFormatStatus
    message: str = Field(default="")
    patched_html: str | None = None


class PatchFormatResult(BaseModel):
    patches: list[FormattedPatch] = Field(default_factory=list)


class ProjectedScoreResult(BaseModel):
    """Per-opportunity projection via the existing Phase E scorer."""

    opportunity_id: str = Field(..., min_length=1)
    schema_type: SchemaRemediationTarget | None = None
    current_score: float = Field(..., ge=0.0, le=100.0)
    projected_score: float = Field(..., ge=0.0, le=100.0)
    delta: float
    current_breakdown: ScoreBreakdown
    projected_breakdown: ScoreBreakdown
    patch_reference: str | None = None

    @model_validator(mode="after")
    def _delta_matches(self) -> ProjectedScoreResult:
        expected = self.projected_score - self.current_score
        if abs(self.delta - expected) > 1e-9:
            raise ValueError(
                f"delta must equal projected_score - current_score; "
                f"got {self.delta}, expected {expected}"
            )
        return self


class ProjectedScoreBatchResult(BaseModel):
    """Independent projections for multiple opportunities (not cumulative)."""

    projections: list[ProjectedScoreResult] = Field(default_factory=list)
