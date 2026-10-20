"""PostgreSQL integration: AI Website Health Brief v2 (generate_summary).

Requires FINDABLE_PG_INTEGRATION=1 and a disposable PostgreSQL URL (see pg_disposable).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth import hash_api_key
from app.core.config import settings
from app.core.llm import LLMClient
from app.core.llm_errors import ErrorClass, LLMAuthError, LLMProviderError
from app.models.database import (
    ApiKey,
    DOMChunk,
    Evidence,
    Intent,
    Organization,
    RemediationRun,
    Scan,
    ScanSummary,
)
from app.orchestration import scan_summary as scan_summary_mod
from app.orchestration.scan_summary import (
    PROMPT_VERSION,
    build_scan_snapshot,
    compute_input_hash,
    generate_summary,
    get_summary,
    prepare_summary_input,
)
from app.schemas.summary import (
    LlmFactStatement,
    LlmNextStep,
    LlmOverallAssessment,
    LlmSummaryPayload,
    SummaryPriority,
    SummaryReason,
    SummaryStatus,
    SummaryVerdict,
)
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

FINDING_KEY = "hours"
_FORBIDDEN_HEALTH = re.compile(
    r"\b(healthy|no issues|passed|all clear|no problems|fully verified)\b",
    re.IGNORECASE,
)


class _FakeCompletions:
    def __init__(self, handler: AsyncMock) -> None:
        self.create = handler


class _FakeChat:
    def __init__(self, handler: AsyncMock) -> None:
        self.completions = _FakeCompletions(handler)


class _FakeInstructorClient:
    def __init__(self, handler: AsyncMock) -> None:
        self.chat = _FakeChat(handler)


def _issues_found_payload(intent_key: str = FINDING_KEY) -> LlmSummaryPayload:
    fid = f"I_{intent_key}"
    return LlmSummaryPayload(
        overall_assessment=LlmOverallAssessment(
            text="The scan found conflicting evidence for a business claim.",
            fact_ids=[fid],
        ),
        what_the_scan_found=[
            LlmFactStatement(
                text="Excerpts disagree on stated business hours.",
                fact_ids=[fid],
            ),
        ],
        why_it_matters=[
            LlmFactStatement(
                text="Inconsistent hours can confuse visitors.",
                fact_ids=[fid],
            ),
        ],
        evidence_gaps=[],
        next_steps=[
            LlmNextStep(
                text="Align hours copy across the site.",
                priority=SummaryPriority.HIGH,
                fact_ids=[fid],
            ),
        ],
        limitations="",
    )


def _insufficient_evidence_payload() -> LlmSummaryPayload:
    return LlmSummaryPayload(
        overall_assessment=LlmOverallAssessment(
            text="Evidence was too limited to confirm site claims.",
            fact_ids=["E_unknown_count", "F_dom_chunks"],
        ),
        what_the_scan_found=[
            LlmFactStatement(
                text="Intent checks returned UNKNOWN without supporting excerpts.",
                fact_ids=["E_unknown_count"],
            ),
        ],
        why_it_matters=[
            LlmFactStatement(
                text="Without DOM chunks, grounding stays uncertain.",
                fact_ids=["F_dom_chunks"],
            ),
        ],
        evidence_gaps=[
            LlmFactStatement(
                text="All intents are UNKNOWN and no DOM chunks were captured.",
                fact_ids=["E_unknown_count", "F_dom_chunks"],
            ),
        ],
        next_steps=[
            LlmNextStep(
                text="Re-run the scan after pages expose readable content.",
                priority=SummaryPriority.MEDIUM,
                fact_ids=["F_dom_chunks"],
            ),
        ],
        limitations="",
    )


class ControllableSummaryLlm:
    """Deterministic fake instructor backend with call counting."""

    def __init__(self) -> None:
        self.handler = AsyncMock(side_effect=self._dispatch)
        self.responses: list[Any] = []
        self.call_count = 0
        self.model = settings.SUMMARY_LLM_MODEL

    async def _dispatch(self, **_kwargs: Any) -> LlmSummaryPayload:
        self.call_count += 1
        if not self.responses:
            return _issues_found_payload()
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def client(self) -> LLMClient:
        return LLMClient(
            api_key="test-summary-key",
            model=self.model,
            max_calls=5,
            instructor_client=_FakeInstructorClient(self.handler),
        )


@pytest_asyncio.fixture
async def pg_url() -> str:
    if not integration_enabled():
        pytest.skip("FINDABLE_PG_INTEGRATION not enabled")
    url = resolve_pg_url()
    assert_disposable_url(url)
    try:
        await ensure_database_exists(url)
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    return url


@pytest_asyncio.fixture
async def pg_engine(pg_url: str):
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    await reset_public_schema(engine)
    await create_all_with_vector(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session_factory(pg_engine):
    return async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def pg_session(pg_session_factory):
    async with pg_session_factory() as session:
        yield session


async def _seed_org_key(
    session: AsyncSession,
    *,
    name: str = "Org",
) -> tuple[uuid.UUID, str]:
    org_id = uuid.uuid4()
    raw_key = f"fnd_live_{org_id.hex[:12]}_summary_key"
    session.add(
        Organization(
            id=org_id,
            name=name,
            slug=f"org-{org_id.hex[:8]}",
            rate_limit_per_min=1000,
        )
    )
    session.add(
        ApiKey(
            id=uuid.uuid4(),
            org_id=org_id,
            key_prefix="fnd_live",
            hashed_key=hash_api_key(raw_key),
            name="test",
            rate_limit_per_min=1000,
        )
    )
    await session.flush()
    return org_id, raw_key


async def _seed_finding_scan(
    session: AsyncSession,
    *,
    org_id: uuid.UUID | None,
    outcome: str = "success",
    batches_completed: int | None = 10,
    batches_total: int | None = 10,
    llm_calls_made: int = 2,
    remediation_eligible: bool | None = True,
) -> uuid.UUID:
    """Scan A: CONTRADICTED intent + evidence + DOM chunk => issues_found."""
    scan_id = uuid.uuid4()
    session.add(
        Scan(
            id=scan_id,
            org_id=org_id,
            url="https://summary.example/",
            status="completed",
            outcome=outcome,
            batches_completed=batches_completed,
            batches_total=batches_total,
            llm_calls_made=llm_calls_made,
            remediation_eligible=remediation_eligible,
        )
    )
    chunk_id = uuid.uuid4()
    session.add(
        DOMChunk(
            id=chunk_id,
            scan_id=scan_id,
            url="https://summary.example/hours",
            dom_path="main > section",
            content="Hours Mon-Fri 9-5",
            tag="section",
            word_count=4,
        )
    )
    intent_id = uuid.uuid4()
    session.add(
        Intent(
            id=intent_id,
            scan_id=scan_id,
            intent_key=FINDING_KEY,
            category="availability",
            query="What are your hours?",
            status="CONTRADICTED",
            reasoning="Conflicting hours.",
            confidence=0.88,
        )
    )
    session.add(
        Evidence(
            id=uuid.uuid4(),
            intent_id=intent_id,
            chunk_id=chunk_id,
            rank=1,
            rrf_score=0.05,
            source_url="https://summary.example/hours",
            excerpt="Open Monday through Friday 9am to 5pm",
            dom_path="main > section",
        )
    )
    await session.flush()
    return scan_id


async def _seed_insufficient_scan(
    session: AsyncSession,
    *,
    org_id: uuid.UUID | None,
) -> uuid.UUID:
    """Scan B: all UNKNOWN intents, zero evidence, zero DOM chunks."""
    scan_id = uuid.uuid4()
    session.add(
        Scan(
            id=scan_id,
            org_id=org_id,
            url="https://meetonmemory.example/",
            status="completed",
            outcome="success",
            batches_completed=10,
            batches_total=10,
            llm_calls_made=0,
        )
    )
    for key in ("hours", "contact", "services"):
        session.add(
            Intent(
                id=uuid.uuid4(),
                scan_id=scan_id,
                intent_key=key,
                category="general",
                query=f"What is your {key}?",
                status="UNKNOWN",
                reasoning="No evidence.",
                confidence=0.0,
            )
        )
    await session.flush()
    return scan_id


async def _seed_score_mismatch_scan(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
) -> uuid.UUID:
    scan_id = await _seed_finding_scan(session, org_id=org_id)
    scan = await session.get(Scan, scan_id)
    assert scan is not None
    scan.f_score = 30.0
    scan.s_ans = 0.0
    scan.s_con = 0.0
    scan.s_str = 0.0
    scan.s_acc = 0.0
    await session.flush()
    return scan_id


@pytest.mark.asyncio
async def test_pg_cross_tenant_summary_denied(pg_session: AsyncSession) -> None:
    from fastapi import HTTPException

    from app.core.auth import TenantContext
    from app.core.tenancy import get_scan_for_org

    org_a, _ = await _seed_org_key(pg_session, name="A")
    org_b, _ = await _seed_org_key(pg_session, name="B")
    scan_b = await _seed_finding_scan(pg_session, org_id=org_b)
    await pg_session.commit()

    tenant_a = TenantContext(org_id=org_a, role="member")
    with pytest.raises(HTTPException) as exc:
        await get_scan_for_org(pg_session, scan_b, tenant_a)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_pg_legacy_null_org_scan_denied_for_org_tenant(
    pg_session: AsyncSession,
) -> None:
    from fastapi import HTTPException

    from app.core.auth import TenantContext
    from app.core.tenancy import get_scan_for_org

    org_a, _ = await _seed_org_key(pg_session)
    scan_legacy = await _seed_finding_scan(pg_session, org_id=None)
    await pg_session.commit()

    tenant_a = TenantContext(org_id=org_a, role="member")
    with pytest.raises(HTTPException) as exc:
        await get_scan_for_org(pg_session, scan_legacy, tenant_a)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_pg_issues_found_llm_called(pg_session: AsyncSession) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    fake.responses = [_issues_found_payload()]
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        resp, status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert status == 200
    assert fake.call_count >= 1
    assert resp.verdict == SummaryVerdict.ISSUES_FOUND


@pytest.mark.asyncio
async def test_pg_insufficient_evidence_llm_still_called(pg_session: AsyncSession) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_insufficient_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    fake.responses = [_insufficient_evidence_payload()]
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        resp, status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert status == 200
    assert fake.call_count >= 1
    assert resp.verdict == SummaryVerdict.INSUFFICIENT_EVIDENCE
    assert resp.evidence_gaps
    combined = " ".join(
        [resp.overall_assessment.text if resp.overall_assessment else ""]
        + [s.text for s in resp.evidence_gaps]
    )
    assert not _FORBIDDEN_HEALTH.search(combined)


@pytest.mark.asyncio
async def test_pg_zero_dom_chunks_signal(pg_session: AsyncSession) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_insufficient_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    fake.responses = [_insufficient_evidence_payload()]
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        resp, status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert status == 200
    assert resp.signals is not None
    assert resp.signals.zero_dom_chunks is True


@pytest.mark.asyncio
async def test_pg_score_pillar_mismatch_signal(pg_session: AsyncSession) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_score_mismatch_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    fake.responses = [_issues_found_payload()]
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        resp, status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert status == 200
    assert resp.signals is not None
    assert resp.signals.score_pillar_mismatch is True


@pytest.mark.asyncio
async def test_pg_ineligible_scan_409(pg_session: AsyncSession) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = uuid.uuid4()
    pg_session.add(
        Scan(
            id=scan_id,
            org_id=org_id,
            url="https://failed.example/",
            status="failed",
            outcome="failed",
        )
    )
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        resp, status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert status == 409
    assert resp.reason == SummaryReason.SCAN_FAILED.value
    assert fake.call_count == 0


@pytest.mark.asyncio
async def test_pg_cache_hit_second_post_no_extra_llm(
    pg_session: AsyncSession,
) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    fake.responses = [_issues_found_payload()]
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        first, s1 = await generate_summary(pg_session, scan, llm_client=fake.client())
        assert s1 == 200
        assert first.cached is False

    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        second, s2 = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert s2 == 200
    assert fake.call_count == 1
    assert second.cached is True
    assert second.overall_assessment == first.overall_assessment


@pytest.mark.asyncio
async def test_pg_prompt_version_bump_regenerates(
    pg_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    fake.responses = [_issues_found_payload(), _issues_found_payload()]
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        await generate_summary(pg_session, scan, llm_client=fake.client())
    assert fake.call_count == 1

    from app.core.budget import clear_process_response_cache

    clear_process_response_cache()
    monkeypatch.setattr(scan_summary_mod, "PROMPT_VERSION", "v2-bump-test")
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        await generate_summary(pg_session, scan, llm_client=fake.client())
    assert fake.call_count == 2


@pytest.mark.asyncio
async def test_pg_single_flight_one_llm_call(
    pg_session_factory,
    pg_url: str,
) -> None:
    org_id = uuid.uuid4()
    scan_id = uuid.uuid4()
    async with pg_session_factory() as session:
        async with session.begin():
            session.add(
                Organization(
                    id=org_id,
                    name="SF",
                    slug=f"sf-{org_id.hex[:6]}",
                    rate_limit_per_min=1000,
                )
            )
            scan_id = await _seed_finding_scan(session, org_id=org_id)

    fake = ControllableSummaryLlm()

    async def slow(**_kwargs: Any) -> LlmSummaryPayload:
        fake.call_count += 1
        await asyncio.sleep(0.4)
        return _issues_found_payload()

    fake.handler = AsyncMock(side_effect=slow)
    client = fake.client()

    async def _post_once() -> int:
        engine = create_async_engine(pg_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                async with session.begin():
                    scan = await session.get(Scan, scan_id)
                    assert scan is not None
                    _, code = await generate_summary(session, scan, llm_client=client)
                await session.commit()
                return code
        finally:
            await engine.dispose()

    codes = await asyncio.gather(*[_post_once() for _ in range(5)])
    assert all(c in (200, 202) for c in codes)
    assert fake.call_count == 1


@pytest.mark.asyncio
async def test_pg_rate_limit_boundary_ok_then_429(
    pg_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    monkeypatch.setattr(settings, "SUMMARY_RATE_LIMIT_PER_SCAN_PER_HOUR", 3)
    now = datetime.now(UTC)

    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        snapshot = await build_scan_snapshot(pg_session, scan)
        base_hash = compute_input_hash(snapshot)
        for i in range(2):
            alt_hash = f"{i:02x}{base_hash}"[:64]
            pg_session.add(
                ScanSummary(
                    id=uuid.uuid4(),
                    scan_id=scan_id,
                    org_id=org_id,
                    input_hash=alt_hash,
                    prompt_version=PROMPT_VERSION,
                    model=settings.SUMMARY_LLM_MODEL,
                    status="ready",
                    content={
                        "overall_assessment": {"text": "cached", "fact_ids": []},
                        "verdict": SummaryVerdict.ISSUES_FOUND.value,
                    },
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=5),
                )
            )

    fake = ControllableSummaryLlm()
    fake.responses = [_issues_found_payload()]
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        ok_resp, ok_status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert ok_status == 200
    assert fake.call_count == 1

    async with pg_session.begin():
        pg_session.add(
            ScanSummary(
                id=uuid.uuid4(),
                scan_id=scan_id,
                org_id=org_id,
                input_hash=f"ee{base_hash}"[:64],
                prompt_version=PROMPT_VERSION,
                model=settings.SUMMARY_LLM_MODEL,
                status="ready",
                content={
                    "overall_assessment": {"text": "cached2", "fact_ids": []},
                    "verdict": SummaryVerdict.ISSUES_FOUND.value,
                },
                created_at=now - timedelta(minutes=2),
                updated_at=now - timedelta(minutes=2),
            )
        )

    intent = (
        await pg_session.execute(
            select(Intent).where(Intent.scan_id == scan_id, Intent.intent_key == FINDING_KEY)
        )
    ).scalar_one()
    ev = (
        await pg_session.execute(select(Evidence).where(Evidence.intent_id == intent.id))
    ).scalar_one()
    ev.excerpt = "Change hash so cache miss triggers new generation"
    # Invalidate prepared summary-input so the next generate rebuilds a new hash.
    scan_row = await pg_session.get(Scan, scan_id)
    assert scan_row is not None
    scan_row.summary_input = None
    scan_row.summary_input_hash = None
    scan_row.summary_input_prepared_at = None
    await pg_session.commit()

    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        limited, lim_status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert lim_status == 429
    assert limited.reason == SummaryReason.SUMMARY_RATE_LIMITED.value
    assert fake.call_count == 1
    assert ok_resp.overall_assessment is not None


@pytest.mark.asyncio
async def test_pg_validation_repair_then_502(pg_session: AsyncSession) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    bad = LlmSummaryPayload(
        overall_assessment=LlmOverallAssessment(
            text="The site is healthy and fully verified with no issues.",
            fact_ids=["nonexistent_fact"],
        ),
        what_the_scan_found=[
            LlmFactStatement(text="Invented claim.", fact_ids=["nonexistent_fact"]),
        ],
        why_it_matters=[
            LlmFactStatement(text="Invented why.", fact_ids=["nonexistent_fact"]),
        ],
        evidence_gaps=[],
        next_steps=[
            LlmNextStep(
                text="Do nothing.",
                priority=SummaryPriority.LOW,
                fact_ids=["nonexistent_fact"],
            ),
        ],
        limitations="",
    )
    fake.responses = [bad, bad]

    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        resp, status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert status == 502
    assert resp.reason == SummaryReason.SUMMARY_GENERATION_FAILED.value
    assert fake.call_count == 2


@pytest.mark.asyncio
async def test_pg_provider_auth_error_no_retry(pg_session: AsyncSession) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    fake.responses = [
        LLMAuthError(
            "invalid key",
            provider="test",
            model=settings.SUMMARY_LLM_MODEL,
            error_class=ErrorClass.AUTH,
        )
    ]

    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        resp, status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert status == 502
    assert resp.reason == SummaryReason.PROVIDER_AUTH_ERROR.value
    assert fake.call_count == 1


@pytest.mark.asyncio
async def test_pg_truncation_repair_then_success(pg_session: AsyncSession) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    fake.responses = [
        LLMProviderError(
            "The output is incomplete due to a max_tokens length limit.",
            provider="gemini",
            model=settings.SUMMARY_LLM_MODEL,
            error_class=ErrorClass.CONTEXT_LENGTH,
        ),
        _issues_found_payload(),
    ]

    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        resp, status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert status == 200
    assert resp.status == SummaryStatus.READY
    assert fake.call_count == 2


@pytest.mark.asyncio
async def test_pg_prepare_summary_input_reused_on_generate(
    pg_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    build_calls = {"n": 0}
    real_build = scan_summary_mod.build_scan_snapshot

    async def _counting_build(session: AsyncSession, scan: Scan):
        build_calls["n"] += 1
        return await real_build(session, scan)

    monkeypatch.setattr(scan_summary_mod, "build_scan_snapshot", _counting_build)

    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        snap = await prepare_summary_input(pg_session, scan)
        assert snap is not None
        assert scan.summary_input_hash
        assert scan.summary_input is not None

    after_prepare = build_calls["n"]
    assert after_prepare >= 1

    fake = ControllableSummaryLlm()
    fake.responses = [_issues_found_payload()]
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        resp, status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert status == 200
    assert resp.status == SummaryStatus.READY
    # load_or_build should reuse prepared snapshot (no extra rebuild).
    assert build_calls["n"] == after_prepare


@pytest.mark.asyncio
async def test_pg_secondary_key_failover_on_rate_limit(
    pg_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    monkeypatch.setattr(scan_summary_mod.settings, "SUMMARY_PROVIDER_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(
        scan_summary_mod,
        "_summary_api_keys",
        lambda: ["primary-key", "secondary-key"],
    )

    clients: list[str] = []
    payloads = [
        LLMProviderError(
            "rate limit 429",
            provider="gemini",
            model=settings.SUMMARY_LLM_MODEL,
            error_class=ErrorClass.RATE_LIMIT,
        ),
        _issues_found_payload(),
    ]

    class _SlotFake:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key
            self.handler = AsyncMock(side_effect=self._dispatch)
            self.model = settings.SUMMARY_LLM_MODEL

        async def _dispatch(self, **_kwargs: Any) -> LlmSummaryPayload:
            item = payloads.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

        def client(self) -> LLMClient:
            return LLMClient(
                api_key=self.api_key,
                model=self.model,
                max_calls=5,
                instructor_client=_FakeInstructorClient(self.handler),
            )

    def _make(*, api_key: str, model: str) -> LLMClient:
        clients.append(api_key)
        return _SlotFake(api_key).client()

    monkeypatch.setattr(scan_summary_mod, "_make_summary_client", _make)

    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        resp, status = await generate_summary(pg_session, scan)
    assert status == 200
    assert resp.status == SummaryStatus.READY
    assert clients == ["primary-key", "secondary-key"]


@pytest.mark.asyncio
async def test_pg_remediation_unavailable_when_not_eligible(
    pg_session: AsyncSession,
) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id, remediation_eligible=False)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    fake.responses = [_issues_found_payload()]
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        resp, status = await generate_summary(pg_session, scan, llm_client=fake.client())
    assert status == 200
    assert resp.remediation_status is not None
    assert resp.remediation_status.value == "unavailable"


@pytest.mark.asyncio
async def test_pg_remediation_label_updates_without_regeneration(
    pg_session: AsyncSession,
) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    fake.responses = [_issues_found_payload()]
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        await generate_summary(pg_session, scan, llm_client=fake.client())

    run_id = uuid.uuid4()
    async with pg_session.begin():
        pg_session.add(
            RemediationRun(
                id=run_id,
                scan_id=scan_id,
                idempotency_key=f"idem-{run_id.hex}",
                repo_full_name="acme/site",
                base_branch="main",
                lifecycle_state="mutating",
            )
        )

    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        got = await get_summary(pg_session, scan)
    assert got.remediation_status is not None
    assert got.remediation_status.value == "in_progress"

    async with pg_session.begin():
        run = await pg_session.get(RemediationRun, run_id)
        assert run is not None
        run.lifecycle_state = "verified"
        await pg_session.flush()
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        got2 = await get_summary(pg_session, scan)
    assert got2.remediation_status is not None
    assert got2.remediation_status.value == "done"
    assert fake.call_count == 1


@pytest.mark.asyncio
async def test_pg_summary_does_not_change_scan_llm_budget(
    pg_session: AsyncSession,
) -> None:
    org_id, _ = await _seed_org_key(pg_session)
    scan_id = await _seed_finding_scan(pg_session, org_id=org_id, llm_calls_made=7)
    await pg_session.commit()

    fake = ControllableSummaryLlm()
    fake.responses = [_issues_found_payload()]
    async with pg_session.begin():
        scan = await pg_session.get(Scan, scan_id)
        assert scan is not None
        before = int(scan.llm_calls_made or 0)
        await generate_summary(pg_session, scan, llm_client=fake.client())
        after = int(scan.llm_calls_made or 0)
    assert before == 7
    assert after == 7
    assert fake.call_count == 1
