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

from app.core.config import settings
from app.core.llm import BudgetExhausted, LLMClient
from app.core.llm_errors import ErrorClass, LLMProviderError
from app.schemas.intelligence import (
    EntailmentStatus,
    EvidenceReference,
    IntentEvaluation,
    IntentEvaluationBatch,
    IntentQuery,
)

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
# Success-path default: 30 intents → 3 persona batches of 10. Overridable via
# EVAL_BATCH_SIZE / EntailmentEngine(batch_size=...).
DEFAULT_BATCH_SIZE = 10

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
        truncated = raw_text[:400] if len(raw_text) > 400 else raw_text
        blocks.append(
            f"[{item.chunk_id}]\n"
            f"URL: {item.url or '(none)'}\n"
            f"DOM PATH: {item.dom_path}\n"
            f"CONTENT:\n{truncated}"
        )
    return "\n\n".join(blocks)


def format_evidence_compact(evidence: Sequence[RetrievedEvidence], *, max_chars: int = 180) -> str:
    """Batch prompt: chunk id + truncated content only (URL/DOM rebuilt at validate)."""
    blocks: list[str] = []
    for item in evidence:
        raw_text = (item.content or "").strip()
        truncated = raw_text[:max_chars] if len(raw_text) > max_chars else raw_text
        blocks.append(f"[{item.chunk_id}] {truncated}")
    return "\n".join(blocks)


def build_nli_user_prompt(*, intent: IntentQuery, evidence: Sequence[RetrievedEvidence]) -> str:
    return (
        f"INTENT ID: {intent.intent_id}\n"
        f"INTENT:\n{intent.query}\n\n"
        f"EVIDENCE CHUNKS:\n\n{format_evidence_for_prompt(evidence)}"
    )


