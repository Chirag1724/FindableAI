"""Unit tests for P2-3.2 JSON-LD generator."""

from __future__ import annotations

import json

import pytest

from app.engines.jsonld_generator import (
    JsonLdGenerator,
    JsonLdGeneratorError,
    build_faq_page,
    build_geo_coordinates,
    build_local_business,
    build_menu,
    build_opening_hours,
    build_postal_address,
    dumps_jsonld,
    generate_for_opportunity,
    validate_generated_jsonld,
)
from app.schemas.intelligence import (
    EntailmentStatus,
    EvidenceReference,
    IntentEvaluation,
)
from app.schemas.patching import (
    BusinessFacts,
    FaqEntry,
    MenuItemFact,
    OpeningHoursFact,
    PatchPrioritizationResult,
    RemediationKind,
    RemediationOpportunity,
    SchemaRemediationTarget,
)


def _opp(
    *,
    opportunity_id: str,
    target: SchemaRemediationTarget,
    impact: float = 80.0,
    confidence: float = 1.0,
    difficulty: int = 2,
    related_intent_ids: list[str] | None = None,
) -> RemediationOpportunity:
    priority = (impact * confidence) / float(difficulty)
    return RemediationOpportunity(
        opportunity_id=opportunity_id,
        kind=RemediationKind.MISSING_SCHEMA,
        title=f"Add {target.value}",
        reason=f"missing {target.value}",
        impact=impact,
        confidence=confidence,
        difficulty=difficulty,
        priority=priority,
        schema_target=target,
        related_intent_ids=related_intent_ids or [],
        dedupe_key=f"MISSING_SCHEMA|{target.value}",
    )


def _eval_supported(intent_id: str, query: str, answer: str) -> IntentEvaluation:
    return IntentEvaluation(
        intent_id=intent_id,
        query=query,
        status=EntailmentStatus.SUPPORTED,
        reasoning="fixture",
        evidence=[EvidenceReference(chunk_id="c1", dom_path="/p[1]", excerpt=answer)],
        confidence=0.9,
    )


# --- FAQPage ---


def test_faq_valid_generation():
    payload = build_faq_page([FaqEntry(question="Are dogs allowed?", answer="Yes, on the patio.")])
    validate_generated_jsonld(payload, expected_type=SchemaRemediationTarget.FAQ_PAGE)
    assert payload["@context"] == "https://schema.org"
    assert payload["@type"] == "FAQPage"
    assert len(payload["mainEntity"]) == 1


def test_faq_multiple_questions():
    payload = build_faq_page(
        [
            FaqEntry(question="Q1?", answer="A1"),
            FaqEntry(question="Q2?", answer="A2"),
        ]
    )
    assert len(payload["mainEntity"]) == 2


def test_faq_missing_answer_rejected():
    with pytest.raises(JsonLdGeneratorError):
        build_faq_page([FaqEntry(question="Q?", answer="   ")])


def test_faq_empty_question_rejected():
    with pytest.raises(JsonLdGeneratorError):
        build_faq_page([FaqEntry(question="   ", answer="A")])


def test_faq_deterministic():
    entries = [FaqEntry(question="Hours?", answer="10-10")]
    assert dumps_jsonld(build_faq_page(entries)) == dumps_jsonld(build_faq_page(entries))


def test_faq_from_supported_intent_evidence():
    opp = _opp(
        opportunity_id="missing_schema:FAQPage",
        target=SchemaRemediationTarget.FAQ_PAGE,
        related_intent_ids=["i1"],
    )
    result = generate_for_opportunity(
        opp,
        facts=BusinessFacts(),
        intent_evaluations=[
            _eval_supported("i1", "Do you allow pets?", "Yes, leashed dogs on the patio.")
        ],
    )
    assert result.schema_type == SchemaRemediationTarget.FAQ_PAGE
    assert "patio" in result.json_text


# --- LocalBusiness ---


def test_local_business_valid():
    payload = build_local_business(BusinessFacts(name="Bistro 2026", telephone="+91 9876543210"))
    validate_generated_jsonld(payload, expected_type=SchemaRemediationTarget.LOCAL_BUSINESS)
    assert payload["name"] == "Bistro 2026"


def test_local_business_no_fabrication():
    with pytest.raises(JsonLdGeneratorError, match="insufficient"):
        build_local_business(BusinessFacts(name="Bistro 2026"))


def test_local_business_with_address_evidence():
    payload = build_local_business(
        BusinessFacts(
            name="Bistro",
            street_address="12 MG Road",
            address_locality="Bengaluru",
        )
    )
    assert "address" in payload
    assert "12 MG Road" in json.dumps(payload)


# --- PostalAddress ---


def test_postal_address_valid():
    payload = build_postal_address(
        BusinessFacts(street_address="1 Main", address_locality="Bengaluru")
    )
    validate_generated_jsonld(payload, expected_type=SchemaRemediationTarget.POSTAL_ADDRESS)


def test_postal_address_partial_no_invention():
    payload = build_postal_address(BusinessFacts(postal_code="560001"))
    assert "streetAddress" not in payload
    assert payload["postalCode"] == "560001"


def test_postal_address_insufficient():
    with pytest.raises(JsonLdGeneratorError, match="insufficient"):
        build_postal_address(BusinessFacts())


# --- OpeningHours ---


def test_opening_hours_valid():
    payload = build_opening_hours(
        BusinessFacts(
            opening_hours=[OpeningHoursFact(day_of_week="Monday", opens="10:00", closes="22:00")]
        )
    )
    validate_generated_jsonld(payload, expected_type=SchemaRemediationTarget.OPENING_HOURS)


