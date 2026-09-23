import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models.database import DOMChunk

from .dom_chunker import ChunkData

logger = logging.getLogger(__name__)


async def store_dom_chunks(
    scan_id: uuid.UUID,
    chunks: Sequence[ChunkData],
    session: AsyncSession | None = None,
) -> list[DOMChunk]:
    """
    Persist extracted DOM chunks into the database associated with a scan.
    """
    if not chunks:
        return []

    async def _insert(s: AsyncSession) -> list[DOMChunk]:
        from app.core.embeddings import get_embeddings_batch

        texts = [chunk.content for chunk in chunks]
        embeddings = await get_embeddings_batch(texts)

        db_records = [
            DOMChunk(
                scan_id=scan_id,
                url=chunk.url,
                dom_path=chunk.dom_path,
                content=chunk.content,
                tag=chunk.tag,
                word_count=chunk.word_count,
                embedding=embeddings[i] if i < len(embeddings) else None,
            )
            for i, chunk in enumerate(chunks)
        ]
        s.add_all(db_records)
        await s.flush()
        return db_records

    if session is not None:
        return await _insert(session)

    async with AsyncSessionLocal() as s:
        async with s.begin():
            return await _insert(s)


async def hybrid_search(
    query: str,
    scan_id: uuid.UUID,
    k: int = 5,
    session: AsyncSession | None = None,
) -> list[DOMChunk]:
    """
    Hybrid Search Engine — Interface Contract 1.
    Fuses PostgreSQL Full-Text Search (BM25/tsvector) with keyword relevance
    to retrieve the top-k most relevant DOM chunks for a given query.

    Parameters:
        query: User or synthetic intent query string.
        scan_id: Unique UUID of the active audit scan.
        k: Maximum number of chunks to return (default: 5).
        session: Optional external AsyncSession.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    async def _execute_search(s: AsyncSession) -> list[DOMChunk]:
        # 1. Try full-text search against content_tsv using plainto_tsquery
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

            # If full-text search returned sufficient matches, return them
            if len(chunks) >= min(k, 3):
                return chunks
        except Exception as e:
            logger.debug("Full text tsvector query fallback triggered: %s", e)
            chunks = []

        # 2. Fallback / supplementary search using tokenized ILIKE matching
        # Ensures robust retrieval even if exact tsvector dictionary misses slang/brand terms
        words = [w.lower() for w in cleaned_query.split() if len(w) > 2]
        if not words:
            words = [cleaned_query.lower()]

        fallback_stmt = select(DOMChunk).where(DOMChunk.scan_id == scan_id)

        # Retrieve candidate chunks for the scan
        all_scan_chunks_res = await s.execute(fallback_stmt)
        all_chunks = list(all_scan_chunks_res.scalars().all())

        # Simple term frequency scoring fallback
        scored: list[tuple[float, DOMChunk]] = []
        for chunk in all_chunks:
            chunk_text = chunk.content.lower()
            match_score = sum(1.0 for word in words if word in chunk_text)
            if match_score > 0:
                # Slight boost for shorter, tighter chunks
                normalized_score = match_score / (1.0 + 0.05 * chunk.word_count)
                scored.append((normalized_score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        fallback_chunks = [item[1] for item in scored[:k]]

        # Merge results preserving order and avoiding duplicates
        seen_ids = {c.id for c in chunks}
        for c in fallback_chunks:
            if c.id not in seen_ids:
                chunks.append(c)
                seen_ids.add(c.id)

        return chunks[:k]

    if session is not None:
        return await _execute_search(session)

    async with AsyncSessionLocal() as s:
        return await _execute_search(s)
