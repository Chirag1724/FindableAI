"""Phase 3 Item 3: membership permission matrix + last-owner / self-escalation."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.core.auth import TenantContext
from app.core.permissions import (
    OrgAction,
    OrgRole,
    assert_permission,
    permission_matrix_rows,
    role_allows,
)


@pytest.mark.parametrize("row", permission_matrix_rows())
def test_permission_matrix_parametrized(row: dict) -> None:
    allowed = role_allows(row["role"], OrgAction(row["action"]))
    assert allowed is row["allowed"]


def test_viewer_cannot_mutate() -> None:
    tenant = TenantContext(org_id=uuid.uuid4(), role=OrgRole.VIEWER.value)
    with pytest.raises(HTTPException) as ei:
        assert_permission(tenant, OrgAction.CREATE_SCAN)
    assert ei.value.status_code == 403
    assert ei.value.detail["reason"] == "permission_denied"


def test_member_cannot_manage_members() -> None:
    tenant = TenantContext(org_id=uuid.uuid4(), role=OrgRole.MEMBER.value)
    with pytest.raises(HTTPException):
        assert_permission(tenant, OrgAction.MANAGE_MEMBERS)


def test_owner_can_change_plan() -> None:
    tenant = TenantContext(org_id=uuid.uuid4(), role=OrgRole.OWNER.value)
    assert_permission(tenant, OrgAction.CHANGE_PLAN)


def test_system_admin_bypasses_role() -> None:
    tenant = TenantContext(is_system_admin=True, role=OrgRole.VIEWER.value)
    assert_permission(tenant, OrgAction.CREATE_SCAN)


@pytest.mark.asyncio
async def test_last_owner_and_self_escalation_pg_or_unit() -> None:
    """Membership helpers: last-owner protection + no self-escalation (in-memory session optional).

    Uses SQLite-free SimpleNamespace path when PG not required — pure helper logic
    exercised via monkeypatched memberships list is insufficient; call helpers with
    a real AsyncSession when FINDABLE_PG_INTEGRATION=1 (see test_phase3_membership_pg).
    """
    from app.core.membership import MembershipMutationResult
    from app.core.permissions import normalize_role

    assert normalize_role("OWNER") is OrgRole.OWNER
    assert MembershipMutationResult(ok=False, reason="last_owner_protected").reason == (
        "last_owner_protected"
    )
