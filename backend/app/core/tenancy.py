"""Centralized scan tenant authorization (deny-by-default).

All scan-owned resources (chunks, intents, contradictions, evidence, remediation,
SSE, lighthouse) must be authorized via the parent scan's ``org_id``.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import TenantContext
from app.models.database import Scan as ScanModel

_NOT_FOUND = "Scan not found"


def can_access_scan_org(
    *,
    scan_org_id: uuid.UUID | None,
    tenant: TenantContext,
) -> bool:
    """Return True when ``tenant`` may access a scan owned by ``scan_org_id``.

    - System admins (static API_KEY) may access any scan, including legacy NULL org.
    - Org principals may only access scans whose ``org_id`` matches their org.
    - Legacy rows with ``org_id IS NULL`` are denied to non-admin principals.
    - Principals without an org_id (and not admin) are denied.
    """
    if tenant.is_system_admin:
        return True
    if tenant.org_id is None:
        return False
    if scan_org_id is None:
        return False
    return scan_org_id == tenant.org_id


def assert_scan_org_access(
    *,
    scan_org_id: uuid.UUID | None,
    tenant: TenantContext,
) -> None:
    """Raise 404 when access is denied (avoid cross-tenant ID enumeration)."""
    if not can_access_scan_org(scan_org_id=scan_org_id, tenant=tenant):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_NOT_FOUND,
        )


async def get_scan_for_org(
    session: AsyncSession,
    scan_uuid: uuid.UUID,
    tenant: TenantContext,
) -> ScanModel:
    """Load a scan by id and authorize for ``tenant``. Fail closed with 404."""
    scan = await session.get(ScanModel, scan_uuid)
    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_NOT_FOUND,
        )
    assert_scan_org_access(
        scan_org_id=getattr(scan, "org_id", None),
        tenant=tenant,
    )
    return scan


async def get_scan_for_org_by_ref(
    session: AsyncSession,
    scan_ref: str,
    tenant: TenantContext,
    *,
    resolve_uuid: Any,
) -> ScanModel:
    """Resolve a public scan_id string, then authorize via ``get_scan_for_org``."""
    scan_uuid = resolve_uuid(scan_ref)
    if scan_uuid is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_NOT_FOUND,
        )
    return await get_scan_for_org(session, scan_uuid, tenant)


async def list_scans_for_org(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    limit: int = 100,
) -> list[ScanModel]:
    """List recent scans visible to ``tenant`` (SQL-level org filter)."""
    stmt = select(ScanModel).order_by(ScanModel.created_at.desc()).limit(limit)
    if tenant.is_system_admin:
        pass
    elif tenant.org_id is None:
        return []
    else:
        stmt = stmt.where(ScanModel.org_id == tenant.org_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())
