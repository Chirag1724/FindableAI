"""Phase 3 Item 3: membership last-owner / revoke / cross-tenant on real Postgres."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth import TenantContext, hash_api_key
from app.core.membership import remove_member, set_member_role
from app.core.permissions import OrgRole
from app.models.database import ApiKey, Organization, OrgMembership
from tests.pg_disposable import (
    PG_SKIP_REASON,
    assert_disposable_url,
    create_all_with_vector,
    ensure_database_exists,
    integration_enabled,
    reset_public_schema,
    resolve_pg_url,
)

pytestmark = pytest.mark.skipif(not integration_enabled(), reason=PG_SKIP_REASON)


@pytest_asyncio.fixture
async def pg_session():
    if not integration_enabled():
        pytest.fail("NOT VERIFIED: FINDABLE_PG_INTEGRATION not set")
    url = resolve_pg_url()
    assert_disposable_url(url)
    try:
        await ensure_database_exists(url)
    except Exception as exc:
        pytest.fail(f"NOT VERIFIED: PostgreSQL unavailable: {exc}")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.fail(f"NOT VERIFIED: PostgreSQL unreachable: {exc}")
    try:
        await reset_public_schema(engine)
        await create_all_with_vector(engine)
    except Exception as exc:
        await engine.dispose()
        pytest.fail(f"NOT VERIFIED: schema prepare failed: {exc}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_org(session: AsyncSession) -> tuple[Organization, uuid.UUID, uuid.UUID]:
    org = Organization(id=uuid.uuid4(), name="Org", slug=f"org-{uuid.uuid4().hex[:8]}")
    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    session.add(org)
    session.add(
        OrgMembership(id=uuid.uuid4(), org_id=org.id, user_id=owner_id, role=OrgRole.OWNER.value)
    )
    session.add(
        OrgMembership(id=uuid.uuid4(), org_id=org.id, user_id=member_id, role=OrgRole.MEMBER.value)
    )
    raw = f"fai_test_{uuid.uuid4().hex}"
    key = ApiKey(
        id=uuid.uuid4(),
        org_id=org.id,
        key_prefix=raw[:8],
        hashed_key=hash_api_key(raw),
        name="owner-key",
        role=OrgRole.OWNER.value,
        user_id=owner_id,
    )
    member_raw = f"fai_mem_{uuid.uuid4().hex}"
    member_key = ApiKey(
        id=uuid.uuid4(),
        org_id=org.id,
        key_prefix=member_raw[:8],
        hashed_key=hash_api_key(member_raw),
        name="member-key",
        role=OrgRole.MEMBER.value,
        user_id=member_id,
    )
    session.add(key)
    session.add(member_key)
    await session.flush()
    return org, owner_id, member_id


@pytest.mark.asyncio
async def test_last_owner_protected(pg_session: AsyncSession):
    async with pg_session.begin():
        org, owner_id, _member_id = await _seed_org(pg_session)
        tenant = TenantContext(
            org_id=org.id, role=OrgRole.OWNER.value, api_key_id=uuid.uuid4(), is_system_admin=False
        )
        demote = await set_member_role(
            pg_session,
            tenant=tenant,
            org_id=org.id,
            target_user_id=owner_id,
            new_role=OrgRole.MEMBER.value,
            actor_user_id=uuid.uuid4(),
        )
        assert demote.ok is False
        assert demote.reason == "last_owner_protected"
        removed = await remove_member(
            pg_session,
            tenant=tenant,
            org_id=org.id,
            target_user_id=owner_id,
            actor_user_id=uuid.uuid4(),
        )
        assert removed.ok is False
        assert removed.reason == "last_owner_protected"


@pytest.mark.asyncio
async def test_no_self_escalation(pg_session: AsyncSession):
    async with pg_session.begin():
        org, owner_id, _member_id = await _seed_org(pg_session)
        tenant = TenantContext(
            org_id=org.id, role=OrgRole.OWNER.value, api_key_id=uuid.uuid4(), is_system_admin=False
        )
        result = await set_member_role(
            pg_session,
            tenant=tenant,
            org_id=org.id,
            target_user_id=owner_id,
            new_role=OrgRole.OWNER.value,
            actor_user_id=owner_id,
        )
        assert result.ok is False
        assert result.reason == "self_role_change_forbidden"

        # Member cannot manage members at all
        member_tenant = TenantContext(
            org_id=org.id, role=OrgRole.MEMBER.value, api_key_id=uuid.uuid4(), is_system_admin=False
        )
        with pytest.raises(HTTPException) as ei:
            await set_member_role(
                pg_session,
                tenant=member_tenant,
                org_id=org.id,
                target_user_id=owner_id,
                new_role=OrgRole.MEMBER.value,
                actor_user_id=uuid.uuid4(),
            )
        assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_removed_member_keys_revoked_immediately(pg_session: AsyncSession):
    async with pg_session.begin():
        org, owner_id, member_id = await _seed_org(pg_session)
        tenant = TenantContext(
            org_id=org.id, role=OrgRole.OWNER.value, api_key_id=uuid.uuid4(), is_system_admin=False
        )
        result = await remove_member(
            pg_session,
            tenant=tenant,
            org_id=org.id,
            target_user_id=member_id,
            actor_user_id=owner_id,
        )
        assert result.ok is True
        rows = (
            await pg_session.execute(
                select(ApiKey).where(ApiKey.org_id == org.id, ApiKey.user_id == member_id)
            )
        ).scalars().all()
        assert rows
        assert all(r.revoked_at is not None for r in rows)


@pytest.mark.asyncio
async def test_cross_tenant_membership_denied(pg_session: AsyncSession):
    async with pg_session.begin():
        org_a, owner_a, _ = await _seed_org(pg_session)
        org_b, owner_b, _ = await _seed_org(pg_session)
        tenant_a = TenantContext(
            org_id=org_a.id, role=OrgRole.OWNER.value, api_key_id=uuid.uuid4(), is_system_admin=False
        )
        with pytest.raises(HTTPException) as ei:
            await remove_member(
                pg_session,
                tenant=tenant_a,
                org_id=org_b.id,
                target_user_id=owner_b,
                actor_user_id=owner_a,
            )
        assert ei.value.status_code == 404
