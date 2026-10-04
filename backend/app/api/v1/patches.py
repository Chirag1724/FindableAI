import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.v1.scans import SCANS_DB, apply_scan_patch, parse_github_repo_owner_name
from app.schemas.patch import PullRequestResult

logger = logging.getLogger(__name__)

router = APIRouter()


class ApplyPatchRequest(BaseModel):
    patch_id: str
    github_repo_url: str
    target_branch: str = "main"


@router.post("/apply-pr", response_model=PullRequestResult)
async def apply_patch_as_pr(request: ApplyPatchRequest) -> PullRequestResult:
    """Triggers autonomous GitHub Pull Request creation by delegating to unified scan PR handler."""
    if not request.github_repo_url or not request.github_repo_url.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No GitHub repository configured. Provide a valid repo URL to enable automated PR creation.",
        )

    # Validate format upfront using shared parser
    try:
        parse_github_repo_owner_name(request.github_repo_url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Find matching scan in SCANS_DB
    matching_scan = None
    for s in SCANS_DB.values():
        for p in s.patches:
            if p.patch_id == request.patch_id:
                matching_scan = s
                break
        if matching_scan:
            break

    if matching_scan:
        matching_scan.repo_url = request.github_repo_url
        matching_scan.github_repo_url = request.github_repo_url
        return await apply_scan_patch(matching_scan.scan_id)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Scan associated with patch '{request.patch_id}' not found.",
    )
