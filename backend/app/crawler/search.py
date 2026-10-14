"""Chunk persistence and query-time retrieval (dense + lexical + RRF).

Contract: ACT consumes ``hybrid_search`` fused candidates when the DB/index is
available. Modes are explicit — lexical-only is never labelled as dense/RRF.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, overload

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.embeddings import EMBEDDING_DIM, get_embedding
from app.db import AsyncSessionLocal
from app.models.database import DOMChunk

from .dom_chunker import ChunkData

logger = logging.getLogger(__name__)

MODE_RRF_HYBRID = "rrf_hybrid"
MODE_DENSE_ONLY = "dense_only"
MODE_LEXICAL_ONLY = "lexical_only"
MODE_MEMORY_FALLBACK = "memory_fallback"
MODE_EMPTY = "empty"

# Deterministic namespace for ephemeral in-memory retrieval ids (UUID5).
# Durable DOMChunk primary keys are UUID4; evidence persistence rejects UUID5 cites.
MEMORY_FALLBACK_NS = uuid.UUID("6f696e64-6162-4c65-9a69-6d656d303031")


def ephemeral_memory_chunk_id(scan_id: uuid.UUID, index: int, content: str) -> uuid.UUID:
    """Stable-looking but non-durable UUID5 id for process-local memory fallback chunks."""
    digest = f"{scan_id}:{index}:{content[:240]}"
    return uuid.uuid5(MEMORY_FALLBACK_NS, digest)


@dataclass
class RetrievalMeta:
    """Honest description of which retrieval algorithms actually ran."""

    mode: str
    dense_hits: int = 0
    lexical_hits: int = 0
    fused_hits: int = 0
    warnings: list[str] = field(default_factory=list)
    rrf_k: int = 60


def reciprocal_rank_fusion(
    ranked_id_lists: Sequence[Sequence[uuid.UUID]],
    *,
    rrf_k: int | None = None,
    limit: int = 5,
) -> list[tuple[uuid.UUID, float]]:
    """Fuse ranked candidate lists with Reciprocal Rank Fusion.

    score(d) = sum 1/(rrf_k + rank). Ties broken by UUID string for stability.
    """
    k = int(rrf_k if rrf_k is not None else getattr(settings, "RETRIEVAL_RRF_K", 60))
    if k < 1:
        k = 60
    scores: dict[uuid.UUID, float] = {}
    for ranked in ranked_id_lists:
        seen_in_list: set[uuid.UUID] = set()
        rank = 0
        for cid in ranked:
            if not isinstance(cid, uuid.UUID):
                continue
            if cid in seen_in_list:
                # Duplicate within one ranked list must not inflate RRF score.
                continue
            seen_in_list.add(cid)
            rank += 1
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))
    return ordered[: max(0, int(limit))]


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        fx = float(x)
        fy = float(y)
        dot += fx * fy
        na += fx * fx
        nb += fy * fy
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


async def store_dom_chunks(
    scan_id: uuid.UUID,
    chunks: Sequence[ChunkData],
    session: AsyncSession | None = None,
) -> list[DOMChunk]:
    """Persist extracted DOM chunks into the database associated with a scan."""
    if not chunks:
        return []

    async def _insert(s: AsyncSession) -> list[DOMChunk]:
        from app.core.embeddings import get_embeddings_batch

        texts = [chunk.content for chunk in chunks]
        embeddings = await get_embeddings_batch(texts)

        db_records: list[DOMChunk] = []
        for i, chunk in enumerate(chunks):
            emb = embeddings[i] if i < len(embeddings) else None
            if emb is not None:
                try:
                    emb_list = [float(x) for x in list(emb)]
                except (TypeError, ValueError):
                    emb_list = None
                if emb_list is None or len(emb_list) != EMBEDDING_DIM:
                    logger.warning(
                        "Dropping embedding for scan %s chunk[%s]: dim=%s expected=%s",
                        scan_id,
                        i,
                        None if emb_list is None else len(emb_list),
                        EMBEDDING_DIM,
                    )
                    emb_list = None
                emb = emb_list
            db_records.append(
                DOMChunk(
                    scan_id=scan_id,
                    url=chunk.url,
                    dom_path=chunk.dom_path,
                    content=chunk.content,
                    tag=chunk.tag,
                    word_count=chunk.word_count,
                    embedding=emb,
                )
            )
        s.add_all(db_records)
        await s.flush()
        return db_records

    if session is not None:
        return await _insert(session)

    async with AsyncSessionLocal() as s:
        async with s.begin():
            return await _insert(s)


async def lexical_search(
    query: str,
    scan_id: uuid.UUID,
    k: int = 5,
    session: AsyncSession | None = None,
) -> list[DOMChunk]:
    """PostgreSQL FTS (tsvector) with ILIKE term-frequency fallback."""
    cleaned_query = query.strip()
    if not cleaned_query or k <= 0:
        return []

    async def _execute(s: AsyncSession) -> list[DOMChunk]:
        chunks: list[DOMChunk] = []
        try:
            ts_query = func.plainto_tsquery("english", cleaned_query)
            rank_col = func.ts_rank_cd(DOMChunk.content_tsv, ts_query).label("rank")
            stmt = (
                select(DOMChunk)
                .where(
                    DOMChunk.scan_id == scan_id,
                    DOMChunk.content_tsv.bool_op("@@")(ts_query),
                )
                .order_by(rank_col.desc())
                .limit(k)
            )
            result = await s.execute(stmt)
            chunks = list(result.scalars().all())
            if len(chunks) >= min(k, 3):
                return chunks
        except Exception as e:
            logger.debug("Full text tsvector query fallback triggered: %s", e)
            chunks = []

        words = [w.lower() for w in cleaned_query.split() if len(w) > 2]
        if not words:
            words = [cleaned_query.lower()]

        all_scan_chunks_res = await s.execute(select(DOMChunk).where(DOMChunk.scan_id == scan_id))
        all_chunks = list(all_scan_chunks_res.scalars().all())
        scored: list[tuple[float, DOMChunk]] = []
        for chunk in all_chunks:
            chunk_text = chunk.content.lower()
            match_score = sum(1.0 for word in words if word in chunk_text)
            if match_score > 0:
                normalized_score = match_score / (1.0 + 0.05 * chunk.word_count)
                scored.append((normalized_score, chunk))
        scored.sort(key=lambda item: (-item[0], str(item[1].id)))
        fallback_chunks = [item[1] for item in scored[:k]]
        seen = {c.id for c in chunks}
        for c in fallback_chunks:
            if c.id not in seen:
                chunks.append(c)
                seen.add(c.id)
        return chunks[:k]

    if session is not None:
        return await _execute(session)
    async with AsyncSessionLocal() as s:
        return await _execute(s)


async def dense_search(
    query: str,
    scan_id: uuid.UUID,
    k: int = 5,
    session: AsyncSession | None = None,
) -> tuple[list[DOMChunk], list[str]]:
    """Query-time semantic retrieval against persisted embeddings.

    Prefers pgvector cosine distance; falls back to in-process cosine over
    loaded embeddings when the operator is unavailable (e.g. SQLite tests).
    """
    warnings: list[str] = []
    cleaned = query.strip()
    if not cleaned or k <= 0:
        return [], warnings

    query_emb = await get_embedding(cleaned)
    if len(query_emb) != EMBEDDING_DIM:
        warnings.append(
            f"Query embedding dimension {len(query_emb)} != expected {EMBEDDING_DIM}; dense skipped."
        )
        return [], warnings
    if all(abs(float(x)) < 1e-12 for x in query_emb):
        warnings.append("Query embedding is empty; dense skipped.")
        return [], warnings

    async def _execute(s: AsyncSession) -> list[DOMChunk]:
        # Attempt native pgvector ordering first.
        try:
            distance = DOMChunk.embedding.cosine_distance(query_emb)  # type: ignore[attr-defined]
            stmt = (
                select(DOMChunk)
                .where(
                    DOMChunk.scan_id == scan_id,
                    DOMChunk.embedding.isnot(None),
                )
                .order_by(distance)
                .limit(k)
            )
            result = await s.execute(stmt)
            rows = list(result.scalars().all())
            if rows:
                return rows
        except Exception as exc:
            logger.debug("pgvector dense query unavailable (%s); using python cosine", exc)
            warnings.append("pgvector cosine unavailable; used in-process dense scoring.")

        result = await s.execute(
            select(DOMChunk).where(
                DOMChunk.scan_id == scan_id,
                DOMChunk.embedding.isnot(None),
            )
        )
        candidates = list(result.scalars().all())
        scored: list[tuple[float, DOMChunk]] = []
        for chunk in candidates:
            emb = chunk.embedding
            if emb is None:
                continue
            try:
                vec = [float(x) for x in list(emb)]
            except (TypeError, ValueError):
                continue
            if len(vec) != EMBEDDING_DIM:
                continue
            sim = _cosine_similarity(query_emb, vec)
            if sim > 0.0:
                scored.append((sim, chunk))
        scored.sort(key=lambda item: (-item[0], str(item[1].id)))
        return [c for _, c in scored[:k]]

    try:
        if session is not None:
            return await _execute(session), warnings
        async with AsyncSessionLocal() as s:
            return await _execute(s), warnings
    except Exception as exc:
        warnings.append(f"Dense retrieval failed: {type(exc).__name__}")
        logger.debug("dense_search failed: %s", exc)
        return [], warnings


def _coerce_scan_uuid(scan_id: uuid.UUID | str) -> uuid.UUID:
    if isinstance(scan_id, uuid.UUID):
        return scan_id
    try:
        return uuid.UUID(str(scan_id))
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"findableai:scan:{scan_id}")


def _memory_fallback_chunks(query: str, scan_id: uuid.UUID, k: int) -> list[DOMChunk]:
    """Lexical scoring over process-local CHUNKS_DB when the database path fails.

    Chunk ids are either the real persisted UUID (when present) or a deterministic
    ephemeral uuid5. Never invents small-int UUIDs that could collide with durable rows.
    """
    from app.api.v1 import scans as scans_module

    resolved_scan = _coerce_scan_uuid(scan_id)
    lookup_keys = [str(resolved_scan), resolved_scan.hex]
    lookup_keys.append(f"scan_{resolved_scan.hex}")
    lookup_keys.append(f"scan_{resolved_scan.hex[:12]}")
    raw_chunks = []
    for key in lookup_keys:
        if key in scans_module.CHUNKS_DB:
            raw_chunks = scans_module.CHUNKS_DB[key]
            break
    if not raw_chunks:
        return []

    words = [w.lower() for w in query.split() if len(w) > 2] or [query.lower()]
    scored: list[tuple[float, DOMChunk]] = []
    for i, rc in enumerate(raw_chunks):
        content = getattr(rc, "content", "") or ""
        text = content.lower()
        match_score = sum(1.0 for word in words if word in text)
        if match_score > 0:
            c_id = getattr(rc, "id", None)
            if isinstance(c_id, str):
                try:
                    c_id = uuid.UUID(c_id)
                except (ValueError, AttributeError, TypeError):
                    c_id = None
            if not isinstance(c_id, uuid.UUID):
                c_id = ephemeral_memory_chunk_id(resolved_scan, i, content)
            chunk_obj = DOMChunk(
                id=c_id,
                scan_id=resolved_scan,
                url=getattr(rc, "url", "") or "",
                dom_path=getattr(rc, "dom_path", "") or f"/memory[{i}]",
                content=content,
                tag=getattr(rc, "tag", "div") or "div",
                word_count=getattr(rc, "word_count", len(content.split())),
            )
            scored.append((match_score, chunk_obj))
    scored.sort(key=lambda item: (-item[0], str(item[1].id)))
    return [item[1] for item in scored[:k]]


@overload
async def hybrid_search(
    query: str,
    scan_id: uuid.UUID,
    k: int = 5,
    session: AsyncSession | None = None,
    *,
    return_meta: Literal[False] = False,
) -> list[DOMChunk]: ...


@overload
async def hybrid_search(
    query: str,
    scan_id: uuid.UUID,
    k: int = 5,
    session: AsyncSession | None = None,
    *,
    return_meta: Literal[True],
) -> tuple[list[DOMChunk], RetrievalMeta]: ...


async def hybrid_search(
    query: str,
    scan_id: uuid.UUID,
    k: int = 5,
    session: AsyncSession | None = None,
    *,
    return_meta: bool = False,
) -> list[DOMChunk] | tuple[list[DOMChunk], RetrievalMeta]:
    """Dense + lexical retrieval fused with RRF (Contract-1).

    When a side fails, results are returned with an honest mode (not silently
    labelled as full hybrid). Falls back to in-memory lexical scoring only when
    the database path is unavailable.
    """
    cleaned_query = query.strip()
    limit = max(0, int(k))
    dense_k = int(getattr(settings, "RETRIEVAL_DENSE_K", 10))
    lexical_k = int(getattr(settings, "RETRIEVAL_LEXICAL_K", 10))
    rrf_k = int(getattr(settings, "RETRIEVAL_RRF_K", 60))
    meta = RetrievalMeta(mode=MODE_EMPTY, rrf_k=rrf_k)

    if not cleaned_query or limit <= 0:
        return ([], meta) if return_meta else []

    async def _db_path(s: AsyncSession) -> list[DOMChunk]:
        dense_rows, dense_warns = await dense_search(cleaned_query, scan_id, k=dense_k, session=s)
        meta.warnings.extend(dense_warns)
        lexical_rows = await lexical_search(cleaned_query, scan_id, k=lexical_k, session=s)
        meta.dense_hits = len(dense_rows)
        meta.lexical_hits = len(lexical_rows)

        dense_ids = [c.id for c in dense_rows]
        lexical_ids = [c.id for c in lexical_rows]
        by_id = {c.id: c for c in dense_rows}
        for c in lexical_rows:
            by_id.setdefault(c.id, c)

        def _attach_scores(ordered: list[tuple[uuid.UUID, float]]) -> list[DOMChunk]:
            out: list[DOMChunk] = []
            for cid, score in ordered:
                chunk = by_id.get(cid)
                if chunk is None:
                    continue
                # Ephemeral attribute for NLI/evidence; not an ORM column.
                chunk._retrieval_rrf_score = float(score)  # type: ignore[attr-defined]
                out.append(chunk)
            return out

        if dense_ids and lexical_ids:
            fused = reciprocal_rank_fusion([dense_ids, lexical_ids], rrf_k=rrf_k, limit=limit)
            meta.mode = MODE_RRF_HYBRID
            meta.fused_hits = len(fused)
            return _attach_scores(fused)

        if dense_ids:
            meta.mode = MODE_DENSE_ONLY
            meta.warnings.append("Lexical retrieval returned no candidates; dense-only result.")
            ranked = [
                (cid, 1.0 / (rrf_k + rank)) for rank, cid in enumerate(dense_ids[:limit], start=1)
            ]
            meta.fused_hits = len(ranked)
            return _attach_scores(ranked)

        if lexical_ids:
            meta.mode = MODE_LEXICAL_ONLY
            meta.warnings.append("Dense retrieval returned no candidates; lexical-only result.")
            ranked = [
                (cid, 1.0 / (rrf_k + rank)) for rank, cid in enumerate(lexical_ids[:limit], start=1)
            ]
            meta.fused_hits = len(ranked)
            return _attach_scores(ranked)

        meta.mode = MODE_EMPTY
        return []

    try:
        if session is not None:
            chunks = await _db_path(session)
        else:
            async with AsyncSessionLocal() as s:
                chunks = await _db_path(s)
        if return_meta:
            return chunks, meta
        return chunks
    except Exception as exc:
        logger.debug(
            "Database hybrid_search unavailable (%s); using in-memory candidate scoring",
            exc,
        )
        mem = _memory_fallback_chunks(cleaned_query, scan_id, limit)
        meta.mode = MODE_MEMORY_FALLBACK
        meta.lexical_hits = len(mem)
        meta.fused_hits = len(mem)
        meta.warnings.append("Database retrieval unavailable; memory lexical fallback.")
        if return_meta:
            return mem, meta
        return mem
