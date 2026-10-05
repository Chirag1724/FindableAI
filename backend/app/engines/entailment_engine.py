"""Evidence-grounded NLI entailment engine.

Flow (production):
    IntentQuery
        → hybrid_search(query, scan_id, k=5)   # crawler/search ownership
        → top-5 DOM chunks
        → one structured LLMClient NLI call
        → IntentEvaluation (+ deterministic citation validation)

Retrieval internals (vector/BM25/RRF) remain owned by ``app.crawler.search``.
This module only consumes the Contract-1 retriever interface.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast, runtime_checkable

from app.core.llm import BudgetExhausted, LLMClient
from app.schemas.intelligence import (
    EntailmentStatus,
    EvidenceReference,
    IntentEvaluation,
    IntentQuery,
)

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5

NLI_SYSTEM_PROMPT = """You are an evidence-grounded classifier.

You may ONLY use the supplied evidence chunks.
Never use outside knowledge.
Never rely on assumptions.
Never infer business facts that are not explicitly supported.

If the evidence does not answer the question, return UNKNOWN.
If the evidence directly supports the requested fact, return SUPPORTED.
If the evidence supports only part of the requested fact, return PARTIALLY_SUPPORTED.
If the evidence directly conflicts with the requested fact, return CONTRADICTED.

Every non-UNKNOWN result MUST cite one or more supplied chunk IDs.
You MUST NOT invent chunk IDs.
Only cite chunk IDs that appear in the provided evidence.

Do not answer the user directly.
Return only the structured classification (IntentEvaluation).

