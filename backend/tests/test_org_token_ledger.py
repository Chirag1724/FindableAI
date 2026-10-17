"""Tests for OrgTokenLedger ORM model and cascade behavior."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.models.database import ApiKey, Base, Organization, OrgMembership, OrgTokenLedger, Scan


@pytest.mark.asyncio
async def test_org_token_ledger_relationship_and_cascade():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Base.metadata.tables[Organization.__tablename__],
                    Base.metadata.tables[ApiKey.__tablename__],
                    Base.metadata.tables[OrgMembership.__tablename__],
                    Base.metadata.tables[Scan.__tablename__],
                    Base.metadata.tables[OrgTokenLedger.__tablename__],
                ],
            )
        )

    try:
        async with async_session() as session:
            async with session.begin():
                org = Organization(
                    name="Acme Enterprise",
                    slug="acme-enterprise",
                    plan_tier="pro",
                    rate_limit_per_min=120,
                )
                scan = Scan(
                    url="https://acme.com",
                    status="completed",
                    llm_tokens_in=1500,
                    llm_tokens_out=450,
                    llm_usd_estimated=0.0035,
                    primary_llm_model="groq/openai/gpt-oss-120b",
                )
                org.scans.append(scan)
                session.add(org)
                await session.flush()

                ledger_entry = OrgTokenLedger(
                    org_id=org.id,
                    scan_id=scan.id,
                    model="groq/openai/gpt-oss-120b",
                    tokens_in=1500,
                    tokens_out=450,
                    cost_usd=0.0035,
                )
                session.add(ledger_entry)

        # Verify entry persisted and relationships resolve
        async with async_session() as session:
            stmt = select(OrgTokenLedger).where(OrgTokenLedger.org_id == org.id)
            res = await session.scalar(stmt)
            assert res is not None
            assert res.model == "groq/openai/gpt-oss-120b"
            assert res.tokens_in == 1500
            assert res.tokens_out == 450
            assert abs(res.cost_usd - 0.0035) < 1e-6
            assert res.scan_id == scan.id

            # Verify organization relationship backref
            stmt_org = (
                select(Organization)
                .options(selectinload(Organization.token_ledger))
                .where(Organization.id == org.id)
            )
            org_db = await session.scalar(stmt_org)
            assert org_db is not None
            assert len(org_db.token_ledger) == 1
            assert org_db.token_ledger[0].id == res.id

        # Verify cascade delete: deleting organization removes ledger rows
        async with async_session() as session:
            async with session.begin():
                org_to_delete = await session.get(Organization, org.id)
                assert org_to_delete is not None
                await session.delete(org_to_delete)

        async with async_session() as session:
            stmt = select(OrgTokenLedger).where(OrgTokenLedger.org_id == org.id)
            deleted_res = await session.scalar(stmt)
            assert deleted_res is None
    finally:
        await engine.dispose()
