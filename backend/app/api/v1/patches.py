import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.v1.scans import (
    SCANS_DB,
    ApplyScanPatchRequest,
    apply_scan_patch,
    get_scan,
    parse_github_repo_owner_name,
)
from app.core.auth import verify_api_key
from app.core.rate_limiter import rate_limit_mutating
from app.db import AsyncSessionLocal
from app.models.database import Patch as PatchModel
from app.schemas.patch import PullRequestResult

logger = logging.getLogger(__name__)

router = APIRouter()


class ApplyPatchRequest(BaseModel):
    patch_id: str
    github_repo_url: str
    target_branch: str = "main"


@router.post(
    "/apply-pr",
    response_model=PullRequestResult,
    dependencies=[Depends(verify_api_key), Depends(rate_limit_mutating)],
)
async def apply_patch_as_pr(request: ApplyPatchRequest) -> PullRequestResult:
    """
    Triggers automated GitHub Pull Request creation by delegating to unified scan PR handler.
    Checks in-memory cache and falls back to persistent database to resolve scan context.
    """
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

    # 1. Search in-memory active cache
    matching_scan = None
    for s in SCANS_DB.values():
        for p in s.patches:
            if p.patch_id == request.patch_id:
                matching_scan = s
                break
        if matching_scan:
            break

    # 2. Fallback to database lookup if not present in memory
    if not matching_scan:
        try:
            # Strip 'patch_' prefix if present to match UUID
            raw_id = request.patch_id.removeprefix("patch_")
            async with AsyncSessionLocal() as session:
                # Try exact UUID or prefix match
                stmt = select(PatchModel)
                res = await session.execute(stmt)
                all_patches = res.scalars().all()
                for p_rec in all_patches:
                    if p_rec.id.hex.startswith(raw_id) or str(p_rec.id) == raw_id:
                        # Found matching patch; reconstruct scan via get_scan
                        scan_id_str = f"scan_{p_rec.scan_id.hex}"
                        matching_scan = await get_scan(scan_id_str)
                        break
        except Exception as db_err:
            logger.warning(
                "Database fallback lookup for patch '%s' failed: %s", request.patch_id, db_err
            )

    if matching_scan:
        matching_scan.repo_url = request.github_repo_url
        matching_scan.github_repo_url = request.github_repo_url
        SCANS_DB[matching_scan.scan_id] = matching_scan
        return await apply_scan_patch(
            matching_scan.scan_id,
            payload=ApplyScanPatchRequest(
                repo_url=request.github_repo_url,
                target_branch=request.target_branch,
            ),
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Scan associated with patch '{request.patch_id}' not found.",
    )
