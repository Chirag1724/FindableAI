"""Deterministic Schema.org JSON-LD generator (P2-3.2).

Consumes PatchPrioritizationResult + evidence-backed BusinessFacts.
Validates via the existing Phase E ``analyze_schema_org`` checker.

No LLM, network, database, GitHub, filesystem writes, diffs, or scoring.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

from app.engines.scorer import analyze_schema_org
from app.schemas.intelligence import EntailmentStatus, IntentEvaluation
from app.schemas.patching import (
    SCHEMA_ORG_CONTEXT,
    BusinessFacts,
    FaqEntry,
    GeneratedJsonLd,
    JsonLdGenerationResult,
    JsonLdSkip,
    PatchPrioritizationResult,
    RemediationKind,
    RemediationOpportunity,
    SchemaRemediationTarget,
)

logger = logging.getLogger(__name__)

VALID_DAYS_ORDER: tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
VALID_DAYS: frozenset[str] = frozenset(VALID_DAYS_ORDER)
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class JsonLdGeneratorError(Exception):
    """Raised when generation or validation fails deterministically."""

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "jsonld_generator_error"
        super().__init__(message)


def dumps_jsonld(payload: dict[str, Any]) -> str:
    """Deterministic pretty JSON (stable field insertion order; no sort_keys)."""
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _wrap_for_checker(json_text: str) -> str:
    return (
        "<!DOCTYPE html><html><head>"
        f'<script type="application/ld+json">{json_text}</script>'
        "</head><body></body></html>"
    )


def validate_generated_jsonld(
    payload: dict[str, Any],
    *,
    expected_type: SchemaRemediationTarget,
) -> None:
    """Reject invalid JSON-LD using Phase E checker + structural guards."""
    if payload.get("@context") != SCHEMA_ORG_CONTEXT:
        raise JsonLdGeneratorError(
            "@context must be https://schema.org",
            reason="invalid_context",
        )
    type_value = payload.get("@type")
    if not type_value:
        raise JsonLdGeneratorError("missing @type", reason="missing_type")
    if expected_type == SchemaRemediationTarget.LOCAL_BUSINESS:
        allowed = {SchemaRemediationTarget.LOCAL_BUSINESS.value}
        if isinstance(type_value, str) and type_value not in allowed:
            # Only LocalBusiness itself is emitted by this generator (controlled).
            raise JsonLdGeneratorError(
                f"unsupported @type for LocalBusiness generation: {type_value}",
                reason="unsupported_type",
            )
    elif type_value != expected_type.value:
        raise JsonLdGeneratorError(
            f"@type must be {expected_type.value}; got {type_value!r}",
            reason="type_mismatch",
        )

    if expected_type == SchemaRemediationTarget.FAQ_PAGE:
        _validate_faq_structure(payload)
    elif expected_type == SchemaRemediationTarget.GEO_COORDINATES:
        _validate_geo_structure(payload)
    elif expected_type == SchemaRemediationTarget.OPENING_HOURS:
        _validate_hours_structure(payload)

    try:
        json_text = dumps_jsonld(payload)
        json.loads(json_text)
    except (TypeError, ValueError) as exc:
        raise JsonLdGeneratorError(
            f"payload is not JSON-serializable: {exc}",
            reason="not_serializable",
        ) from exc

    report = analyze_schema_org([_wrap_for_checker(json_text)])
    match = next((t for t in report.types if t.schema_type == expected_type.value), None)
    if match is None or not match.present or not match.valid:
        issues = match.issues if match else report.issues
        raise JsonLdGeneratorError(
            f"Phase E schema checker rejected {expected_type.value}: {issues}",
            reason="schema_validation_failed",
        )


def _validate_faq_structure(payload: dict[str, Any]) -> None:
    main = payload.get("mainEntity")
    if not isinstance(main, list) or not main:
        raise JsonLdGeneratorError(
            "FAQPage.mainEntity must be a non-empty list", reason="invalid_faq"
        )
    for item in main:
        if not isinstance(item, dict):
            raise JsonLdGeneratorError("FAQ question must be an object", reason="invalid_faq")
        if item.get("@type") != "Question":
            raise JsonLdGeneratorError("FAQ item @type must be Question", reason="invalid_faq")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise JsonLdGeneratorError("Question.name must be non-empty", reason="invalid_faq")
        answer = item.get("acceptedAnswer")
        if not isinstance(answer, dict):
            raise JsonLdGeneratorError("acceptedAnswer required", reason="invalid_faq")
        if answer.get("@type") != "Answer":
            raise JsonLdGeneratorError("acceptedAnswer.@type must be Answer", reason="invalid_faq")
        text = answer.get("text")
        if not isinstance(text, str) or not text.strip():
            raise JsonLdGeneratorError(
                "acceptedAnswer.text must be non-empty", reason="invalid_faq"
            )


def _validate_geo_structure(payload: dict[str, Any]) -> None:
    try:
        lat = float(payload["latitude"])  # type: ignore[arg-type]
        lon = float(payload["longitude"])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as exc:
        raise JsonLdGeneratorError(
            "GeoCoordinates require numeric latitude and longitude",
            reason="invalid_geo",
        ) from exc
    if lat < -90.0 or lat > 90.0:
        raise JsonLdGeneratorError(f"latitude out of range: {lat}", reason="invalid_geo")
    if lon < -180.0 or lon > 180.0:
        raise JsonLdGeneratorError(f"longitude out of range: {lon}", reason="invalid_geo")


def _validate_hours_structure(payload: dict[str, Any]) -> None:
    day = payload.get("dayOfWeek")
    days: list[str]
    if isinstance(day, str):
        days = [day]
    elif isinstance(day, list):
        days = [str(d) for d in day]
    else:
        raise JsonLdGeneratorError("dayOfWeek required", reason="invalid_hours")
    for d in days:
        bare = d.rsplit("/", 1)[-1]
        if bare not in VALID_DAYS:
            raise JsonLdGeneratorError(f"invalid dayOfWeek: {d}", reason="invalid_hours")
    for key in ("opens", "closes"):
        value = payload.get(key)
        if not isinstance(value, str) or not _TIME_RE.match(value):
            raise JsonLdGeneratorError(
                f"{key} must be HH:MM 24h time; got {value!r}",
                reason="invalid_hours",
            )


def _faq_entries_from_intents(
    evaluations: Sequence[IntentEvaluation],
    related_ids: Sequence[str],
) -> list[FaqEntry]:
    entries: list[FaqEntry] = []
    related = set(related_ids)
    ordered = sorted(evaluations, key=lambda e: e.intent_id)
    for evaluation in ordered:
        if related and evaluation.intent_id not in related:
            continue
        if evaluation.status is not EntailmentStatus.SUPPORTED:
            continue
        excerpts = [
            ref.excerpt.strip()
            for ref in evaluation.evidence
            if ref.excerpt and ref.excerpt.strip()
        ]
        if not excerpts:
            continue
        entries.append(
            FaqEntry(
                question=evaluation.query.strip(),
                answer=" ".join(excerpts),
                source_intent_id=evaluation.intent_id,
            )
        )
    return entries


def build_faq_page(
    entries: Sequence[FaqEntry],
) -> dict[str, Any]:
    if not entries:
        raise JsonLdGeneratorError(
            "insufficient evidence for FAQPage: no question/answer pairs",
            reason="insufficient_evidence",
        )
    main_entity: list[dict[str, Any]] = []
    for entry in entries:
        question = entry.question.strip()
        answer = entry.answer.strip()
        if not question:
            raise JsonLdGeneratorError("empty question rejected", reason="invalid_faq")
        if not answer:
            raise JsonLdGeneratorError("missing answer rejected", reason="invalid_faq")
        main_entity.append(
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
        )
    return {
        "@context": SCHEMA_ORG_CONTEXT,
        "@type": SchemaRemediationTarget.FAQ_PAGE.value,
        "mainEntity": main_entity,
    }


def build_postal_address(facts: BusinessFacts) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "@context": SCHEMA_ORG_CONTEXT,
        "@type": SchemaRemediationTarget.POSTAL_ADDRESS.value,
    }
    mapping = (
        ("street_address", "streetAddress"),
        ("address_locality", "addressLocality"),
        ("address_region", "addressRegion"),
        ("postal_code", "postalCode"),
        ("address_country", "addressCountry"),
    )
    for attr, key in mapping:
        value = getattr(facts, attr)
        if value is not None and str(value).strip():
            payload[key] = str(value).strip()
    address_keys = {
        "streetAddress",
        "addressLocality",
        "addressRegion",
        "postalCode",
        "addressCountry",
    }
    if not any(k in payload for k in address_keys):
        raise JsonLdGeneratorError(
            "insufficient evidence for PostalAddress",
            reason="insufficient_evidence",
        )
    return payload


def build_geo_coordinates(facts: BusinessFacts) -> dict[str, Any]:
    if facts.latitude is None or facts.longitude is None:
        raise JsonLdGeneratorError(
            "insufficient evidence for GeoCoordinates",
            reason="insufficient_evidence",
        )
    payload = {
        "@context": SCHEMA_ORG_CONTEXT,
        "@type": SchemaRemediationTarget.GEO_COORDINATES.value,
        "latitude": float(facts.latitude),
        "longitude": float(facts.longitude),
    }
    _validate_geo_structure(payload)
    return payload


def build_opening_hours(facts: BusinessFacts) -> dict[str, Any]:
    if not facts.opening_hours:
        raise JsonLdGeneratorError(
            "insufficient evidence for OpeningHoursSpecification",
            reason="insufficient_evidence",
        )
    # Emit one specification object; if multiple days share opens/closes, list them.
    # If hours differ, emit the first sorted day group deterministically as a single
    # block (checker accepts one node). Prefer grouping identical open/close.
    groups: dict[tuple[str, str], list[str]] = {}
    for item in facts.opening_hours:
        day = item.day_of_week.strip()
        bare = day.rsplit("/", 1)[-1]
        if bare not in VALID_DAYS:
            raise JsonLdGeneratorError(f"invalid dayOfWeek: {day}", reason="invalid_hours")
        opens = item.opens.strip()
        closes = item.closes.strip()
        if not _TIME_RE.match(opens) or not _TIME_RE.match(closes):
            raise JsonLdGeneratorError(
                f"invalid time opens={opens!r} closes={closes!r}",
                reason="invalid_hours",
            )
        groups.setdefault((opens, closes), []).append(bare)
    # Stable: pick group with most days, tie-break by opens, closes
    best_key = sorted(
        groups.keys(),
        key=lambda oc: (-len(groups[oc]), oc[0], oc[1]),
    )[0]
    days = sorted(groups[best_key], key=lambda d: VALID_DAYS_ORDER.index(d))
    opens, closes = best_key
    day_value: str | list[str] = days[0] if len(days) == 1 else days
    return {
        "@context": SCHEMA_ORG_CONTEXT,
        "@type": SchemaRemediationTarget.OPENING_HOURS.value,
        "dayOfWeek": day_value,
        "opens": opens,
        "closes": closes,
    }


def build_menu(facts: BusinessFacts) -> dict[str, Any]:
    if not facts.menu_name and not facts.menu_items:
        raise JsonLdGeneratorError(
            "insufficient evidence for Menu",
            reason="insufficient_evidence",
        )
    payload: dict[str, Any] = {
        "@context": SCHEMA_ORG_CONTEXT,
        "@type": SchemaRemediationTarget.MENU.value,
    }
    if facts.menu_name and facts.menu_name.strip():
        payload["name"] = facts.menu_name.strip()
    if facts.menu_items:
        items: list[dict[str, Any]] = []
        for item in facts.menu_items:
            name = item.name.strip()
            if not name:
                raise JsonLdGeneratorError("menu item name empty", reason="invalid_menu")
            entry: dict[str, Any] = {"@type": "MenuItem", "name": name}
            if item.price is not None and str(item.price).strip():
                entry["offers"] = {
                    "@type": "Offer",
                    "price": str(item.price).strip(),
                }
            items.append(entry)
        payload["hasMenuItem"] = items
    return payload


def build_local_business(facts: BusinessFacts) -> dict[str, Any]:
    if not facts.name or not str(facts.name).strip():
        raise JsonLdGeneratorError(
            "insufficient evidence for LocalBusiness: name required",
            reason="insufficient_evidence",
        )
    payload: dict[str, Any] = {
        "@context": SCHEMA_ORG_CONTEXT,
        "@type": SchemaRemediationTarget.LOCAL_BUSINESS.value,
        "name": str(facts.name).strip(),
    }
    if facts.telephone and str(facts.telephone).strip():
        payload["telephone"] = str(facts.telephone).strip()
    if facts.email and str(facts.email).strip():
        payload["email"] = str(facts.email).strip()

    # Nested evidence-backed structures when available (no invention).
    try:
        address = build_postal_address(facts)
        address.pop("@context", None)
        payload["address"] = address
    except JsonLdGeneratorError:
        pass
    try:
        geo = build_geo_coordinates(facts)
        geo.pop("@context", None)
        payload["geo"] = geo
    except JsonLdGeneratorError:
        pass

    if not any(k in payload for k in ("telephone", "address", "geo")):
        raise JsonLdGeneratorError(
            "insufficient evidence for LocalBusiness: need telephone, address, or geo",
            reason="insufficient_evidence",
        )
    return payload


def generate_for_opportunity(
    opportunity: RemediationOpportunity,
    *,
    facts: BusinessFacts,
    intent_evaluations: Sequence[IntentEvaluation] = (),
) -> GeneratedJsonLd:
    if opportunity.kind is not RemediationKind.MISSING_SCHEMA:
        raise JsonLdGeneratorError(
            f"opportunity kind {opportunity.kind.value} is not a schema generation target",
            reason="unsupported_kind",
        )
    if opportunity.schema_target is None:
        raise JsonLdGeneratorError(
            "MISSING_SCHEMA opportunity lacks schema_target",
            reason="missing_schema_target",
        )
    target = opportunity.schema_target
    notes: list[str] = []

    if target is SchemaRemediationTarget.FAQ_PAGE:
        entries = list(facts.faq_entries)
        from_intents = _faq_entries_from_intents(
            intent_evaluations,
            opportunity.related_intent_ids,
        )
        # Prefer explicit facts; supplement with SUPPORTED intent evidence.
        seen_q = {e.question.strip().lower() for e in entries}
        for entry in from_intents:
            key = entry.question.strip().lower()
            if key not in seen_q:
                entries.append(entry)
                seen_q.add(key)
        payload = build_faq_page(entries)
        notes.append(f"faq_entries={len(entries)}")
    elif target is SchemaRemediationTarget.LOCAL_BUSINESS:
        payload = build_local_business(facts)
    elif target is SchemaRemediationTarget.POSTAL_ADDRESS:
        payload = build_postal_address(facts)
    elif target is SchemaRemediationTarget.OPENING_HOURS:
        payload = build_opening_hours(facts)
    elif target is SchemaRemediationTarget.GEO_COORDINATES:
        payload = build_geo_coordinates(facts)
    elif target is SchemaRemediationTarget.MENU:
        payload = build_menu(facts)
    else:
        raise JsonLdGeneratorError(
            f"unsupported schema type: {target}",
            reason="unsupported_type",
        )

    validate_generated_jsonld(payload, expected_type=target)
    json_text = dumps_jsonld(payload)
    return GeneratedJsonLd(
        opportunity_id=opportunity.opportunity_id,
        schema_type=target,
        payload=payload,
        json_text=json_text,
        related_intent_ids=list(opportunity.related_intent_ids),
        related_contradiction_ids=list(opportunity.related_contradiction_ids),
        evidence_notes=notes,
    )


class JsonLdGenerator:
    """Generate controlled Schema.org JSON-LD for prioritized remediations."""

    def generate(
        self,
        prioritization: PatchPrioritizationResult,
        *,
        facts: BusinessFacts,
        intent_evaluations: Sequence[IntentEvaluation] = (),
    ) -> JsonLdGenerationResult:
        generated: list[GeneratedJsonLd] = []
        skipped: list[JsonLdSkip] = []
        for opportunity in prioritization.opportunities:
            if opportunity.kind is not RemediationKind.MISSING_SCHEMA:
                skipped.append(
                    JsonLdSkip(
                        opportunity_id=opportunity.opportunity_id,
                        schema_type=opportunity.schema_target,
                        reason=f"kind {opportunity.kind.value} not eligible for JSON-LD",
                    )
                )
                continue
            try:
                generated.append(
                    generate_for_opportunity(
                        opportunity,
                        facts=facts,
                        intent_evaluations=intent_evaluations,
                    )
                )
            except JsonLdGeneratorError as exc:
                if exc.reason == "insufficient_evidence":
                    skipped.append(
                        JsonLdSkip(
                            opportunity_id=opportunity.opportunity_id,
                            schema_type=opportunity.schema_target,
                            reason=str(exc),
                        )
                    )
                    continue
                raise
        # Stable order by opportunity_id already from prioritizer; keep as-is.
        logger.info(
            "JSON-LD generation produced %d payloads, skipped %d",
            len(generated),
            len(skipped),
        )
        return JsonLdGenerationResult(generated=generated, skipped=skipped)


def generate_jsonld(
    prioritization: PatchPrioritizationResult,
    *,
    facts: BusinessFacts,
    intent_evaluations: Sequence[IntentEvaluation] = (),
) -> JsonLdGenerationResult:
    return JsonLdGenerator().generate(
        prioritization,
        facts=facts,
        intent_evaluations=intent_evaluations,
    )


__all__ = [
    "JsonLdGenerator",
    "JsonLdGeneratorError",
    "build_faq_page",
    "build_geo_coordinates",
    "build_local_business",
    "build_menu",
    "build_opening_hours",
    "build_postal_address",
    "dumps_jsonld",
    "generate_for_opportunity",
    "generate_jsonld",
    "validate_generated_jsonld",
]
