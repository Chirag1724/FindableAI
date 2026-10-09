from pydantic import BaseModel, Field


class SubScoreMetric(BaseModel):
    name: str
    weight: float
    score: float = Field(ge=0.0, le=100.0)
    details: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class FScoreBreakdown(BaseModel):
    overall_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Overall Findability F-Score computed via weighted formula",
    )
    grade: str = Field(..., description="Letter grade: A, B, C, D, or F")
    coverage: SubScoreMetric = Field(
        ..., description="Weight: 40% - Ratio of intent queries answered by content"
    )
    contradiction_penalty: SubScoreMetric = Field(
        ..., description="Weight: 30% - Penalty for conflicting facts across DOM chunks"
    )
    structural_clarity: SubScoreMetric = Field(
        ..., description="Weight: 20% - Schema.org JSON-LD microdata & semantic DOM completeness"
    )
    entailment: SubScoreMetric = Field(
        ...,
        description="Weight: 10% - Machine accessibility & factual extractability of core business metadata",
    )
