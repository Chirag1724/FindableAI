"""Cross-page contradiction detection — deterministic first, LLM only for ambiguity.

Flow:
    DOM chunks
        → structured fact extraction
        → canonical normalization
        → same-entity grouping
        → deterministic comparison
        → semantic LLM classification (ambiguous pairs only)
        → deduplicated Contradiction results

Maps onto Phase A ``Contradiction`` / ``ContradictionSeverity``.
Does not own retrieval, scoring, patches, or orchestration.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.llm import BudgetExhausted, LLMClient
from app.schemas.intelligence import Contradiction, ContradictionSeverity

logger = logging.getLogger(__name__)

SEMANTIC_SYSTEM_PROMPT = """You are an evidence-grounded contradiction judge.

You may ONLY use the two supplied source statements.
Never use outside knowledge.
Never invent facts.
Never invent chunk IDs.

Decide whether the statements are contradictory about the SAME business fact.

If they clearly conflict, set contradictory=true and choose:
- HARD_CONTRADICTION for incompatible factual values
- SOFT_INCONSISTENCY for ambiguous or qualified inconsistency

If they are compatible, complementary, refer to different entities/conditions,
or evidence is insufficient, set contradictory=false.

Do not force a contradiction.
Return only the structured SemanticConflictJudgment.
"""


class ContradictionDetectionError(Exception):
    """Raised when contradiction detection input, extraction, or LLM output fails."""

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "contradiction_detection_failed"
        super().__init__(message)


class FactType(StrEnum):
    PHONE = "phone"
    EMAIL = "email"
    ADDRESS = "address"
    PRICE = "price"
    OPENING_HOURS = "opening_hours"
    COORDINATES = "coordinates"
    POLICY = "policy"


@runtime_checkable
class EvidenceChunk(Protocol):
    """Minimum chunk contract for contradiction detection."""

    @property
    def id(self) -> UUID | str: ...

    @property
    def url(self) -> str: ...

    @property
    def dom_path(self) -> str: ...

    @property
    def content(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SourceRef:
    chunk_id: str
    url: str
    dom_path: str


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    entity: str
    fact_type: FactType
    normalized_value: str
    raw_value: str
    source: SourceRef
    extraction_method: str
    comparable: bool = True


class SemanticConflictJudgment(BaseModel):
    """Internal LLM response for ambiguous semantic pairs only."""

    contradictory: bool
    severity: ContradictionSeverity | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = Field(default="", min_length=0)


_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s\-().]{8,}\d)(?!\w)")
_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b")
_PRICE_RE = re.compile(
    r"(?i)(?P<currency>₹|rs\.?|inr|\$|usd|€|eur|£|gbp)\s*"
    r"(?P<amount>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"|(?P<amount2>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<currency2>₹|rs\.?|inr|\$|usd|€|eur|£|gbp)"
)
_COORD_RE = re.compile(r"(?i)(?P<lat>-?\d{1,2}\.\d{3,})\s*[,/\s]\s*(?P<lon>-?\d{1,3}\.\d{3,})")
_HOURS_RE = re.compile(
    r"(?i)\b(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)"
    r"\b[:\s,]*"
    r"(?P<start>\d{1,2}(?::\d{2})?\s*(?:am|pm)?|\d{1,2}:\d{2})"
    r"\s*[-to\u2013\u2014]+\s*"
    r"(?P<end>\d{1,2}(?::\d{2})?\s*(?:am|pm)?|\d{1,2}:\d{2})"
)
_ADDRESS_HINT_RE = re.compile(
    r"(?i)\b(address|located at|find us at|visit us at)\b[:\s]*(?P<addr>[^\n]{8,120})"
)
_DAY_ALIASES: Mapping[str, str] = {
    "mon": "monday",
    "tue": "tuesday",
    "tues": "tuesday",
    "wed": "wednesday",
    "thu": "thursday",
    "thur": "thursday",
    "thurs": "thursday",
    "fri": "friday",
    "sat": "saturday",
    "sun": "sunday",
    "monday": "monday",
    "tuesday": "tuesday",
    "wednesday": "wednesday",
    "thursday": "thursday",
    "friday": "friday",
    "saturday": "saturday",
    "sunday": "sunday",
}
_CURRENCY_ALIASES: Mapping[str, str] = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
}

# Opposing natural-language policy cues (semantic candidates only).
_POLICY_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "pets",
        "allowed",
        re.compile(r"(?i)\b(pets?\s+allowed|dog[s]?\s+welcome|pet[s]?\s+friendly)\b"),
    ),
    (
        "pets",
        "forbidden",
        re.compile(r"(?i)\b(no\s+pets|pets?\s+not\s+(allowed|permitted)|pets?\s+prohibited)\b"),
    ),
    (
        "parking",
        "free",
        re.compile(r"(?i)\b(free\s+parking|parking\s+is\s+free|complimentary\s+parking)\b"),
    ),
    ("parking", "paid", re.compile(r"(?i)\b(paid\s+parking|parking\s+fee|parking\s+charges)\b")),
    (
        "reservations",
        "required",
        re.compile(r"(?i)\b(reservations?\s+required|booking\s+required|must\s+reserve)\b"),
    ),
    (
        "reservations",
        "walkin",
        re.compile(
            r"(?i)\b(walk[-\s]?ins?\s+welcome|no\s+reservation\s+needed|reservations?\s+not\s+required)\b"
        ),
    ),
)


def _source_from_chunk(chunk: EvidenceChunk) -> SourceRef:
    chunk_id = str(chunk.id).strip()
    if not chunk_id:
        raise ContradictionDetectionError(
            "chunk is missing id",
            reason="invalid_source",
        )
    return SourceRef(
        chunk_id=chunk_id,
        url=(chunk.url or "").strip(),
        dom_path=(chunk.dom_path or "").strip() or "(unknown)",
    )


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_phone(raw: str) -> str | None:
    """
    Canonical phone form for comparison.

    Indian mobiles are normalized to ``+91`` + 10-digit national number so that
    ``9876543210``, ``919876543210``, and ``+91 98765 43210`` compare equal.
    """
    digits = re.sub(r"\D+", "", raw)
    if len(digits) < 10:
        return None

    # Strip trunk prefix 0 from 11-digit local dialing forms.
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    # Indian country code + 10-digit national number.
    if len(digits) == 12 and digits.startswith("91"):
        national = digits[2:]
        if national[0] in "6789":
            return f"+91{national}"
        return f"+{digits}"

    # Bare 10-digit Indian mobile (starts with 6-9).
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91{digits}"

    if len(digits) > 10:
        return f"+{digits}"
    return digits


def normalize_email(raw: str) -> str:
    return raw.strip().casefold()


def normalize_address(raw: str) -> str:
    cleaned = _normalize_whitespace(raw)
    cleaned = re.sub(r"[|]+", ",", cleaned)
    cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
    cleaned = re.sub(r"[.]{2,}", ".", cleaned)
    cleaned = cleaned.casefold().rstrip(" ,.")
    # Light abbreviation normalization (does not strip meaningful place names).
    cleaned = re.sub(r"\bstreet\b", "st", cleaned)
    cleaned = re.sub(r"\broad\b", "rd", cleaned)
    cleaned = re.sub(r"\bavenue\b", "ave", cleaned)
    cleaned = re.sub(r"\bbangalore\b", "bengaluru", cleaned)
    return _normalize_whitespace(cleaned)


def addresses_are_compatible(left: str, right: str) -> bool:
    """
    Conservative address equivalence.

    Returns True when values should NOT be reported as HARD_CONTRADICTION
    (identical, formatting-only, or incomplete vs more-complete).
    """
    a = normalize_address(left)
    b = normalize_address(right)
    if not a or not b:
        return True
    if a == b:
        return True
    # Incomplete vs extended: one normalized string contains the other.
    if a in b or b in a:
        return True

    tokens_a = set(re.findall(r"[a-z0-9]+", a))
    tokens_b = set(re.findall(r"[a-z0-9]+", b))
    if not tokens_a or not tokens_b:
        return True

    shorter, longer = (
        (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    )
    overlap = len(shorter & longer) / len(shorter)
    # High containment of the shorter token set ⇒ treat as compatible refinement.
    if overlap >= 0.8:
        return True
    return False


def _parse_amount(amount: str) -> Decimal | None:
    try:
        return Decimal(amount.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def normalize_price(currency_raw: str, amount_raw: str) -> tuple[str, str] | None:
    currency = _CURRENCY_ALIASES.get(currency_raw.strip().casefold().rstrip("."))
    if currency is None:
        currency = _CURRENCY_ALIASES.get(currency_raw.strip())
    if currency is None:
        return None
    amount = _parse_amount(amount_raw)
    if amount is None:
        return None
    quantized = format(amount.normalize(), "f")
    if "." in quantized:
        quantized = quantized.rstrip("0").rstrip(".")
    return currency, quantized


def _parse_clock_to_minutes(token: str, *, inherit_meridiem: str | None = None) -> int | None:
    cleaned = token.strip().casefold().replace(".", "")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", cleaned)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3) or inherit_meridiem
    if meridiem:
        if hour == 12:
            hour = 0
        if meridiem == "pm":
            hour += 12
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def normalize_hours_interval(day_raw: str, start_raw: str, end_raw: str) -> str | None:
    day = _DAY_ALIASES.get(day_raw.strip().casefold())
    if day is None:
        return None
    end_meridiem_match = re.search(r"(?i)\b(am|pm)\b", end_raw)
    inherit = end_meridiem_match.group(1).casefold() if end_meridiem_match else None
    start = _parse_clock_to_minutes(start_raw, inherit_meridiem=inherit)
    end = _parse_clock_to_minutes(end_raw)
    if start is None or end is None:
        return None
    return f"{day}:{start:04d}-{end:04d}"


def normalize_coordinates(lat: str, lon: str) -> str | None:
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except ValueError:
        return None
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return None
    # 5 decimal places ≈ 1.1m; avoids false positives from harmless precision noise.
    return f"{lat_f:.5f},{lon_f:.5f}"


def _price_entity_hint(content: str, match_start: int) -> str:
    window = content[max(0, match_start - 48) : match_start]
    window = _normalize_whitespace(window)
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-']{2,}", window)
    if not tokens:
        return "price:unspecified"
    # Prefer nearby noun-ish tokens; skip filler.
    skip = {"the", "and", "for", "only", "just", "from", "with", "our", "price", "cost"}
    meaningful = [t for t in tokens if t.casefold() not in skip]
    label = meaningful[-1] if meaningful else tokens[-1]
    return f"price:{label.casefold()}"


def _phone_entity_hint(content: str, match_start: int) -> str:
    window = content[max(0, match_start - 40) : match_start + 40].casefold()
    if "reservation" in window or "booking" in window:
        return "phone:reservations"
    if "support" in window or "helpdesk" in window:
        return "phone:support"
    if "billing" in window or "invoice" in window:
        return "phone:billing"
    if "primary" in window or "main" in window or "contact" in window:
        return "phone:primary"
    return "phone:primary"


def _email_entity_hint(content: str, match_start: int, email: str) -> str:
    window = content[max(0, match_start - 40) : match_start + 40].casefold()
    local = email.split("@", 1)[0].casefold()
    if (
        "reservation" in window
        or "booking" in window
        or local.startswith(("reserv", "booking", "bookings"))
    ):
        return "email:reservations"
    if "support" in window or "helpdesk" in window or local.startswith(("support", "help")):
        return "email:support"
    if (
        "billing" in window
        or "invoice" in window
        or local.startswith(("billing", "accounts", "invoice"))
    ):
        return "email:billing"
    if "primary" in window or "main" in window or "contact" in window:
        return "email:primary"
    if local.startswith(("info", "contact", "hello", "hi")):
        return "email:primary"
    return "email:primary"


def extract_facts_from_chunk(chunk: EvidenceChunk) -> list[ExtractedFact]:
    source = _source_from_chunk(chunk)
    content = chunk.content or ""
    facts: list[ExtractedFact] = []

    for match in _PHONE_RE.finditer(content):
        raw = match.group(0)
        normalized = normalize_phone(raw)
        if normalized is None:
            continue
        facts.append(
            ExtractedFact(
                entity=_phone_entity_hint(content, match.start()),
                fact_type=FactType.PHONE,
                normalized_value=normalized,
                raw_value=_normalize_whitespace(raw),
                source=source,
                extraction_method="regex_phone",
            )
        )

    for match in _EMAIL_RE.finditer(content):
        raw = match.group(0)
        facts.append(
            ExtractedFact(
                entity=_email_entity_hint(content, match.start(), raw),
                fact_type=FactType.EMAIL,
                normalized_value=normalize_email(raw),
                raw_value=raw.strip(),
                source=source,
                extraction_method="regex_email",
            )
        )

    for match in _PRICE_RE.finditer(content):
        currency = match.group("currency") or match.group("currency2")
        amount = match.group("amount") or match.group("amount2")
        if not currency or not amount:
            continue
        price_norm = normalize_price(currency, amount)
        if price_norm is None:
            continue
        currency_code, amount_norm = price_norm
        facts.append(
            ExtractedFact(
                entity=_price_entity_hint(content, match.start()),
                fact_type=FactType.PRICE,
                normalized_value=f"{currency_code}:{amount_norm}",
                raw_value=_normalize_whitespace(match.group(0)),
                source=source,
                extraction_method="regex_price",
            )
        )

    for match in _HOURS_RE.finditer(content):
        hours_norm = normalize_hours_interval(
            match.group("day"),
            match.group("start"),
            match.group("end"),
        )
        if hours_norm is None:
            continue
        day = hours_norm.split(":", 1)[0]
        facts.append(
            ExtractedFact(
                entity=f"opening_hours:{day}",
                fact_type=FactType.OPENING_HOURS,
                normalized_value=hours_norm,
                raw_value=_normalize_whitespace(match.group(0)),
                source=source,
                extraction_method="regex_hours",
            )
        )

    for match in _COORD_RE.finditer(content):
        coord_norm = normalize_coordinates(match.group("lat"), match.group("lon"))
        if coord_norm is None:
            continue
        facts.append(
            ExtractedFact(
                entity="coordinates:location",
                fact_type=FactType.COORDINATES,
                normalized_value=coord_norm,
                raw_value=_normalize_whitespace(match.group(0)),
                source=source,
                extraction_method="regex_coordinates",
            )
        )

    for match in _ADDRESS_HINT_RE.finditer(content):
        raw = match.group("addr")
        facts.append(
            ExtractedFact(
                entity="address:primary",
                fact_type=FactType.ADDRESS,
                normalized_value=normalize_address(raw),
                raw_value=_normalize_whitespace(raw),
                source=source,
                extraction_method="regex_address",
                comparable=True,
            )
        )

    for topic, stance, pattern in _POLICY_PATTERNS:
        for match in pattern.finditer(content):
            facts.append(
                ExtractedFact(
                    entity=f"policy:{topic}",
                    fact_type=FactType.POLICY,
                    normalized_value=stance,
                    raw_value=_normalize_whitespace(match.group(0)),
                    source=source,
                    extraction_method="regex_policy_cue",
                    comparable=False,  # semantic path only
                )
            )

    return facts


def extract_facts(chunks: Sequence[EvidenceChunk]) -> list[ExtractedFact]:
    if not isinstance(chunks, Sequence):
        raise ContradictionDetectionError(
            "chunks must be a sequence",
            reason="invalid_input",
        )
    facts: list[ExtractedFact] = []
    seen_chunk_ids: set[str] = set()
    for chunk in chunks:
        source = _source_from_chunk(chunk)
        if source.chunk_id in seen_chunk_ids:
            # Same chunk twice: still extract once for stability.
            continue
        seen_chunk_ids.add(source.chunk_id)
        facts.extend(extract_facts_from_chunk(chunk))
    return facts


def _pair_key(a: ExtractedFact, b: ExtractedFact) -> tuple[str, str]:
    left, right = sorted(
        (a.source.chunk_id, b.source.chunk_id),
    )
    return left, right


def find_deterministic_conflicts(facts: Sequence[ExtractedFact]) -> list[Contradiction]:
    by_entity: dict[str, list[ExtractedFact]] = defaultdict(list)
    for fact in facts:
        if fact.comparable and fact.fact_type != FactType.POLICY:
            by_entity[fact.entity].append(fact)

    results: list[Contradiction] = []
    for entity, group in sorted(by_entity.items()):
        # Unique normalized values per chunk (keep first raw/source).
        by_chunk_value: dict[tuple[str, str], ExtractedFact] = {}
        for fact in group:
            key = (fact.source.chunk_id, fact.normalized_value)
            by_chunk_value.setdefault(key, fact)

        unique_facts = list(by_chunk_value.values())
        for i, left in enumerate(unique_facts):
            for right in unique_facts[i + 1 :]:
                if left.source.chunk_id == right.source.chunk_id:
                    continue
                if left.normalized_value == right.normalized_value:
                    continue
                # Different currencies for prices are not merged / not equalized.
                if left.fact_type is FactType.PRICE and right.fact_type is FactType.PRICE:
                    left_cur = left.normalized_value.split(":", 1)[0]
                    right_cur = right.normalized_value.split(":", 1)[0]
                    if left_cur != right_cur:
                        continue
                if left.fact_type is FactType.ADDRESS and right.fact_type is FactType.ADDRESS:
                    # Conservative: formatting / incomplete-vs-complete are not HARD.
                    if addresses_are_compatible(left.normalized_value, right.normalized_value):
                        continue
                results.append(
                    _build_contradiction(
                        entity=entity,
                        left=left,
                        right=right,
                        severity=ContradictionSeverity.HARD_CONTRADICTION,
                        conflict=(
                            f"Conflicting {left.fact_type.value} for {entity}: "
                            f"{left.raw_value!r} vs {right.raw_value!r}"
                        ),
                    )
                )
    return results


def find_semantic_candidate_pairs(
    facts: Sequence[ExtractedFact],
) -> list[tuple[ExtractedFact, ExtractedFact]]:
    by_entity: dict[str, list[ExtractedFact]] = defaultdict(list)
    for fact in facts:
        if fact.fact_type is FactType.POLICY:
            by_entity[fact.entity].append(fact)

    pairs: list[tuple[ExtractedFact, ExtractedFact]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for entity, group in sorted(by_entity.items()):
        for i, left in enumerate(group):
            for right in group[i + 1 :]:
                if left.source.chunk_id == right.source.chunk_id:
                    continue
                if left.normalized_value == right.normalized_value:
                    continue
                chunk_a, chunk_b = sorted((left.source.chunk_id, right.source.chunk_id))
                value_a, value_b = sorted((left.normalized_value, right.normalized_value))
                key = (entity, chunk_a, chunk_b, value_a, value_b)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append((left, right))
    return pairs


def _build_contradiction(
    *,
    entity: str,
    left: ExtractedFact,
    right: ExtractedFact,
    severity: ContradictionSeverity,
    conflict: str,
) -> Contradiction:
    # Stable source ordering by chunk_id for deterministic output.
    first, second = (left, right)
    if right.source.chunk_id < left.source.chunk_id:
        first, second = right, left

    values = [
        {
            "value": first.normalized_value,
            "raw": first.raw_value,
            "chunk_id": first.source.chunk_id,
        },
        {
            "value": second.normalized_value,
            "raw": second.raw_value,
            "chunk_id": second.source.chunk_id,
        },
    ]
    contradiction_id = hashlib.sha1(
        f"{severity.value}|{entity}|{first.normalized_value}|{second.normalized_value}|"
        f"{first.source.chunk_id}|{second.source.chunk_id}".encode()
    ).hexdigest()[:16]

    return Contradiction(
        entity=entity,
        conflict=conflict,
        values=values,
        severity=severity,
        source_urls=[u for u in (first.source.url, second.source.url) if u],
        dom_paths=[first.source.dom_path, second.source.dom_path],
        contradiction_id=contradiction_id,
    )


def validate_contradiction(
    item: Contradiction,
    *,
    chunk_ids: set[str],
) -> Contradiction:
    if not isinstance(item, Contradiction):
        raise ContradictionDetectionError(
            f"Expected Contradiction, got {type(item).__name__}",
            reason="invalid_llm_output",
        )
    if not isinstance(item.severity, ContradictionSeverity):
        raise ContradictionDetectionError(
            f"Invalid severity: {item.severity!r}",
            reason="invalid_llm_output",
        )
    if not item.entity.strip():
        raise ContradictionDetectionError("entity must be non-empty", reason="invalid_llm_output")
    if not item.conflict.strip():
        raise ContradictionDetectionError("conflict must be non-empty", reason="invalid_llm_output")
    if len(item.values) < 2:
        raise ContradictionDetectionError(
            "values must contain at least two entries",
            reason="invalid_llm_output",
        )

    cited: list[str] = []
    for entry in item.values:
        if not isinstance(entry, dict):
            raise ContradictionDetectionError(
                "values entries must be objects with chunk_id",
                reason="invalid_source_reference",
            )
        chunk_id = str(entry.get("chunk_id", "")).strip()
        if not chunk_id:
            raise ContradictionDetectionError(
                "values entry missing chunk_id",
                reason="invalid_source_reference",
            )
        if chunk_id not in chunk_ids:
            raise ContradictionDetectionError(
                f"Unknown chunk_id in contradiction: {chunk_id}",
                reason="invalid_source_reference",
            )
        cited.append(chunk_id)

    if len(set(cited)) < 2:
        raise ContradictionDetectionError(
            "Contradiction must cite two distinct source chunks",
            reason="invalid_source_reference",
        )

    if item.severity is ContradictionSeverity.HARD_CONTRADICTION:
        norms = [str(v.get("value", "")).strip() for v in item.values[:2]]
        if len(norms) >= 2 and norms[0] == norms[1]:
            raise ContradictionDetectionError(
                "HARD_CONTRADICTION requires different normalized values",
                reason="invalid_llm_output",
            )

    return item


def dedupe_contradictions(items: Sequence[Contradiction]) -> list[Contradiction]:
    seen: set[str] = set()
    ordered: list[Contradiction] = []
    for item in items:
        key = (
            item.contradiction_id
            or hashlib.sha1(
                f"{item.severity.value}|{item.entity}|{item.values!r}".encode()
            ).hexdigest()
        )
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    ordered.sort(key=lambda c: (c.severity.value, c.entity, c.contradiction_id or ""))
    return ordered


class ContradictionDetector:
    """Hybrid contradiction detector over caller-provided evidence chunks."""

    def __init__(self, *, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client or LLMClient()

    @property
    def llm_client(self) -> LLMClient:
        return self._llm

    async def _classify_semantic_pair(
        self,
        left: ExtractedFact,
        right: ExtractedFact,
        *,
        chunk_map: Mapping[str, SourceRef],
    ) -> Contradiction | None:
        user_prompt = (
            f"ENTITY: {left.entity}\n\n"
            f"STATEMENT A (chunk_id={left.source.chunk_id}):\n{left.raw_value}\n\n"
            f"STATEMENT B (chunk_id={right.source.chunk_id}):\n{right.raw_value}\n"
        )
        try:
            judgment = await self._llm.create(
                SemanticConflictJudgment,
                messages=[
                    {"role": "system", "content": SEMANTIC_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_retries=1,
                max_tokens=600,
            )
        except BudgetExhausted:
            raise
        except Exception as exc:
            raise ContradictionDetectionError(
                f"Semantic classification failed: {exc}",
                reason="semantic_classification_failure",
            ) from exc

        if not isinstance(judgment, SemanticConflictJudgment):
            raise ContradictionDetectionError(
                "Invalid semantic judgment type",
                reason="invalid_llm_output",
            )
        if not judgment.contradictory:
            return None
        if judgment.severity is None:
            raise ContradictionDetectionError(
                "contradictory judgment missing severity",
                reason="invalid_llm_output",
            )
        # Conservative: never let the model escalate beyond SOFT unless it chose HARD
        # with explicit incompatible stances we already flagged as opposing cues.
        severity = judgment.severity
        if severity is ContradictionSeverity.HARD_CONTRADICTION:
            # Policy cues stay HARD only for direct antonym stance pairs.
            antonyms = {
                frozenset({"allowed", "forbidden"}),
                frozenset({"free", "paid"}),
                frozenset({"required", "walkin"}),
            }
            stance_pair = frozenset({left.normalized_value, right.normalized_value})
            if stance_pair not in antonyms:
                severity = ContradictionSeverity.SOFT_INCONSISTENCY

        # Rebuild provenance exclusively from original sources — ignore any LLM metadata.
        src_left = chunk_map[left.source.chunk_id]
        src_right = chunk_map[right.source.chunk_id]
        rebuilt_left = ExtractedFact(
            entity=left.entity,
            fact_type=left.fact_type,
            normalized_value=left.normalized_value,
            raw_value=left.raw_value,
            source=src_left,
            extraction_method=left.extraction_method,
            comparable=False,
        )
        rebuilt_right = ExtractedFact(
            entity=right.entity,
            fact_type=right.fact_type,
            normalized_value=right.normalized_value,
            raw_value=right.raw_value,
            source=src_right,
            extraction_method=right.extraction_method,
            comparable=False,
        )
        rationale = (
            judgment.rationale or ""
        ).strip() or "Semantic inconsistency in source statements."
        return _build_contradiction(
            entity=left.entity,
            left=rebuilt_left,
            right=rebuilt_right,
            severity=severity,
            conflict=rationale,
        )

    async def detect_contradictions(
        self,
        *,
        chunks: Sequence[EvidenceChunk],
    ) -> list[Contradiction]:
        started = time.perf_counter()
        if chunks is None:
            raise ContradictionDetectionError("chunks is required", reason="invalid_input")

        chunk_map: dict[str, SourceRef] = {}
        for chunk in chunks:
            ref = _source_from_chunk(chunk)
            chunk_map[ref.chunk_id] = ref

        facts = extract_facts(chunks)
        deterministic = find_deterministic_conflicts(facts)
        semantic_pairs = find_semantic_candidate_pairs(facts)
        cap = max(0, int(settings.MAX_SEMANTIC_CONTRADICTION_CALLS))
        if cap == 0:
            semantic_pairs = []
        elif len(semantic_pairs) > cap:
            logger.info(
                "semantic_pairs_capped from=%s to=%s",
                len(semantic_pairs),
                cap,
            )
            semantic_pairs = semantic_pairs[:cap]

        logger.info(
            "Contradiction detection start chunks=%s facts=%s deterministic_candidates=%s "
            "semantic_candidates=%s cap=%s",
            len(chunk_map),
            len(facts),
            len(deterministic),
            len(semantic_pairs),
            cap,
        )

        semantic_results: list[Contradiction] = []
        if semantic_pairs:
            sem = asyncio.Semaphore(3)

            async def _classify_with_sem(
                left: ExtractedFact, right: ExtractedFact
            ) -> Contradiction | None:
                async with sem:
                    return await self._classify_semantic_pair(left, right, chunk_map=chunk_map)

            tasks = [_classify_with_sem(left, right) for left, right in semantic_pairs]
            judged = await asyncio.gather(*tasks)
            semantic_results = [item for item in judged if item is not None]

        merged = deterministic + semantic_results
        validated = [validate_contradiction(item, chunk_ids=set(chunk_map)) for item in merged]
        final = dedupe_contradictions(validated)

        hard = sum(1 for c in final if c.severity is ContradictionSeverity.HARD_CONTRADICTION)
        soft = sum(1 for c in final if c.severity is ContradictionSeverity.SOFT_INCONSISTENCY)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Contradiction detection complete contradictions=%s hard=%s soft=%s "
            "llm_calls=%s elapsed_ms=%s",
            len(final),
            hard,
            soft,
            self._llm.calls_made,
            elapsed_ms,
        )
        return final


async def detect_contradictions(
    *,
    chunks: Sequence[EvidenceChunk],
    llm_client: LLMClient | None = None,
) -> list[Contradiction]:
    detector = ContradictionDetector(llm_client=llm_client)
    return await detector.detect_contradictions(chunks=chunks)
