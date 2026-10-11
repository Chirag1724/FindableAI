"""Phase 2 Stage 2: durable evidence write/hydrate helpers (no fabricated cites)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.orchestration.evidence_persistence import (
    OBSERVATION_SCAN,
    OBSERVATION_VERIFICATION,
    ROLE_SUPPORTING,
    build_evidence_rows_for_intent,
    evidence_persistence_warning,
    evidence_role_for_status,
)
from app.schemas.intelligence import (
    EntailmentStatus,
    EvidenceReference,
    IntentCategory,
    IntentEvaluation,
)


def _chunk(
    cid: uuid.UUID, *, url: str = "https://ex.com", path: str = "main > p"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=cid,
        url=url,
        dom_path=path,
        content="Hours are 9am to 5pm Monday through Friday on the contact page.",
    )


def test_resolved_uuid_citations_persist_with_provenance():
    intent_id = uuid.uuid4()
    real_id = uuid.uuid4()
    chunk_map = {real_id: _chunk(real_id, url="https://ex.com/hours", path="section#hours")}
    evaluation = IntentEvaluation(
        intent_id="intent_01",
        query="What are the hours?",
        status=EntailmentStatus.SUPPORTED,
        reasoning="Cited chunk supports hours.",
        confidence=0.9,
        category=IntentCategory.AVAILABILITY,
        evidence=[
            EvidenceReference(
                chunk_id=str(real_id),
                dom_path="section#hours",
                rank=1,
                url="https://ex.com/hours",
                excerpt="Hours are 9am to 5pm",
                rrf_score=0.42,
            ),
        ],
    )
    built = build_evidence_rows_for_intent(
        intent_id=intent_id,
        evaluation=evaluation,
        chunk_map=chunk_map,
    )
    assert built.citation_count == 1
    assert built.persisted_count == 1
    assert built.unresolved_count == 0
    assert len(built.rows) == 1
    row = built.rows[0]
    assert row.chunk_id == real_id
    assert row.intent_id == intent_id
    assert row.evidence_role == ROLE_SUPPORTING
    assert row.source_url == "https://ex.com/hours"
    assert row.excerpt == "Hours are 9am to 5pm"
    assert row.dom_path == "section#hours"
    assert row.observation_phase == OBSERVATION_SCAN
    assert row.rrf_score == 0.42


def test_index_style_chunk_ids_are_not_persisted():
    intent_id = uuid.uuid4()
    real_id = uuid.uuid4()
    chunk_map = {real_id: _chunk(real_id)}
    evaluation = IntentEvaluation(
        intent_id="intent_01",
        query="What are the hours?",
        status=EntailmentStatus.SUPPORTED,
        reasoning="Cited chunk supports hours.",
        confidence=0.9,
        category=IntentCategory.AVAILABILITY,
        evidence=[
            EvidenceReference(chunk_id="chunk_0", dom_path="main > p", rank=1),
            EvidenceReference(
                chunk_id=str(real_id), dom_path="main > p", rank=2, url="https://ex.com"
            ),
        ],
    )
    built = build_evidence_rows_for_intent(
        intent_id=intent_id,
        evaluation=evaluation,
        chunk_map=chunk_map,
    )
    assert built.citation_count == 2
    assert built.persisted_count == 1
    assert built.unresolved_count == 1
    assert len(built.rows) == 1
    assert built.rows[0].chunk_id == real_id
    assert built.rows[0].evidence_role == ROLE_SUPPORTING
    assert built.rows[0].source_url == "https://ex.com"
    assert built.rows[0].excerpt
    assert built.rows[0].dom_path == "main > p"


def test_unknown_chunk_uuid_skipped_no_fabrication():
    intent_id = uuid.uuid4()
    evaluation = IntentEvaluation(
        intent_id="intent_02",
        query="Pricing?",
        status=EntailmentStatus.SUPPORTED,
        reasoning="Would cite missing chunk.",
        confidence=0.8,
        category=IntentCategory.PRICING,
        evidence=[
            EvidenceReference(
                chunk_id=str(uuid.uuid4()),
                dom_path="main > div",
                rank=1,
            )
        ],
    )
    built = build_evidence_rows_for_intent(
        intent_id=intent_id,
        evaluation=evaluation,
        chunk_map={},
    )
    assert built.rows == []
    assert built.persisted_count == 0
    assert built.unresolved_count == 1
    assert evidence_persistence_warning(built.citation_count, built.persisted_count)


def test_supporting_and_contradicting_roles():
    intent_id = uuid.uuid4()
    cid = uuid.uuid4()
    chunk_map = {cid: _chunk(cid)}
    supporting = IntentEvaluation(
        intent_id="intent_s",
        query="Hours?",
        status=EntailmentStatus.SUPPORTED,
        reasoning="ok",
        confidence=0.9,
        category=IntentCategory.AVAILABILITY,
        evidence=[EvidenceReference(chunk_id=str(cid), dom_path="main > p", rank=1)],
    )
    contradicting = IntentEvaluation(
        intent_id="intent_c",
        query="Hours?",
        status=EntailmentStatus.CONTRADICTED,
        reasoning="conflict",
        confidence=0.7,
        category=IntentCategory.AVAILABILITY,
        evidence=[EvidenceReference(chunk_id=str(cid), dom_path="main > p", rank=1)],
    )
    assert (
        build_evidence_rows_for_intent(
            intent_id=intent_id, evaluation=supporting, chunk_map=chunk_map
        )
        .rows[0]
        .evidence_role
        == "supporting"
    )
    assert (
        build_evidence_rows_for_intent(
            intent_id=intent_id, evaluation=contradicting, chunk_map=chunk_map
        )
        .rows[0]
        .evidence_role
        == "contradicting"
    )


def test_duplicate_chunk_citations_deduped_same_phase():
    intent_id = uuid.uuid4()
    cid = uuid.uuid4()
    chunk_map = {cid: _chunk(cid)}
    evaluation = IntentEvaluation(
        intent_id="intent_03",
        query="Hours?",
        status=EntailmentStatus.CONTRADICTED,
        reasoning="Conflict in hours.",
        confidence=0.7,
        category=IntentCategory.AVAILABILITY,
        evidence=[
            EvidenceReference(chunk_id=str(cid), dom_path="main > p", rank=1),
            EvidenceReference(chunk_id=str(cid), dom_path="main > p", rank=2),
        ],
    )
    built = build_evidence_rows_for_intent(
        intent_id=intent_id,
        evaluation=evaluation,
        chunk_map=chunk_map,
    )
    assert len(built.rows) == 1
    assert built.rows[0].evidence_role == "contradicting"
    assert built.unresolved_count == 1


def test_verification_phase_allowed_distinct_from_scan():
    intent_id = uuid.uuid4()
    cid = uuid.uuid4()
    chunk_map = {cid: _chunk(cid)}
    evaluation = IntentEvaluation(
        intent_id="intent_v",
        query="Hours?",
        status=EntailmentStatus.SUPPORTED,
        reasoning="re-check",
        confidence=0.9,
        category=IntentCategory.AVAILABILITY,
        evidence=[EvidenceReference(chunk_id=str(cid), dom_path="main > p", rank=1)],
    )
    scan_row = build_evidence_rows_for_intent(
        intent_id=intent_id,
        evaluation=evaluation,
        chunk_map=chunk_map,
        observation_phase=OBSERVATION_SCAN,
    ).rows[0]
    verify_row = build_evidence_rows_for_intent(
        intent_id=intent_id,
        evaluation=evaluation,
        chunk_map=chunk_map,
        observation_phase=OBSERVATION_VERIFICATION,
    ).rows[0]
    assert scan_row.observation_phase == OBSERVATION_SCAN
    assert verify_row.observation_phase == OBSERVATION_VERIFICATION
    assert scan_row.chunk_id == verify_row.chunk_id
    assert scan_row.observation_phase != verify_row.observation_phase


def test_evidence_role_mapping():
    assert evidence_role_for_status(EntailmentStatus.SUPPORTED) == "supporting"
    assert evidence_role_for_status(EntailmentStatus.CONTRADICTED) == "contradicting"
    assert evidence_role_for_status(EntailmentStatus.UNKNOWN) == "cited"


def test_persistence_warning_partial_and_empty():
    assert evidence_persistence_warning(0, 0) is None
    assert evidence_persistence_warning(2, 2) is None
    assert "no evidence rows" in (evidence_persistence_warning(3, 0) or "")
    assert "Only 1 of 3" in (evidence_persistence_warning(3, 1) or "")


@pytest.mark.asyncio
async def test_hydrate_uses_stored_dom_path_without_chunk_join():
    """Cold hydrate must work from Evidence provenance when chunk is unavailable."""
    from app.orchestration.evidence_persistence import hydrate_evidence_for_intents

    intent_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    intent = SimpleNamespace(id=intent_id)
    ev = SimpleNamespace(
        id=uuid.uuid4(),
        intent_id=intent_id,
        chunk_id=chunk_id,
        rank=1,
        rrf_score=0.5,
        source_url="https://ex.com/hours",
        excerpt="Open 9-5",
        dom_path="footer > .hours",
        chunk=None,
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [ev]

    class _Session:
        async def execute(self, _stmt):
            return _Result()

    hydrated = await hydrate_evidence_for_intents(_Session(), [intent])
    assert len(hydrated[intent_id]) == 1
    ref = hydrated[intent_id][0]
    assert ref.chunk_id == str(chunk_id)
    assert ref.dom_path == "footer > .hours"
    assert ref.excerpt == "Open 9-5"
    assert ref.url == "https://ex.com/hours"


@pytest.mark.asyncio
async def test_hydrate_evidence_for_intents_roundtrip():
    """SQLite-free unit hydrate: mock session returning evidence-shaped rows."""
    from app.orchestration.evidence_persistence import hydrate_evidence_for_intents

    intent_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    intent = SimpleNamespace(id=intent_id)
    chunk = _chunk(chunk_id)
    ev = SimpleNamespace(
        intent_id=intent_id,
        chunk_id=chunk_id,
        rank=1,
        rrf_score=0.5,
        source_url="https://ex.com/hours",
        excerpt="Open 9-5",
        dom_path=None,
        chunk=chunk,
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [ev]

    class _Session:
        async def execute(self, _stmt):
            return _Result()

    hydrated = await hydrate_evidence_for_intents(_Session(), [intent])
    assert intent_id in hydrated
    assert len(hydrated[intent_id]) == 1
    ref = hydrated[intent_id][0]
    assert ref.chunk_id == str(chunk_id)
    assert ref.dom_path == "main > p"
    assert ref.excerpt == "Open 9-5"
    assert ref.url == "https://ex.com/hours"


@pytest.mark.asyncio
async def test_hydrate_skips_rows_without_any_dom_path():
    from app.orchestration.evidence_persistence import hydrate_evidence_for_intents

    intent_id = uuid.uuid4()
    intent = SimpleNamespace(id=intent_id)
    ev = SimpleNamespace(
        id=uuid.uuid4(),
        intent_id=intent_id,
        chunk_id=uuid.uuid4(),
        rank=1,
        rrf_score=None,
        source_url=None,
        excerpt=None,
        dom_path=None,
        chunk=None,
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [ev]

    class _Session:
        async def execute(self, _stmt):
            return _Result()

    hydrated = await hydrate_evidence_for_intents(_Session(), [intent])
    assert hydrated[intent_id] == []
