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
    IntentEvaluationBatch,
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

BATCH_NLI_SYSTEM_PROMPT = """You are an evidence-grounded classifier evaluating multiple intent claims in batch.

You may ONLY use the supplied evidence chunks for each intent.
Never use outside knowledge or assumptions.
Never infer business facts that are not explicitly supported.

For EACH intent query item:
- If the evidence does not answer the question, return UNKNOWN with evidence as an empty list [].
- If the evidence directly supports the requested fact, return SUPPORTED (cite 1+ valid chunk IDs).
- If the evidence supports only part of the requested fact, return PARTIALLY_SUPPORTED (cite 1+ valid chunk IDs).
- If the evidence directly conflicts with the requested fact, return CONTRADICTED (cite 1+ valid chunk IDs).

Every non-UNKNOWN result MUST cite one or more supplied chunk IDs that appear in that item's evidence chunks.
You MUST NOT invent chunk IDs.
Only cite chunk IDs that appear in that specific item's provided evidence.
Confidence must be a float between 0.0 and 1.0.

Return an IntentEvaluationBatch with an evaluation corresponding to EACH provided intent item.
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
    rrf_score: float | None = None


def _chunk_id(chunk: RetrievableChunk) -> str:
    return str(chunk.id)


def _chunk_rrf_score(chunk: RetrievableChunk) -> float | None:
    raw = getattr(chunk, "_retrieval_rrf_score", None)
    if raw is None:
        raw = getattr(chunk, "rrf_score", None)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0.0 else None


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
                rrf_score=_chunk_rrf_score(chunk),
            )
        )
    return evidence


def format_evidence_for_prompt(evidence: Sequence[RetrievedEvidence]) -> str:
    blocks: list[str] = []
    for item in evidence:
        raw_text = (item.content or "").strip()
        truncated = raw_text[:800] if len(raw_text) > 800 else raw_text
        blocks.append(
            f"[{item.chunk_id}]\n"
            f"URL: {item.url or '(none)'}\n"
            f"DOM PATH: {item.dom_path}\n"
            f"CONTENT:\n{truncated}"
        )
    return "\n\n".join(blocks)


def build_nli_user_prompt(*, intent: IntentQuery, evidence: Sequence[RetrievedEvidence]) -> str:
    return (
        f"INTENT ID: {intent.intent_id}\n"
        f"INTENT:\n{intent.query}\n\n"
        f"EVIDENCE CHUNKS:\n\n{format_evidence_for_prompt(evidence)}"
    )


def build_batch_nli_user_prompt(
    items: Sequence[tuple[IntentQuery, Sequence[RetrievedEvidence]]],
) -> str:
    sections: list[str] = []
    for idx, (intent, evidence) in enumerate(items, start=1):
        ev_text = (
            format_evidence_for_prompt(evidence) if evidence else "(No evidence chunks retrieved)"
        )
        category_val = (
            intent.category.value if hasattr(intent.category, "value") else intent.category
        )
        sections.append(
            f"=== ITEM {idx} ===\n"
            f"INTENT ID: {intent.intent_id}\n"
            f"CATEGORY: {category_val}\n"
            f"PERSONA: {intent.persona}\n"
            f"INTENT QUERY:\n{intent.query}\n\n"
            f"EVIDENCE CHUNKS:\n{ev_text}"
        )
    return "\n\n".join(sections)


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
                    rrf_score=item.rrf_score,
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
        concurrency: int = 1,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        self._llm = llm_client or LLMClient()
        self._retriever: Retriever = retriever or default_hybrid_retriever
        self._top_k = top_k
        self._concurrency = max(1, concurrency)

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
                max_retries=2,
                max_tokens=1500,
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

    async def evaluate_intent_batch(
        self,
        *,
        batch: Sequence[tuple[IntentQuery, Sequence[RetrievedEvidence]]],
        scan_id: uuid.UUID,
    ) -> list[IntentEvaluation]:
        """Evaluate a batch of (IntentQuery, RetrievedEvidence) pairs using 1 structured LLM call."""
        if not batch:
            return []

        results: list[IntentEvaluation | None] = [None] * len(batch)
        items_for_llm: list[tuple[int, IntentQuery, Sequence[RetrievedEvidence]]] = []

        for idx, (intent, evidence) in enumerate(batch):
            if not evidence:
                results[idx] = IntentEvaluation(
                    intent_id=intent.intent_id,
                    query=intent.query,
                    category=intent.category,
                    persona=intent.persona,
                    status=EntailmentStatus.UNKNOWN,
                    reasoning="No evidence chunks were retrieved for this intent.",
                    evidence=[],
                    confidence=0.0,
                )
            else:
                items_for_llm.append((idx, intent, evidence))

        if not items_for_llm:
            return [cast(IntentEvaluation, r) for r in results]

        user_prompt = build_batch_nli_user_prompt([(item[1], item[2]) for item in items_for_llm])
        raw_batch: IntentEvaluationBatch | None = None
        try:
            raw_batch = await self._llm.create(
                IntentEvaluationBatch,
                messages=[
                    {"role": "system", "content": BATCH_NLI_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_retries=2,
                max_tokens=2500,
            )
        except BudgetExhausted:
            raise
        except Exception as exc:
            logger.warning(
                "Batch NLI LLM call failed for scan_id=%s batch_size=%d (%s); falling back to individual calls",
                scan_id,
                len(items_for_llm),
                exc,
            )

        if raw_batch and raw_batch.evaluations:
            eval_map: dict[str, IntentEvaluation] = {
                e.intent_id: e for e in raw_batch.evaluations if e.intent_id
            }
            for list_idx, (orig_idx, intent, evidence) in enumerate(items_for_llm):
                candidate = eval_map.get(intent.intent_id)
                if not candidate and list_idx < len(raw_batch.evaluations):
                    candidate = raw_batch.evaluations[list_idx]
                if candidate:
                    try:
                        validated = validate_intent_evaluation(
                            candidate,
                            intent=intent,
                            retrieved=evidence,
                        )
                        results[orig_idx] = validated
                    except EntailmentError as v_err:
                        logger.warning(
                            "Batch item validation failed for intent %s (%s); setting UNKNOWN",
                            intent.intent_id,
                            v_err,
                        )
                        results[orig_idx] = IntentEvaluation(
                            intent_id=intent.intent_id,
                            query=intent.query,
                            category=intent.category,
                            persona=intent.persona,
                            status=EntailmentStatus.UNKNOWN,
                            reasoning=f"Batch validation: {v_err}",
                            evidence=[],
                            confidence=0.85,
                        )

        # For any items that were not resolved by the batch call (e.g. LLM omitted or failed):
        unresolved = [
            items_for_llm[i]
            for i in range(len(items_for_llm))
            if results[items_for_llm[i][0]] is None
        ]
        if unresolved:
            logger.info("Resolving %d items individually via fallback", len(unresolved))
            sem = asyncio.Semaphore(3)

            async def _resolve_single(
                orig_idx: int, it: IntentQuery, ev: Sequence[RetrievedEvidence]
            ) -> None:
                async with sem:
                    try:
                        user_prompt = build_nli_user_prompt(intent=it, evidence=ev)
                        raw = await self._llm.create(
                            IntentEvaluation,
                            messages=[
                                {"role": "system", "content": NLI_SYSTEM_PROMPT},
                                {"role": "user", "content": user_prompt},
                            ],
                            max_retries=2,
                            max_tokens=1500,
                        )
                        results[orig_idx] = validate_intent_evaluation(raw, intent=it, retrieved=ev)
                    except BudgetExhausted:
                        raise
                    except Exception as err:
                        logger.warning("Fallback evaluation failed for %s: %s", it.intent_id, err)
                        results[orig_idx] = IntentEvaluation(
                            intent_id=it.intent_id,
                            query=it.query,
                            category=it.category,
                            persona=it.persona,
                            status=EntailmentStatus.UNKNOWN,
                            reasoning=f"Evaluation temporarily unavailable: {err}",
                            evidence=[],
                            confidence=0.85,
                        )

            await asyncio.gather(
                *[_resolve_single(orig_idx, it, ev) for orig_idx, it, ev in unresolved]
            )

        return [cast(IntentEvaluation, r) for r in results]

    async def evaluate_intents(
        self,
        *,
        intents: Sequence[IntentQuery],
        scan_id: uuid.UUID,
        progress_callback: Callable[[int, int, IntentEvaluation], Awaitable[None]] | None = None,
    ) -> list[IntentEvaluation]:
        """
        Evaluate intents in parallel batches (e.g. 3 batches of 10 for 30 intents).
        """
        if not intents:
            return []

        total_count = len(intents)
        completed_count = 0
        progress_lock = asyncio.Lock()

        # Step 1: Concurrently retrieve evidence for all intents (Contract-1 hybrid_search)
        retrieval_tasks = [self._retrieve(query=it.query, scan_id=scan_id) for it in intents]
        retrieved_list = await asyncio.gather(*retrieval_tasks)
        paired = list(zip(intents, retrieved_list, strict=True))

        # Step 2: Split into batches of 10 (3 batches for 30 intents)
        batch_size = 10
        chunks = [paired[i : i + batch_size] for i in range(0, len(paired), batch_size)]

        async def _process_batch(
            chunk: Sequence[tuple[IntentQuery, Sequence[RetrievedEvidence]]],
        ) -> list[IntentEvaluation]:
            nonlocal completed_count
            evaluations = await self.evaluate_intent_batch(batch=chunk, scan_id=scan_id)
            if progress_callback is not None:
                for item in evaluations:
                    async with progress_lock:
                        completed_count += 1
                        current_completed = completed_count
                    try:
                        await progress_callback(current_completed, total_count, item)
                    except Exception:
                        pass
            return evaluations

        if self._concurrency > 1:
            batch_results = await asyncio.gather(*[_process_batch(c) for c in chunks])
        else:
            batch_results = []
            for c in chunks:
                batch_results.append(await _process_batch(c))
        flattened: list[IntentEvaluation] = []
        for br in batch_results:
            flattened.extend(br)
        return flattened


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
    concurrency: int = 1,
) -> list[IntentEvaluation]:
    engine = EntailmentEngine(llm_client=llm_client, retriever=retriever, concurrency=concurrency)
    return await engine.evaluate_intents(intents=intents, scan_id=scan_id)
