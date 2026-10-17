"""AI/ML pipeline Pydantic contracts (Person 2 intelligence layer).

These models are the structured I/O for intent generation, NLI evaluation,
contradiction detection, and scan aggregation. They coexist with the HTTP API
contracts in ``scan.py``, ``fscore.py``, and ``patch.py`` (``ScanResponse``,
``FScoreBreakdown``, ``PatchProposal``) and do not replace them.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class IntentCategory(StrEnum):
    """Ten taxonomy classes used by the intent generator."""

    ELIGIBILITY = "eligibility"
    POLICY = "policy"
    AVAILABILITY = "availability"
    PRICING = "pricing"
    ACCESSIBILITY = "accessibility"
    COMMERCIAL = "commercial"
    LOCAL = "local"
    TRANSACTIONAL = "transactional"
    TRUST = "trust"
    EDGE_CASES = "edge_cases"


class EntailmentStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"


class ContradictionSeverity(StrEnum):
    HARD_CONTRADICTION = "HARD_CONTRADICTION"
    SOFT_INCONSISTENCY = "SOFT_INCONSISTENCY"


class IntentQuery(BaseModel):
    intent_id: str = Field(..., min_length=1, description="Stable id, e.g. eligibility_01")
    category: IntentCategory
    query: str = Field(..., min_length=1, description="Customer / AI-search question")
    difficulty: Literal["easy", "medium", "hard"]
    expected_evidence_type: str = Field(
        ...,
        min_length=1,
        description="Where the answer should appear, e.g. menu table, FAQ section",
    )
    persona: str | None = Field(
        default=None, description="Originating persona: cto, developer, or procurement"
    )

    @field_validator("difficulty", mode="before")
    @classmethod
    def _normalize_difficulty(cls, v: Any) -> str:
        if isinstance(v, str):
            v_lower = v.strip().lower()
            if v_lower in ("easy", "low", "simple", "basic"):
                return "easy"
            if v_lower in ("hard", "high", "complex", "difficult", "advanced"):
                return "hard"
            return "medium"
        return "medium"


class IntentBatch(BaseModel):
    business_type: str = Field(..., min_length=1, description="Inferred business category")
    queries: list[IntentQuery] = Field(
        ...,
        min_length=30,
        max_length=30,
        description="Batch of 30 intent queries (3 per taxonomy category)",
    )


class PersonaIntentBatch(BaseModel):
    business_type: str = Field(..., min_length=1, description="Inferred business category")
    queries: list[IntentQuery] = Field(
        ...,
        min_length=10,
        max_length=10,
        description="10 intent queries: exactly 1 per taxonomy category for the assigned persona",
    )


class EvidenceReference(BaseModel):
    """Citation to a retrieved DOM chunk used during entailment judging."""

    chunk_id: str = Field(..., min_length=1)
    dom_path: str = Field(..., min_length=1)
    url: str | None = None
    rank: int | None = Field(default=None, ge=1)
    rrf_score: float | None = Field(default=None, ge=0.0)
    excerpt: str | None = None


class IntentEvaluation(BaseModel):
    intent_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    # Grounding anchor: model extracts verbatim evidence quote before classification
    verbatim_quote: str | None = Field(
        default=None,
        description="Exact verbatim sentence or table cell copied from the evidence. None if not found.",
    )
    cited_chunk_id: str | None = Field(
        default=None,
        description="UUID/ID of the chunk that contains the verbatim_quote.",
    )
    status: EntailmentStatus
    reasoning: str = Field(..., min_length=1)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    category: IntentCategory | None = Field(default=None, description="Intent taxonomy category")
    persona: str | None = Field(
        default=None, description="Originating persona: cto, developer, or procurement"
    )

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v: Any) -> Any:
        if isinstance(v, list) and v:
            v = v[0]
        if isinstance(v, str):
            v_clean = v.strip().upper()
            if v_clean in EntailmentStatus._value2member_map_:
                return EntailmentStatus(v_clean)
        return v

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v: Any) -> Any:
        if isinstance(v, list) and v:
            v = v[0]
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean in IntentCategory._value2member_map_:
                return IntentCategory(v_clean)
            return None
        return v

    @field_validator("persona", mode="before")
    @classmethod
    def _normalize_persona(cls, v: Any) -> Any:
        if isinstance(v, list) and v:
            v = v[0]
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @property
    def evidence_chunk_ids(self) -> list[str]:
        return [item.chunk_id for item in self.evidence]

    @property
    def cited_dom_paths(self) -> list[str]:
        return [item.dom_path for item in self.evidence]


class IntentEvaluationBatch(BaseModel):
    evaluations: list[IntentEvaluation] = Field(
        ...,
        description="Batch of evaluated intent claims grounded in evidence",
    )


class Contradiction(BaseModel):
    entity: str = Field(..., min_length=1, description="Normalized entity key, e.g. opening_hours")
    conflict: str = Field(..., min_length=1, description="Human-readable conflict summary")
    values: list[Any] = Field(..., min_length=2, description="Conflicting values across pages")
    severity: ContradictionSeverity
    source_urls: list[str] = Field(default_factory=list)
    dom_paths: list[str] = Field(default_factory=list)
    contradiction_id: str | None = None


class Patch(BaseModel):
    """Intelligence-pipeline patch artifact (distinct from API ``PatchProposal``)."""

    patch_id: str = Field(..., min_length=1)
    file_path: str = Field(..., min_length=1)
    patch_type: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1, description="Unified diff or JSON-LD payload")
    priority: int = Field(..., ge=1)
    rationale: str | None = None
    impact_score_delta: float | None = None
    pr_url: str | None = None


class ScanResult(BaseModel):
    """Aggregated intelligence output for a completed (or in-progress) scan."""

    scan_id: str = Field(..., min_length=1)
    status: Literal["completed", "in_progress", "failed"]
    f_score: float = Field(..., ge=0.0, le=100.0)
    s_ans: float = Field(..., ge=0.0, le=100.0)
    s_con: float = Field(..., ge=0.0, le=100.0)
    s_str: float = Field(..., ge=0.0, le=100.0)
    s_acc: float = Field(..., ge=0.0, le=100.0)
    intents: list[IntentEvaluation] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    patches: list[Patch] = Field(default_factory=list)

    @field_validator("scan_id")
    @classmethod
    def _scan_id_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("scan_id must not be blank")
        return cleaned
