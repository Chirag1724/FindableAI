"""Organization membership management (Phase 3).

Plan-tier quotas are out of scope — ``plan_tier`` is a label only.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.auth import TenantContext, verify_api_key
from app.core.membership import remove_member, set_member_role
from app.core.permissions import OrgAction, assert_permission, normalize_role
from app.core.rate_limiter import rate_limit_mutating
from app.db import AsyncSessionLocal
from app.models.database import OrgMembership

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _tenant(request: Request) -> TenantContext:
    tenant = getattr(request.state, "tenant", None)
    if not isinstance(tenant, TenantContext):
        raise HTTPException(status_code=401, detail="Missing tenant context")
    return tenant


class MembershipOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    user_id: uuid.UUID
    role: str


class SetRoleRequest(BaseModel):
    role: str = Field(..., min_length=3, max_length=50)
    actor_user_id: uuid.UUID | None = None


@router.get("/{org_id}/members", response_model=list[MembershipOut])
async def list_members(org_id: uuid.UUID, request: Request) -> list[MembershipOut]:
    tenant = _tenant(request)
    assert_permission(tenant, OrgAction.MANAGE_MEMBERS)
    if tenant.org_id is not None and tenant.org_id != org_id and not tenant.is_system_admin:
        raise HTTPException(status_code=404, detail="Organization not found")
    async with AsyncSessionLocal() as session:
        rows = (
            (await session.execute(select(OrgMembership).where(OrgMembership.org_id == org_id)))
            .scalars()
            .all()
        )
        return [
            MembershipOut(id=r.id, org_id=r.org_id, user_id=r.user_id, role=r.role) for r in rows
        ]


@router.patch(
    "/{org_id}/members/{user_id}",
    dependencies=[Depends(rate_limit_mutating)],
)
async def change_member_role(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: SetRoleRequest,
    request: Request,
) -> dict[str, Any]:
    tenant = _tenant(request)
    # Role from body is the *target* role being assigned, not the caller's role.
    _ = normalize_role(body.role)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await set_member_role(
                session,
                tenant=tenant,
                org_id=org_id,
                target_user_id=user_id,
                new_role=body.role,
                actor_user_id=body.actor_user_id,
            )
    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason": result.reason, "action": OrgAction.MANAGE_MEMBERS.value},
        )
    return {"ok": True, "role": normalize_role(body.role).value}


@router.delete(
    "/{org_id}/members/{user_id}",
    dependencies=[Depends(rate_limit_mutating)],
)
async def delete_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    actor_user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    tenant = _tenant(request)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await remove_member(
                session,
                tenant=tenant,
                org_id=org_id,
                target_user_id=user_id,
                actor_user_id=actor_user_id,
            )
    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason": result.reason, "action": OrgAction.MANAGE_MEMBERS.value},
        )
    return {"ok": True}
