"""Tests for enterprise multi-tenancy, scoped API keys, and token-bucket rate limiting."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth import TenantContext, hash_api_key, verify_api_key
from app.core.config import settings
from app.core.rate_limiter import enforce_rate_limit, limiter_registry
from app.models.database import ApiKey, Base, Organization, Scan


@pytest_asyncio.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Organization.__table__,
                    ApiKey.__table__,
                    Scan.__table__,
                ],
            )
        )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_token_bucket_enforces_limit_and_rfc_headers():
    limiter_registry.reset_for_test()
    test_id = f"test_org_{uuid.uuid4().hex[:8]}"

    # Rate limit of 3 requests per minute
    # First 3 should pass
    r1 = await enforce_rate_limit(test_id, limit_per_min=3)
    assert r1.allowed is True
    assert r1.remaining == 2

    r2 = await enforce_rate_limit(test_id, limit_per_min=3)
    assert r2.allowed is True
    assert r2.remaining == 1

    r3 = await enforce_rate_limit(test_id, limit_per_min=3)
    assert r3.allowed is True
    assert r3.remaining == 0

    # 4th request must be rejected with HTTP 429 and headers
    with pytest.raises(HTTPException) as exc_info:
        await enforce_rate_limit(test_id, limit_per_min=3)

    assert exc_info.value.status_code == 429
    headers = exc_info.value.headers
    assert "Retry-After" in headers
    assert headers["X-RateLimit-Limit"] == "3"
    assert headers["X-RateLimit-Remaining"] == "0"
    assert int(headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_api_key_hashing_consistency():
    key = "fnd_live_testsecretkey123"
    hashed1 = hash_api_key(key)
    hashed2 = hash_api_key(f"  {key}  ")  # whitespace stripped
    assert hashed1 == hashed2
    assert len(hashed1) == 64  # SHA-256


@pytest.mark.asyncio
async def test_multi_tenant_api_key_validation(memory_db, monkeypatch):
    limiter_registry.reset_for_test()
    # Mock AsyncSessionLocal to use memory_db
    from app import db as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", memory_db)
    monkeypatch.setattr(settings, "API_KEY", "system-admin-secret")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    raw_key = "fnd_live_org_abc123456789"
    org_id = uuid.uuid4()

    # Seed an Organization and an ApiKey
    async with memory_db() as session:
        org = Organization(
            id=org_id,
            name="Acme Corp",
            slug=f"acme-{uuid.uuid4().hex[:6]}",
            plan_tier="enterprise",
            rate_limit_per_min=100,
        )
        api_key = ApiKey(
            id=uuid.uuid4(),
            org_id=org_id,
            key_prefix="fnd_live_org",
            hashed_key=hash_api_key(raw_key),
            name="Production Key",
            rate_limit_per_min=100,
        )
        session.add(org)
        session.add(api_key)
        await session.commit()

    class _MockRequest:
        state = type("State", (), {"tenant": None})()

    req = _MockRequest()

    # 1. Valid Org API key
    ctx = await verify_api_key(request=req, header_key=raw_key)
    assert isinstance(ctx, TenantContext)
    assert ctx.org_id == org_id
    assert ctx.org_name == "Acme Corp"
    assert ctx.plan_tier == "enterprise"
    assert ctx.is_system_admin is False

    # 2. System admin key bypass
    sys_ctx = await verify_api_key(request=req, header_key="system-admin-secret")
    assert sys_ctx.is_system_admin is True
    assert sys_ctx.org_id is None

    # 3. Invalid key fails with 401
    with pytest.raises(HTTPException) as exc:
        await verify_api_key(request=req, header_key="fnd_live_invalid_key")
    assert exc.value.status_code == 401

    # 4. Revoked key fails with 401
    revoked_raw = "fnd_live_revoked_key"
    async with memory_db() as session:
        rev_key = ApiKey(
            id=uuid.uuid4(),
            org_id=org_id,
            key_prefix="fnd_live_rev",
            hashed_key=hash_api_key(revoked_raw),
            name="Revoked Key",
            revoked_at=datetime.now(UTC),
        )
        session.add(rev_key)
        await session.commit()

    with pytest.raises(HTTPException) as exc_rev:
        await verify_api_key(request=req, header_key=revoked_raw)
    assert exc_rev.value.status_code == 401
    assert "revoked" in exc_rev.value.detail.lower()


@pytest.mark.asyncio
async def test_scan_organization_association(memory_db):
    org_id = uuid.uuid4()
    scan_id = uuid.uuid4()

    async with memory_db() as session:
        org = Organization(
            id=org_id,
            name="Tenant One",
            slug=f"tenant-one-{uuid.uuid4().hex[:6]}",
        )
        scan = Scan(
            id=scan_id,
            org_id=org_id,
            url="https://tenant-one.com",
            status="completed",
        )
        session.add(org)
        session.add(scan)
        await session.commit()

    async with memory_db() as session:
        loaded_scan = await session.get(Scan, scan_id)
        assert loaded_scan is not None
        assert loaded_scan.org_id == org_id
