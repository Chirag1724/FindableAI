"""Phase 2 Item 1: DB-backed list_scans with SQL org filter + keyset pagination."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1 import api_v1_router
from app.api.v1 import scans as scans_mod
from app.core.auth import TenantContext
from app.core.config import settings
from app.core.tenancy import (
    clamp_list_limit,
    decode_scan_list_cursor,
    encode_scan_list_cursor,
    list_scans_for_org,
)
from app.models.database import Base, Organization, Scan
from app.schemas.scan import ScanResponse, ScanStatus


@pytest.fixture
def secured_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(settings, "API_KEY", "phase2-system-secret")
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "DURABLE_SCAN_JOBS", False)
    app = FastAPI()
    app.include_router(api_v1_router)
    return app


@pytest.fixture
def client(secured_app: FastAPI) -> TestClient:
    return TestClient(secured_app)


def test_clamp_list_limit_bounds() -> None:
    assert clamp_list_limit(None) == 20
    assert clamp_list_limit(1) == 1
    assert clamp_list_limit(100) == 100
    assert clamp_list_limit(999) == 100
    assert clamp_list_limit(0) == 1


def test_scan_list_cursor_roundtrip() -> None:
    created = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
    scan_id = uuid.uuid4()
    cursor = encode_scan_list_cursor(created_at=created, scan_id=scan_id)
    got_ts, got_id = decode_scan_list_cursor(cursor)
    assert got_id == scan_id
    assert got_ts == created


def test_anonymous_list_scans_401(client: TestClient) -> None:
    assert client.get("/api/v1/scans").status_code == 401


@pytest.mark.asyncio
async def test_list_scans_for_org_sql_filter_hides_other_org_and_null() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c,
                tables=[
                    Base.metadata.tables[Organization.__tablename__],
                    Base.metadata.tables[Scan.__tablename__],
                ],
            )
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    scan_a1 = uuid.uuid4()
    scan_a2 = uuid.uuid4()
    scan_b = uuid.uuid4()
    scan_null = uuid.uuid4()
    t0 = datetime.now(UTC)

    async with factory() as session:
        async with session.begin():
            session.add_all(
                [
                    Organization(id=org_a, name="A", slug=f"a-{org_a.hex[:6]}"),
                    Organization(id=org_b, name="B", slug=f"b-{org_b.hex[:6]}"),
                    Scan(
                        id=scan_a1,
                        org_id=org_a,
                        url="https://a1.example/",
                        status="completed",
                        created_at=t0,
                    ),
                    Scan(
                        id=scan_a2,
                        org_id=org_a,
                        url="https://a2.example/",
                        status="completed",
                        created_at=t0 + timedelta(seconds=1),
                    ),
                    Scan(
                        id=scan_b,
                        org_id=org_b,
                        url="https://b.example/",
                        status="completed",
                        created_at=t0 + timedelta(seconds=2),
                    ),
                    Scan(
                        id=scan_null,
                        org_id=None,
                        url="https://legacy.example/",
                        status="completed",
                        created_at=t0 + timedelta(seconds=3),
                    ),
                ]
            )

    member_a = TenantContext(org_id=org_a, is_system_admin=False)
    async with factory() as session:
        rows = await list_scans_for_org(session, member_a, limit=100)
    ids = {r.id for r in rows}
    assert ids == {scan_a1, scan_a2}
    assert rows[0].id == scan_a2  # newest first

    # Fresh session (restart simulation) — identical listing.
    async with factory() as session:
        rows2 = await list_scans_for_org(session, member_a, limit=100)
    assert [r.id for r in rows2] == [r.id for r in rows]

    async with factory() as session:
        page1 = await list_scans_for_org(session, member_a, limit=1)
        assert len(page1) == 1 and page1[0].id == scan_a2
        cursor = encode_scan_list_cursor(
            created_at=page1[0].created_at, scan_id=page1[0].id
        )
        page2 = await list_scans_for_org(session, member_a, limit=1, cursor=cursor)
        assert len(page2) == 1 and page2[0].id == scan_a1
        cursor2 = encode_scan_list_cursor(
            created_at=page2[0].created_at, scan_id=page2[0].id
        )
        page3 = await list_scans_for_org(session, member_a, limit=1, cursor=cursor2)
        assert page3 == []

        # No duplicates across pages.
        assert {page1[0].id, page2[0].id} == {scan_a1, scan_a2}

    await engine.dispose()


def test_list_scans_http_ignores_scans_db(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mem_id = f"scan_{uuid.uuid4().hex}"
    scans_mod.SCANS_DB[mem_id] = ScanResponse(
        scan_id=mem_id,
        target_url="https://memory-only.example/",
        status=ScanStatus.COMPLETED,
        created_at=datetime.now(UTC),
        org_id=None,
    )

    async def _empty_list(*_a, **_k):
        return []

    monkeypatch.setattr(scans_mod, "list_scans_for_org", _empty_list)
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(scans_mod, "AsyncSessionLocal", MagicMock(return_value=session))

    try:
        resp = client.get("/api/v1/scans", headers={"X-API-Key": "phase2-system-secret"})
        assert resp.status_code == 200
        assert resp.json() == []
        assert mem_id not in {row.get("scan_id") for row in resp.json()}
    finally:
        scans_mod.SCANS_DB.pop(mem_id, None)


def test_list_scans_http_sets_next_cursor_header(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = uuid.uuid4()
    t0 = datetime.now(UTC)
    rows = [
        Scan(
            id=uuid.uuid4(),
            org_id=org_id,
            url=f"https://p{i}.example/",
            status="completed",
            created_at=t0 + timedelta(seconds=i),
        )
        for i in range(2)
    ]
    # Newest-first order as SQL would return.
    rows = sorted(rows, key=lambda r: (r.created_at, r.id), reverse=True)

    async def _page(*_a, **_k):
        return rows[:2]

    monkeypatch.setattr(scans_mod, "list_scans_for_org", _page)
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(scans_mod, "AsyncSessionLocal", MagicMock(return_value=session))

    resp = client.get(
        "/api/v1/scans?limit=2",
        headers={"X-API-Key": "phase2-system-secret"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert "X-Next-Cursor" in resp.headers
    decode_scan_list_cursor(resp.headers["X-Next-Cursor"])
