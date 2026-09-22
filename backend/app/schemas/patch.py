from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PatchType(StrEnum):
    CONTENT_CLARIFICATION = "content_clarification"
    SCHEMA_MICRODATA = "schema_microdata"
    HEADING_STRUCTURE = "heading_structure"
    FACTUAL_CONFLICT_RESOLUTION = "factual_conflict_resolution"


class DOMSelectorAnchor(BaseModel):
    css_selector: str = Field(..., description="Precise CSS selector path to target DOM node")
    tag_name: str
    original_snippet: str
    suggested_snippet: str


class PatchProposal(BaseModel):
    patch_id: str
    patch_type: PatchType
    title: str
    rationale: str
    impact_score_delta: float = Field(
        ..., description="Estimated F-Score improvement if this patch is applied"
    )
    dom_anchor: DOMSelectorAnchor
    unified_diff: str = Field(..., description="Standard git-compatible unified diff format")
    applied: bool = False


class PullRequestResult(BaseModel):
    pr_url: str
    pr_number: int
    branch_name: str
    title: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
