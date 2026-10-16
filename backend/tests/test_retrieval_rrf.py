"""Stage 3: RRF fusion + retrieval mode honesty (no fabricated dense claims)."""

from __future__ import annotations

import uuid

import pytest

from app.crawler.search import (
    MODE_DENSE_ONLY,
    MODE_LEXICAL_ONLY,
    MODE_RRF_HYBRID,
    reciprocal_rank_fusion,
)


def test_rrf_prefers_items_high_in_both_lists():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fused = reciprocal_rank_fusion([[a, b, c], [a, c, b]], rrf_k=60, limit=3)
    ids = [cid for cid, _ in fused]
    assert ids[0] == a
    assert set(ids) == {a, b, c}


def test_rrf_dedupes_and_is_deterministic():
    x, y = uuid.uuid4(), uuid.uuid4()
    # Force tie via same ranks in swapped lists — UUID string breaks ties stably.
    first = reciprocal_rank_fusion([[x, y], [y, x]], rrf_k=60, limit=2)
    second = reciprocal_rank_fusion([[x, y], [y, x]], rrf_k=60, limit=2)
    assert first == second
    assert len(first) == 2


def test_rrf_empty_lists():
    assert reciprocal_rank_fusion([[], []], limit=5) == []
    assert reciprocal_rank_fusion([], limit=5) == []


def test_rrf_single_list_preserves_order():
    ids = [uuid.uuid4() for _ in range(4)]
    fused = reciprocal_rank_fusion([ids], rrf_k=60, limit=3)
    assert [cid for cid, _ in fused] == ids[:3]


def test_rrf_ignores_non_uuid_entries_and_dedupes_within_list():
    a, b = uuid.uuid4(), uuid.uuid4()
    fused = reciprocal_rank_fusion([[a, "not-uuid", a, b], [b]], rrf_k=60, limit=5)
    ids = [cid for cid, _ in fused]
    assert set(ids) == {a, b}
    # Duplicate `a` in first list must not inflate score; second list contributes for `b` only.
    score_a = dict(fused)[a]
    score_b = dict(fused)[b]
    assert score_a == pytest.approx(1.0 / (60 + 1))
    assert score_b == pytest.approx(1.0 / (60 + 2) + 1.0 / (60 + 1))


def test_rrf_tie_break_is_uuid_string_stable():
    # Identical single-list ranks → equal RRF scores; order must follow str(uuid).
    x = uuid.UUID("00000000-0000-0000-0000-000000000002")
    y = uuid.UUID("00000000-0000-0000-0000-000000000001")
    fused = reciprocal_rank_fusion([[x], [y]], rrf_k=60, limit=2)
    assert [cid for cid, _ in fused] == sorted([x, y], key=str)


def test_ephemeral_memory_chunk_id_is_deterministic_not_small_int():
    from app.crawler.search import ephemeral_memory_chunk_id

    scan = uuid.uuid4()
    a = ephemeral_memory_chunk_id(scan, 0, "hello world")
    b = ephemeral_memory_chunk_id(scan, 0, "hello world")
    c = ephemeral_memory_chunk_id(scan, 1, "hello world")
    assert a == b
    assert a != c
    assert a.int > 1000


def test_retrieval_mode_constants_are_distinct():
    assert len({MODE_RRF_HYBRID, MODE_DENSE_ONLY, MODE_LEXICAL_ONLY}) == 3


def test_rrf_score_threads_into_retrieved_evidence():
    from types import SimpleNamespace

    from app.engines.entailment_engine import to_retrieved_evidence

    chunk = SimpleNamespace(
        id=uuid.uuid4(),
        url="https://ex.com",
        dom_path="main > p",
        content="Open Monday 9am",
        _retrieval_rrf_score=0.03125,
    )
    evidence = to_retrieved_evidence([chunk])
    assert len(evidence) == 1
    assert evidence[0].rrf_score == 0.03125
    assert evidence[0].rank == 1


def test_recall_at_k_and_mrr_on_labelled_fixture():
    """Small deterministic labelled corpus measuring Recall@k and MRR.

    Corpus: three queries with known relevant chunk UUIDs. Ranker under test is
    RRF over two hand-ranked lists (simulating dense vs lexical), not a mock of
    RRF itself.
    """
    # Labelled relevant sets
    q1_rel = {uuid.UUID(int=1), uuid.UUID(int=2)}
    q2_rel = {uuid.UUID(int=10)}
    q3_rel = {uuid.UUID(int=20), uuid.UUID(int=21)}

    # Simulated ranked lists (dense, lexical) per query
    fixtures = [
        (
            q1_rel,
            [uuid.UUID(int=1), uuid.UUID(int=3), uuid.UUID(int=2)],
            [uuid.UUID(int=2), uuid.UUID(int=1), uuid.UUID(int=4)],
        ),
        (
            q2_rel,
            [uuid.UUID(int=11), uuid.UUID(int=10), uuid.UUID(int=12)],
            [uuid.UUID(int=10), uuid.UUID(int=13)],
        ),
        (
            q3_rel,
            [uuid.UUID(int=30), uuid.UUID(int=20)],
            [uuid.UUID(int=21), uuid.UUID(int=22)],
        ),
    ]

    k = 3
    recalls: list[float] = []
    mrrs: list[float] = []
    for relevant, dense, lexical in fixtures:
        fused = reciprocal_rank_fusion([dense, lexical], rrf_k=60, limit=k)
        ranked = [cid for cid, _ in fused]
        hit = sum(1 for cid in ranked if cid in relevant)
        recalls.append(hit / len(relevant))
        rr = 0.0
        for i, cid in enumerate(ranked, start=1):
            if cid in relevant:
                rr = 1.0 / i
                break
        mrrs.append(rr)

    recall_at_k = sum(recalls) / len(recalls)
    mrr = sum(mrrs) / len(mrrs)
    # Recorded measured values for this fixture (assert floor, not marketing).
    assert recall_at_k >= 0.8  # measured: typically 1.0 on this fixture
    assert mrr >= 0.5
    # Expose exact measured floats for the report via pytest -s if needed
    print(f"RETRIEVAL_BENCHMARK recall@{k}={recall_at_k:.4f} mrr={mrr:.4f}")
