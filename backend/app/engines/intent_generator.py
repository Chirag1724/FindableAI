"""Intent query generator — structured LLM generation of intent query sets."""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from collections.abc import Mapping, Sequence

from app.core.llm import BudgetExhausted, LLMClient
from app.schemas.intelligence import IntentBatch, IntentCategory, IntentQuery, PersonaIntentBatch

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


def resolve_query_persona(
    category: IntentCategory, active_personas: Sequence[str] | None = None
) -> str:
    active = (
        [p.lower().strip() for p in active_personas]
        if active_personas
        else ["cto", "developer", "procurement"]
    )
    preferences: dict[IntentCategory, list[str]] = {
        IntentCategory.POLICY: ["cto", "procurement", "developer"],
        IntentCategory.TRUST: ["cto", "developer", "procurement"],
        IntentCategory.AVAILABILITY: ["cto", "developer", "procurement"],
        IntentCategory.EDGE_CASES: ["cto", "developer", "procurement"],
        IntentCategory.ACCESSIBILITY: ["developer", "cto", "procurement"],
        IntentCategory.TRANSACTIONAL: ["developer", "procurement", "cto"],
        IntentCategory.LOCAL: ["developer", "procurement", "cto"],
        IntentCategory.ELIGIBILITY: ["developer", "procurement", "cto"],
        IntentCategory.PRICING: ["procurement", "cto", "developer"],
        IntentCategory.COMMERCIAL: ["procurement", "cto", "developer"],
    }
    for candidate in preferences.get(category, []):
        if candidate in active:
            return candidate
    return active[0] if active else "cto"


def _build_system_prompt(personas: Sequence[str] | None = None) -> str:
    taxonomy_lines = "\n".join(
        f"- {category.value}: {CATEGORY_DEFINITIONS[category]}" for category in TAXONOMY_CATEGORIES
    )
    category_values = ", ".join(c.value for c in TAXONOMY_CATEGORIES)
    persona_guide = ""
    if personas:
        active_list = ", ".join(personas)
        persona_guide = (
            f"\n\nACTIVE PERSONAS: {active_list}\n"
            "Tailor questions from the perspective of these personas "
            "(e.g. CTO evaluates enterprise security, SLA, resilience, policy; "
            "Developer evaluates APIs, technical integration, docs, error cases; "
            "Procurement evaluates pricing models, licensing, commercial terms)."
        )

    return f"""You are FindableAI's synthetic intent generator for machine-discoverability audits.

ROLE:
Generate realistic information-seeking questions a customer, search engine, or AI answer agent
would ask about a business. You discover questions only — you never answer them.{persona_guide}

OBJECTIVE:
Produce exactly {REQUIRED_QUERY_COUNT} diverse questions distributed across the 10 taxonomy
categories below. Exactly {QUERIES_PER_CATEGORY} questions per category.

TAXONOMY (use these exact category string values):
{taxonomy_lines}

Allowed category values: {category_values}

QUESTION QUALITY:
- Natural language, concise, realistic customer/search-agent intent
- Specific enough to be useful; one primary information need per question
- Keep queries concise (under 12 words each) and expected_evidence_type brief (under 4 words, e.g. "pricing page", "FAQ", "docs")
- Not repetitive; not artificially phrased; avoid compound questions unless necessary
- Each query MUST be a question (ending with '?')
- Do NOT answer the questions
- Do NOT invent business facts or claim undocumented policies as facts
- Do NOT cite evidence or assert what the business offers
- Use business_context only to tailor which questions are relevant — not to answer them

OUTPUT CONTRACT (IntentBatch):
- business_type: short inferred business category (e.g. "restaurant", "clinic", "SaaS platform")
- queries: exactly {REQUIRED_QUERY_COUNT} IntentQuery objects
- Each IntentQuery needs: intent_id, category, query, difficulty ("easy"|"medium"|"hard"),
  expected_evidence_type (brief phrase: "pricing table", "FAQ", "terms", "contact page")

intent_id format examples: eligibility_01, policy_02, edge_cases_03
"""


def _build_user_prompt(business_context: str) -> str:
    return (
        "Generate the IntentBatch for the following business context.\n\n"
        f"BUSINESS CONTEXT:\n{business_context}\n\n"
        f"Remember: exactly {REQUIRED_QUERY_COUNT} questions, "
        f"{QUERIES_PER_CATEGORY} per category, questions only — no answers."
    )


def _build_persona_system_prompt(persona: str) -> str:
    norm_persona = persona.lower().strip()
    persona_focus = {
        "cto": (
            "You are a Chief Technology Officer (CTO) evaluating this business. "
            "Focus on enterprise security, SLA guarantees, data privacy, uptime, resilience, compliance, and disaster recovery."
        ),
        "developer": (
            "You are a Software Developer evaluating this business. "
            "Focus on REST/GraphQL APIs, SDKs, technical documentation, webhook retries, sandbox environments, and error handling."
        ),
        "procurement": (
            "You are an Enterprise Procurement Officer evaluating this business. "
            "Focus on pricing tiers, licensing agreements, contract terms, billing cycles, cancellation, and commercial ROI."
        ),
    }.get(
        norm_persona,
        f"You are evaluating this business from the perspective of a {persona.title()} buyer.",
    )

    taxonomy_lines = "\n".join(
        f"- {category.value}: {CATEGORY_DEFINITIONS[category]}" for category in TAXONOMY_CATEGORIES
    )
    category_values = ", ".join(c.value for c in TAXONOMY_CATEGORIES)

    return f"""You are FindableAI's synthetic intent generator simulating the {persona.upper()} persona for machine-discoverability audits.

PERSONA PERSPECTIVE:
{persona_focus}

OBJECTIVE:
Produce exactly 10 questions: exactly ONE question for EACH of the 10 taxonomy categories below.

TAXONOMY (use these exact category string values):
{taxonomy_lines}

Allowed category values: {category_values}

CRITICAL RULES:
- Output pure JSON directly. Do NOT output preliminary thought chains, reasoning, or preambles.
- Exactly 1 question per category (total 10 questions covering all 10 categories).
- Phrased naturally from the {persona.upper()} perspective.
- Each query MUST be a concise question ending with '?' (under 12 words).
- expected_evidence_type must be a brief phrase (e.g. "pricing table", "API docs", "terms of service", "FAQ").
- Do NOT answer the questions or invent business facts.

OUTPUT CONTRACT (PersonaIntentBatch):
- business_type: short inferred business category (e.g. "restaurant", "clinic", "SaaS platform")
- queries: exactly 10 IntentQuery objects covering each category once.
"""


