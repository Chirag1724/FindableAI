"""PostgreSQL integration: retrieval isolation + evidence persistence/integrity.

Requires FINDABLE_PG_INTEGRATION=1 and a disposable PostgreSQL+pgvector URL.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.crawler.dom_chunker import ChunkData
from app.crawler.search import hybrid_search, store_dom_chunks
from app.models.database import DOMChunk, Evidence, Intent, Scan
from app.orchestration.evidence_persistence import (
    apply_persisted_evidence_integrity,
    build_evidence_rows_for_intent,
    hydrate_evidence_for_intents,
    load_chunk_id_map,
)
from app.schemas.intelligence import (
    EntailmentStatus,
    EvidenceReference,
    IntentCategory,
    IntentEvaluation,
)
from tests.pg_disposable import (
    PG_SKIP_REASON,
    assert_disposable_url,
    create_all_with_vector,
    ensure_database_exists,
    integration_enabled,
    reset_public_schema,
    resolve_pg_url,
    run_alembic_upgrade,
)

pytestmark = pytest.mark.skipif(not integration_enabled(), reason=PG_SKIP_REASON)


@pytest_asyncio.fixture
async def pg_url() -> str:
    if not integration_enabled():
        pytest.skip("FINDABLE_PG_INTEGRATION not enabled")
    url = resolve_pg_url()
    assert_disposable_url(url)
    try:
        await ensure_database_exists(url)
    except Exception as exc:
        pytest.skip(f"PostgreSQL admin/bootstrap unavailable: {exc}")
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    await engine.dispose()
    return url


@pytest_asyncio.fixture
async def pg_session(pg_url: str):
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    try:
        await reset_public_schema(engine)
        await create_all_with_vector(engine)
    except Exception as exc:
        await engine.dispose()
        pytest.fail(f"Failed to prepare disposable schema with pgvector: {exc}")

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_scan_with_chunk(
    session: AsyncSession,
    *,
    content: str,
    url: str = "https://example.com/hours",
) -> tuple[uuid.UUID, uuid.UUID]:
    scan_id = uuid.uuid4()
    session.add(
        Scan(
            id=scan_id,
            url=url,
            status="completed",
        )
    )
    await session.flush()
    rows = await store_dom_chunks(
        scan_id,
        [
            ChunkData(
                url=url,
                dom_path="main > section.hours",
                content=content,
                tag="section",
                word_count=len(content.split()),
            )
        ],
        session=session,
    )
    assert len(rows) == 1
    return scan_id, rows[0].id


@pytest.mark.asyncio
async def test_pg_retrieval_scan_isolation(pg_session: AsyncSession):
    """hybrid_search must not return chunks belonging to another scan."""
    async with pg_session.begin():
        scan_a, _ = await _seed_scan_with_chunk(
            pg_session, content="Office hours are Monday to Friday 9am to 5pm."
        )
        scan_b, chunk_b = await _seed_scan_with_chunk(
            pg_session, content="Completely unrelated pricing table for enterprise plans."
        )

    hits_a = await hybrid_search("office hours Monday Friday", scan_a, k=5, session=pg_session)
    assert hits_a
    assert all(h.scan_id == scan_a for h in hits_a)
    assert all(h.id != chunk_b for h in hits_a)

    hits_b = await hybrid_search("enterprise pricing plans", scan_b, k=5, session=pg_session)
    assert hits_b
    assert all(h.scan_id == scan_b for h in hits_b)


@pytest.mark.asyncio
async def test_pg_evidence_persist_reload_fresh_session(pg_url: str, pg_session: AsyncSession):
    """Evidence + provenance survive commit and reload in a new DB session."""
    async with pg_session.begin():
        scan_id, chunk_id = await _seed_scan_with_chunk(
            pg_session, content="We are open Monday through Friday from 9am until 5pm."
        )
        intent_id = uuid.uuid4()
        pg_session.add(
            Intent(
                id=intent_id,
                scan_id=scan_id,
                category="availability",
                persona="cto",
                query="What are the hours?",
                status="SUPPORTED",
                reasoning="Hours stated on the page.",
                confidence=0.91,
            )
        )
        await pg_session.flush()
        chunk_map = await load_chunk_id_map(pg_session, scan_id)
        evaluation = IntentEvaluation(
            intent_id="intent_hours",
            query="What are the hours?",
            status=EntailmentStatus.SUPPORTED,
            reasoning="Hours stated on the page.",
            confidence=0.91,
            category=IntentCategory.AVAILABILITY,
            evidence=[
                EvidenceReference(
                    chunk_id=str(chunk_id),
                    dom_path="main > section.hours",
                    rank=1,
                    url="https://example.com/hours",
                    excerpt="open Monday through Friday",
                    rrf_score=0.03125,
                )
            ],
        )
        built = build_evidence_rows_for_intent(
            intent_id=intent_id,
            evaluation=evaluation,
            chunk_map=chunk_map,
            intent_scan_id=scan_id,
        )
        assert built.persisted_count == 1
        for row in built.rows:
            pg_session.add(row)

    # Fresh session (process restart simulation)
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as fresh:
            intent = await fresh.get(Intent, intent_id)
            assert intent is not None
            hydrated = await hydrate_evidence_for_intents(fresh, [intent])
            refs = hydrated[intent_id]
            assert len(refs) == 1
            assert refs[0].chunk_id == str(chunk_id)
            assert refs[0].dom_path == "main > section.hours"
            assert refs[0].excerpt == "open Monday through Friday"
            assert refs[0].rrf_score == 0.03125
            assert refs[0].url == "https://example.com/hours"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pg_cross_scan_evidence_rejected_app_and_trigger(pg_url: str):
    """Cross-scan cites are rejected by app mapping and by the 0007 DB trigger."""
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    try:
        await reset_public_schema(engine)
        run_alembic_upgrade(pg_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            async with session.begin():
                scan_a = uuid.uuid4()
                scan_b = uuid.uuid4()
                session.add_all(
                    [
                        Scan(id=scan_a, url="https://a.example/", status="completed"),
                        Scan(id=scan_b, url="https://b.example/", status="completed"),
                    ]
                )
                await session.flush()
                chunk_a = DOMChunk(
                    id=uuid.uuid4(),
                    scan_id=scan_a,
                    url="https://a.example/",
                    dom_path="main > p",
                    content="Hours A",
                    tag="p",
                    word_count=2,
                )
                chunk_b = DOMChunk(
                    id=uuid.uuid4(),
                    scan_id=scan_b,
                    url="https://b.example/",
                    dom_path="main > p",
                    content="Hours B",
                    tag="p",
                    word_count=2,
                )
                session.add_all([chunk_a, chunk_b])
                intent_a = Intent(
                    id=uuid.uuid4(),
                    scan_id=scan_a,
                    category="availability",
                    query="Hours?",
                    status="SUPPORTED",
                    reasoning="cite",
                    confidence=0.9,
                )
                session.add(intent_a)
                await session.flush()

                # App-layer: foreign chunk must not persist even if stuffed into map.
                stuffed = {chunk_a.id: chunk_a, chunk_b.id: chunk_b}
                evaluation = IntentEvaluation(
                    intent_id="i1",
                    query="Hours?",
                    status=EntailmentStatus.SUPPORTED,
                    reasoning="Would cite foreign chunk.",
                    confidence=0.9,
                    category=IntentCategory.AVAILABILITY,
                    evidence=[
                        EvidenceReference(
                            chunk_id=str(chunk_b.id),
                            dom_path="main > p",
                            rank=1,
                        )
                    ],
                )
                built = build_evidence_rows_for_intent(
                    intent_id=intent_a.id,
                    evaluation=evaluation,
                    chunk_map=stuffed,
                    intent_scan_id=scan_a,
                )
                assert built.persisted_count == 0
                assert built.cross_scan_count == 1
                clean = apply_persisted_evidence_integrity(evaluation, built)
                assert clean.status is EntailmentStatus.UNKNOWN
                assert clean.evidence == []

                # DB trigger: attempting a cross-scan evidence row must fail.
                with pytest.raises((DBAPIError, Exception)):
                    async with session.begin_nested():
                        session.add(
                            Evidence(
                                id=uuid.uuid4(),
                                intent_id=intent_a.id,
                                chunk_id=chunk_b.id,
                                rank=1,
                                observation_phase="scan",
                                dom_path="main > p",
                                excerpt="Hours B",
                            )
                        )
                        await session.flush()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pg_malformed_and_missing_evidence_downgrade(pg_session: AsyncSession):
    async with pg_session.begin():
        scan_id, chunk_id = await _seed_scan_with_chunk(
            pg_session, content="Refunds are processed within 14 days."
        )
        chunk_map = await load_chunk_id_map(pg_session, scan_id)
        intent_id = uuid.uuid4()
        bad = IntentEvaluation(
            intent_id="i_bad",
            query="Refund policy?",
            status=EntailmentStatus.SUPPORTED,
            reasoning="Model invented a citation.",
            confidence=0.88,
            category=IntentCategory.POLICY,
            evidence=[
                EvidenceReference(chunk_id="chunk_0", dom_path="main > p", rank=1),
                EvidenceReference(chunk_id=str(uuid.uuid4()), dom_path="main > p", rank=2),
                EvidenceReference(chunk_id="not-a-uuid", dom_path="main > p", rank=3),
            ],
        )
        built = build_evidence_rows_for_intent(
            intent_id=intent_id,
            evaluation=bad,
            chunk_map=chunk_map,
            intent_scan_id=scan_id,
        )
        assert built.persisted_count == 0
        clean = apply_persisted_evidence_integrity(bad, built)
        assert clean.status is EntailmentStatus.UNKNOWN
        assert clean.evidence == []
        assert "Evidence validation failed" in clean.reasoning

        good = IntentEvaluation(
            intent_id="i_good",
            query="Refund policy?",
            status=EntailmentStatus.SUPPORTED,
            reasoning="Cited persisted chunk.",
            confidence=0.88,
            category=IntentCategory.POLICY,
            evidence=[
                EvidenceReference(
                    chunk_id=str(chunk_id),
                    dom_path="main > section.hours",
                    rank=1,
                    excerpt="Refunds are processed within 14 days.",
                )
            ],
        )
        built_ok = build_evidence_rows_for_intent(
            intent_id=intent_id,
            evaluation=good,
            chunk_map=chunk_map,
            intent_scan_id=scan_id,
        )
        clean_ok = apply_persisted_evidence_integrity(good, built_ok)
        assert clean_ok.status is EntailmentStatus.SUPPORTED
        assert len(clean_ok.evidence) == 1
        assert clean_ok.evidence[0].chunk_id == str(chunk_id)


@pytest.mark.asyncio
async def test_pg_migration_0007_removes_legacy_cross_scan_evidence(pg_url: str):
    """Non-empty DB: 0007 deletes only cross-scan evidence, keeps valid rows + trigger."""
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    try:
        await reset_public_schema(engine)
        run_alembic_upgrade(pg_url, revision="0006_progress_checkpoints")

        scan_a = uuid.uuid4()
        scan_b = uuid.uuid4()
        chunk_a = uuid.uuid4()
        chunk_b = uuid.uuid4()
        intent_a = uuid.uuid4()
        valid_ev = uuid.uuid4()
        bad_ev = uuid.uuid4()

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO scans (id, url, status) VALUES "
                    "(:a, 'https://a.example/', 'completed'), "
                    "(:b, 'https://b.example/', 'completed')"
                ),
                {"a": scan_a, "b": scan_b},
            )
            await conn.execute(
                text(
                    "INSERT INTO dom_chunks "
                    "(id, scan_id, url, dom_path, content, tag, word_count) VALUES "
                    "(:ca, :a, 'https://a.example/', 'main > p', 'Hours A', 'p', 2), "
                    "(:cb, :b, 'https://b.example/', 'main > p', 'Hours B', 'p', 2)"
                ),
                {"ca": chunk_a, "cb": chunk_b, "a": scan_a, "b": scan_b},
            )
            await conn.execute(
                text(
                    "INSERT INTO intents (id, scan_id, category, query, status, reasoning, confidence) "
                    "VALUES (:i, :a, 'availability', 'Hours?', 'SUPPORTED', 'ok', 0.9)"
                ),
                {"i": intent_a, "a": scan_a},
            )
            # Valid same-scan evidence + invalid cross-scan evidence (pre-trigger).
            await conn.execute(
                text(
                    "INSERT INTO evidence "
                    "(id, intent_id, chunk_id, rank, observation_phase, dom_path, excerpt) VALUES "
                    "(:v, :i, :ca, 1, 'scan', 'main > p', 'Hours A'), "
                    "(:bad, :i, :cb, 2, 'scan', 'main > p', 'Hours B')"
                ),
                {"v": valid_ev, "bad": bad_ev, "i": intent_a, "ca": chunk_a, "cb": chunk_b},
            )

        run_alembic_upgrade(pg_url, revision="head")

        async with engine.connect() as conn:
            remaining = await conn.execute(text("SELECT id FROM evidence ORDER BY rank"))
            ids = {row[0] for row in remaining}
            assert valid_ev in ids
            assert bad_ev not in ids

            intent_still = await conn.scalar(
                text("SELECT 1 FROM intents WHERE id = :i"), {"i": intent_a}
            )
            assert intent_still == 1

            persona = await conn.scalar(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'intents' AND column_name = 'persona'"
                )
            )
            assert persona == 1

            trigger = await conn.scalar(
                text(
                    "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_evidence_same_scan' "
                    "AND NOT tgisinternal"
                )
            )
            assert trigger == 1

            rev = await conn.scalar(text("SELECT version_num FROM alembic_version"))
            assert rev == "0017_phase3_integrity"
    finally:
        await engine.dispose()
