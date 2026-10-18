"""Org role permission matrix (Phase 3). Roles come from ApiKey.role in the DB.

Plan-tier quotas are out of scope: ``organizations.plan_tier`` is a label and
``rate_limit_per_min`` is already enforced at auth time. No scan/member/LLM
quota tables exist — do not invent a billing system here.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import HTTPException, Request, status

from app.core.auth import TenantContext


class OrgRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class OrgAction(StrEnum):
    READ_SCANS = "read_scans"
    CREATE_SCAN = "create_scan"
    CANCEL_SCAN = "cancel_scan"
    RUN_REMEDIATION = "run_remediation"
    MANAGE_MEMBERS = "manage_members"
    CHANGE_PLAN = "change_plan"


# Role → allowed actions. Viewers are read-only. Members cannot manage members
# or change plan. Admins can manage members but not change plan. Owners can all.
_MATRIX: dict[OrgRole, frozenset[OrgAction]] = {
    OrgRole.VIEWER: frozenset({OrgAction.READ_SCANS}),
    OrgRole.MEMBER: frozenset(
        {
            OrgAction.READ_SCANS,
            OrgAction.CREATE_SCAN,
            OrgAction.CANCEL_SCAN,
            OrgAction.RUN_REMEDIATION,
        }
    ),
    OrgRole.ADMIN: frozenset(
        {
            OrgAction.READ_SCANS,
            OrgAction.CREATE_SCAN,
            OrgAction.CANCEL_SCAN,
            OrgAction.RUN_REMEDIATION,
            OrgAction.MANAGE_MEMBERS,
        }
    ),
    OrgRole.OWNER: frozenset(set(OrgAction)),
}


def normalize_role(role: str | None) -> OrgRole:
    raw = (role or "member").strip().lower()
    try:
        return OrgRole(raw)
    except ValueError:
        return OrgRole.MEMBER


def role_allows(role: str | None, action: OrgAction) -> bool:
    return action in _MATRIX[normalize_role(role)]


def assert_permission(tenant: TenantContext, action: OrgAction) -> None:
    """Raise 403 when the principal's DB role cannot perform ``action``.

    System admins bypass. Fail closed for unknown/missing roles on org keys.
    """
    if tenant.is_system_admin:
        return
    if tenant.org_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "permission_denied",
                "action": action.value,
                "role": None,
            },
        )
    if not role_allows(tenant.role, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "permission_denied",
                "action": action.value,
                "role": normalize_role(tenant.role).value,
            },
        )


def require_action(action: OrgAction):
    """FastAPI dependency factory: enforce ``action`` using request.state.tenant."""

    async def _dep(request: Request) -> TenantContext:
        tenant = getattr(request.state, "tenant", None)
        if not isinstance(tenant, TenantContext):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing tenant context",
            )
        assert_permission(tenant, action)
        return tenant

    return _dep


def permission_matrix_rows() -> list[dict[str, Any]]:
    """Flat matrix for tests / docs."""
    rows: list[dict[str, Any]] = []
    for role in OrgRole:
        for action in OrgAction:
            rows.append(
                {
                    "role": role.value,
                    "action": action.value,
                    "allowed": action in _MATRIX[role],
                }
            )
    return rows
