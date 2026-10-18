import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.v1.scans import (
    SCANS_DB,
    ApplyScanPatchRequest,
    _tenant_from_request,
    apply_scan_patch,
    get_scan_for_tenant,
    parse_github_repo_owner_name,
)
from app.core.auth import verify_api_key
from app.core.permissions import OrgAction, assert_permission
from app.core.rate_limiter import rate_limit_mutating
from app.core.tenancy import assert_scan_org_access, get_scan_for_org
from app.db import AsyncSessionLocal
from app.models.database import Patch as PatchModel
from app.models.database import Scan as ScanModel
from app.schemas.patch import PullRequestResult

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


class ApplyPatchRequest(BaseModel):
    patch_id: str
    github_repo_url: str
    target_branch: str = "main"


@router.post(
    "/apply-pr",
    response_model=PullRequestResult,
    dependencies=[Depends(rate_limit_mutating)],
)
async def apply_patch_as_pr(
    body: ApplyPatchRequest,
    http_request: Request,
) -> PullRequestResult:
    """
    Triggers automated GitHub Pull Request creation by delegating to unified scan PR handler.
    Checks in-memory cache and falls back to persistent database to resolve scan context.
    """
    tenant = _tenant_from_request(http_request)
    assert_permission(tenant, OrgAction.RUN_REMEDIATION)

    if not body.github_repo_url or not body.github_repo_url.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No GitHub repository configured. Provide a valid repo URL to enable automated PR creation.",
        )

    try:
        parse_github_repo_owner_name(body.github_repo_url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    matching_scan = None
    for s in SCANS_DB.values():
        mem_org: uuid.UUID | None = None
        if getattr(s, "org_id", None):
            try:
                mem_org = uuid.UUID(str(s.org_id))
            except ValueError:
                mem_org = None
        try:
            assert_scan_org_access(scan_org_id=mem_org, tenant=tenant)
        except HTTPException:
            continue
        for p in s.patches:
            if p.patch_id == body.patch_id:
                matching_scan = s
                break
        if matching_scan:
            break

    if not matching_scan:
        try:
            raw_id = body.patch_id.removeprefix("patch_")
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(PatchModel, ScanModel)
                    .join(ScanModel, PatchModel.scan_id == ScanModel.id)
                    .where(PatchModel.scan_id == ScanModel.id)
                )
                if not tenant.is_system_admin:
                    if tenant.org_id is None:
                        raise HTTPException(status_code=404, detail="Scan not found")
                    stmt = stmt.where(ScanModel.org_id == tenant.org_id)
                res = await session.execute(stmt)
                for p_rec, scan_row in res.all():
                    if p_rec.id.hex.startswith(raw_id) or str(p_rec.id) == raw_id:
                        await get_scan_for_org(session, scan_row.id, tenant)
                        scan_id_str = f"scan_{p_rec.scan_id.hex}"
                        matching_scan = await get_scan_for_tenant(scan_id_str, tenant)
                        break
        except HTTPException:
            raise
        except Exception as db_err:
            logger.warning(
                "Database fallback lookup for patch failed: %s",
                type(db_err).__name__,
            )

    if matching_scan:
        matching_scan.repo_url = body.github_repo_url
        matching_scan.github_repo_url = body.github_repo_url
        SCANS_DB[matching_scan.scan_id] = matching_scan
        return await apply_scan_patch(
            matching_scan.scan_id,
            http_request,
            payload=ApplyScanPatchRequest(
                repo_url=body.github_repo_url,
                target_branch=body.target_branch,
            ),
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Scan associated with patch not found.",
    )
