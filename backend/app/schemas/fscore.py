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
        ..., description="Weight: 40% - Ratio of synthetic user queries answered by content"
    )
    entailment: SubScoreMetric = Field(
        ...,
        description="Weight: 35% - Proportion of claims that strictly entail unambiguous factual grounding",
    )
    contradiction_penalty: SubScoreMetric = Field(
        ..., description="Weight: 15% - Penalty for conflicting facts across DOM chunks"
    )
    structural_clarity: SubScoreMetric = Field(
        ..., description="Weight: 10% - Schema.org JSON-LD microdata & semantic DOM completeness"
    )
