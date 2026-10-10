from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PatchType(StrEnum):
    CONTENT_CLARIFICATION = "content_clarification"
    SCHEMA_MICRODATA = "schema_microdata"
    HEADING_STRUCTURE = "heading_structure"
    FACTUAL_CONFLICT_RESOLUTION = "factual_conflict_resolution"
    ROBOTS_GOVERNANCE = "robots_governance"
    LLMS_MANIFEST = "llms_manifest"


class DOMSelectorAnchor(BaseModel):
    css_selector: str = Field(..., description="Precise CSS selector path to target DOM node")
    tag_name: str
    original_snippet: str
    suggested_snippet: str


class AuxiliaryFile(BaseModel):
    file_path: str = Field(..., description="Path to new auxiliary file in repository")
    content: str = Field(..., description="Source code content")
    action: str = Field(default="create", description="Action to perform: create | modify | delete")


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
    target_file: str | None = Field(
        default=None,
        description="Path to target file in repository, e.g. frontend/src/app/layout.tsx",
    )
    code_diff: str | None = Field(
        default=None,
        description="Framework-native unified git diff against repository source",
    )
    auxiliary_files: list[AuxiliaryFile] = Field(
        default_factory=list,
        description="Associated new files such as React components",
    )
    framework: str | None = Field(
        default=None,
        description="Detected repository framework, e.g. nextjs_app_router",
    )
    is_synthetic: bool = Field(
        default=False,
        description=(
            "True when this patch is a demo/mock artifact and must not be treated "
            "as evidence-backed remediation"
        ),
    )


class PullRequestResult(BaseModel):
    pr_url: str
    pr_number: int
    branch_name: str
    title: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
