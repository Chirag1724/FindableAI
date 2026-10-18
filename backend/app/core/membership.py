"""Org membership mutations with last-owner and no-self-escalation rules.

Roles on ``org_memberships`` are the human-user source of truth. API keys carry
a mirrored ``role`` used at request time. Removing a member revokes that user's
keys for the org so active SSE/sessions fail on the next DB re-validation.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import TenantContext
from app.core.permissions import OrgAction, OrgRole, assert_permission, normalize_role
from app.models.database import ApiKey, OrgMembership

logger = logging.getLogger(__name__)

_ROLE_RANK = {
    OrgRole.VIEWER: 0,
    OrgRole.MEMBER: 1,
    OrgRole.ADMIN: 2,
    OrgRole.OWNER: 3,
}


@dataclass(frozen=True, slots=True)
class MembershipMutationResult:
    ok: bool
    reason: str | None = None


async def count_owners(session: AsyncSession, org_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(OrgMembership)
            .where(OrgMembership.org_id == org_id, OrgMembership.role == OrgRole.OWNER.value)
        )
        or 0
    )


async def get_membership(
    session: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID
) -> OrgMembership | None:
    result = await session.scalar(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id, OrgMembership.user_id == user_id
        )
    )
    return result if isinstance(result, OrgMembership) else None


def _deny(reason: str) -> MembershipMutationResult:
    return MembershipMutationResult(ok=False, reason=reason)


async def set_member_role(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    org_id: uuid.UUID,
    target_user_id: uuid.UUID,
    new_role: str,
    actor_user_id: uuid.UUID | None = None,
) -> MembershipMutationResult:
    """Change a member's role. Blocks self-escalation and demoting the last owner."""
    assert_permission(tenant, OrgAction.MANAGE_MEMBERS)
    if tenant.org_id is not None and tenant.org_id != org_id and not tenant.is_system_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    desired = normalize_role(new_role)
    actor_role = normalize_role(tenant.role)
    if actor_user_id is not None and actor_user_id == target_user_id:
        # Cannot escalate (or otherwise change) own role via this path.
        if _ROLE_RANK[desired] > _ROLE_RANK[actor_role]:
            return _deny("self_escalation_forbidden")
        return _deny("self_role_change_forbidden")

    # Non-owners cannot grant owner.
    if desired is OrgRole.OWNER and actor_role is not OrgRole.OWNER and not tenant.is_system_admin:
        return _deny("cannot_grant_owner")

    membership = await get_membership(session, org_id=org_id, user_id=target_user_id)
    if membership is None:
        return _deny("membership_not_found")

    prior = normalize_role(membership.role)
    if prior is OrgRole.OWNER and desired is not OrgRole.OWNER:
        if await count_owners(session, org_id) <= 1:
            return _deny("last_owner_protected")

    membership.role = desired.value
    await session.flush()
    logger.info(
        "membership_role_changed org_id=%s user_id=%s from=%s to=%s by_key=%s",
        org_id,
        target_user_id,
        prior.value,
        desired.value,
        tenant.api_key_id,
    )
    return MembershipMutationResult(ok=True)


async def remove_member(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    org_id: uuid.UUID,
    target_user_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> MembershipMutationResult:
    """Remove membership and revoke org API keys so access ends immediately."""
    assert_permission(tenant, OrgAction.MANAGE_MEMBERS)
    if tenant.org_id is not None and tenant.org_id != org_id and not tenant.is_system_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    if actor_user_id is not None and actor_user_id == target_user_id:
        return _deny("cannot_remove_self_via_manage")

    membership = await get_membership(session, org_id=org_id, user_id=target_user_id)
    if membership is None:
        return _deny("membership_not_found")

    if normalize_role(membership.role) is OrgRole.OWNER:
        if await count_owners(session, org_id) <= 1:
            return _deny("last_owner_protected")

    await session.delete(membership)
    # Immediate access loss: revoke every active API key bound to this user+org.
    now = datetime.now(UTC)
    result = await session.execute(
        update(ApiKey)
        .where(
            ApiKey.org_id == org_id,
            ApiKey.user_id == target_user_id,
            ApiKey.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    revoked = int(getattr(result, "rowcount", 0) or 0)
    await session.flush()
    logger.info(
        "membership_removed org_id=%s user_id=%s keys_revoked=%s by_key=%s",
        org_id,
        target_user_id,
        revoked,
        tenant.api_key_id,
    )
    return MembershipMutationResult(ok=True)


async def revoke_api_key(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    key_id: uuid.UUID,
) -> MembershipMutationResult:
    """Revoke an org API key (manage_members). Access fails on next auth / SSE recheck."""
    assert_permission(tenant, OrgAction.MANAGE_MEMBERS)
    row = await session.get(ApiKey, key_id)
    if row is None:
        return _deny("api_key_not_found")
    if tenant.org_id is not None and row.org_id != tenant.org_id and not tenant.is_system_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await session.flush()
    return MembershipMutationResult(ok=True)


async def api_key_still_active(session: AsyncSession, api_key_id: uuid.UUID | None) -> bool:
    """Used by SSE to re-validate that the principal was not revoked mid-stream."""
    if api_key_id is None:
        return False
    row = await session.get(ApiKey, api_key_id)
    if row is None:
        return False
    return row.revoked_at is None
