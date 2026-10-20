"""Centralized scan tenant authorization (deny-by-default).

All scan-owned resources (chunks, intents, contradictions, evidence, remediation,
SSE, lighthouse) must be authorized via the parent scan's ``org_id``.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import TenantContext
from app.models.database import Scan as ScanModel

_NOT_FOUND = "Scan not found"
LIST_DEFAULT_LIMIT = 20
LIST_MAX_LIMIT = 100


def clamp_list_limit(limit: int | None) -> int:
    """Hard-cap list page size (default 20, max 100)."""
    if limit is None:
        return LIST_DEFAULT_LIMIT
    return max(1, min(int(limit), LIST_MAX_LIMIT))


def encode_scan_list_cursor(*, created_at: datetime, scan_id: uuid.UUID) -> str:
    """Opaque keyset cursor: base64(created_at_iso|uuid_hex)."""
    raw = f"{created_at.isoformat()}|{scan_id.hex}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_scan_list_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Parse keyset cursor; raises HTTP 400 on malformed input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ts_part, id_part = raw.split("|", 1)
        created_at = datetime.fromisoformat(ts_part)
        scan_id = uuid.UUID(id_part)
    except (ValueError, binascii.Error, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid list cursor",
        ) from exc
    return created_at, scan_id


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
    limit: int = LIST_DEFAULT_LIMIT,
    cursor: str | None = None,
) -> list[ScanModel]:
    """List recent scans visible to ``tenant`` (SQL-level org filter only).

    Ordering is ``created_at DESC, id DESC``. Optional keyset ``cursor`` continues
    after the prior page. Normal org members never see ``org_id IS NULL`` rows.
    """
    page_size = clamp_list_limit(limit)
    stmt = select(ScanModel)

    if tenant.is_system_admin:
        pass
    elif tenant.org_id is None:
        return []
    else:
        # Fail closed: SQL filter only — never fetch-all then filter in Python.
        stmt = stmt.where(ScanModel.org_id == tenant.org_id)

    if cursor:
        cursor_created_at, cursor_id = decode_scan_list_cursor(cursor)
        stmt = stmt.where(
            or_(
                ScanModel.created_at < cursor_created_at,
                and_(
                    ScanModel.created_at == cursor_created_at,
                    ScanModel.id < cursor_id,
                ),
            )
        )

    stmt = stmt.order_by(ScanModel.created_at.desc(), ScanModel.id.desc()).limit(page_size)
    result = await session.execute(stmt)
    return list(result.scalars().all())
