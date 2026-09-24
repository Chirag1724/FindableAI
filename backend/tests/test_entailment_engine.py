"""Unit tests for EntailmentEngine — retrieval + NLI + citation validation."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.core.llm import BudgetExhausted, LLMClient
from app.engines.entailment_engine import (
    DEFAULT_TOP_K,
    NLI_SYSTEM_PROMPT,
    EntailmentEngine,
    EntailmentError,
    RetrievedEvidence,
    build_nli_user_prompt,
    evaluate_intent,
    validate_intent_evaluation,
)
from app.schemas.intelligence import (
    EntailmentStatus,
    EvidenceReference,
    IntentCategory,
    IntentEvaluation,
    IntentQuery,
)


@dataclass
class FakeChunk:
    id: uuid.UUID
    url: str
    dom_path: str
    content: str
    tag: str = "p"
    word_count: int = 10


class _FakeCompletions:
    def __init__(self, handler: AsyncMock) -> None:
        self.create = handler


class _FakeChat:
    def __init__(self, handler: AsyncMock) -> None:
        self.completions = _FakeCompletions(handler)


class _FakeInstructorClient:
    def __init__(self, handler: AsyncMock) -> None:
        self.chat = _FakeChat(handler)


def _llm(handler: AsyncMock, *, max_calls: int = 35) -> LLMClient:
    return LLMClient(
        api_key="test-secret-key-do-not-leak",
        model="groq/qwen-2.5-72b-instruct",
        max_calls=max_calls,
        instructor_client=_FakeInstructorClient(handler),
    )


def _intent(query: str = "Are dogs allowed on the patio?") -> IntentQuery:
    return IntentQuery(
        intent_id="policy_01",
        category=IntentCategory.POLICY,
        query=query,
        difficulty="medium",
        expected_evidence_type="policy section",
    )


def _chunks(n: int = 5) -> list[FakeChunk]:
    items: list[FakeChunk] = []
    for i in range(n):
        items.append(
            FakeChunk(
                id=uuid.uuid4(),
                url=f"https://example.com/page-{i}",
                dom_path=f"main > section:nth-of-type({i + 1})",
                content=f"Evidence content number {i}: patio dogs welcome."
                if i == 0
                else f"Other fact {i}.",
            )
        )
    return items


def _retrieved_from(chunks: list[FakeChunk]) -> list[RetrievedEvidence]:
    return [
        RetrievedEvidence(
            chunk_id=str(c.id),
            url=c.url,
            dom_path=c.dom_path,
            content=c.content,
            rank=i + 1,
        )
        for i, c in enumerate(chunks)
    ]


def _evaluation(
    *,
    status: EntailmentStatus,
    chunk_ids: list[str],
    confidence: float = 0.9,
    reasoning: str = "Based solely on the supplied evidence.",
) -> IntentEvaluation:
    evidence = [EvidenceReference(chunk_id=cid, dom_path="ignored", url=None) for cid in chunk_ids]
    return IntentEvaluation(
        intent_id="will-be-overwritten",
        query="will-be-overwritten",
        status=status,
        reasoning=reasoning,
        evidence=evidence,
        confidence=confidence,
    )


@pytest.mark.asyncio
async def test_supported_classification():
    chunks = _chunks(3)
    handler = AsyncMock(
        return_value=_evaluation(
            status=EntailmentStatus.SUPPORTED,
            chunk_ids=[str(chunks[0].id)],
        )
    )
    retriever = AsyncMock(return_value=chunks)
    engine = EntailmentEngine(llm_client=_llm(handler), retriever=retriever)

    result = await engine.evaluate_intent(intent=_intent(), scan_id=uuid.uuid4())

    assert result.status is EntailmentStatus.SUPPORTED
    assert result.evidence[0].chunk_id == str(chunks[0].id)
    assert result.evidence[0].dom_path == chunks[0].dom_path
    assert handler.await_count == 1
    retriever.assert_awaited_once()
    assert retriever.await_args.args[2] == DEFAULT_TOP_K


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        EntailmentStatus.PARTIALLY_SUPPORTED,
        EntailmentStatus.CONTRADICTED,
        EntailmentStatus.UNKNOWN,
    ],
)
async def test_status_variants(status: EntailmentStatus):
    chunks = _chunks(2)
    cited = [] if status is EntailmentStatus.UNKNOWN else [str(chunks[0].id)]
    handler = AsyncMock(return_value=_evaluation(status=status, chunk_ids=cited))
    engine = EntailmentEngine(
        llm_client=_llm(handler),
        retriever=AsyncMock(return_value=chunks),
    )
    result = await engine.evaluate_intent(intent=_intent(), scan_id=uuid.uuid4())
    assert result.status is status
    if status is EntailmentStatus.UNKNOWN:
        assert result.evidence == []
    else:
        assert len(result.evidence) >= 1


@pytest.mark.asyncio
async def test_top_five_retrieval_requested_and_ids_in_prompt():
    chunks = _chunks(5)
    captured: dict[str, object] = {}

    async def create_side_effect(**kwargs):  # type: ignore[no-untyped-def]
        captured["messages"] = kwargs["messages"]
        return _evaluation(
            status=EntailmentStatus.SUPPORTED,
            chunk_ids=[str(chunks[0].id)],
        )

    handler = AsyncMock(side_effect=create_side_effect)
    retriever = AsyncMock(return_value=chunks)
    engine = EntailmentEngine(llm_client=_llm(handler), retriever=retriever)

    await engine.evaluate_intent(intent=_intent(), scan_id=uuid.uuid4())

    assert retriever.await_args.args[2] == 5
    system_msg = captured["messages"][0]["content"]  # type: ignore[index]
    user_msg = captured["messages"][1]["content"]  # type: ignore[index]
    assert "evidence-grounded classifier" in system_msg.casefold()
    assert "ONLY use the supplied evidence" in system_msg
    assert "Never use outside knowledge" in system_msg
    assert "UNKNOWN" in system_msg
    for chunk in chunks:
        assert str(chunk.id) in user_msg
        assert chunk.content in user_msg
    assert "Are dogs allowed on the patio?" in user_msg


@pytest.mark.asyncio
async def test_unknown_has_no_evidence_citations():
    chunks = _chunks(2)
    handler = AsyncMock(return_value=_evaluation(status=EntailmentStatus.UNKNOWN, chunk_ids=[]))
    result = await EntailmentEngine(
        llm_client=_llm(handler),
        retriever=AsyncMock(return_value=chunks),
    ).evaluate_intent(intent=_intent(), scan_id=uuid.uuid4())
    assert result.status is EntailmentStatus.UNKNOWN
    assert result.evidence == []


@pytest.mark.asyncio
async def test_invalid_chunk_citation_rejected_without_retry():
    chunks = _chunks(2)
    handler = AsyncMock(
        return_value=_evaluation(
            status=EntailmentStatus.SUPPORTED,
            chunk_ids=["fabricated-chunk-id"],
        )
    )
    llm = _llm(handler)
    engine = EntailmentEngine(llm_client=llm, retriever=AsyncMock(return_value=chunks))

    with pytest.raises(EntailmentError) as exc_info:
        await engine.evaluate_intent(intent=_intent(), scan_id=uuid.uuid4())

    assert exc_info.value.reason == "invalid_evidence_reference"
    assert handler.await_count == 1
    assert llm.calls_made == 1


@pytest.mark.asyncio
async def test_non_unknown_without_evidence_rejected():
    chunks = _chunks(2)
    handler = AsyncMock(return_value=_evaluation(status=EntailmentStatus.SUPPORTED, chunk_ids=[]))
    with pytest.raises(EntailmentError) as exc_info:
        await EntailmentEngine(
            llm_client=_llm(handler),
            retriever=AsyncMock(return_value=chunks),
        ).evaluate_intent(intent=_intent(), scan_id=uuid.uuid4())
    assert exc_info.value.reason == "invalid_evidence_reference"


def test_duplicate_citations_normalized():
    chunks = _chunks(2)
    retrieved = _retrieved_from(chunks)
    dup_id = str(chunks[0].id)
    raw = _evaluation(
        status=EntailmentStatus.SUPPORTED,
        chunk_ids=[dup_id, dup_id],
    )
    validated = validate_intent_evaluation(raw, intent=_intent(), retrieved=retrieved)
    assert [e.chunk_id for e in validated.evidence] == [dup_id]


@pytest.mark.asyncio
async def test_zero_retrieved_chunks_returns_deterministic_unknown_without_llm():
    handler = AsyncMock()
    llm = _llm(handler)
    result = await EntailmentEngine(
        llm_client=llm,
        retriever=AsyncMock(return_value=[]),
    ).evaluate_intent(intent=_intent(), scan_id=uuid.uuid4())

    assert result.status is EntailmentStatus.UNKNOWN
    assert result.confidence == 0.0
    assert result.evidence == []
    assert handler.await_count == 0
    assert llm.calls_made == 0


@pytest.mark.asyncio
async def test_llm_failure_becomes_entailment_error():
    handler = AsyncMock(side_effect=RuntimeError("provider down"))
    with pytest.raises(EntailmentError) as exc_info:
        await EntailmentEngine(
            llm_client=_llm(handler),
            retriever=AsyncMock(return_value=_chunks(1)),
        ).evaluate_intent(intent=_intent(), scan_id=uuid.uuid4())
    assert exc_info.value.reason == "llm_failure"
    assert "test-secret-key-do-not-leak" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_retrieval_failure_becomes_entailment_error():
    handler = AsyncMock()
    with pytest.raises(EntailmentError) as exc_info:
        await EntailmentEngine(
            llm_client=_llm(handler),
            retriever=AsyncMock(side_effect=RuntimeError("db unavailable")),
        ).evaluate_intent(intent=_intent(), scan_id=uuid.uuid4())
    assert exc_info.value.reason == "retrieval_failure"
    assert handler.await_count == 0


def test_invalid_confidence_rejected():
    chunks = _chunks(1)
    retrieved = _retrieved_from(chunks)
    raw = IntentEvaluation.model_construct(
        intent_id="x",
        query="y?",
        status=EntailmentStatus.SUPPORTED,
        reasoning="ok",
        evidence=[EvidenceReference(chunk_id=str(chunks[0].id), dom_path="p")],
        confidence=1.5,
    )
    with pytest.raises(EntailmentError) as exc_info:
        validate_intent_evaluation(raw, intent=_intent(), retrieved=retrieved)
    assert exc_info.value.reason == "invalid_confidence"


@pytest.mark.asyncio
async def test_batch_preserves_order_and_is_concurrent():
    chunks = _chunks(3)
    intents = [
        _intent(query="Question one about hours?"),
        _intent(query="Question two about menu?"),
        _intent(query="Question three about parking?"),
    ]
    for i, intent in enumerate(intents):
        intents[i] = intent.model_copy(update={"intent_id": f"policy_{i + 1:02d}"})

    started: list[float] = []
    finished: list[float] = []
    loop = asyncio.get_running_loop()

    async def create_side_effect(**kwargs):  # type: ignore[no-untyped-def]
        started.append(loop.time())
        await asyncio.sleep(0.05)
        finished.append(loop.time())
        user = kwargs["messages"][1]["content"]
        # cite first chunk always
        return _evaluation(
            status=EntailmentStatus.SUPPORTED,
            chunk_ids=[str(chunks[0].id)],
            reasoning=f"ok for {user[:40]}",
        )

    handler = AsyncMock(side_effect=create_side_effect)
    llm = _llm(handler)
    engine = EntailmentEngine(
        llm_client=llm,
        retriever=AsyncMock(return_value=chunks),
    )

    results = await engine.evaluate_intents(intents=intents, scan_id=uuid.uuid4())

    assert [r.intent_id for r in results] == [i.intent_id for i in intents]
    assert [r.query for r in results] == [i.query for i in intents]
    assert handler.await_count == 3
    assert llm.calls_made == 3
    # Overlapping execution: second start before first finish
    assert started[1] < finished[0]


@pytest.mark.asyncio
async def test_shared_llm_client_budget_not_bypassed():
    chunks = _chunks(1)
    handler = AsyncMock(
        return_value=_evaluation(
            status=EntailmentStatus.SUPPORTED,
            chunk_ids=[str(chunks[0].id)],
        )
    )
    llm = _llm(handler, max_calls=2)
    engine = EntailmentEngine(
        llm_client=llm,
        retriever=AsyncMock(return_value=chunks),
    )
    scan_id = uuid.uuid4()
    intents = [
        _intent(query="Q1?").model_copy(update={"intent_id": "a_01"}),
        _intent(query="Q2?").model_copy(update={"intent_id": "a_02"}),
        _intent(query="Q3?").model_copy(update={"intent_id": "a_03"}),
    ]

    with pytest.raises((EntailmentError, BudgetExhausted)):
        await engine.evaluate_intents(intents=intents, scan_id=scan_id)

    assert llm.calls_made == 2
    assert handler.await_count == 2


@pytest.mark.asyncio
async def test_thirty_intents_make_thirty_llm_calls():
    chunks = _chunks(2)
    handler = AsyncMock(
        return_value=_evaluation(
            status=EntailmentStatus.SUPPORTED,
            chunk_ids=[str(chunks[0].id)],
        )
    )
    llm = _llm(handler, max_calls=35)
    intents = [
        _intent(query=f"Unique question number {i}?").model_copy(
            update={"intent_id": f"edge_cases_{i:02d}"}
        )
        for i in range(1, 31)
    ]
    results = await EntailmentEngine(
        llm_client=llm,
        retriever=AsyncMock(return_value=chunks),
    ).evaluate_intents(intents=intents, scan_id=uuid.uuid4())

    assert len(results) == 30
    assert handler.await_count == 30
    assert llm.calls_made == 30


@pytest.mark.asyncio
async def test_module_level_evaluate_intent_helper():
    chunks = _chunks(1)
    handler = AsyncMock(
        return_value=_evaluation(
            status=EntailmentStatus.PARTIALLY_SUPPORTED,
            chunk_ids=[str(chunks[0].id)],
        )
    )
    result = await evaluate_intent(
        intent=_intent(),
        scan_id=uuid.uuid4(),
        llm_client=_llm(handler),
        retriever=AsyncMock(return_value=chunks),
    )
    assert result.status is EntailmentStatus.PARTIALLY_SUPPORTED


def test_prompt_builder_includes_anti_hallucination_contract():
    assert "Never use outside knowledge" in NLI_SYSTEM_PROMPT
    assert "MUST NOT invent chunk IDs" in NLI_SYSTEM_PROMPT
    chunks = _retrieved_from(_chunks(1))
    prompt = build_nli_user_prompt(intent=_intent(), evidence=chunks)
    assert chunks[0].chunk_id in prompt
    assert "INTENT:" in prompt