def build_batch_nli_user_prompt(
    items: Sequence[tuple[IntentQuery, Sequence[RetrievedEvidence]]],
) -> str:
    """Compact batch prompt so 10 intents fit under Groq free-tier 8K TPM."""
    persona = None
    if items:
        persona = items[0][0].persona
    header_parts = ["Return one evaluation per INTENT ID. Cite only that item's chunk ids."]
    if persona:
        header_parts.append(f"PERSONA: {persona}")
    sections: list[str] = [" ".join(header_parts)]
    for intent, evidence in items:
        ev_text = format_evidence_compact(evidence) if evidence else "(no evidence)"
        sections.append(f"INTENT ID: {intent.intent_id}\nQ: {intent.query}\nEVIDENCE:\n{ev_text}")
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
        batch_size: int | None = None,
        concurrency: int | None = None,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        resolved_batch = int(settings.EVAL_BATCH_SIZE) if batch_size is None else int(batch_size)
        if resolved_batch < 1:
            raise ValueError("batch_size must be >= 1")
        resolved_conc = (
            int(settings.EVAL_BATCH_CONCURRENCY) if concurrency is None else int(concurrency)
        )
        if resolved_conc < 1:
            raise ValueError("concurrency must be >= 1")
        self._llm = llm_client or LLMClient()
        self._retriever: Retriever = retriever or default_hybrid_retriever
        self._top_k = top_k
        self._batch_size = resolved_batch
        self._concurrency = max(1, min(3, resolved_conc))
        self._batch_retries = max(0, int(settings.EVAL_BATCH_RETRIES))
        self._split_min = max(1, int(settings.EVAL_SPLIT_MIN_BATCH))
        self._max_recovery = max(1, int(settings.EVAL_MAX_RECOVERY_REQUESTS_PER_BATCH))

    @property
    def llm_client(self) -> LLMClient:
        return self._llm

    @property
    def top_k(self) -> int:
        return self._top_k

    @property
    def batch_size(self) -> int:
        return self._batch_size

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

    @staticmethod
    def _honest_unresolved(intent: IntentQuery, reason: str) -> IntentEvaluation:
        """Truthful UNKNOWN after recovery is exhausted — never a fabricated success."""
        return IntentEvaluation(
            intent_id=intent.intent_id,
            query=intent.query,
            category=intent.category,
            persona=intent.persona,
            status=EntailmentStatus.UNKNOWN,
            reasoning=f"Evaluation unresolved after bounded recovery: {reason}",
            evidence=[],
            confidence=0.0,
        )

    @staticmethod
    def _split_immediately(exc: BaseException | None) -> bool:
        if isinstance(exc, LLMProviderError):
            return exc.error_class in (ErrorClass.CONTEXT_LENGTH, ErrorClass.INVALID_OUTPUT)
        return False

    async def _try_batch_llm(
        self,
        items: list[tuple[int, IntentQuery, Sequence[RetrievedEvidence]]],
        scan_id: uuid.UUID,
    ) -> tuple[
        dict[int, IntentEvaluation],
        list[tuple[int, IntentQuery, Sequence[RetrievedEvidence]]],
        BaseException | None,
    ]:
        """One structured batch request. Keep only items whose intent_id validates."""
        user_prompt = build_batch_nli_user_prompt([(it, ev) for _, it, ev in items])
        n = len(items)
        try:
            raw_batch = await self._llm.create(
                IntentEvaluationBatch,
                messages=[
                    {"role": "system", "content": BATCH_NLI_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_retries=0,
                max_tokens=min(2048, 160 * n + 200),
            )
        except BudgetExhausted:
            raise
        except Exception as exc:
            logger.warning(
                "batch_nli_failed scan_id=%s size=%s error_type=%s",
                scan_id,
                n,
                type(exc).__name__,
            )
            return {}, list(items), exc

        eval_map: dict[str, IntentEvaluation] = {
            e.intent_id: e for e in (raw_batch.evaluations or []) if e.intent_id
        }
        validated: dict[int, IntentEvaluation] = {}
        unresolved: list[tuple[int, IntentQuery, Sequence[RetrievedEvidence]]] = []
        for orig_idx, intent, evidence in items:
            candidate = eval_map.get(intent.intent_id)
            if candidate is None:
                unresolved.append((orig_idx, intent, evidence))
                continue
            try:
                validated[orig_idx] = validate_intent_evaluation(
                    candidate, intent=intent, retrieved=evidence
                )
            except EntailmentError as v_err:
                logger.warning(
                    "batch_item_invalid intent_id=%s reason=%s; will re-request",
                    intent.intent_id,
                    v_err.reason,
                )
                unresolved.append((orig_idx, intent, evidence))
        return validated, unresolved, None

    async def _try_single_llm(
        self,
        orig_idx: int,
        intent: IntentQuery,
        evidence: Sequence[RetrievedEvidence],
    ) -> tuple[int, IntentEvaluation] | None:
        try:
            raw = await self._llm.create(
                IntentEvaluation,
                messages=[
                    {"role": "system", "content": NLI_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_nli_user_prompt(intent=intent, evidence=evidence),
                    },
                ],
                max_retries=0,
                max_tokens=900,
            )
            return orig_idx, validate_intent_evaluation(raw, intent=intent, retrieved=evidence)
        except BudgetExhausted:
            raise
        except Exception as err:
            logger.warning(
                "per_intent_nli_failed intent_id=%s error_type=%s",
                intent.intent_id,
                type(err).__name__,
            )
            return None

    async def _resolve_with_recovery(
        self,
        items: list[tuple[int, IntentQuery, Sequence[RetrievedEvidence]]],
        scan_id: uuid.UUID,
        *,
        spend: list[int],
        cap: int,
        allow_retry: bool,
        charge: bool,
    ) -> dict[int, IntentEvaluation]:
        """Retry once → split into halves → per-intent. Keep every validated row.

        ``spend`` is a 1-int list shared with recursive splits so the recovery
        cap applies to the original batch as a whole. The success-path first
        call uses ``charge=False``; every retry/split/per-intent call charges.
        """
        if not items:
            return {}
        if charge:
            if spend[0] >= cap:
                return {idx: self._honest_unresolved(it, "recovery_cap") for idx, it, _ in items}
            spend[0] += 1

        validated, unresolved, err = await self._try_batch_llm(items, scan_id)
        if not unresolved:
            return validated

        if allow_retry and self._batch_retries > 0 and not self._split_immediately(err):
            if spend[0] < cap:
                spend[0] += 1
                obs = getattr(getattr(self._llm, "budget_guard", None), "observability", None)
                if obs is not None:
                    try:
                        await obs.batch_retrying()
                    except Exception:
                        logger.debug("batch_retrying_counter_failed", exc_info=True)
                more, unresolved, err = await self._try_batch_llm(unresolved, scan_id)
                validated.update(more)
                if not unresolved:
                    return validated

        if len(unresolved) > self._split_min and spend[0] < cap:
            mid = max(1, len(unresolved) // 2)
            left, right = unresolved[:mid], unresolved[mid:]
            logger.info(
                "batch_split scan_id=%s left=%s right=%s recovery_used=%s/%s",
                scan_id,
                len(left),
                len(right),
                spend[0],
                cap,
            )
            if left:
                validated.update(
                    await self._resolve_with_recovery(
                        left, scan_id, spend=spend, cap=cap, allow_retry=False, charge=True
                    )
                )
            if right:
                validated.update(
                    await self._resolve_with_recovery(
                        right, scan_id, spend=spend, cap=cap, allow_retry=False, charge=True
                    )
                )
            unresolved = [t for t in unresolved if t[0] not in validated]
            if not unresolved:
                return validated

        for orig_idx, intent, evidence in list(unresolved):
            if spend[0] >= cap:
                break
            spend[0] += 1
            got = await self._try_single_llm(orig_idx, intent, evidence)
            if got is not None:
                validated[got[0]] = got[1]

        for orig_idx, intent, _evidence in unresolved:
            if orig_idx not in validated:
                validated[orig_idx] = self._honest_unresolved(
                    intent, err.__class__.__name__ if err else "missing_or_invalid_id"
                )
        return validated

    async def evaluate_intent_batch(
        self,
        *,
        batch: Sequence[tuple[IntentQuery, Sequence[RetrievedEvidence]]],
        scan_id: uuid.UUID,
    ) -> list[IntentEvaluation]:
        """Evaluate a persona-sized batch. Success path: exactly one provider request."""
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

        if items_for_llm:
            resolved = await self._resolve_with_recovery(
                items_for_llm,
                scan_id,
                spend=[0],
                cap=self._max_recovery,
                allow_retry=True,
                charge=False,
            )
            for orig_idx, evaluation in resolved.items():
                results[orig_idx] = evaluation
            for orig_idx, intent, _evidence in items_for_llm:
                if results[orig_idx] is None:
                    results[orig_idx] = self._honest_unresolved(intent, "unresolved")

        return [cast(IntentEvaluation, r) for r in results]

    async def evaluate_intents(
        self,
        *,
        intents: Sequence[IntentQuery],
        scan_id: uuid.UUID,
        progress_callback: Callable[[int, int, IntentEvaluation], Awaitable[None]] | None = None,
    ) -> list[IntentEvaluation]:
        """
        Evaluate intents grouped by persona, then chunked by batch_size
        (default 10 → 3 requests for 30 intents across 3 personas).
        Results are returned in the original intent order.
        """
        if not intents:
            return []

        total_count = len(intents)
        completed_count = 0
        progress_lock = asyncio.Lock()

        retrieval_tasks = [self._retrieve(query=it.query, scan_id=scan_id) for it in intents]
        retrieved_list = await asyncio.gather(*retrieval_tasks)
        paired = list(zip(intents, retrieved_list, strict=True))

        groups: dict[str, list[tuple[IntentQuery, Sequence[RetrievedEvidence]]]] = {}
        group_order: list[str] = []
        for intent, evidence in paired:
            key = (intent.persona or "").strip().lower() or "_unassigned"
            if key not in groups:
                groups[key] = []
                group_order.append(key)
            groups[key].append((intent, evidence))

        batch_size = self._batch_size
        chunks: list[list[tuple[IntentQuery, Sequence[RetrievedEvidence]]]] = []
        for key in group_order:
            group = groups[key]
            for i in range(0, len(group), batch_size):
                chunks.append(group[i : i + batch_size])
        obs = getattr(getattr(self._llm, "budget_guard", None), "observability", None)
        if obs is not None:
            try:
                await obs.init_batches(len(chunks))
            except Exception:
                pass

        async def _process_batch(
            chunk: Sequence[tuple[IntentQuery, Sequence[RetrievedEvidence]]],
        ) -> list[IntentEvaluation]:
            nonlocal completed_count
            if obs is not None:
                try:
                    await obs.batch_started()
                except Exception:
                    pass
            try:
                evaluations = await self.evaluate_intent_batch(batch=chunk, scan_id=scan_id)
            except Exception:
                if obs is not None:
                    try:
                        await obs.batch_failed()
                    except Exception:
                        pass
                raise
            if obs is not None:
                try:
                    await obs.batch_completed()
                except Exception:
                    pass
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
            sem = asyncio.Semaphore(self._concurrency)

            async def _bounded_batch(
                c: Sequence[tuple[IntentQuery, Sequence[RetrievedEvidence]]],
            ) -> list[IntentEvaluation]:
                async with sem:
                    return await _process_batch(c)

            batch_results = await asyncio.gather(*[_bounded_batch(c) for c in chunks])
        else:
            batch_results = []
            for c in chunks:
                batch_results.append(await _process_batch(c))
        flattened: list[IntentEvaluation] = []
        for br in batch_results:
            flattened.extend(br)
        by_id = {e.intent_id: e for e in flattened}
        ordered: list[IntentEvaluation] = []
        for intent in intents:
            ev = by_id.get(intent.intent_id)
            ordered.append(
                ev if ev is not None else self._honest_unresolved(intent, "missing_batch_result")
            )
        return ordered


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
    batch_size: int = DEFAULT_BATCH_SIZE,
    concurrency: int = 1,
) -> list[IntentEvaluation]:
    engine = EntailmentEngine(
        llm_client=llm_client,
        retriever=retriever,
        batch_size=batch_size,
        concurrency=concurrency,
    )
    return await engine.evaluate_intents(intents=intents, scan_id=scan_id)
