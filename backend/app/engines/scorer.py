"""Deterministic Findability F-score calculator + Schema.org JSON-LD checker.

Phase E (P2-2.6 / P2-2.7). No LLM, network, or database access.

Architecture:
    intent evaluations + contradictions + HTML + DOM chunks
        → S_ans / S_con / S_str / S_acc
        → configurable weighted F
        → ScoreBreakdown (+ SchemaOrgReport)

Production weighting is configuration-driven pending team confirmation of the
canonical F-score specification (docs vs README conflict).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from bs4 import BeautifulSoup

from app.engines.contradiction import extract_facts
from app.schemas.intelligence import (
    Contradiction,
    ContradictionSeverity,
    EntailmentStatus,
    IntentEvaluation,
)
from app.schemas.scoring import (
    WEIGHT_SUM_TOLERANCE,
    ContradictionSeverityWeights,
    SchemaOrgReport,
    SchemaTypeResult,
    ScoreBreakdown,
    ScoreWeights,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TEAM DECISION REQUIRED
# ---------------------------------------------------------------------------
# Option A (docs/01, docs/04 — provisional default in ScoreWeights):
#   F = 0.40*S_ans + 0.30*S_con + 0.20*S_str + 0.10*S_acc
# Option B (README.md alternative formulation — NOT used as default):
#   F-Score = 100 * (0.40*S_coverage + 0.35*S_entailment
#                    - 0.15*S_contradiction + 0.10*S_structure)
# Change only ScoreWeights / provisional_score_weights() after confirmation.
# ---------------------------------------------------------------------------

REQUIRED_SCHEMA_TYPES: tuple[str, ...] = (
    "LocalBusiness",
    "PostalAddress",
    "OpeningHoursSpecification",
    "GeoCoordinates",
    "Menu",
    "FAQPage",
)

# LocalBusiness may appear as a more specific subtype (architecture note).
LOCAL_BUSINESS_SUBTYPES: frozenset[str] = frozenset(
    {
        "LocalBusiness",
        "Restaurant",
        "FoodEstablishment",
        "CafeOrCoffeeShop",
        "Bakery",
        "BarOrPub",
        "Store",
        "EntertainmentBusiness",
        "HealthAndBeautyBusiness",
        "HomeAndConstructionBusiness",
        "LodgingBusiness",
        "MedicalBusiness",
        "ProfessionalService",
        "SportsActivityLocation",
    }
)

ANSWERABILITY_CONTRIBUTION: Mapping[EntailmentStatus, float] = {
    EntailmentStatus.SUPPORTED: 100.0,
    EntailmentStatus.PARTIALLY_SUPPORTED: 50.0,
    EntailmentStatus.CONTRADICTED: 0.0,
    EntailmentStatus.UNKNOWN: 0.0,
}

CRITICAL_FIELD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("phone", re.compile(r"(?:\+?\d[\d\s\-().]{8,}\d)")),
    ("email", re.compile(r"(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b")),
    (
        "hours",
        re.compile(
            r"(?i)\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
            r"open|hours|am|pm)\b"
        ),
    ),
    (
        "address",
        re.compile(r"(?i)\b(address|street|road|avenue|suite|city|zip|postal)\b"),
    ),
    ("price", re.compile(r"(?i)(₹|rs\.?|\$|€|£|\bprice\b|\bcost\b)")),
    ("name", re.compile(r"(?i)\b(welcome|restaurant|bistro|cafe|clinic|hotel)\b")),
)

HEADING_TAGS: frozenset[str] = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


class ScorerError(Exception):
    """Raised when scorer inputs violate contracts (not for optional JSON-LD issues)."""

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "scorer_error"
        super().__init__(message)


@runtime_checkable
class TextChunk(Protocol):
    content: str
    tag: str
    word_count: int


@dataclass(frozen=True, slots=True)
class ScoreInputs:
    """All data required for a deterministic score pass (no I/O inside Scorer)."""

    intent_evaluations: Sequence[IntentEvaluation] = ()
    contradictions: Sequence[Contradiction] = ()
    html_documents: Sequence[str] = ()
    chunks: Sequence[TextChunk] = ()
    extracted_fact_count: int | None = None
    weights: ScoreWeights | None = None
    contradiction_severity_weights: ContradictionSeverityWeights | None = None


def provisional_score_weights() -> ScoreWeights:
    """Provisional defaults aligned with docs/01 & docs/04 (pending team confirmation)."""
    return ScoreWeights()


def validate_component_score(name: str, value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ScorerError(f"{name} must be numeric", reason="invalid_component_score")
    score = float(value)
    if score < 0.0 or score > 100.0:
        raise ScorerError(
            f"{name} must be in [0, 100]; got {score}",
            reason="invalid_component_score",
        )
    return score


def calculate_f_score(
    *,
    s_ans: float,
    s_con: float,
    s_str: float,
    s_acc: float,
    weights: ScoreWeights | None = None,
) -> float:
    """Weighted aggregation F = Σ w_i * S_i with validated components and weights."""
    w = weights or provisional_score_weights()
    # Re-validate sum in case caller constructed ScoreWeights incorrectly via model_construct.
    total_w = w.w_ans + w.w_con + w.w_str + w.w_acc
    if abs(total_w - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ScorerError(
            f"weights must sum to 1.0; got {total_w}",
            reason="invalid_weights",
        )
    if min(w.w_ans, w.w_con, w.w_str, w.w_acc) < 0.0:
        raise ScorerError("weights must be non-negative", reason="invalid_weights")

    ans = validate_component_score("s_ans", s_ans)
    con = validate_component_score("s_con", s_con)
    structure = validate_component_score("s_str", s_str)
    acc = validate_component_score("s_acc", s_acc)

    f_score = w.w_ans * ans + w.w_con * con + w.w_str * structure + w.w_acc * acc
    if f_score < -WEIGHT_SUM_TOLERANCE or f_score > 100.0 + WEIGHT_SUM_TOLERANCE:
        raise ScorerError(
            f"computed F out of bounds: {f_score}",
            reason="invalid_f_score",
        )
    return max(0.0, min(100.0, f_score))


def calculate_answerability(
    evaluations: Sequence[IntentEvaluation],
) -> tuple[float, dict[str, Any]]:
    """
    S_ans: mean contribution of entailment statuses (0-100).

    SUPPORTED=100, PARTIALLY_SUPPORTED=50, CONTRADICTED=0, UNKNOWN=0.
    Empty list -> 0.0 (no evidence of answerability).
    Malformed optional entries are skipped with a diagnostic count.
    """
    contributions: list[float] = []
    skipped = 0
    status_counts: dict[str, int] = {s.value: 0 for s in EntailmentStatus}

    for item in evaluations:
        if not isinstance(item, IntentEvaluation):
            skipped += 1
            continue
        if not isinstance(item.status, EntailmentStatus):
            skipped += 1
            continue
        status_counts[item.status.value] += 1
        contributions.append(ANSWERABILITY_CONTRIBUTION[item.status])

    if not contributions:
        return 0.0, {
            "evaluated": 0,
            "skipped_malformed": skipped,
            "status_counts": status_counts,
            "rule": "mean(SUPPORTED=100, PARTIAL=50, CONTRADICTED=0, UNKNOWN=0)",
        }

    score = sum(contributions) / len(contributions)
    return score, {
        "evaluated": len(contributions),
        "skipped_malformed": skipped,
        "status_counts": status_counts,
        "rule": "mean(SUPPORTED=100, PARTIAL=50, CONTRADICTED=0, UNKNOWN=0)",
    }


def _contradiction_impact(
    contradictions: Sequence[Contradiction],
    *,
    severity_weights: ContradictionSeverityWeights,
) -> float:
    impact = 0.0
    for item in contradictions:
        if not isinstance(item, Contradiction):
            continue
        if item.severity is ContradictionSeverity.HARD_CONTRADICTION:
            impact += severity_weights.hard
        elif item.severity is ContradictionSeverity.SOFT_INCONSISTENCY:
            impact += severity_weights.soft
    return impact


def calculate_consistency(
    contradictions: Sequence[Contradiction],
    *,
    fact_count: int,
    severity_weights: ContradictionSeverityWeights | None = None,
) -> tuple[float, dict[str, Any]]:
    """
    S_con = 100 * (1 - normalized_impact).

    normalized_impact = min(1, weighted_contradictions / max(fact_count, 1))

    Architecture reference: (1 - contradictions/entities) x 100, extended with
    configurable HARD/SOFT severity weights (defaults hard=1.0, soft=0.5).
    """
    weights = severity_weights or ContradictionSeverityWeights()
    unique = _dedupe_contradictions(contradictions)
    if not unique:
        return 100.0, {
            "contradictions": 0,
            "fact_count": max(fact_count, 0),
            "impact": 0.0,
            "severity_weights": weights.model_dump(),
        }

    denominator = max(int(fact_count), 1)
    raw_impact = _contradiction_impact(unique, severity_weights=weights)
    normalized = min(1.0, raw_impact / float(denominator))
    score = 100.0 * (1.0 - normalized)
    hard = sum(1 for c in unique if c.severity is ContradictionSeverity.HARD_CONTRADICTION)
    soft = sum(1 for c in unique if c.severity is ContradictionSeverity.SOFT_INCONSISTENCY)
    return score, {
        "contradictions": len(unique),
        "hard": hard,
        "soft": soft,
        "fact_count": denominator,
        "raw_impact": raw_impact,
        "normalized_impact": normalized,
        "severity_weights": weights.model_dump(),
        "rule": "100*(1-min(1, weighted_contradictions/max(facts,1)))",
    }


def _dedupe_contradictions(
    contradictions: Sequence[Contradiction],
) -> list[Contradiction]:
    seen: set[str] = set()
    ordered: list[Contradiction] = []
    for item in contradictions:
        if not isinstance(item, Contradiction):
            continue
        key = item.contradiction_id or f"{item.severity.value}|{item.entity}|{item.values!r}"
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    ordered.sort(key=lambda c: (c.severity.value, c.entity, c.contradiction_id or ""))
    return ordered


def _as_type_list(type_value: Any) -> list[str]:
    if type_value is None:
        return []
    if isinstance(type_value, str):
        return [type_value.split("/")[-1]]
    if isinstance(type_value, list):
        names: list[str] = []
        for item in type_value:
            names.extend(_as_type_list(item))
        return names
    return []


def _iter_jsonld_nodes(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_jsonld_nodes(item)
        return
    if not isinstance(payload, dict):
        return
    yield payload
    graph = payload.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _iter_jsonld_nodes(item)
    for key, value in payload.items():
        if key in {"@graph", "@context"}:
            continue
        if isinstance(value, (dict, list)):
            yield from _iter_jsonld_nodes(value)


def _matches_required_type(
    node_types: Sequence[str],
    required: str,
    *,
    node: Mapping[str, Any] | None = None,
) -> bool:
    names = set(node_types)
    if required == "LocalBusiness":
        return bool(names & LOCAL_BUSINESS_SUBTYPES) or any(n.endswith("Business") for n in names)
    if required == "Menu":
        if "Menu" in names or "MenuSection" in names:
            return True
        return bool(node is not None and node.get("hasMenu") is not None)
    return required in names


def _validate_schema_node(required: str, node: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    types = _as_type_list(node.get("@type"))
    if not types and not (required == "Menu" and node.get("hasMenu") is not None):
        issues.append("MISSING_TYPE")
        return issues

    if required == "LocalBusiness":
        if "name" not in node and "legalName" not in node:
            issues.append("MISSING_REQUIRED_STRUCTURE:name")
        has_locationish = any(key in node for key in ("address", "location", "geo", "telephone"))
        if not has_locationish:
            issues.append("MISSING_REQUIRED_STRUCTURE:location_or_contact")
    elif required == "PostalAddress":
        if not any(
            key in node
            for key in ("streetAddress", "addressLocality", "postalCode", "addressCountry")
        ):
            issues.append("MISSING_REQUIRED_STRUCTURE:address_fields")
    elif required == "OpeningHoursSpecification":
        if not any(
            key in node
            for key in ("opens", "closes", "dayOfWeek", "openingHours", "openingHoursSpecification")
        ):
            issues.append("MISSING_REQUIRED_STRUCTURE:hours_fields")
    elif required == "GeoCoordinates":
        if "latitude" not in node:
            issues.append("MISSING_LATITUDE")
        if "longitude" not in node:
            issues.append("MISSING_LONGITUDE")
    elif required == "Menu":
        if node.get("hasMenu") is not None:
            return []
        if not any(key in node for key in ("hasMenuItem", "hasMenuSection", "name", "url")):
            issues.append("MISSING_REQUIRED_STRUCTURE:menu_fields")
    elif required == "FAQPage":
        main_entity = node.get("mainEntity")
        if main_entity is None:
            issues.append("MISSING_MAIN_ENTITY")
        elif isinstance(main_entity, list) and not main_entity:
            issues.append("MISSING_MAIN_ENTITY")
    return issues


def analyze_schema_org(html_documents: Sequence[str]) -> SchemaOrgReport:
    """
    Parse untrusted JSON-LD from HTML documents (BeautifulSoup + json.loads).

    Malformed blocks are recorded; they do not raise.
    ``valid_blocks`` counts only parsed blocks that contain at least one node
    with a Schema.org ``@type`` (or Menu via ``hasMenu``). Plain JSON objects
    without schema types are ``invalid_blocks``.
    """
    total_blocks = 0
    valid_blocks = 0
    invalid_blocks = 0
    malformed_blocks = 0
    global_issues: list[str] = []

    found_nodes: dict[str, list[dict[str, Any]]] = {t: [] for t in REQUIRED_SCHEMA_TYPES}
    type_issues: dict[str, list[str]] = {t: [] for t in REQUIRED_SCHEMA_TYPES}
    type_source_docs: dict[str, set[int]] = {t: set() for t in REQUIRED_SCHEMA_TYPES}

    for doc_index, html in enumerate(html_documents):
        if not html or not str(html).strip():
            continue
        soup = BeautifulSoup(str(html), "lxml")
        scripts = soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)})
        for script in scripts:
            total_blocks += 1
            raw = script.string if script.string is not None else script.get_text()
            if raw is None or not str(raw).strip():
                malformed_blocks += 1
                global_issues.append("INVALID_JSON:empty_block")
                continue
            try:
                payload = json.loads(str(raw))
            except json.JSONDecodeError:
                malformed_blocks += 1
                global_issues.append("INVALID_JSON")
                continue

            block_has_schema_type = False
            for node in _iter_jsonld_nodes(payload):
                if not isinstance(node, dict):
                    continue
                node_types = _as_type_list(node.get("@type"))
                if node_types or node.get("hasMenu") is not None:
                    block_has_schema_type = True
                for required in REQUIRED_SCHEMA_TYPES:
                    matched = _matches_required_type(node_types, required, node=node)
                    if not matched:
                        continue
                    issues = _validate_schema_node(required, node)
                    found_nodes[required].append(node)
                    type_source_docs[required].add(doc_index)
                    if issues:
                        type_issues[required].extend(issues)
            if block_has_schema_type:
                valid_blocks += 1
            else:
                invalid_blocks += 1
                global_issues.append("INVALID_TYPE:no_schema_entities")

    type_results: list[SchemaTypeResult] = []
    present_valid = 0
    for required in REQUIRED_SCHEMA_TYPES:
        nodes = found_nodes[required]
        present = len(nodes) > 0
        issues = sorted(set(type_issues[required]))
        valid = False
        if present:
            for node in nodes:
                node_issues = _validate_schema_node(required, node)
                if not node_issues:
                    valid = True
                    break
            if not valid and present and not issues:
                valid = True
        if present and valid:
            present_valid += 1
        type_results.append(
            SchemaTypeResult(
                schema_type=required,
                present=present,
                valid=valid,
                occurrences=len(nodes),
                source_count=len(type_source_docs[required]),
                issues=issues,
            )
        )

    score = 100.0 * (present_valid / float(len(REQUIRED_SCHEMA_TYPES)))

    return SchemaOrgReport(
        total_blocks=total_blocks,
        valid_blocks=valid_blocks,
        invalid_blocks=invalid_blocks,
        malformed_blocks=malformed_blocks,
        required_types=list(REQUIRED_SCHEMA_TYPES),
        types=type_results,
        score=score,
        issues=sorted(set(global_issues)),
    )


def calculate_structure(schema_report: SchemaOrgReport) -> tuple[float, dict[str, Any]]:
    """S_str from equal-weight coverage of structurally valid required schema types."""
    required = len(schema_report.required_types) or len(REQUIRED_SCHEMA_TYPES)
    valid_present = sum(1 for t in schema_report.types if t.present and t.valid)
    present_any = sum(1 for t in schema_report.types if t.present)
    score = 100.0 * (valid_present / float(required))
    return score, {
        "required": required,
        "present": present_any,
        "structurally_valid": valid_present,
        "malformed_blocks": schema_report.malformed_blocks,
        "rule": "100 * (valid_required_types / 6) equal weight",
    }


def calculate_accessibility(
    chunks: Sequence[TextChunk],
) -> tuple[float, dict[str, Any]]:
    """
    S_acc: machine extractability from DOM chunks (not WCAG).

    Signals actually supported by ChunkData-like input:
    - critical field presence in concatenated text
    - share of chunks with non-empty text / positive word_count
    - heading-tagged chunk coverage
    """
    if not chunks:
        return 0.0, {
            "critical_fields_found": 0,
            "critical_fields_total": len(CRITICAL_FIELD_PATTERNS),
            "text_extractability": 0.0,
            "heading_support": 0.0,
            "chunk_count": 0,
        }

    texts: list[str] = []
    text_bearing = 0
    heading_chunks = 0
    for chunk in chunks:
        content = (getattr(chunk, "content", None) or "").strip()
        tag = (getattr(chunk, "tag", None) or "").casefold()
        word_count = int(getattr(chunk, "word_count", 0) or 0)
        if content:
            texts.append(content)
        if content and word_count > 0:
            text_bearing += 1
        elif content:
            text_bearing += 1
        if tag in HEADING_TAGS:
            heading_chunks += 1

    blob = "\n".join(texts)
    found_fields = [name for name, pattern in CRITICAL_FIELD_PATTERNS if pattern.search(blob)]
    field_ratio = len(found_fields) / float(len(CRITICAL_FIELD_PATTERNS))
    text_ratio = text_bearing / float(len(chunks))
    heading_ratio = heading_chunks / float(len(chunks))

    # Equal blend of supported signals only.
    score = 100.0 * ((field_ratio + text_ratio + heading_ratio) / 3.0)
    return score, {
        "critical_fields_found": len(found_fields),
        "critical_fields_total": len(CRITICAL_FIELD_PATTERNS),
        "fields_found": sorted(found_fields),
        "text_extractability": text_ratio,
        "heading_support": heading_ratio,
        "chunk_count": len(chunks),
        "text_bearing_chunks": text_bearing,
        "heading_chunks": heading_chunks,
        "rule": "100 * mean(field_ratio, text_ratio, heading_chunks/total_chunks)",
    }


@dataclass(frozen=True, slots=True)
class _FactCountResolution:
    fact_count: int
    source: str
    insufficient_denominator: bool
    note: str = ""


def _resolve_fact_count(inputs: ScoreInputs) -> _FactCountResolution:
    """
    Resolve the S_con denominator.

    Preference order:
    1. Explicit ``ScoreInputs.extracted_fact_count``
    2. Phase D ``extract_facts()`` when chunks expose id/url/dom_path/content
    3. Otherwise insufficient — never invent a fact count from contradiction entities
    """
    if inputs.extracted_fact_count is not None:
        if inputs.extracted_fact_count < 0:
            raise ScorerError(
                "extracted_fact_count must be >= 0",
                reason="invalid_input",
            )
        return _FactCountResolution(
            fact_count=int(inputs.extracted_fact_count),
            source="explicit",
            insufficient_denominator=False,
        )
    if inputs.chunks and all(
        hasattr(c, "id") and hasattr(c, "url") and hasattr(c, "dom_path") and hasattr(c, "content")
        for c in inputs.chunks
    ):
        facts = extract_facts(inputs.chunks)  # type: ignore[arg-type]
        return _FactCountResolution(
            fact_count=len(facts),
            source="extract_facts",
            insufficient_denominator=False,
        )
    return _FactCountResolution(
        fact_count=0,
        source="insufficient",
        insufficient_denominator=True,
        note=(
            "No extracted_fact_count and chunks lack EvidenceChunk fields; "
            "refusing contradiction-entity-count as a fact denominator."
        ),
    )


class Scorer:
    """Pure evaluation layer: supplied intelligence artifacts → ScoreBreakdown."""

    def score(self, inputs: ScoreInputs) -> ScoreBreakdown:
        weights = inputs.weights or provisional_score_weights()
        severity_weights = inputs.contradiction_severity_weights or ContradictionSeverityWeights()

        s_ans, ans_diag = calculate_answerability(inputs.intent_evaluations)
        fact_resolution = _resolve_fact_count(inputs)
        unique_contras = _dedupe_contradictions(inputs.contradictions)

        if fact_resolution.insufficient_denominator and unique_contras:
            # Conservative fallback: without a real fact denominator, do not claim
            # consistency when contradictions exist (S_con = 0).
            s_con = 0.0
            con_diag: dict[str, Any] = {
                "contradictions": len(unique_contras),
                "fact_count": 0,
                "insufficient_denominator": True,
                "fact_count_source": fact_resolution.source,
                "fallback": "s_con_0_without_fact_denominator",
                "note": fact_resolution.note,
                "severity_weights": severity_weights.model_dump(),
            }
        else:
            s_con, con_diag = calculate_consistency(
                inputs.contradictions,
                fact_count=fact_resolution.fact_count,
                severity_weights=severity_weights,
            )
            con_diag = {
                **con_diag,
                "insufficient_denominator": fact_resolution.insufficient_denominator,
                "fact_count_source": fact_resolution.source,
                "note": fact_resolution.note,
            }

        schema_report = analyze_schema_org(inputs.html_documents)
        s_str, str_diag = calculate_structure(schema_report)
        s_acc, acc_diag = calculate_accessibility(inputs.chunks)

        f_score = calculate_f_score(
            s_ans=s_ans,
            s_con=s_con,
            s_str=s_str,
            s_acc=s_acc,
            weights=weights,
        )

        diagnostics = {
            "s_ans": ans_diag,
            "s_con": con_diag,
            "s_str": str_diag,
            "s_acc": acc_diag,
            "weights_note": (
                "Production weighting remains configuration-driven pending team "
                "confirmation of the canonical F-score specification "
                "(docs Option A vs README Option B)."
            ),
        }

        logger.info(
            "Score computed f=%.4f s_ans=%.4f s_con=%.4f s_str=%.4f s_acc=%.4f",
            f_score,
            s_ans,
            s_con,
            s_str,
            s_acc,
        )

        return ScoreBreakdown(
            f_score=f_score,
            s_ans=s_ans,
            s_con=s_con,
            s_str=s_str,
            s_acc=s_acc,
            weights=weights,
            schema_report=schema_report,
            diagnostics=diagnostics,
        )


def score(inputs: ScoreInputs) -> ScoreBreakdown:
    return Scorer().score(inputs)
