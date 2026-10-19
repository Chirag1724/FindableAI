"""Live proof for AI Website Health Brief (cache, single-flight, zero findings, tenancy).

Usage (API + Postgres running; migration applied):
  cd backend
  .venv/Scripts/python.exe scripts/live_proof_summary.py

Uses a deterministic fake LLM by default. Set LIVE_PROOF_REAL_GEMINI=1 to call
the real provider with GEMINI_API_KEY_AI_SUMMARY / GEMINI_API_KEY.
Never prints secrets.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

# Ensure backend root on path
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth import TenantContext
from app.core.config import settings
from app.core.llm import LLMClient
from app.core.tenancy import get_scan_for_org
from app.models.database import (
    DOMChunk,
    Evidence,
    Intent,
    Organization,
    Scan,
    ScanSummary,
)
from app.orchestration.scan_summary import generate_summary, get_summary
from app.schemas.summary import LlmSummaryItem, LlmSummaryPayload, SummaryPriority
from fastapi import HTTPException


class _FakeCompletions:
    def __init__(self, handler: AsyncMock) -> None:
        self.create = handler


class _FakeChat:
    def __init__(self, handler: AsyncMock) -> None:
        self.completions = _FakeCompletions(handler)


class _FakeInstructorClient:
    def __init__(self, handler: AsyncMock) -> None:
        self.chat = _FakeChat(handler)


def _payload(finding_id: str) -> LlmSummaryPayload:
    return LlmSummaryPayload(
        headline="Hours need a single source of truth",
        overview="Your site shows conflicting opening hours that confuse visitors.",
        items=[
            LlmSummaryItem(
                finding_ids=[finding_id],
                what_is_wrong="Two different hour ranges appear on the site.",
                why_it_matters="Customers may show up when you are closed.",
                recommended_action="Publish one hours block everywhere.",
                priority=SummaryPriority.HIGH,
            )
        ],
        limitations="",
    )


async def _seed(
    session: AsyncSession, *, with_finding: bool
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    session.add(Organization(id=org_a, name="ProofA", slug=f"pa-{org_a.hex[:8]}"))
    session.add(Organization(id=org_b, name="ProofB", slug=f"pb-{org_b.hex[:8]}"))
    scan_id = uuid.uuid4()
    session.add(
        Scan(
            id=scan_id,
            org_id=org_a,
            url="https://proof.example/",
            status="completed",
            outcome="success",
            batches_completed=10,
            batches_total=10,
            llm_calls_made=4,
        )
    )
    if with_finding:
        chunk_id = uuid.uuid4()
        intent_id = uuid.uuid4()
        session.add(
            DOMChunk(
                id=chunk_id,
                scan_id=scan_id,
                url="https://proof.example/hours",
                dom_path="main",
                content="Hours 9-5",
                tag="section",
                word_count=2,
            )
        )
        session.add(
            Intent(
                id=intent_id,
                scan_id=scan_id,
                intent_key="intent_hours",
                category="availability",
                query="What are your hours?",
                status="CONTRADICTED",
                reasoning="Conflict",
                confidence=0.9,
            )
        )
        session.add(
            Evidence(
                id=uuid.uuid4(),
                intent_id=intent_id,
                chunk_id=chunk_id,
                rank=1,
                rrf_score=0.1,
                source_url="https://proof.example/hours",
                excerpt="Open Mon-Fri 9am-5pm",
                dom_path="main",
            )
        )
    await session.flush()
    return org_a, org_b, scan_id


async def main() -> int:
    use_real = os.environ.get("LIVE_PROOF_REAL_GEMINI", "").lower() in ("1", "true", "yes")
    has_key = bool(
        (settings.GEMINI_API_KEY_AI_SUMMARY or settings.GEMINI_API_KEY or "").strip()
    )
    if use_real and not has_key:
        print("LIVE_PROOF_REAL_GEMINI=1 but no Gemini key configured; aborting.")
        return 2

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    call_count = 0

    async def _dispatch(**_kwargs: Any) -> LlmSummaryPayload:
        nonlocal call_count
        call_count += 1
        return _payload("intent_hours")

    fake_client = LLMClient(
        api_key="proof-fake-key",
        model=settings.SUMMARY_LLM_MODEL,
        max_calls=10,
        instructor_client=_FakeInstructorClient(AsyncMock(side_effect=_dispatch)),
    )

    print("=== Live proof: AI Website Health Brief ===")
    print(f"model={settings.SUMMARY_LLM_MODEL} real_gemini={use_real and has_key}")

    llm = None if (use_real and has_key) else fake_client

    async with factory() as session:
        async with session.begin():
            org_a, org_b, scan_id = await _seed(session, with_finding=True)

    # (a) first generation
    async with factory() as session:
        async with session.begin():
            scan = await session.get(Scan, scan_id)
            assert scan is not None
            before_calls = int(scan.llm_calls_made or 0)
            resp1, code1 = await generate_summary(session, scan, llm_client=llm)
        assert code1 == 200 and resp1.status.value == "ready" and resp1.cached is False
        row = (
            await session.execute(
                select(ScanSummary).where(
                    ScanSummary.scan_id == scan_id, ScanSummary.status == "ready"
                )
            )
        ).scalars().first()
        assert row is not None
        print(
            f"(a) first generate OK cached={resp1.cached} "
            f"tokens_in={row.input_tokens} tokens_out={row.output_tokens} "
            f"latency_ms={row.latency_ms}"
        )
        llm_calls_after_a = call_count if llm is not None else "n/a(real)"

    # (b) cache hit
    async with factory() as session:
        async with session.begin():
            scan = await session.get(Scan, scan_id)
            assert scan is not None
            resp2, code2 = await generate_summary(session, scan, llm_client=llm)
        assert code2 == 200 and resp2.cached is True
        print(f"(b) second generate cached={resp2.cached} fake_llm_calls={call_count}")
        if llm is not None:
            assert call_count == 1

    # (c) concurrent single-flight on a fresh scan
    async with factory() as session:
        async with session.begin():
            org_c = uuid.uuid4()
            session.add(Organization(id=org_c, name="ProofC", slug=f"pc-{org_c.hex[:8]}"))
            scan2 = uuid.uuid4()
            session.add(
                Scan(
                    id=scan2,
                    org_id=org_c,
                    url="https://proof2.example/",
                    status="completed",
                    outcome="success",
                    batches_completed=5,
                    batches_total=5,
                    llm_calls_made=1,
                )
            )
            chunk2 = uuid.uuid4()
            intent2 = uuid.uuid4()
            session.add(
                DOMChunk(
                    id=chunk2,
                    scan_id=scan2,
                    url="https://proof2.example/",
                    dom_path="body",
                    content="Price $10 vs $12",
                    tag="p",
                    word_count=4,
                )
            )
            session.add(
                Intent(
                    id=intent2,
                    scan_id=scan2,
                    intent_key="intent_hours",
                    category="pricing",
                    query="What is the price?",
                    status="CONTRADICTED",
                    reasoning="Conflict",
                    confidence=0.8,
                )
            )
            session.add(
                Evidence(
                    id=uuid.uuid4(),
                    intent_id=intent2,
                    chunk_id=chunk2,
                    rank=1,
                    rrf_score=0.2,
                    source_url="https://proof2.example/",
                    excerpt="Price is $10 on one page and $12 on another",
                    dom_path="body",
                )
            )

    conc_calls_before = call_count

    async def _slow_dispatch(**_kwargs: Any) -> LlmSummaryPayload:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.35)
        return _payload("intent_hours")

    slow_client = LLMClient(
        api_key="proof-fake-key",
        model=settings.SUMMARY_LLM_MODEL,
        max_calls=10,
        instructor_client=_FakeInstructorClient(AsyncMock(side_effect=_slow_dispatch)),
    )

    async def _post_scan2() -> int:
        async with factory() as s:
            async with s.begin():
                sc = await s.get(Scan, scan2)
                assert sc is not None
                _, code = await generate_summary(s, sc, llm_client=slow_client)
            return code

    codes = await asyncio.gather(*[_post_scan2() for _ in range(4)])
    assert all(c in (200, 202) for c in codes)
    assert call_count - conc_calls_before == 1
    print(f"(c) concurrent POSTs codes={codes} llm_calls={call_count - conc_calls_before}")

    # (d) zero findings
    async with factory() as session:
        async with session.begin():
            _, _, empty_scan = await _seed(session, with_finding=False)
    z_before = call_count
    async with factory() as session:
        async with session.begin():
            scan = await session.get(Scan, empty_scan)
            assert scan is not None
            zresp, zcode = await generate_summary(session, scan, llm_client=fake_client)
        zcount = (
            await session.execute(
                select(func.count())
                .select_from(ScanSummary)
                .where(ScanSummary.scan_id == empty_scan)
            )
        ).scalar_one()
    assert zcode == 200 and zresp.reason == "zero_findings"
    assert int(zcount or 0) == 0
    assert call_count == z_before
    print(f"(d) zero findings OK llm_calls_unchanged={call_count == z_before} rows={zcount}")

    # (e) cross-tenant denied
    async with factory() as session:
        tenant_b = TenantContext(org_id=org_b, role="member")
        try:
            await get_scan_for_org(session, scan_id, tenant_b)
            denied = False
        except HTTPException as exc:
            denied = exc.status_code == 404
    assert denied
    print("(e) cross-tenant denied with 404")

    async with factory() as session:
        scan = await session.get(Scan, scan_id)
        assert scan is not None
        assert int(scan.llm_calls_made or 0) == before_calls
    print(f"scan.llm_calls_made unchanged={before_calls}")
    print(f"fake_llm_total_calls={call_count} (a_calls={llm_calls_after_a})")

    await engine.dispose()
    print("=== LIVE PROOF PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
