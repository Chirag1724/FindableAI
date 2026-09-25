"""Synthetic intent generator — one structured LLM call → 30 IntentQuery objects."""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from collections.abc import Mapping

from app.core.llm import BudgetExhausted, LLMClient
from app.schemas.intelligence import IntentBatch, IntentCategory, IntentQuery

logger = logging.getLogger(__name__)

REQUIRED_QUERY_COUNT = 30
QUERIES_PER_CATEGORY = 3
MIN_BUSINESS_CONTEXT_LENGTH = 12

TAXONOMY_CATEGORIES: tuple[IntentCategory, ...] = tuple(IntentCategory)

CATEGORY_DEFINITIONS: Mapping[IntentCategory, str] = {
    IntentCategory.ELIGIBILITY: (
        "Who is eligible or permitted to use, buy, or access the service "
        "(dietary, age, credentials, membership)?"
    ),
    IntentCategory.POLICY: (
        "Rules, restrictions, permissions, cancellations, conduct, pets, children, etc."
    ),
    IntentCategory.AVAILABILITY: (
        "Opening times, dates, service availability, inventory or appointment availability."
    ),
    IntentCategory.PRICING: (
        "Prices, fees, deposits, discounts, minimum spends, taxes where relevant."
    ),
    IntentCategory.ACCESSIBILITY: (
        "Wheelchair access, accessibility facilities, accommodations, assistance."
    ),
    IntentCategory.COMMERCIAL: (
        "Events, catering, corporate bookings, private dining, commercial arrangements."
    ),
    IntentCategory.LOCAL: (
        "Location, address, directions, parking, nearby landmarks, service area."
    ),
    IntentCategory.TRANSACTIONAL: (
        "Reservations, bookings, ordering, appointments, payment methods, how to complete an action."
    ),
    IntentCategory.TRUST: (
        "Certifications, credentials, guarantees, safety, authenticity, reputation-related facts."
    ),
    IntentCategory.EDGE_CASES: (
        "Unusual but realistic scenarios, holidays, weather, exceptions, special circumstances."
    ),
}

_WHITESPACE_RE = re.compile(r"\s+")
_PLACEHOLDER_RE = re.compile(
    r"^(n/?a|none|null|todo|tbd|placeholder|example|lorem ipsum|question\s*\d*)$",
    re.IGNORECASE,
)
_ANSWER_LIKE_RE = re.compile(
    r"^\s*(yes|no|yeah|yep|nope)([,.!]|\s)|"
    r"^\s*the\s+(business|restaurant|company|store|hotel|clinic)\b|"
    r"^\s*we\s+(offer|are|have|provide|accept|do|don't)\b|"
    r"^\s*our\s+(hours|menu|policy|address|phone)\b",
    re.IGNORECASE,
)


class IntentGenerationError(Exception):
    """Raised when intent generation input, LLM output, or validation fails."""

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "intent_generation_failed"
        super().__init__(message)


