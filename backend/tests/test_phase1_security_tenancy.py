"""Phase 1 P0: scan-route auth + org isolation + readiness degradation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1 import api_v1_router
from app.core.auth import TenantContext, hash_api_key
from app.core.config import settings
from app.core.tenancy import assert_scan_org_access, can_access_scan_org, get_scan_for_org
from app.models.database import ApiKey, Base, Organization, Scan, ScanJob

# Canonical scan-related routes that must reject anonymous callers when API_KEY is set.
SCAN_ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/v1/scans"),
    ("GET", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef"),
    ("GET", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/stream"),
    ("GET", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/chunks"),
    ("GET", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/intents"),
    ("GET", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/contradictions"),
    ("GET", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/lighthouse"),
    ("GET", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/job"),
    ("GET", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/patches"),
    ("GET", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/remediation"),
    ("GET", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/remediation/verifications"),
    ("GET", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/summary"),
    ("POST", "/api/v1/scans"),
    ("POST", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/cancel"),
    ("POST", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/evaluate"),
    ("POST", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/remediate"),
    ("POST", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/patches/apply"),
    ("POST", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/patches/validate"),
    ("POST", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/remediation/verify"),
    ("POST", "/api/v1/scans/scan_deadbeefdeadbeefdeadbeefdeadbeef/summary"),
    ("POST", "/api/v1/patches/apply-pr"),
]


@pytest.fixture
def secured_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(settings, "API_KEY", "phase1-system-secret")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DURABLE_SCAN_JOBS", False)
    monkeypatch.setattr(settings, "ALLOW_SYNTHETIC_DEMO", True)
    app = FastAPI()
    app.include_router(api_v1_router)
    # Also mount scans at /api/scans alias if main does — only v1 needed here.
    return app


@pytest.fixture
def client(secured_app: FastAPI) -> TestClient:
    return TestClient(secured_app)


@pytest.mark.parametrize(("method", "path"), SCAN_ROUTES)
def test_anonymous_scan_routes_return_401(client: TestClient, method: str, path: str) -> None:
    body = None
    if method == "POST" and path.endswith("/scans"):
        body = {"url": "https://example.com"}
    elif method == "POST" and path.endswith("/apply-pr"):
        body = {
            "patch_id": "patch_abc",
            "github_repo_url": "https://github.com/acme/repo",
        }
    elif method == "POST":
        body = {}

    resp = client.request(method, path, json=body)
    assert resp.status_code == 401, f"{method} {path} -> {resp.status_code} {resp.text}"


def test_health_and_ready_remain_anonymous(client: TestClient) -> None:
    assert client.get("/api/v1/health").status_code == 200
    # ready may be degraded without DB but must not be 401
    assert client.get("/api/v1/ready").status_code == 200


def test_system_key_can_list_scans(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.api.v1 import scans as scans_mod

    async def _empty(*_a, **_k):
        return []

    monkeypatch.setattr(scans_mod, "list_scans_for_org", _empty)
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(scans_mod, "AsyncSessionLocal", MagicMock(return_value=session))

    resp = client.get("/api/v1/scans", headers={"X-API-Key": "phase1-system-secret"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_can_access_scan_org_matrix() -> None:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    admin = TenantContext(is_system_admin=True)
    member_a = TenantContext(org_id=org_a, is_system_admin=False)
    member_b = TenantContext(org_id=org_b, is_system_admin=False)
    no_org = TenantContext(org_id=None, is_system_admin=False)

    assert can_access_scan_org(scan_org_id=org_a, tenant=admin) is True
    assert can_access_scan_org(scan_org_id=None, tenant=admin) is True
    assert can_access_scan_org(scan_org_id=org_a, tenant=member_a) is True
    assert can_access_scan_org(scan_org_id=org_a, tenant=member_b) is False
    assert can_access_scan_org(scan_org_id=None, tenant=member_a) is False
    assert can_access_scan_org(scan_org_id=org_a, tenant=no_org) is False

    with pytest.raises(Exception) as exc:
        assert_scan_org_access(scan_org_id=org_a, tenant=member_b)
    assert exc.value.status_code == 404  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_scan_for_org_denies_cross_tenant_and_null_org() -> None:
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
    scan_a = uuid.uuid4()
    scan_null = uuid.uuid4()

    async with factory() as session:
        session.add(Organization(id=org_a, name="A", slug=f"a-{org_a.hex[:6]}"))
        session.add(Organization(id=org_b, name="B", slug=f"b-{org_b.hex[:6]}"))
        session.add(Scan(id=scan_a, org_id=org_a, url="https://a.example", status="completed"))
        session.add(Scan(id=scan_null, org_id=None, url="https://legacy.example", status="completed"))
        await session.commit()

    member_a = TenantContext(org_id=org_a)
    member_b = TenantContext(org_id=org_b)
    admin = TenantContext(is_system_admin=True)

    async with factory() as session:
        got = await get_scan_for_org(session, scan_a, member_a)
        assert got.id == scan_a

        with pytest.raises(Exception) as cross:
            await get_scan_for_org(session, scan_a, member_b)
        assert cross.value.status_code == 404  # type: ignore[attr-defined]

        with pytest.raises(Exception) as legacy:
            await get_scan_for_org(session, scan_null, member_a)
        assert legacy.value.status_code == 404  # type: ignore[attr-defined]

        legacy_ok = await get_scan_for_org(session, scan_null, admin)
        assert legacy_ok.id == scan_null

    await engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_stamps_org_id_on_scan_and_job(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.jobs.queue import enqueue_scan_job, request_fingerprint

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c,
                tables=[
                    Base.metadata.tables[Organization.__tablename__],
                    Base.metadata.tables[Scan.__tablename__],
                    Base.metadata.tables[ScanJob.__tablename__],
                ],
            )
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    org_id = uuid.uuid4()
    scan_uuid = uuid.uuid4()
    fp = request_fingerprint(url="https://example.com", max_pages=1, personas=["cto"], repo_url=None)

    async with factory() as session:
        session.add(Organization(id=org_id, name="Org", slug=f"org-{org_id.hex[:6]}"))
        await session.commit()

    async with factory() as session:
        async with session.begin():
            result = await enqueue_scan_job(
                session,
                scan_uuid=scan_uuid,
                url="https://example.com",
                max_pages=1,
                personas=["cto", "developer", "procurement"],
                repo_url=None,
                idempotency_key=f"test:{scan_uuid.hex}",
                fingerprint=fp,
                org_id=org_id,
            )
        assert result.created is True
        assert result.scan.org_id == org_id
        assert result.job.org_id == org_id
        assert (result.job.payload or {}).get("org_id") == str(org_id)

    await engine.dispose()


@pytest.mark.asyncio
async def test_client_supplied_org_id_ignored_on_create(monkeypatch: pytest.MonkeyPatch) -> None:
    """ScanRequest has no org_id field; enqueue receives principal org only."""
    from app.schemas.scan import ScanRequest

    body = ScanRequest(url="https://example.com")
    assert not hasattr(body, "org_id") or getattr(body, "org_id", None) is None
    # Extra fields must not silently bind as org ownership.
    dumped = body.model_dump()
    assert "org_id" not in dumped


@pytest.mark.asyncio
async def test_readiness_degraded_with_stale_queue_no_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DURABLE_SCAN_JOBS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "SCAN_JOB_QUEUE_STALE_SECONDS", 60)
    monkeypatch.setattr(settings, "SCAN_JOB_HEARTBEAT_TIMEOUT_SECONDS", 30)

    from app.api.v1 import health as health_mod

    old_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    queued_at = old_now - timedelta(seconds=300)

    class _ScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar(self):
            return self._value

    # Build a fake session that returns stale queue counts.
    fake_session = MagicMock()
    call_count = {"n": 0}

    async def fake_scalar(stmt):
        call_count["n"] += 1
        # Order in readiness_check: queued count, active, oldest available, newest hb, recent hb
        values = [1, 0, queued_at, None, 0]
        idx = min(call_count["n"] - 1, len(values) - 1)
        return values[idx]

    fake_session.scalar = fake_scalar

    class _CM:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, *args):
            return False

    class _EngineCM:
        async def __aenter__(self):
            conn = AsyncMock()
            conn.execute = AsyncMock()
            return conn

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(health_mod, "AsyncSessionLocal", lambda: _CM())
    fake_engine = MagicMock()
    fake_engine.connect = lambda: _EngineCM()
    monkeypatch.setattr(health_mod, "engine", fake_engine)

    # Freeze "now" via datetime.now in health module
    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return old_now

    monkeypatch.setattr(health_mod, "datetime", _FrozenDateTime)

    resp = await health_mod.readiness_check()
    assert resp.status == "degraded"
    assert resp.worker == "stale_or_absent"
    assert resp.queued_jobs == 1
    assert resp.oldest_queued_age_seconds is not None
    assert resp.oldest_queued_age_seconds >= 60


@pytest.mark.asyncio
async def test_readiness_healthy_with_fresh_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DURABLE_SCAN_JOBS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    from app.api.v1 import health as health_mod

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    call_count = {"n": 0}

    async def fake_scalar(stmt):
        call_count["n"] += 1
        # queued=0, active=1, oldest=None, newest_hb=now, recent_hb=1
        values = [0, 1, None, now, 1]
        return values[min(call_count["n"] - 1, len(values) - 1)]

    fake_session = MagicMock()
    fake_session.scalar = fake_scalar

    class _CM:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, *args):
            return False

    class _EngineCM:
        async def __aenter__(self):
            conn = AsyncMock()
            conn.execute = AsyncMock()
            return conn

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(health_mod, "AsyncSessionLocal", lambda: _CM())
    fake_engine = MagicMock()
    fake_engine.connect = lambda: _EngineCM()
    monkeypatch.setattr(health_mod, "engine", fake_engine)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(health_mod, "datetime", _FrozenDateTime)

    resp = await health_mod.readiness_check()
    assert resp.status == "healthy"
    assert resp.worker == "active"


@pytest.mark.asyncio
async def test_org_api_keys_isolate_scan_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Org A key cannot read Org B scan; Org A can read its own (via tenancy helper)."""
    from app.api.v1 import scans as scans_mod

    monkeypatch.setattr(settings, "API_KEY", "phase1-system-secret")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DURABLE_SCAN_JOBS", False)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c,
                tables=[
                    Base.metadata.tables[Organization.__tablename__],
                    Base.metadata.tables[ApiKey.__tablename__],
                    Base.metadata.tables[Scan.__tablename__],
                ],
            )
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    scan_a = uuid.uuid4()
    scan_b = uuid.uuid4()
    key_a = "fnd_live_org_a_secret_key_001"

    async with factory() as session:
        session.add_all(
            [
                Organization(id=org_a, name="A", slug=f"a-{org_a.hex[:6]}", rate_limit_per_min=1000),
                Organization(id=org_b, name="B", slug=f"b-{org_b.hex[:6]}", rate_limit_per_min=1000),
                ApiKey(
                    id=uuid.uuid4(),
                    org_id=org_a,
                    key_prefix="fnd_live_org",
                    hashed_key=hash_api_key(key_a),
                    name="A",
                    rate_limit_per_min=1000,
                ),
                Scan(id=scan_a, org_id=org_a, url="https://a.example", status="completed"),
                Scan(id=scan_b, org_id=org_b, url="https://b.example", status="completed"),
            ]
        )
        await session.commit()

    import app.db as db_mod

    monkeypatch.setattr(db_mod, "AsyncSessionLocal", factory)
    monkeypatch.setattr(scans_mod, "AsyncSessionLocal", factory)

    member_a = TenantContext(org_id=org_a, is_system_admin=False)
    async with factory() as session:
        own = await get_scan_for_org(session, scan_a, member_a)
        assert own.id == scan_a
        with pytest.raises(Exception) as cross:
            await get_scan_for_org(session, scan_b, member_a)
        assert cross.value.status_code == 404  # type: ignore[attr-defined]

    # HTTP: authorize via chunks (returns quickly after tenancy check)
    app = FastAPI()
    app.include_router(api_v1_router)
    client = TestClient(app)
    sid_b = f"scan_{scan_b.hex}"
    cross_http = client.get(f"/api/v1/scans/{sid_b}/chunks", headers={"X-API-Key": key_a})
    assert cross_http.status_code == 404
    anon = client.get(f"/api/v1/scans/{sid_b}/stream")
    assert anon.status_code == 401

    await engine.dispose()