When status is UNKNOWN, evidence must be an empty list.
When status is SUPPORTED, PARTIALLY_SUPPORTED, or CONTRADICTED, evidence must list
EvidenceReference entries whose chunk_id values exactly match supplied IDs.
Include reasoning that cites only the provided evidence.
Confidence must be a float between 0.0 and 1.0.
"""


class EntailmentError(Exception):
    """Raised when retrieval, NLI classification, or citation validation fails."""

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "entailment_failed"
        super().__init__(message)


@runtime_checkable
class RetrievableChunk(Protocol):
    """Minimal fields required from hybrid_search / DOMChunk results."""

    @property
    def id(self) -> uuid.UUID | str: ...

    @property
    def url(self) -> str: ...

    @property
    def dom_path(self) -> str: ...

    @property
    def content(self) -> str: ...


Retriever = Callable[..., Awaitable[Sequence[RetrievableChunk]]]


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    """Engine-facing evidence view (no embeddings / DB-only fields)."""

    chunk_id: str
    url: str
    dom_path: str
    content: str
    rank: int


def _chunk_id(chunk: RetrievableChunk) -> str:
    return str(chunk.id)


def to_retrieved_evidence(chunks: Sequence[RetrievableChunk]) -> list[RetrievedEvidence]:
    """Map retriever output into ranked evidence records (preserve order)."""
    evidence: list[RetrievedEvidence] = []
    for index, chunk in enumerate(chunks, start=1):
        content = (chunk.content or "").strip()
        dom_path = (chunk.dom_path or "").strip()
        url = (chunk.url or "").strip()
        chunk_id = _chunk_id(chunk).strip()
        if not chunk_id:
            raise EntailmentError(
                "Retrieved chunk is missing an id",
                reason="invalid_nli_output",
            )
        evidence.append(
            RetrievedEvidence(
                chunk_id=chunk_id,
                url=url,
                dom_path=dom_path or "(unknown)",
                content=content,
                rank=index,
            )
        )
    return evidence


def format_evidence_for_prompt(evidence: Sequence[RetrievedEvidence]) -> str:
    blocks: list[str] = []
    for item in evidence:
        blocks.append(
            f"[{item.chunk_id}]\n"
            f"URL: {item.url or '(none)'}\n"
            f"DOM PATH: {item.dom_path}\n"
            f"CONTENT:\n{item.content}"
        )
    return "\n\n".join(blocks)


def build_nli_user_prompt(*, intent: IntentQuery, evidence: Sequence[RetrievedEvidence]) -> str:
    return (
        f"INTENT ID: {intent.intent_id}\n"
        f"INTENT:\n{intent.query}\n\n"
        f"EVIDENCE CHUNKS:\n\n{format_evidence_for_prompt(evidence)}"
    )


async def default_hybrid_retriever(
    query: str,
    scan_id: uuid.UUID,
    k: int = DEFAULT_TOP_K,
) -> Sequence[RetrievableChunk]:
    """Production default: Contract-1 ``hybrid_search`` (crawler/search owned).

    Imported lazily so unit tests can inject a fake retriever without requiring
    the PostgreSQL/asyncpg stack at import time.
    """
    from app.crawler.search import hybrid_search

    # DOMChunk structurally satisfies RetrievableChunk; cast keeps the crawler
    # dependency at the boundary without coupling engines to SQLAlchemy types.
    return cast(Sequence[RetrievableChunk], await hybrid_search(query, scan_id, k=k))


def validate_intent_evaluation(
    evaluation: IntentEvaluation,
    *,
    intent: IntentQuery,
    retrieved: Sequence[RetrievedEvidence],
) -> IntentEvaluation:
    """
    Deterministic citation / status validation.

    Does not call the LLM. Rebuilds EvidenceReference rows from retrieved chunks
    so URL/DOM path/excerpt cannot be fabricated by the model.
    """
    if not isinstance(evaluation, IntentEvaluation):
        raise EntailmentError(
            f"Expected IntentEvaluation, got {type(evaluation).__name__}",
            reason="invalid_nli_output",
        )

    if not isinstance(evaluation.status, EntailmentStatus):
        raise EntailmentError(
            f"Invalid entailment status: {evaluation.status!r}",
            reason="invalid_classification",
        )

    if not (0.0 <= float(evaluation.confidence) <= 1.0):
        raise EntailmentError(
            f"Confidence out of range: {evaluation.confidence}",
            reason="invalid_confidence",
        )

    reasoning = (evaluation.reasoning or "").strip()
    if not reasoning:
        raise EntailmentError(
            "reasoning must be non-empty",
            reason="invalid_nli_output",
        )

    retrieved_by_id: Mapping[str, RetrievedEvidence] = {item.chunk_id: item for item in retrieved}
    cited_ids: list[str] = []
    for ref in evaluation.evidence:
        chunk_id = (ref.chunk_id or "").strip()
        if not chunk_id:
            raise EntailmentError(
                "Evidence reference missing chunk_id",
                reason="invalid_evidence_reference",
            )
        if chunk_id not in retrieved_by_id:
            raise EntailmentError(
                f"Fabricated or unknown chunk_id cited: {chunk_id}",
                reason="invalid_evidence_reference",
            )
        if chunk_id not in cited_ids:
            cited_ids.append(chunk_id)

    if evaluation.status is EntailmentStatus.UNKNOWN:
        if cited_ids:
            raise EntailmentError(
                "UNKNOWN evaluations must not cite evidence chunk IDs",
                reason="invalid_evidence_reference",
            )
        rebuilt: list[EvidenceReference] = []
    else:
        if not cited_ids:
            raise EntailmentError(
                f"{evaluation.status.value} requires at least one valid evidence citation",
                reason="invalid_evidence_reference",
            )
        rebuilt = []
        for chunk_id in cited_ids:
            item = retrieved_by_id[chunk_id]
            excerpt = item.content if len(item.content) <= 280 else f"{item.content[:277]}..."
            rebuilt.append(
                EvidenceReference(
                    chunk_id=item.chunk_id,
                    dom_path=item.dom_path,
                    url=item.url or None,
                    rank=item.rank,
                    excerpt=excerpt or None,
                )
            )

    return IntentEvaluation(
        intent_id=intent.intent_id,
        query=intent.query,
        category=intent.category,
        persona=intent.persona,
        status=evaluation.status,
        reasoning=reasoning,
        evidence=rebuilt,
        confidence=float(evaluation.confidence),
    )


class EntailmentEngine:
    """Evaluate intents against retrieved DOM evidence via structured NLI."""

    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        retriever: Retriever | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        self._llm = llm_client or LLMClient()
        self._retriever: Retriever = retriever or default_hybrid_retriever
        self._top_k = top_k

    @property
    def llm_client(self) -> LLMClient:
        return self._llm

    @property
    def top_k(self) -> int:
        return self._top_k

    async def _retrieve(
        self,
        *,
        query: str,
        scan_id: uuid.UUID,
    ) -> list[RetrievedEvidence]:
        try:
            raw_chunks = await self._retriever(query, scan_id, self._top_k)
        except EntailmentError:
            raise
        except Exception as exc:
            logger.error(
                "Entailment retrieval failed scan_id=%s error_type=%s",
                scan_id,
                type(exc).__name__,
            )
            raise EntailmentError(
                f"Retrieval failed: {exc}",
                reason="retrieval_failure",
            ) from exc

        if raw_chunks is None:
            raise EntailmentError(
                "Retriever returned None",
                reason="retrieval_failure",
            )

        try:
            return to_retrieved_evidence(list(raw_chunks)[: self._top_k])
        except EntailmentError:
            raise
        except Exception as exc:
            raise EntailmentError(
                f"Failed to normalize retrieved chunks: {exc}",
                reason="retrieval_failure",
            ) from exc

    async def evaluate_intent(
        self,
        *,
        intent: IntentQuery,
        scan_id: uuid.UUID,
    ) -> IntentEvaluation:
        if not isinstance(intent, IntentQuery):
            raise EntailmentError(
                "intent must be an IntentQuery",
                reason="invalid_nli_output",
            )
        if not isinstance(scan_id, uuid.UUID):
            raise EntailmentError(
                "scan_id must be a UUID",
                reason="invalid_nli_output",
            )

        started = time.perf_counter()
        retrieved = await self._retrieve(query=intent.query, scan_id=scan_id)

        if not retrieved:
            logger.info(
                "Entailment UNKNOWN (no evidence) scan_id=%s intent_id=%s retrieved=0",
                scan_id,
                intent.intent_id,
            )
            return IntentEvaluation(
                intent_id=intent.intent_id,
                query=intent.query,
                category=intent.category,
                persona=intent.persona,
                status=EntailmentStatus.UNKNOWN,
                reasoning="No evidence chunks were retrieved for this intent.",
                evidence=[],
                confidence=0.0,
            )

        user_prompt = build_nli_user_prompt(intent=intent, evidence=retrieved)

        try:
            raw = await self._llm.create(
                IntentEvaluation,
                messages=[
                    {"role": "system", "content": NLI_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_retries=0,
                max_tokens=300,
            )
        except BudgetExhausted:
            raise
        except EntailmentError:
            raise
        except Exception as exc:
            logger.error(
                "Entailment LLM call failed scan_id=%s intent_id=%s error_type=%s",
                scan_id,
                intent.intent_id,
                type(exc).__name__,
            )
            raise EntailmentError(
                f"LLM entailment classification failed: {exc}",
                reason="llm_failure",
            ) from exc

        try:
            validated = validate_intent_evaluation(
                raw,
                intent=intent,
                retrieved=retrieved,
            )
        except EntailmentError as exc:
            logger.error(
                "Entailment validation failed scan_id=%s intent_id=%s reason=%s",
                scan_id,
                intent.intent_id,
                exc.reason,
            )
            raise

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Entailment complete scan_id=%s intent_id=%s status=%s confidence=%.3f "
            "retrieved=%s cited=%s elapsed_ms=%s",
            scan_id,
            intent.intent_id,
            validated.status.value,
            validated.confidence,
            len(retrieved),
            len(validated.evidence),
            elapsed_ms,
        )
        return validated

    async def evaluate_intents(
        self,
        *,
        intents: Sequence[IntentQuery],
        scan_id: uuid.UUID,
    ) -> list[IntentEvaluation]:
        """
        Evaluate intents concurrently with ``asyncio.gather``.

        Result order matches ``intents`` order. All tasks share this engine's
        single ``LLMClient`` so Phase A budget accounting remains correct
        (default 35 calls/scan; 30 NLI calls leave headroom for intent gen / later stages).
        """
        if not intents:
            return []

        sem = asyncio.Semaphore(5)

        async def _eval_with_sem(intent: IntentQuery) -> IntentEvaluation:
            async with sem:
                return await self.evaluate_intent(intent=intent, scan_id=scan_id)

        tasks = [_eval_with_sem(intent) for intent in intents]
        return list(await asyncio.gather(*tasks))


async def evaluate_intent(
    *,
    intent: IntentQuery,
    scan_id: uuid.UUID,
    llm_client: LLMClient | None = None,
    retriever: Retriever | None = None,
) -> IntentEvaluation:
    engine = EntailmentEngine(llm_client=llm_client, retriever=retriever)
    return await engine.evaluate_intent(intent=intent, scan_id=scan_id)


async def evaluate_intents(
    *,
    intents: Sequence[IntentQuery],
    scan_id: uuid.UUID,
    llm_client: LLMClient | None = None,
    retriever: Retriever | None = None,
) -> list[IntentEvaluation]:
    engine = EntailmentEngine(llm_client=llm_client, retriever=retriever)
    return await engine.evaluate_intents(intents=intents, scan_id=scan_id)
