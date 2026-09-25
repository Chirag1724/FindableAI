"""End-to-end orchestration with injectable fakes (no LLM/GitHub/network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest

from app.core.llm import LLMClient
from app.engines.scorer import ScoreInputs
from app.orchestration.dag import FindableAIDAG, ObservationInput, run_scan
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
    for cat in IntentCategory:
        for j in range(1, 4):
            queries.append(
                IntentQuery(
                    intent_id=f"{cat.value}_{j:02d}",
                    category=cat,
                    query=f"Question about {cat.value} number {j}?",
                    difficulty="easy",
                    expected_evidence_type="page text",
                )
            )
    return IntentBatch(business_type="restaurant", queries=queries)


def _eval(intent_id: str) -> IntentEvaluation:
    return IntentEvaluation(
        intent_id=intent_id,
        query="Q?",
        status=EntailmentStatus.UNKNOWN,
        reasoning="fixture",
        evidence=[],
        confidence=0.0,
    )


def _schema_report(*, score: float = 0.0) -> SchemaOrgReport:
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
                present=False,
                valid=False,
                occurrences=0,
                source_count=0,
            )
            for name in required
        ],
        score=score,
        issues=[],
    )


def _score(f: float = 42.0) -> ScoreBreakdown:
    return ScoreBreakdown(
        f_score=f,
        s_ans=f,
        s_con=100.0,
        s_str=0.0,
        s_acc=50.0,
        weights=ScoreWeights(),
        schema_report=_schema_report(),
    )


@dataclass
class Trace:
    events: list[str] = field(default_factory=list)


@dataclass
class Engines:
    trace: Trace = field(default_factory=Trace)
    opportunities: int = 0
    fail_stage: str | None = None

    async def generate_intents(self, *, business_context: str) -> IntentBatch:
        self.trace.events.append("plan")
        if self.fail_stage == "plan":
            raise RuntimeError("plan fail")
        assert len(business_context) >= 20
        return _intent_batch()

    async def evaluate_intents(self, *, intents: Any, scan_id: UUID) -> list[IntentEvaluation]:
        self.trace.events.append("act")
        if self.fail_stage == "act":
            raise RuntimeError("act fail")
        assert isinstance(scan_id, UUID)
        return [_eval(q.intent_id) for q in intents]

    async def detect_contradictions(self, *, chunks: Any) -> list:
        self.trace.events.append("verify_contradiction")
        if self.fail_stage == "contradiction":
            raise RuntimeError("contradiction fail")
        return []

    def score(self, inputs: ScoreInputs) -> ScoreBreakdown:
        self.trace.events.append("verify_score")
        if self.fail_stage == "score":
            raise RuntimeError("score fail")
        return _score()

    def prioritize(self, inputs: PatchPrioritizerInput | dict) -> PatchPrioritizationResult:
        self.trace.events.append("reflect_prioritize")
        if self.fail_stage == "prioritize":
            raise RuntimeError("prioritize fail")
        if self.opportunities <= 0:
            return PatchPrioritizationResult(opportunities=[], total_candidates=0, selected_count=0)
        impact, conf, diff = 80.0, 1.0, 2
        opp = RemediationOpportunity(
            opportunity_id="missing_schema:FAQPage",
            kind=RemediationKind.MISSING_SCHEMA,
            title="Add FAQPage",
            reason="missing FAQPage",
            impact=impact,
            confidence=conf,
            difficulty=diff,
            priority=(impact * conf) / diff,
            schema_target=SchemaRemediationTarget.FAQ_PAGE,
            dedupe_key="MISSING_SCHEMA|FAQPage",
        )
        return PatchPrioritizationResult(opportunities=[opp], total_candidates=1, selected_count=1)

    def generate(
        self, prioritization: Any, *, facts: Any, intent_evaluations: Any = ()
    ) -> JsonLdGenerationResult:
        self.trace.events.append("reflect_jsonld")
        if self.fail_stage == "jsonld":
            raise RuntimeError("jsonld fail")
        payload = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": "Hours?",
                    "acceptedAnswer": {"@type": "Answer", "text": "9-5"},
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

    def format_all(
        self, generated: Any, *, html: str, file_path: str = "index.html"
    ) -> PatchFormatResult:
        self.trace.events.append("reflect_format")
        if self.fail_stage == "format":
            raise RuntimeError("format fail")
        return PatchFormatResult(
            patches=[
                FormattedPatch(
                    opportunity_id="missing_schema:FAQPage",
                    schema_type=SchemaRemediationTarget.FAQ_PAGE,
                    file_path=file_path,
                    status=PatchFormatStatus.APPLIED,
                    patched_html=html + "<!--patched-->",
                    message="ok",
                )
            ]
        )

    def project(self, generated: Any, **kwargs: Any) -> ProjectedScoreBatchResult:
        self.trace.events.append("reflect_projected")
        if self.fail_stage == "projected":
            raise RuntimeError("projected fail")
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

    def create_remediation_pr(self, request: Any) -> Any:
        self.trace.events.append("reflect_pr")
        if self.fail_stage == "pr":
            raise RuntimeError("pr fail")
        from app.schemas.github_pr import PREngineResult

        return PREngineResult(
            source_repository=request.source_repo,
            fork_repository="bot/demo",
            target_branch=request.target_branch,
            generated_branch="findableai/remediation/x",
            commit_sha="deadbeef",
            pr_number=7,
            pr_url="https://example.com/pr/7",
            changed_files=["index.html"],
            applied_opportunity_ids=["missing_schema:FAQPage"],
            current_score=40.0,
            projected_score=55.0,
            delta=15.0,
            pr_body="# report\n",
            markdown_scan_id=request.scan_id,
        )


def _dag(engines: Engines, *, create_markdown: bool = True) -> FindableAIDAG:
    return FindableAIDAG(
        llm_client=LLMClient(max_calls=35, instructor_client=object()),
        intent_generator=engines,  # type: ignore[arg-type]
        entailment_engine=engines,  # type: ignore[arg-type]
        contradiction_detector=engines,  # type: ignore[arg-type]
        scorer=engines,  # type: ignore[arg-type]
        patch_prioritizer=engines,  # type: ignore[arg-type]
        jsonld_generator=engines,  # type: ignore[arg-type]
        patch_formatter=engines,  # type: ignore[arg-type]
        projected_score=engines,  # type: ignore[arg-type]
        pr_engine=engines,  # type: ignore[arg-type]
        markdown_generator=(lambda report: f"# MD {report.scan_id}\n") if create_markdown else None,
    )


def _obs(**kwargs: Any) -> ObservationInput:
    base: dict[str, Any] = dict(
        scan_id="22222222-2222-2222-2222-222222222222",
        business_context="Neighborhood bistro with lunch specials and patio seating available.",
        chunks=[
            OrchestrationChunk(
                id="c1",
                url="https://ex.com/",
                dom_path="/main/p[1]",
                content="Welcome to the bistro",
                tag="p",
                word_count=4,
            )
        ],
        html_documents=["<html><head></head><body>Hi</body></html>"],
        create_pr=False,
    )
    base.update(kwargs)
    return ObservationInput(**base)


@pytest.mark.asyncio
async def test_e2e_no_remediation_success():
    engines = Engines(opportunities=0)
    result = await _dag(engines).run(_obs())
    assert result.success is True
    assert result.final_state is ScanPhase.STOP
    assert result.remediation_available is False
    assert result.pr_created is False
    assert result.stage_trace == [
        "observe",
        "plan",
        "act",
        "verify",
        "reflect",
        "stop",
    ]
    assert "reflect_jsonld" not in engines.trace.events
    assert "reflect_pr" not in engines.trace.events
    assert result.intent_count == 30
    assert result.evaluation_count == 30
    assert result.llm_calls_remaining == 35


@pytest.mark.asyncio
async def test_e2e_remediation_with_pr():
    engines = Engines(opportunities=1)
    result = await _dag(engines).run(_obs(create_pr=True, source_repo="acme/bistro"))
    assert result.success is True
    assert result.remediation_available is True
    assert result.pr_created is True
    assert result.pr_result is not None
    assert result.pr_result.pr_number == 7
    assert "reflect_pr" in engines.trace.events
    assert result.patch_count == 1
    assert result.projected_scores[0].delta == 15.0


@pytest.mark.asyncio
async def test_e2e_create_pr_false_skips_github():
    engines = Engines(opportunities=1)
    result = await _dag(engines).run(_obs(create_pr=False, source_repo="acme/bistro"))
    assert result.success
    assert result.remediation_available
    assert result.pr_body is not None
    assert "reflect_pr" not in engines.trace.events
    assert result.pr_created is False


@pytest.mark.asyncio
async def test_e2e_failure_halts_later_stages():
    engines = Engines(fail_stage="act")
    result = await _dag(engines).run(_obs())
    assert result.success is False
    assert result.final_state is ScanPhase.ACT
    assert "verify_contradiction" not in engines.trace.events
    assert "reflect_prioritize" not in engines.trace.events
    assert result.error_reason == "entailment_failed"


@pytest.mark.asyncio
async def test_e2e_prioritize_failure():
    engines = Engines(opportunities=1, fail_stage="prioritize")
    result = await _dag(engines).run(_obs())
    assert result.success is False
    assert result.final_state is ScanPhase.REFLECT
    assert result.error_reason == "prioritization_failed"
    assert "reflect_jsonld" not in engines.trace.events


@pytest.mark.asyncio
async def test_e2e_pr_failure_surfaces():
    engines = Engines(opportunities=1, fail_stage="pr")
    result = await _dag(engines).run(_obs(create_pr=True, source_repo="acme/bistro"))
    assert result.success is False
    assert result.error_reason == "pr_failed"
    assert result.pr_created is False


@pytest.mark.asyncio
async def test_run_scan_helper():
    engines = Engines(opportunities=0)
    dag = _dag(engines)
    result = await run_scan(_obs(), dag=dag)
    assert result.success
    assert result.final_state is ScanPhase.STOP


@pytest.mark.asyncio
async def test_shared_budget_exposed_on_result():
    llm = LLMClient(max_calls=35, instructor_client=object())
    engines = Engines(opportunities=0)
    dag = FindableAIDAG(
        llm_client=llm,
        intent_generator=engines,  # type: ignore[arg-type]
        entailment_engine=engines,  # type: ignore[arg-type]
        contradiction_detector=engines,  # type: ignore[arg-type]
        scorer=engines,  # type: ignore[arg-type]
        patch_prioritizer=engines,  # type: ignore[arg-type]
    )
    result = await dag.run(_obs())
    assert result.llm_calls_made == llm.calls_made
    assert result.llm_calls_remaining == llm.remaining_calls
    assert dag.llm_client is llm