def _normalize_query(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _normalize_for_dedupe(text: str) -> str:
    cleaned = _normalize_query(text).casefold()
    cleaned = cleaned.rstrip(" ?!.").strip()
    return cleaned


def _category_distribution(queries: list[IntentQuery]) -> dict[str, int]:
    counts = Counter(q.category.value for q in queries)
    return {category.value: counts.get(category.value, 0) for category in TAXONOMY_CATEGORIES}


def _build_system_prompt() -> str:
    taxonomy_lines = "\n".join(
        f"- {category.value}: {CATEGORY_DEFINITIONS[category]}" for category in TAXONOMY_CATEGORIES
    )
    category_values = ", ".join(c.value for c in TAXONOMY_CATEGORIES)
    return f"""You are FindableAI's synthetic intent generator for machine-discoverability audits.

ROLE:
Generate realistic information-seeking questions a customer, search engine, or AI answer agent
would ask about a business. You discover questions only — you never answer them.

OBJECTIVE:
Produce exactly {REQUIRED_QUERY_COUNT} diverse questions distributed across the 10 taxonomy
categories below. Exactly {QUERIES_PER_CATEGORY} questions per category.

TAXONOMY (use these exact category string values):
{taxonomy_lines}

Allowed category values: {category_values}

QUESTION QUALITY:
- Natural language, concise, realistic customer/search-agent intent
- Specific enough to be useful; one primary information need per question
- Not repetitive; not artificially phrased; avoid compound questions unless necessary
- Each query MUST be a question (prefer ending with '?')
- Do NOT answer the questions
- Do NOT invent business facts or claim undocumented policies as facts
- Do NOT cite evidence or assert what the business offers
- Use business_context only to tailor which questions are relevant — not to answer them

OUTPUT CONTRACT (IntentBatch):
- business_type: short inferred business category (e.g. "restaurant", "clinic")
- queries: exactly {REQUIRED_QUERY_COUNT} IntentQuery objects
- Each IntentQuery needs: intent_id, category, query, difficulty ("easy"|"medium"|"hard"),
  expected_evidence_type (where an answer would likely appear on a website)

intent_id format examples: eligibility_01, policy_02, edge_cases_03
"""


def _build_user_prompt(business_context: str) -> str:
    return (
        "Generate the IntentBatch for the following business context.\n\n"
        f"BUSINESS CONTEXT:\n{business_context}\n\n"
        f"Remember: exactly {REQUIRED_QUERY_COUNT} questions, "
        f"{QUERIES_PER_CATEGORY} per category, questions only — no answers."
    )


def validate_business_context(business_context: str) -> str:
    if not isinstance(business_context, str):
        raise IntentGenerationError(
            "business_context must be a string",
            reason="invalid_business_context",
        )
    cleaned = _normalize_query(business_context)
    if len(cleaned) < MIN_BUSINESS_CONTEXT_LENGTH:
        raise IntentGenerationError(
            f"business_context must be at least {MIN_BUSINESS_CONTEXT_LENGTH} characters "
            "after normalization",
            reason="invalid_business_context",
        )
    return cleaned


def validate_intent_batch(batch: IntentBatch) -> IntentBatch:
    """
    Deterministic post-LLM validation.

    Does not call the LLM. Raises IntentGenerationError on contract violations.
    """
    if not isinstance(batch, IntentBatch):
        raise IntentGenerationError(
            f"Expected IntentBatch, got {type(batch).__name__}",
            reason="malformed_response",
        )

    normalized_queries: list[IntentQuery] = []
    seen: set[str] = set()

    for index, item in enumerate(batch.queries):
        query_text = _normalize_query(item.query)
        if not query_text:
            raise IntentGenerationError(
                f"Empty query at index {index}",
                reason="empty_query",
            )
        if _PLACEHOLDER_RE.match(query_text):
            raise IntentGenerationError(
                f"Placeholder query rejected at index {index}",
                reason="placeholder_query",
            )
        if _ANSWER_LIKE_RE.match(query_text):
            raise IntentGenerationError(
                f"Answer-like output rejected at index {index}",
                reason="answer_like_query",
            )
        if "?" not in query_text:
            raise IntentGenerationError(
                f"Query at index {index} is not phrased as a question",
                reason="non_question",
            )

        dedupe_key = _normalize_for_dedupe(query_text)
        if dedupe_key in seen:
            raise IntentGenerationError(
                f"Duplicate query detected (case-insensitive): {query_text!r}",
                reason="duplicate_query",
            )
        seen.add(dedupe_key)

        expected_evidence = _normalize_query(item.expected_evidence_type)
        if not expected_evidence or _PLACEHOLDER_RE.match(expected_evidence):
            raise IntentGenerationError(
                f"Invalid expected_evidence_type at index {index}",
                reason="invalid_evidence_type",
            )

        if not isinstance(item.category, IntentCategory):
            raise IntentGenerationError(
                f"Invalid category at index {index}: {item.category!r}",
                reason="invalid_category",
            )

        normalized_queries.append(
            item.model_copy(
                update={
                    "query": query_text,
                    "expected_evidence_type": expected_evidence,
                    "intent_id": _normalize_query(item.intent_id) or f"intent_{index + 1:02d}",
                }
            )
        )

    total = len(normalized_queries)
    if total != REQUIRED_QUERY_COUNT:
        raise IntentGenerationError(
            f"Expected exactly {REQUIRED_QUERY_COUNT} queries, got {total}",
            reason="invalid_query_count",
        )

    distribution = _category_distribution(normalized_queries)
    missing = [name for name, count in distribution.items() if count == 0]
    if missing:
        raise IntentGenerationError(
            f"Missing taxonomy categories: {', '.join(missing)}",
            reason="missing_categories",
        )

    unbalanced = {
        name: count for name, count in distribution.items() if count != QUERIES_PER_CATEGORY
    }
    if unbalanced:
        raise IntentGenerationError(
            f"Expected exactly {QUERIES_PER_CATEGORY} queries per category; got {unbalanced}",
            reason="invalid_category_distribution",
        )

    business_type = _normalize_query(batch.business_type)
    if not business_type:
        raise IntentGenerationError(
            "business_type must be non-empty",
            reason="invalid_business_type",
        )

    # Stable deterministic ids after validation (no LLM repair).
    finalized: list[IntentQuery] = []
    per_category_index: Counter[str] = Counter()
    for query in normalized_queries:
        per_category_index[query.category.value] += 1
        idx = per_category_index[query.category.value]
        finalized.append(
            query.model_copy(
                update={"intent_id": f"{query.category.value}_{idx:02d}"},
            )
        )

    return IntentBatch(business_type=business_type, queries=finalized)


class IntentGenerator:
    """Generate a validated IntentBatch with exactly one LLMClient.create call."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client or LLMClient()

    @property
    def llm_client(self) -> LLMClient:
        return self._llm

    async def generate_intents(self, *, business_context: str) -> IntentBatch:
        cleaned_context = validate_business_context(business_context)
        started = time.perf_counter()

        logger.info(
            "Intent generation started model=%s required_queries=%s",
            self._llm.model,
            REQUIRED_QUERY_COUNT,
        )

        calls_before = self._llm.calls_made
        try:
            # max_retries=0: Instructor must not re-call the model to repair schema.
            raw_batch = await self._llm.create(
                IntentBatch,
                messages=[
                    {"role": "system", "content": _build_system_prompt()},
                    {"role": "user", "content": _build_user_prompt(cleaned_context)},
                ],
                max_retries=0,
            )
        except IntentGenerationError:
            raise
        except BudgetExhausted:
            raise
        except Exception as exc:
            logger.error(
                "Intent generation LLM call failed model=%s error_type=%s",
                self._llm.model,
                type(exc).__name__,
            )
            raise IntentGenerationError(
                f"LLM intent generation failed: {exc}",
                reason="llm_failure",
            ) from exc

        calls_after = self._llm.calls_made
        llm_calls = calls_after - calls_before
        if llm_calls != 1:
            raise IntentGenerationError(
                f"Expected exactly 1 LLM call, observed {llm_calls}",
                reason="unexpected_llm_call_count",
            )

        try:
            validated = validate_intent_batch(raw_batch)
        except IntentGenerationError as exc:
            logger.error(
                "Intent generation validation failed reason=%s model=%s",
                exc.reason,
                self._llm.model,
            )
            raise

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        distribution = _category_distribution(validated.queries)
        logger.info(
            "Intent generation succeeded queries=%s distribution=%s "
            "llm_calls=%s elapsed_ms=%s model=%s",
            len(validated.queries),
            distribution,
            llm_calls,
            elapsed_ms,
            self._llm.model,
        )
        return validated


async def generate_intents(
    *,
    business_context: str,
    llm_client: LLMClient | None = None,
) -> IntentBatch:
    """Module-level entrypoint: business_context → single LLM call → IntentBatch."""
    generator = IntentGenerator(llm_client=llm_client)
    return await generator.generate_intents(business_context=business_context)
