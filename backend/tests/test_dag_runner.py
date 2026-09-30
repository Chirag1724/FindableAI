"""DAG runner tests with injectable fakes (no LLM/GitHub/network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest

from app.core.llm import LLMClient
from app.engines.scorer import ScoreInputs
from app.orchestration.dag import FindableAIDAG, ObservationInput
from app.orchestration.state import OrchestrationChunk, ScanPhase
from app.schemas.intelligence import (
    EntailmentStatus,
    IntentBatch,
    IntentCategory,
    IntentEvaluation,
    IntentQuery,
)
from app.schemas.patching import (
    FormattedPatch,
    GeneratedJsonLd,
    JsonLdGenerationResult,
    PatchFormatResult,
    PatchFormatStatus,
    PatchPrioritizationResult,
    PatchPrioritizerInput,
    ProjectedScoreBatchResult,
    ProjectedScoreResult,
    RemediationKind,
    RemediationOpportunity,
    SchemaRemediationTarget,
)
from app.schemas.scoring import SchemaOrgReport, SchemaTypeResult, ScoreBreakdown, ScoreWeights


def _intent_batch() -> IntentBatch:
    queries = []
    for _, cat in enumerate(list(IntentCategory)):
        for j in range(3):
            queries.append(
                IntentQuery(
                    intent_id=f"{cat.value}_{j + 1:02d}",
                    category=cat,
                    query=f"Question about {cat.value} number {j + 1}?",
                    difficulty="easy",
                    expected_evidence_type="page text",
                )
            )
    return IntentBatch(business_type="restaurant", queries=queries)


def _eval(intent_id: str, status: EntailmentStatus = EntailmentStatus.UNKNOWN) -> IntentEvaluation:
    return IntentEvaluation(
        intent_id=intent_id,
        query="Q?",
        status=status,
        reasoning="fixture",
        evidence=[],
        confidence=0.5,
    )


def _empty_schema_report() -> SchemaOrgReport:
    required = [
        "LocalBusiness",
        "PostalAddress",
        "OpeningHoursSpecification",
        "GeoCoordinates",
        "Menu",
        "FAQPage",
    ]
    return SchemaOrgReport(
        total_blocks=0,
        valid_blocks=0,
        invalid_blocks=0,
        malformed_blocks=0,
        required_types=required,
        types=[
            SchemaTypeResult(
                schema_type=name,
                present=True,
                valid=True,
                occurrences=1,
                source_count=1,
            )
            for name in required
        ],
        score=100.0,
        issues=[],
    )


def _score(f: float = 50.0) -> ScoreBreakdown:
    return ScoreBreakdown(
        f_score=f,
        s_ans=f,
        s_con=100.0,
        s_str=100.0,
        s_acc=50.0,
        weights=ScoreWeights(),
        schema_report=_empty_schema_report(),
    )


@dataclass
class FakeIntent:
    calls: list[str] = field(default_factory=list)
    fail: bool = False

    async def generate_intents(self, *, business_context: str) -> IntentBatch:
        self.calls.append("plan")
        if self.fail:
            raise RuntimeError("intent boom")
        assert len(business_context) >= 20
        return _intent_batch()


@dataclass
class FakeEntailment:
    calls: list[str] = field(default_factory=list)
    fail: bool = False

    async def evaluate_intents(self, *, intents: Any, scan_id: UUID) -> list[IntentEvaluation]:
        self.calls.append("act")
        if self.fail:
            raise RuntimeError("nli boom")
        return [_eval(q.intent_id) for q in intents]


@dataclass
class FakeContradiction:
    calls: list[str] = field(default_factory=list)
    fail: bool = False

    async def detect_contradictions(self, *, chunks: Any) -> list:
        self.calls.append("verify_contradiction")
        if self.fail:
            raise RuntimeError("contra boom")
        return []


@dataclass
class FakeScorer:
    calls: list[str] = field(default_factory=list)

    def score(self, inputs: ScoreInputs) -> ScoreBreakdown:
        self.calls.append("verify_score")
        return _score()


@dataclass
class FakePrioritizer:
    calls: list[str] = field(default_factory=list)
    empty: bool = True
    fail: bool = False

    def prioritize(self, inputs: PatchPrioritizerInput | dict) -> PatchPrioritizationResult:
        self.calls.append("reflect_prioritize")
        if self.fail:
            raise RuntimeError("prio boom")
        if self.empty:
            return PatchPrioritizationResult(opportunities=[], total_candidates=0, selected_count=0)
        impact, conf, diff = 80.0, 1.0, 2
        opp = RemediationOpportunity(
            opportunity_id="missing_schema:FAQPage",
            kind=RemediationKind.MISSING_SCHEMA,
            title="Add FAQPage",
            reason="missing",
            impact=impact,
            confidence=conf,
            difficulty=diff,
            priority=(impact * conf) / diff,
            schema_target=SchemaRemediationTarget.FAQ_PAGE,
            dedupe_key="MISSING_SCHEMA|FAQPage",
        )
        return PatchPrioritizationResult(opportunities=[opp], total_candidates=1, selected_count=1)


@dataclass
class FakeJsonLd:
    calls: list[str] = field(default_factory=list)

    def generate(
        self, prioritization: Any, *, facts: Any, intent_evaluations: Any = ()
    ) -> JsonLdGenerationResult:
        self.calls.append("reflect_jsonld")
        payload = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": "Q?",
                    "acceptedAnswer": {"@type": "Answer", "text": "A"},
                }
            ],
        }
        return JsonLdGenerationResult(
            generated=[
                GeneratedJsonLd(
                    opportunity_id="missing_schema:FAQPage",
                    schema_type=SchemaRemediationTarget.FAQ_PAGE,
                    payload=payload,
                    json_text='{"@type":"FAQPage"}',
                )
            ],
            skipped=[],
        )


@dataclass
class FakeFormatter:
    calls: list[str] = field(default_factory=list)

    def format_all(
        self, generated: Any, *, html: str, file_path: str = "index.html"
    ) -> PatchFormatResult:
        self.calls.append("reflect_format")
        return PatchFormatResult(
            patches=[
                FormattedPatch(
                    opportunity_id="missing_schema:FAQPage",
                    schema_type=SchemaRemediationTarget.FAQ_PAGE,
                    file_path=file_path,
                    status=PatchFormatStatus.APPLIED,
                    patched_html=html.replace(
                        "</head>",
                        '<script type="application/ld+json">{"@type":"FAQPage"}</script></head>',
                    ),
                    message="ok",
                )
            ]
        )


@dataclass
class FakeProjected:
    calls: list[str] = field(default_factory=list)

    def project(self, generated: Any, **kwargs: Any) -> ProjectedScoreBatchResult:
        self.calls.append("reflect_projected")
        cur = _score(40.0)
        proj = _score(55.0)
        return ProjectedScoreBatchResult(
            projections=[
                ProjectedScoreResult(
                    opportunity_id="missing_schema:FAQPage",
                    schema_type=SchemaRemediationTarget.FAQ_PAGE,
                    current_score=40.0,
                    projected_score=55.0,
                    delta=15.0,
                    current_breakdown=cur,
                    projected_breakdown=proj,
                )
            ]
        )


@dataclass
class FakePR:
    calls: list[str] = field(default_factory=list)

    def create_remediation_pr(self, request: Any) -> Any:
        self.calls.append("reflect_pr")
        from app.schemas.github_pr import PREngineResult

        return PREngineResult(
            source_repository=request.source_repo,
            fork_repository="bot/demo",
            target_branch=request.target_branch,
            generated_branch="findableai/remediation/x",
            commit_sha="abc",
            pr_number=1,
            pr_url="https://example.com/pr/1",
            changed_files=["index.html"],
            applied_opportunity_ids=["missing_schema:FAQPage"],
            current_score=40.0,
            projected_score=55.0,
            delta=15.0,
            pr_body="# report\n",
            markdown_scan_id=request.scan_id,
        )


def _observation(**kwargs: Any) -> ObservationInput:
    base = dict(
        scan_id="11111111-1111-1111-1111-111111111111",
        business_context="A local restaurant serving lunch and dinner with patio seating.",
        chunks=[
            OrchestrationChunk(
                id="c1",
                url="https://ex.com",
                dom_path="/p[1]",
                content="Welcome to Bistro",
                tag="p",
                word_count=3,
            )
        ],
        html_documents=["<html><head></head><body>Hi</body></html>"],
        create_pr=False,
    )
    base.update(kwargs)
    return ObservationInput(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_happy_path_stage_order_no_remediation(monkeypatch: pytest.MonkeyPatch):
    intent = FakeIntent()
    entail = FakeEntailment()
    contra = FakeContradiction()
    scorer = FakeScorer()
    prio = FakePrioritizer(empty=True)
    jsonld = FakeJsonLd()
    formatter = FakeFormatter()
    projected = FakeProjected()
    pr = FakePR()

    # analyze_schema_org is real; fine for empty/minimal HTML
    dag = FindableAIDAG(
        llm_client=LLMClient(max_calls=35, instructor_client=object()),
        intent_generator=intent,  # type: ignore[arg-type]
        entailment_engine=entail,  # type: ignore[arg-type]
        contradiction_detector=contra,  # type: ignore[arg-type]
        scorer=scorer,  # type: ignore[arg-type]
        patch_prioritizer=prio,  # type: ignore[arg-type]
        jsonld_generator=jsonld,  # type: ignore[arg-type]
        patch_formatter=formatter,  # type: ignore[arg-type]
        projected_score=projected,  # type: ignore[arg-type]
        pr_engine=pr,  # type: ignore[arg-type]
    )
    result = await dag.run(_observation())
    assert result.success is True
    assert result.final_state is ScanPhase.STOP
    assert result.stage_trace == [
        "observe",
        "plan",
        "act",
        "verify",
        "reflect",
        "stop",
    ]
    assert result.remediation_available is False
    assert result.pr_created is False
    assert jsonld.calls == []
    assert pr.calls == []
    assert intent.calls == ["plan"]
    assert entail.calls == ["act"]


@pytest.mark.asyncio
async def test_remediation_path_without_pr():
    dag = FindableAIDAG(
        llm_client=LLMClient(max_calls=35, instructor_client=object()),
        intent_generator=FakeIntent(),  # type: ignore[arg-type]
        entailment_engine=FakeEntailment(),  # type: ignore[arg-type]
        contradiction_detector=FakeContradiction(),  # type: ignore[arg-type]
        scorer=FakeScorer(),  # type: ignore[arg-type]
        patch_prioritizer=FakePrioritizer(empty=False),  # type: ignore[arg-type]
        jsonld_generator=FakeJsonLd(),  # type: ignore[arg-type]
        patch_formatter=FakeFormatter(),  # type: ignore[arg-type]
        projected_score=FakeProjected(),  # type: ignore[arg-type]
        pr_engine=FakePR(),  # type: ignore[arg-type]
        markdown_generator=lambda report: f"# MD {report.scan_id}\n",
    )
    result = await dag.run(_observation(create_pr=False))
    assert result.success
    assert result.remediation_available
    assert result.patch_count == 1
    assert result.pr_body is not None
    assert result.pr_created is False


@pytest.mark.asyncio
async def test_create_pr_invokes_engine():
    pr = FakePR()
    dag = FindableAIDAG(
        llm_client=LLMClient(max_calls=35, instructor_client=object()),
        intent_generator=FakeIntent(),  # type: ignore[arg-type]
        entailment_engine=FakeEntailment(),  # type: ignore[arg-type]
        contradiction_detector=FakeContradiction(),  # type: ignore[arg-type]
        scorer=FakeScorer(),  # type: ignore[arg-type]
        patch_prioritizer=FakePrioritizer(empty=False),  # type: ignore[arg-type]
        jsonld_generator=FakeJsonLd(),  # type: ignore[arg-type]
        patch_formatter=FakeFormatter(),  # type: ignore[arg-type]
        projected_score=FakeProjected(),  # type: ignore[arg-type]
        pr_engine=pr,  # type: ignore[arg-type]
        markdown_generator=lambda report: "# body\n",
    )
    result = await dag.run(_observation(create_pr=True, source_repo="acme/demo-site"))
    assert result.success
    assert result.pr_created
    assert pr.calls == ["reflect_pr"]


@pytest.mark.asyncio
async def test_create_pr_false_skips_engine():
    pr = FakePR()
    dag = FindableAIDAG(
        llm_client=LLMClient(max_calls=35, instructor_client=object()),
        intent_generator=FakeIntent(),  # type: ignore[arg-type]
        entailment_engine=FakeEntailment(),  # type: ignore[arg-type]
        contradiction_detector=FakeContradiction(),  # type: ignore[arg-type]
        scorer=FakeScorer(),  # type: ignore[arg-type]
        patch_prioritizer=FakePrioritizer(empty=False),  # type: ignore[arg-type]
        jsonld_generator=FakeJsonLd(),  # type: ignore[arg-type]
        patch_formatter=FakeFormatter(),  # type: ignore[arg-type]
        projected_score=FakeProjected(),  # type: ignore[arg-type]
        pr_engine=pr,  # type: ignore[arg-type]
        markdown_generator=lambda report: "# body\n",
    )
    await dag.run(_observation(create_pr=False, source_repo="acme/demo-site"))
    assert pr.calls == []


@pytest.mark.asyncio
async def test_plan_failure_stops_pipeline():
    dag = FindableAIDAG(
        llm_client=LLMClient(max_calls=35, instructor_client=object()),
        intent_generator=FakeIntent(fail=True),  # type: ignore[arg-type]
        entailment_engine=FakeEntailment(),  # type: ignore[arg-type]
        contradiction_detector=FakeContradiction(),  # type: ignore[arg-type]
        scorer=FakeScorer(),  # type: ignore[arg-type]
        patch_prioritizer=FakePrioritizer(),  # type: ignore[arg-type]
    )
    result = await dag.run(_observation())
    assert result.success is False
    assert result.final_state is ScanPhase.PLAN
    assert "act" not in result.stage_trace
    assert result.error_reason == "intent_generation_failed"


@pytest.mark.asyncio
async def test_act_failure_does_not_verify():
    entail = FakeEntailment(fail=True)
    contra = FakeContradiction()
    dag = FindableAIDAG(
        llm_client=LLMClient(max_calls=35, instructor_client=object()),
        intent_generator=FakeIntent(),  # type: ignore[arg-type]
        entailment_engine=entail,  # type: ignore[arg-type]
        contradiction_detector=contra,  # type: ignore[arg-type]
        scorer=FakeScorer(),  # type: ignore[arg-type]
        patch_prioritizer=FakePrioritizer(),  # type: ignore[arg-type]
    )
    result = await dag.run(_observation())
    assert result.success is False
    assert result.final_state is ScanPhase.ACT
    assert contra.calls == []


@pytest.mark.asyncio
async def test_shared_llm_client_injected():
    llm = LLMClient(max_calls=35, instructor_client=object())
    intent = FakeIntent()
    entail = FakeEntailment()
    dag = FindableAIDAG(
        llm_client=llm,
        intent_generator=intent,  # type: ignore[arg-type]
        entailment_engine=entail,  # type: ignore[arg-type]
        contradiction_detector=FakeContradiction(),  # type: ignore[arg-type]
        scorer=FakeScorer(),  # type: ignore[arg-type]
        patch_prioritizer=FakePrioritizer(),  # type: ignore[arg-type]
    )
    assert dag.llm_client is llm
    result = await dag.run(_observation())
    assert result.llm_calls_made == 0  # fakes do not consume budget
    assert result.llm_calls_remaining == 35


@pytest.mark.asyncio
async def test_empty_chunks_still_complete():
    dag = FindableAIDAG(
        llm_client=LLMClient(max_calls=35, instructor_client=object()),
        intent_generator=FakeIntent(),  # type: ignore[arg-type]
        entailment_engine=FakeEntailment(),  # type: ignore[arg-type]
        contradiction_detector=FakeContradiction(),  # type: ignore[arg-type]
        scorer=FakeScorer(),  # type: ignore[arg-type]
        patch_prioritizer=FakePrioritizer(empty=True),  # type: ignore[arg-type]
    )
    result = await dag.run(_observation(chunks=[], html_documents=[]))
    assert result.success
    assert result.final_state is ScanPhase.STOP
