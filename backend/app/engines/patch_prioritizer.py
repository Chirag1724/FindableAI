"""Deterministic Patch Prioritizer (P2-3.1).

Consumes intelligence-layer outputs and ranks the highest-value remediation
opportunities. Prioritization only — no LLM, network, database, GitHub,
JSON-LD generation, patch formatting, or projected scoring.

Pipeline::

    intent evaluations + contradictions + score/schema
            -> identify opportunities
            -> deduplicate
            -> score (Impact, Confidence, Difficulty)
            -> Priority = (Impact * Confidence) / Difficulty
            -> deterministic rank
            -> top 3

Assumptions (deterministic, documented - not a silent new F-score model):

* Impact 0-100 from centralized tables keyed by remediation kind / signals.
* Confidence 0-1 from evaluation confidence, schema observation certainty,
  or contradiction severity (never LLM-estimated).
* Difficulty 1-5 from centralized effort mapping (never zero).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.schemas.intelligence import (
    Contradiction,
    ContradictionSeverity,
    EntailmentStatus,
    EvidenceReference,
    IntentEvaluation,
)
from app.schemas.patching import (
    PatchPrioritizationResult,
    PatchPrioritizerInput,
    RemediationEvidence,
    RemediationKind,
    RemediationOpportunity,
    SchemaRemediationTarget,
)
from app.schemas.scoring import SchemaOrgReport, SchemaTypeResult, ScoreBreakdown

logger = logging.getLogger(__name__)

TOP_N = 3

# ---------------------------------------------------------------------------
# Centralized scoring tables (P2-3.1 assumptions — keep literals here only)
# ---------------------------------------------------------------------------

# Impact contribution when a required Schema.org type is absent/invalid.
SCHEMA_IMPACT: dict[str, float] = {
    SchemaRemediationTarget.LOCAL_BUSINESS.value: 85.0,
    SchemaRemediationTarget.FAQ_PAGE.value: 80.0,
    SchemaRemediationTarget.OPENING_HOURS.value: 75.0,
    SchemaRemediationTarget.POSTAL_ADDRESS.value: 70.0,
    SchemaRemediationTarget.GEO_COORDINATES.value: 65.0,
    SchemaRemediationTarget.MENU.value: 60.0,
}

# Difficulty for adding/fixing each schema type (1=very easy … 5=hard).
SCHEMA_DIFFICULTY: dict[str, int] = {
    SchemaRemediationTarget.FAQ_PAGE.value: 2,
    SchemaRemediationTarget.POSTAL_ADDRESS.value: 2,
    SchemaRemediationTarget.GEO_COORDINATES.value: 2,
    SchemaRemediationTarget.LOCAL_BUSINESS.value: 3,
    SchemaRemediationTarget.OPENING_HOURS.value: 3,
    SchemaRemediationTarget.MENU.value: 3,
}

# Contradiction impact / confidence / difficulty by severity.
CONTRADICTION_IMPACT: dict[ContradictionSeverity, float] = {
    ContradictionSeverity.HARD_CONTRADICTION: 90.0,
    ContradictionSeverity.SOFT_INCONSISTENCY: 60.0,
}
CONTRADICTION_CONFIDENCE: dict[ContradictionSeverity, float] = {
    ContradictionSeverity.HARD_CONTRADICTION: 0.95,
    ContradictionSeverity.SOFT_INCONSISTENCY: 0.75,
}
CONTRADICTION_DIFFICULTY: dict[ContradictionSeverity, int] = {
    ContradictionSeverity.HARD_CONTRADICTION: 4,
    ContradictionSeverity.SOFT_INCONSISTENCY: 3,
}

# Information-gap (UNKNOWN intent) baselines.
INFO_GAP_BASE_IMPACT = 55.0
INFO_GAP_IMPACT_PER_INTENT = 10.0
INFO_GAP_MAX_IMPACT = 90.0
INFO_GAP_DIFFICULTY = 3
# Schema absence is directly observed → high confidence that the gap is real.
SCHEMA_GAP_CONFIDENCE = 1.0

# Low S_str boosts schema-gap impact (bounded).
LOW_S_STR_THRESHOLD = 50.0
LOW_S_STR_IMPACT_BOOST = 5.0

_SUPPORTED_SCHEMA_TARGETS: frozenset[str] = frozenset(t.value for t in SchemaRemediationTarget)

# Theme classifiers for aggregating UNKNOWN intents (gap identification only).
_GAP_THEME_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("address", re.compile(r"(?i)\b(address|street|location|where\s+are\s+you|physical)\b")),
    ("hours", re.compile(r"(?i)\b(hours|open|close|opening|schedule)\b")),
    ("phone", re.compile(r"(?i)\b(phone|telephone|call|contact\s+number)\b")),
    ("email", re.compile(r"(?i)\b(email|e-mail)\b")),
    ("menu", re.compile(r"(?i)\b(menu|dish|food|cuisine)\b")),
    ("price", re.compile(r"(?i)\b(price|cost|fee|how\s+much)\b")),
    ("faq", re.compile(r"(?i)\b(faq|frequently|policy|allow|pets|dogs|gluten)\b")),
)


class PatchPrioritizerError(Exception):
    """Raised when prioritizer inputs violate contracts."""

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "patch_prioritizer_error"
        super().__init__(message)


@dataclass
class _RawOpportunity:
    """Mutable candidate before final scoring / model construction."""

    kind: RemediationKind
    dedupe_key: str
    opportunity_id: str
    title: str
    reason: str
    impact: float
    confidence: float
    difficulty: int
    schema_target: SchemaRemediationTarget | None = None
    intent_ids: list[str] = field(default_factory=list)
    contradiction_ids: list[str] = field(default_factory=list)
    evidence_references: list[EvidenceReference] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    dom_paths: list[str] = field(default_factory=list)
    schema_issues: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Samples retained so merge computes a true mean (not pairwise running average).
    confidence_samples: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.confidence_samples:
            self.confidence_samples = [float(self.confidence)]


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=True)


def contradiction_local_id(item: Contradiction) -> str:
    """Stable contradiction key for prioritizer dedupe.

    Prefer upstream ``contradiction_id``. When absent (manual/malformed inputs),
    hash severity + entity + conflict + sources + values so unrelated records
    with the same entity/severity do not collapse.
    """
    if item.contradiction_id and str(item.contradiction_id).strip():
        return str(item.contradiction_id).strip()
    material = "|".join(
        [
            item.severity.value,
            item.entity,
            item.conflict,
            _stable_json(sorted(item.source_urls)),
            _stable_json(sorted(item.dom_paths)),
            _stable_json(item.values),
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"local:{digest}"


def validate_impact(value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PatchPrioritizerError("impact must be numeric", reason="invalid_impact")
    impact = float(value)
    if impact < 0.0 or impact > 100.0:
        raise PatchPrioritizerError(
            f"impact must be in [0, 100]; got {impact}",
            reason="invalid_impact",
        )
    return impact


def validate_confidence(value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PatchPrioritizerError("confidence must be numeric", reason="invalid_confidence")
    confidence = float(value)
    if confidence < 0.0 or confidence > 1.0:
        raise PatchPrioritizerError(
            f"confidence must be in [0, 1]; got {confidence}",
            reason="invalid_confidence",
        )
    return confidence


def validate_difficulty(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PatchPrioritizerError(
            "difficulty must be an integer",
            reason="invalid_difficulty",
        )
    if value < 1 or value > 5:
        raise PatchPrioritizerError(
            f"difficulty must be in [1, 5] and never zero; got {value}",
            reason="invalid_difficulty",
        )
    return value


def calculate_priority(*, impact: float, confidence: float, difficulty: int) -> float:
    """Priority = (Impact * Confidence) / Difficulty. Pure; no hidden weights."""
    impact_v = validate_impact(impact)
    confidence_v = validate_confidence(confidence)
    difficulty_v = validate_difficulty(difficulty)
    return (impact_v * confidence_v) / float(difficulty_v)


def _clamp_impact(value: float) -> float:
    return max(0.0, min(100.0, value))


def _gap_theme(query: str) -> str:
    for theme, pattern in _GAP_THEME_PATTERNS:
        if pattern.search(query):
            return theme
    return "general"


def _resolve_schema_report(
    score_breakdown: ScoreBreakdown | None,
    schema_report: SchemaOrgReport | None,
) -> SchemaOrgReport | None:
    if schema_report is not None:
        return schema_report
    if score_breakdown is not None:
        return score_breakdown.schema_report
    return None


def _schema_target_or_none(schema_type: str) -> SchemaRemediationTarget | None:
    if schema_type not in _SUPPORTED_SCHEMA_TARGETS:
        return None
    return SchemaRemediationTarget(schema_type)


def identify_schema_opportunities(
    schema_report: SchemaOrgReport | None,
    *,
    s_str: float | None = None,
) -> list[_RawOpportunity]:
    if schema_report is None:
        return []
    out: list[_RawOpportunity] = []
    for result in schema_report.types:
        if not isinstance(result, SchemaTypeResult):
            continue
        target = _schema_target_or_none(result.schema_type)
        if target is None:
            continue
        if result.present and result.valid:
            continue

        base = SCHEMA_IMPACT[target.value]
        if s_str is not None and s_str < LOW_S_STR_THRESHOLD:
            base = _clamp_impact(base + LOW_S_STR_IMPACT_BOOST)

        if not result.present:
            reason = f"Required Schema.org type {target.value} is missing."
            title = f"Add {target.value} schema"
        else:
            reason = (
                f"Schema.org type {target.value} is present but not structurally valid "
                f"(issues: {', '.join(result.issues) or 'unspecified'})."
            )
            title = f"Repair {target.value} schema"

        out.append(
            _RawOpportunity(
                kind=RemediationKind.MISSING_SCHEMA,
                dedupe_key=f"MISSING_SCHEMA|{target.value}",
                opportunity_id=f"missing_schema:{target.value}",
                title=title,
                reason=reason,
                impact=base,
                confidence=SCHEMA_GAP_CONFIDENCE,
                difficulty=SCHEMA_DIFFICULTY[target.value],
                schema_target=target,
                schema_issues=list(result.issues),
                notes=[
                    f"present={result.present}",
                    f"valid={result.valid}",
                    f"occurrences={result.occurrences}",
                    f"source_count={result.source_count}",
                ],
            )
        )
    return out


def identify_contradiction_opportunities(
    contradictions: Sequence[Contradiction],
) -> list[_RawOpportunity]:
    out: list[_RawOpportunity] = []
    for item in contradictions:
        if not isinstance(item, Contradiction):
            raise PatchPrioritizerError(
                "contradictions must be Contradiction instances",
                reason="invalid_input",
            )
        cid = contradiction_local_id(item)
        severity = item.severity
        out.append(
            _RawOpportunity(
                kind=RemediationKind.CONTRADICTION,
                dedupe_key=f"CONTRADICTION|{cid}",
                opportunity_id=f"contradiction:{cid}",
                title=f"Resolve {severity.value.lower().replace('_', ' ')} on {item.entity}",
                reason=item.conflict,
                impact=CONTRADICTION_IMPACT[severity],
                confidence=CONTRADICTION_CONFIDENCE[severity],
                difficulty=CONTRADICTION_DIFFICULTY[severity],
                contradiction_ids=[cid],
                source_urls=list(item.source_urls),
                dom_paths=list(item.dom_paths),
                notes=[
                    f"entity={item.entity}",
                    f"severity={severity.value}",
                    f"values_count={len(item.values)}",
                ],
            )
        )
    return out


def identify_information_gap_opportunities(
    evaluations: Sequence[IntentEvaluation],
) -> list[_RawOpportunity]:
    """Group UNKNOWN intents by theme; identify gaps only (no invented facts)."""
    buckets: dict[str, list[IntentEvaluation]] = {}
    for evaluation in evaluations:
        if not isinstance(evaluation, IntentEvaluation):
            raise PatchPrioritizerError(
                "intent_evaluations must be IntentEvaluation instances",
                reason="invalid_input",
            )
        if evaluation.status is not EntailmentStatus.UNKNOWN:
            continue
        theme = _gap_theme(evaluation.query)
        buckets.setdefault(theme, []).append(evaluation)

    out: list[_RawOpportunity] = []
    for theme in sorted(buckets):
        group = sorted(buckets[theme], key=lambda e: e.intent_id)
        intent_ids = [e.intent_id for e in group]
        refs: list[EvidenceReference] = []
        for evaluation in group:
            refs.extend(evaluation.evidence)
        # Confidence that the gap is real: mean of evaluation confidences.
        confidences = [e.confidence for e in group]
        confidence = sum(confidences) / float(len(confidences))
        impact = _clamp_impact(INFO_GAP_BASE_IMPACT + INFO_GAP_IMPACT_PER_INTENT * (len(group) - 1))
        impact = min(impact, INFO_GAP_MAX_IMPACT)

        sample_query = group[0].query
        out.append(
            _RawOpportunity(
                kind=RemediationKind.INFORMATION_GAP,
                dedupe_key=f"INFORMATION_GAP|{theme}",
                opportunity_id=f"information_gap:{theme}",
                title=f"Unresolved {theme} information gap",
                reason=(
                    f"{theme.capitalize()} information could not be reliably answered "
                    f"({len(group)} UNKNOWN intent(s)). Example question: {sample_query!r}. "
                    "No business fact is invented here — only the gap is recorded."
                ),
                impact=impact,
                confidence=confidence,
                difficulty=INFO_GAP_DIFFICULTY,
                intent_ids=intent_ids,
                evidence_references=refs,
                notes=[f"theme={theme}", f"unknown_intents={len(group)}"],
            )
        )
    return out


def identify_opportunities(inputs: PatchPrioritizerInput) -> list[_RawOpportunity]:
    report = _resolve_schema_report(inputs.score_breakdown, inputs.schema_report)
    s_str = inputs.score_breakdown.s_str if inputs.score_breakdown is not None else None
    raw: list[_RawOpportunity] = []
    raw.extend(identify_schema_opportunities(report, s_str=s_str))
    raw.extend(identify_contradiction_opportunities(inputs.contradictions))
    raw.extend(identify_information_gap_opportunities(inputs.intent_evaluations))
    return raw


def deduplicate_opportunities(raw: Sequence[_RawOpportunity]) -> list[_RawOpportunity]:
    """Merge candidates that share a dedupe key; keep strongest signals."""
    merged: dict[str, _RawOpportunity] = {}
    for item in raw:
        existing = merged.get(item.dedupe_key)
        if existing is None:
            # Copy so later merges do not mutate the caller's list entries in place
            # beyond the retained merged object.
            if not item.confidence_samples:
                item.confidence_samples = [float(item.confidence)]
            merged[item.dedupe_key] = item
            continue
        # Aggregate related IDs / provenance; take max impact, true mean confidence.
        existing.intent_ids = sorted(set(existing.intent_ids) | set(item.intent_ids))
        existing.contradiction_ids = sorted(
            set(existing.contradiction_ids) | set(item.contradiction_ids)
        )
        existing.source_urls = sorted(set(existing.source_urls) | set(item.source_urls))
        existing.dom_paths = sorted(set(existing.dom_paths) | set(item.dom_paths))
        existing.schema_issues = sorted(set(existing.schema_issues) | set(item.schema_issues))
        existing.notes = sorted(set(existing.notes) | set(item.notes))
        # Evidence refs: stable unique by chunk_id+dom_path
        seen_refs: set[tuple[str, str]] = {
            (r.chunk_id, r.dom_path) for r in existing.evidence_references
        }
        for ref in item.evidence_references:
            key = (ref.chunk_id, ref.dom_path)
            if key not in seen_refs:
                existing.evidence_references.append(ref)
                seen_refs.add(key)
        existing.impact = max(existing.impact, item.impact)
        item_samples = item.confidence_samples or [float(item.confidence)]
        existing.confidence_samples.extend(item_samples)
        existing.confidence = sum(existing.confidence_samples) / float(
            len(existing.confidence_samples)
        )
        existing.difficulty = max(existing.difficulty, item.difficulty)
    return [merged[k] for k in sorted(merged)]


def score_opportunities(raw: Sequence[_RawOpportunity]) -> list[RemediationOpportunity]:
    scored: list[RemediationOpportunity] = []
    for item in raw:
        priority = calculate_priority(
            impact=item.impact,
            confidence=item.confidence,
            difficulty=item.difficulty,
        )
        evidence = RemediationEvidence(
            intent_ids=list(item.intent_ids),
            contradiction_ids=list(item.contradiction_ids),
            schema_types=[item.schema_target.value] if item.schema_target else [],
            evidence_references=list(item.evidence_references),
            source_urls=list(item.source_urls),
            dom_paths=list(item.dom_paths),
            schema_issues=list(item.schema_issues),
            notes=list(item.notes),
        )
        scored.append(
            RemediationOpportunity(
                opportunity_id=item.opportunity_id,
                kind=item.kind,
                title=item.title,
                reason=item.reason,
                impact=float(item.impact),
                confidence=float(item.confidence),
                difficulty=int(item.difficulty),
                priority=priority,
                evidence=evidence,
                schema_target=item.schema_target,
                related_intent_ids=list(item.intent_ids),
                related_contradiction_ids=list(item.contradiction_ids),
                dedupe_key=item.dedupe_key,
            )
        )
    return scored


def rank_opportunities(
    opportunities: Sequence[RemediationOpportunity],
) -> list[RemediationOpportunity]:
    """Deterministic sort: priority↓, impact↓, confidence↓, difficulty↑, id↑."""
    return sorted(
        opportunities,
        key=lambda o: (
            -o.priority,
            -o.impact,
            -o.confidence,
            o.difficulty,
            o.opportunity_id,
        ),
    )


def select_top_three(
    opportunities: Sequence[RemediationOpportunity],
) -> list[RemediationOpportunity]:
    ranked = rank_opportunities(opportunities)
    return ranked[:TOP_N]


class PatchPrioritizer:
    """Pure evaluation layer: intelligence artifacts → top-3 remediations."""

    def prioritize(
        self, inputs: PatchPrioritizerInput | dict[str, Any]
    ) -> PatchPrioritizationResult:
        if isinstance(inputs, dict):
            try:
                inputs = PatchPrioritizerInput.model_validate(inputs)
            except Exception as exc:
                raise PatchPrioritizerError(
                    f"invalid PatchPrioritizerInput: {exc}",
                    reason="invalid_input",
                ) from exc
        elif not isinstance(inputs, PatchPrioritizerInput):
            raise PatchPrioritizerError(
                "inputs must be PatchPrioritizerInput",
                reason="invalid_input",
            )

        raw = identify_opportunities(inputs)
        deduped = deduplicate_opportunities(raw)
        scored = score_opportunities(deduped)
        selected = select_top_three(scored)

        logger.info(
            "Patch prioritizer selected %d of %d candidates",
            len(selected),
            len(scored),
        )
        return PatchPrioritizationResult(
            opportunities=selected,
            total_candidates=len(scored),
            selected_count=len(selected),
        )


def prioritize(inputs: PatchPrioritizerInput | dict[str, Any]) -> PatchPrioritizationResult:
    """Module-level convenience wrapper."""
    return PatchPrioritizer().prioritize(inputs)
