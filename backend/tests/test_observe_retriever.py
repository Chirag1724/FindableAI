"""OBSERVE fallback retriever: deterministic ranking / tie-breaks."""

from __future__ import annotations

import uuid

import pytest

from app.orchestration.dag import _observe_chunks_retriever
from app.orchestration.state import OrchestrationChunk


@pytest.mark.asyncio
async def test_observe_tie_break_is_stable_by_id_then_path():
    chunks = [
        OrchestrationChunk(
            id="chunk-b",
            url="https://ex.com",
            dom_path="main > p.b",
            content="office hours monday",
            tag="p",
            word_count=3,
        ),
        OrchestrationChunk(
            id="chunk-a",
            url="https://ex.com",
            dom_path="main > p.a",
            content="office hours monday",
            tag="p",
            word_count=3,
        ),
    ]
    retrieve = _observe_chunks_retriever(chunks)
    scan = uuid.uuid4()
    first = await retrieve("office hours monday", scan, k=2)
    second = await retrieve("office hours monday", scan, k=2)
    assert [c.id for c in first] == [c.id for c in second]
    assert [c.id for c in first] == ["chunk-a", "chunk-b"]