def test_opening_hours_multiple_days():
    payload = build_opening_hours(
        BusinessFacts(
            opening_hours=[
                OpeningHoursFact(day_of_week="Monday", opens="10:00", closes="22:00"),
                OpeningHoursFact(day_of_week="Tuesday", opens="10:00", closes="22:00"),
            ]
        )
    )
    assert payload["dayOfWeek"] == ["Monday", "Tuesday"]


def test_opening_hours_invalid_day():
    with pytest.raises(JsonLdGeneratorError, match="dayOfWeek"):
        build_opening_hours(
            BusinessFacts(
                opening_hours=[
                    OpeningHoursFact(day_of_week="Funday", opens="10:00", closes="22:00")
                ]
            )
        )


def test_opening_hours_invalid_time():
    with pytest.raises(JsonLdGeneratorError, match="time"):
        build_opening_hours(
            BusinessFacts(
                opening_hours=[
                    OpeningHoursFact(day_of_week="Monday", opens="25:00", closes="22:00")
                ]
            )
        )


def test_opening_hours_missing_evidence():
    with pytest.raises(JsonLdGeneratorError, match="insufficient"):
        build_opening_hours(BusinessFacts())


# --- Geo ---


def test_geo_valid():
    payload = build_geo_coordinates(BusinessFacts(latitude=12.97, longitude=77.59))
    validate_generated_jsonld(payload, expected_type=SchemaRemediationTarget.GEO_COORDINATES)


def test_geo_latitude_boundary():
    build_geo_coordinates(BusinessFacts(latitude=90.0, longitude=0.0))
    build_geo_coordinates(BusinessFacts(latitude=-90.0, longitude=0.0))
    with pytest.raises(JsonLdGeneratorError):
        build_geo_coordinates(BusinessFacts(latitude=90.1, longitude=0.0))


def test_geo_longitude_boundary():
    with pytest.raises(JsonLdGeneratorError):
        build_geo_coordinates(BusinessFacts(latitude=0.0, longitude=180.1))


def test_geo_insufficient():
    with pytest.raises(JsonLdGeneratorError, match="insufficient"):
        build_geo_coordinates(BusinessFacts(latitude=1.0))


# --- Menu ---


def test_menu_valid():
    payload = build_menu(
        BusinessFacts(
            menu_name="Dinner",
            menu_items=[MenuItemFact(name="Soup", price="250")],
        )
    )
    validate_generated_jsonld(payload, expected_type=SchemaRemediationTarget.MENU)


def test_menu_missing_evidence():
    with pytest.raises(JsonLdGeneratorError, match="insufficient"):
        build_menu(BusinessFacts())


def test_menu_no_fabricated_items():
    payload = build_menu(BusinessFacts(menu_name="Lunch"))
    assert "hasMenuItem" not in payload


# --- General ---


def test_context_always_schema_org():
    payloads = [
        build_faq_page([FaqEntry(question="Q?", answer="A")]),
        build_local_business(BusinessFacts(name="N", telephone="1")),
        build_postal_address(BusinessFacts(street_address="1")),
        build_opening_hours(
            BusinessFacts(
                opening_hours=[
                    OpeningHoursFact(day_of_week="Friday", opens="09:00", closes="17:00")
                ]
            )
        ),
        build_geo_coordinates(BusinessFacts(latitude=1.0, longitude=2.0)),
        build_menu(BusinessFacts(menu_name="M")),
    ]
    for payload in payloads:
        assert payload["@context"] == "https://schema.org"
        json.loads(dumps_jsonld(payload))


def test_unsupported_kind_skipped():
    priority = (90.0 * 0.95) / 4.0
    contra_opp = RemediationOpportunity(
        opportunity_id="contradiction:c1",
        kind=RemediationKind.CONTRADICTION,
        title="Resolve",
        reason="conflict",
        impact=90.0,
        confidence=0.95,
        difficulty=4,
        priority=priority,
        dedupe_key="CONTRADICTION|c1",
    )
    result = JsonLdGenerator().generate(
        PatchPrioritizationResult(
            opportunities=[contra_opp],
            total_candidates=1,
            selected_count=1,
        ),
        facts=BusinessFacts(name="N", telephone="1"),
    )
    assert result.generated == []
    assert result.skipped[0].opportunity_id == "contradiction:c1"


def test_insufficient_evidence_skipped_not_raised():
    result = JsonLdGenerator().generate(
        PatchPrioritizationResult(
            opportunities=[
                _opp(
                    opportunity_id="missing_schema:LocalBusiness",
                    target=SchemaRemediationTarget.LOCAL_BUSINESS,
                )
            ],
            total_candidates=1,
            selected_count=1,
        ),
        facts=BusinessFacts(),  # no evidence
    )
    assert result.generated == []
    assert "insufficient" in result.skipped[0].reason


def test_no_llm(monkeypatch: pytest.MonkeyPatch):
    def boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr("app.core.llm.LLMClient.create", boom)
    JsonLdGenerator().generate(
        PatchPrioritizationResult(
            opportunities=[
                _opp(
                    opportunity_id="missing_schema:GeoCoordinates",
                    target=SchemaRemediationTarget.GEO_COORDINATES,
                )
            ],
            total_candidates=1,
            selected_count=1,
        ),
        facts=BusinessFacts(latitude=1.0, longitude=2.0),
    )
