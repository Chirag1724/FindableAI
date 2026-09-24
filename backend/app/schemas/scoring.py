"""Scorer / Schema.org report contracts (Phase E).

Coexist with API ``FScoreBreakdown`` in ``fscore.py``. These models use the
intelligence-pipeline field names ``f_score``, ``s_ans``, ``s_con``, ``s_str``,
``s_acc`` compatible with ``ScanResult``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

WEIGHT_SUM_TOLERANCE = 1e-9


class ScoreWeights(BaseModel):
    """
    Configurable F-score component weights.

    TEAM DECISION REQUIRED: production defaults below mirror docs/04 and
    docs/01 (0.40 / 0.30 / 0.20 / 0.10) as a *provisional* configuration only.
    README.md currently documents a different formulation. Canonical production
    weights require team confirmation — change only this model / factory when
    decided; do not scatter literals across scorers.
    """

    w_ans: float = Field(default=0.40, ge=0.0)
    w_con: float = Field(default=0.30, ge=0.0)
    w_str: float = Field(default=0.20, ge=0.0)
    w_acc: float = Field(default=0.10, ge=0.0)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> ScoreWeights:
        total = self.w_ans + self.w_con + self.w_str + self.w_acc
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"ScoreWeights must sum to 1.0 (±{WEIGHT_SUM_TOLERANCE}); got {total}")
        return self


class ContradictionSeverityWeights(BaseModel):
    """Relative impact of contradiction severities on S_con (configurable)."""

    hard: float = Field(default=1.0, ge=0.0)
    soft: float = Field(default=0.5, ge=0.0)


class SchemaTypeResult(BaseModel):
    schema_type: str
    present: bool
    valid: bool
    occurrences: int = Field(ge=0)
    source_count: int = Field(ge=0)
    issues: list[str] = Field(default_factory=list)


class SchemaOrgReport(BaseModel):
    total_blocks: int = Field(ge=0)
    valid_blocks: int = Field(ge=0)
    invalid_blocks: int = Field(ge=0)
    malformed_blocks: int = Field(ge=0)
    required_types: list[str]
    types: list[SchemaTypeResult]
    score: float = Field(ge=0.0, le=100.0)
    issues: list[str] = Field(default_factory=list)

    @field_validator("types")
    @classmethod
    def _stable_type_order(cls, value: list[SchemaTypeResult]) -> list[SchemaTypeResult]:
        return sorted(value, key=lambda item: item.schema_type)


class ComponentDiagnostics(BaseModel):
    """Explainable per-component diagnostics (only include supported signals)."""

    details: dict[str, Any] = Field(default_factory=dict)


class ScoreBreakdown(BaseModel):
    """Deterministic Findability score breakdown (ScanResult-compatible fields)."""

    f_score: float = Field(ge=0.0, le=100.0)
    s_ans: float = Field(ge=0.0, le=100.0)
    s_con: float = Field(ge=0.0, le=100.0)
    s_str: float = Field(ge=0.0, le=100.0)
    s_acc: float = Field(ge=0.0, le=100.0)
    weights: ScoreWeights
    schema_report: SchemaOrgReport
    diagnostics: dict[str, Any] = Field(default_factory=dict)