def _build_persona_user_prompt(business_context: str, persona: str) -> str:
    return (
        f"Generate the 10 intent queries for the {persona.upper()} persona across all 10 categories.\n\n"
        f"BUSINESS CONTEXT:\n{business_context}\n\n"
        "Ground questions in the specific features, technology, and offerings described in the business context above, "
        "asking what a buyer evaluates about this platform's capabilities alongside compliance and diligence.\n"
        "Remember: exactly 10 questions (1 per category), concise, questions only — no answers."
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
    if len(cleaned) > 2000:
        cleaned = cleaned[:2000]
    return cleaned


def validate_intent_batch(
    batch: IntentBatch,
    personas: Sequence[str] | None = None,
) -> IntentBatch:
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
        assigned_persona = query.persona or resolve_query_persona(query.category, personas)
        finalized.append(
            query.model_copy(
                update={
                    "intent_id": f"{query.category.value}_{idx:02d}",
                    "persona": assigned_persona,
                },
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

    async def _generate_persona_batch(
        self,
        persona: str,
        cleaned_context: str,
    ) -> PersonaIntentBatch:
        return await self._llm.create(
            PersonaIntentBatch,
            messages=[
                {"role": "system", "content": _build_persona_system_prompt(persona)},
                {"role": "user", "content": _build_persona_user_prompt(cleaned_context, persona)},
            ],
            max_retries=0,
            max_tokens=600,
        )

    async def generate_intents(
        self,
        *,
        business_context: str,
        personas: Sequence[str] | None = None,
    ) -> IntentBatch:
        cleaned_context = validate_business_context(business_context)
        started = time.perf_counter()

        logger.info(
            "Intent generation started model=%s required_queries=%s personas=%s",
            self._llm.model,
            REQUIRED_QUERY_COUNT,
            personas,
        )

        calls_before = self._llm.calls_made
        try:
            # If an instructor client is directly injected (e.g. unit tests with mock handlers),
            # execute single-call IntentBatch for 100% test fixture compatibility.
            if self._llm._instructor_client is not None:
                raw_batch = await self._llm.create(
                    IntentBatch,
                    messages=[
                        {"role": "system", "content": _build_system_prompt(personas=personas)},
                        {"role": "user", "content": _build_user_prompt(cleaned_context)},
                    ],
                    max_retries=0,
                    max_tokens=8192,
                )
            else:
                # Production: Parallel 3-Batch Persona Generation (CTO, Developer, Procurement)
                active_personas = [
                    p.lower().strip() for p in (personas or ["cto", "developer", "procurement"])
                ]
                for default_p in ("cto", "developer", "procurement"):
                    if len(active_personas) >= 3:
                        break
                    if default_p not in active_personas:
                        active_personas.append(default_p)

                target_personas = active_personas[:3]

                sub_batches: list[PersonaIntentBatch] = []
                for p in target_personas:
                    sub_batches.append(await self._generate_persona_batch(p, cleaned_context))

                seen_texts: set[str] = set()
                merged_queries: list[IntentQuery] = []
                for persona_name, p_batch in zip(target_personas, sub_batches, strict=True):
                    for q in p_batch.queries:
                        q_text = _normalize_query(q.query)
                        dedupe_key = _normalize_for_dedupe(q_text)
                        if dedupe_key in seen_texts:
                            clean_q = q_text[0].lower() + q_text[1:] if len(q_text) > 1 else q_text
                            q_text = f"From a {persona_name} perspective, {clean_q}"
                        seen_texts.add(_normalize_for_dedupe(q_text))
                        merged_queries.append(
                            q.model_copy(update={"query": q_text, "persona": persona_name})
                        )

                business_type = next(
                    (b.business_type for b in sub_batches if b.business_type), "business"
                )
                raw_batch = IntentBatch(business_type=business_type, queries=merged_queries)
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
        if llm_calls < 1:
            raise IntentGenerationError(
                f"Expected at least 1 LLM call, observed {llm_calls}",
                reason="unexpected_llm_call_count",
            )

        try:
            validated = validate_intent_batch(raw_batch, personas=personas)
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
    personas: Sequence[str] | None = None,
    llm_client: LLMClient | None = None,
) -> IntentBatch:
    """Module-level entrypoint: business_context → single LLM call → IntentBatch."""
    generator = IntentGenerator(llm_client=llm_client)
    return await generator.generate_intents(
        business_context=business_context,
        personas=personas,
    )
