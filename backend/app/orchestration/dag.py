"""FindableAI DAG orchestrator (P2-4.1 / P2-4.2).

Coordinates existing Phase 0-3 engines. Does not duplicate intelligence logic.
Uses one scan-scoped ``BudgetGuard`` shared by every LLM consumer.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.budget import BudgetGuard, LLMBudgetExceededError, default_scan_budget
from app.core.llm import LLMClient
from app.engines.contradiction import ContradictionDetector, EvidenceChunk, extract_facts
from app.engines.entailment_engine import DEFAULT_TOP_K, EntailmentEngine, Retriever
from app.engines.intent_generator import IntentGenerator
from app.engines.jsonld_generator import JsonLdGenerator
from app.engines.patch_formatter import PatchFormatter
from app.engines.patch_prioritizer import PatchPrioritizer
from app.engines.projected_score import ProjectedScoreCalculator
from app.engines.scorer import ScoreInputs, Scorer, analyze_schema_org
from app.github.pr_engine import GitHubPRService, PREngineError
from app.github.pr_markdown import generate_pr_markdown
from app.orchestration.errors import (
    MissingStageInputError,
    OrchestrationError,
    StageExecutionError,
)
from app.orchestration.result import OrchestrationResult
from app.orchestration.state import (
    OrchestrationChunk,
    ScanContext,
    ScanPhase,
)
from app.schemas.github_pr import PREngineRequest, PRFileChange, PRReportData
from app.schemas.patching import (
    BusinessFacts,
    PatchFormatStatus,
    PatchPrioritizerInput,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObservationInput:
    """Caller-supplied OBSERVE artifacts (no crawler inside the DAG)."""

    scan_id: str
    business_context: str
    chunks: Sequence[Any] = ()
    html_documents: Sequence[str] = ()
    business_facts: BusinessFacts | None = None
    create_pr: bool = False
    source_repo: str | None = None
    target_branch: str = "main"
    html_file_path: str = "index.html"


def _observe_chunks_retriever(chunks: Sequence[OrchestrationChunk]) -> Retriever:
    """Adapt OBSERVE evidence to the EntailmentEngine retriever contract.

    Does not re-implement hybrid search. Returns the first ``k`` observe chunks
    in stable order so ACT can run without a DB when the caller supplied
    crawler output in-memory. Inject ``retriever=default_hybrid_retriever``
    (or a custom callable) to use Contract-1 search by ``scan_id`` instead.
    """

    snapshot = list(chunks)

    async def _retrieve(
        query: str,
        scan_id: uuid.UUID,
        k: int = DEFAULT_TOP_K,
    ) -> Sequence[OrchestrationChunk]:
        _ = (query, scan_id)
        limit = max(0, int(k))
        return snapshot[:limit]

    return _retrieve


def _as_orchestration_chunk(index: int, raw: Any) -> OrchestrationChunk:
    chunk_id = getattr(raw, "id", None)
    if chunk_id is None:
        chunk_id = f"chunk-{index}"
    url = getattr(raw, "url", "") or ""
    dom_path = getattr(raw, "dom_path", "") or f"/chunk[{index}]"
    content = getattr(raw, "content", "") or ""
    tag = getattr(raw, "tag", "p") or "p"
    word_count = getattr(raw, "word_count", None)
    if word_count is None:
        word_count = len(str(content).split())
    return OrchestrationChunk(
        id=str(chunk_id),
        url=str(url),
        dom_path=str(dom_path),
        content=str(content),
        tag=str(tag),
        word_count=int(word_count),
    )


def _parse_scan_uuid(scan_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(scan_id))
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"findableai:scan:{scan_id}")


class FindableAIDAG:
    """OBSERVE -> PLAN -> ACT -> VERIFY -> REFLECT -> STOP orchestrator."""

    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        budget_guard: BudgetGuard | None = None,
        intent_generator: IntentGenerator | None = None,
        entailment_engine: EntailmentEngine | None = None,
        contradiction_detector: ContradictionDetector | None = None,
        scorer: Scorer | None = None,
        patch_prioritizer: PatchPrioritizer | None = None,
        jsonld_generator: JsonLdGenerator | None = None,
        patch_formatter: PatchFormatter | None = None,
        projected_score: ProjectedScoreCalculator | None = None,
        pr_engine: GitHubPRService | None = None,
        retriever: Retriever | None = None,
        markdown_generator: Callable[[PRReportData], str] | None = None,
    ) -> None:
        # One scan-scoped BudgetGuard shared by every LLM consumer in this DAG.
        if llm_client is not None and budget_guard is not None:
            if llm_client.budget_guard is not budget_guard:
                raise ValueError("llm_client.budget_guard must be the same object as budget_guard")
            self._budget = budget_guard
            self._llm = llm_client
        elif llm_client is not None:
            self._llm = llm_client
            self._budget = llm_client.budget_guard
        else:
            self._budget = budget_guard or default_scan_budget()
            self._llm = LLMClient(budget_guard=self._budget)

        self._intent = intent_generator or IntentGenerator(llm_client=self._llm)
        self._entailment_injected = entailment_engine
        self._retriever_injected = retriever
        # Built lazily in ACT when not injected so OBSERVE chunks can feed NLI.
        self._entailment = entailment_engine
        self._contradiction = contradiction_detector or ContradictionDetector(llm_client=self._llm)
        self._scorer = scorer or Scorer()
        self._prioritizer = patch_prioritizer or PatchPrioritizer()
        self._jsonld = jsonld_generator or JsonLdGenerator()
        self._formatter = patch_formatter or PatchFormatter()
        self._projected = projected_score or ProjectedScoreCalculator()
        self._pr_engine = pr_engine
        self._markdown = markdown_generator or generate_pr_markdown

    @property
    def llm_client(self) -> LLMClient:
        return self._llm

    @property
    def budget_guard(self) -> BudgetGuard:
        return self._budget

    async def run(self, observation: ObservationInput) -> OrchestrationResult:
        ctx = ScanContext(
            scan_id=str(observation.scan_id).strip(),
            business_context=observation.business_context,
            create_pr=bool(observation.create_pr),
            source_repo=observation.source_repo,
            target_branch=observation.target_branch or "main",
            html_file_path=observation.html_file_path or "index.html",
            business_facts=observation.business_facts or BusinessFacts(),
            budget_guard=self._budget,
        )
        if not ctx.scan_id:
            raise MissingStageInputError("scan_id is required", stage=ScanPhase.OBSERVE.value)

        try:
            await self._run_observe(ctx, observation)
            ctx.advance(ScanPhase.PLAN)

            await self._run_plan(ctx)
            ctx.advance(ScanPhase.ACT)

            await self._run_act(ctx)
            ctx.advance(ScanPhase.VERIFY)

            await self._run_verify(ctx)
            ctx.advance(ScanPhase.REFLECT)

            await self._run_reflect(ctx)
            ctx.advance(ScanPhase.STOP)
            ctx.completed_stages.append("stop")
            ctx.stage_trace.append("stop")

            return self._build_result(ctx, success=True)
        except OrchestrationError as exc:
            logger.error(
                "Orchestration failed scan_id=%s state=%s reason=%s",
                ctx.scan_id,
                ctx.state.value,
                exc.reason,
            )
            return self._build_result(
                ctx,
                success=False,
                error=str(exc),
                error_reason=exc.reason,
            )
        except LLMBudgetExceededError as exc:
            logger.error(
                "Orchestration budget exhausted scan_id=%s state=%s used=%s limit=%s",
                ctx.scan_id,
                ctx.state.value,
                exc.used,
                exc.limit,
            )
            return self._build_result(
                ctx,
                success=False,
                error=str(exc),
                error_reason="budget_exhausted",
            )
        except Exception as exc:
            logger.error(
                "Orchestration unexpected failure scan_id=%s state=%s type=%s",
                ctx.scan_id,
                ctx.state.value,
                type(exc).__name__,
            )
            return self._build_result(
                ctx,
                success=False,
                error=str(exc),
                error_reason="unexpected_error",
            )

    async def _run_observe(self, ctx: ScanContext, observation: ObservationInput) -> None:
        ctx.stage_trace.append("observe")
        if ctx.state is not ScanPhase.OBSERVE:
            raise StageExecutionError(
                f"OBSERVE requires state OBSERVE; got {ctx.state.value}",
                stage="observe",
            )
        if (
            not isinstance(observation.business_context, str)
            or not observation.business_context.strip()
        ):
            raise MissingStageInputError(
                "business_context is required",
                stage="observe",
            )

        ctx.chunks = [
            _as_orchestration_chunk(i, raw) for i, raw in enumerate(list(observation.chunks))
        ]
        ctx.html_documents = [str(doc) for doc in observation.html_documents]
        if not ctx.html_documents:
            # Empty HTML is valid; schema score will be zero.
            ctx.html_documents = []

        ctx.completed_stages.append("observe")
        logger.info(
            "OBSERVE complete scan_id=%s chunks=%s html_docs=%s",
            ctx.scan_id,
            len(ctx.chunks),
            len(ctx.html_documents),
        )

    async def _run_plan(self, ctx: ScanContext) -> None:
        ctx.stage_trace.append("plan")
        try:
            batch = await self._intent.generate_intents(business_context=ctx.business_context)
        except LLMBudgetExceededError as exc:
            raise StageExecutionError(
                f"PLAN budget exhausted: {exc}",
                stage="plan",
                reason="budget_exhausted",
            ) from exc
        except Exception as exc:
            raise StageExecutionError(
                f"PLAN intent generation failed: {exc}",
                stage="plan",
                reason="intent_generation_failed",
            ) from exc
        if batch is None or len(batch.queries) != 30:
            raise StageExecutionError(
                "PLAN expected IntentBatch with exactly 30 queries",
                stage="plan",
                reason="invalid_intent_batch",
            )
        ctx.intents = batch
        ctx.completed_stages.append("plan")
        logger.info(
            "PLAN complete scan_id=%s intents=%s llm_calls=%s",
            ctx.scan_id,
            len(batch.queries),
            self._llm.calls_made,
        )

    def _resolve_entailment(self, ctx: ScanContext) -> EntailmentEngine:
        if self._entailment_injected is not None:
            return self._entailment_injected
        if self._entailment is not None:
            return self._entailment
        retriever = self._retriever_injected
        if retriever is None:
            retriever = _observe_chunks_retriever(ctx.chunks)
        self._entailment = EntailmentEngine(
            llm_client=self._llm,
            retriever=retriever,
        )
        return self._entailment

    async def _run_act(self, ctx: ScanContext) -> None:
        ctx.stage_trace.append("act")
        if ctx.intents is None:
            raise MissingStageInputError("intents missing for ACT", stage="act")
        scan_uuid = _parse_scan_uuid(ctx.scan_id)
        entailment = self._resolve_entailment(ctx)
        try:
            evaluations = await entailment.evaluate_intents(
                intents=ctx.intents.queries,
                scan_id=scan_uuid,
            )
        except LLMBudgetExceededError as exc:
            raise StageExecutionError(
                f"ACT budget exhausted: {exc}",
                stage="act",
                reason="budget_exhausted",
            ) from exc
        except Exception as exc:
            raise StageExecutionError(
                f"ACT entailment failed: {exc}",
                stage="act",
                reason="entailment_failed",
            ) from exc
        ctx.evaluations = list(evaluations)
        ctx.completed_stages.append("act")
        logger.info(
            "ACT complete scan_id=%s evaluations=%s llm_calls=%s",
            ctx.scan_id,
            len(ctx.evaluations),
            self._llm.calls_made,
        )

    async def _run_verify(self, ctx: ScanContext) -> None:
        ctx.stage_trace.append("verify")
        chunks: Sequence[EvidenceChunk] = ctx.chunks  # type: ignore[assignment]
        try:
            contradictions = await self._contradiction.detect_contradictions(chunks=chunks)
        except LLMBudgetExceededError as exc:
            raise StageExecutionError(
                f"VERIFY budget exhausted: {exc}",
                stage="verify",
                reason="budget_exhausted",
            ) from exc
        except Exception as exc:
            raise StageExecutionError(
                f"VERIFY contradiction detection failed: {exc}",
                stage="verify",
                reason="contradiction_failed",
            ) from exc
        ctx.contradictions = list(contradictions)

        try:
            schema_report = analyze_schema_org(ctx.html_documents)
        except Exception as exc:
            raise StageExecutionError(
                f"VERIFY schema analysis failed: {exc}",
                stage="verify",
                reason="schema_analysis_failed",
            ) from exc
        ctx.schema_report = schema_report

        fact_count: int | None = None
        try:
            fact_count = len(extract_facts(chunks))
        except Exception:
            fact_count = None

        try:
            score = self._scorer.score(
                ScoreInputs(
                    intent_evaluations=ctx.evaluations,
                    contradictions=ctx.contradictions,
                    html_documents=ctx.html_documents,
                    chunks=ctx.chunks,
                    extracted_fact_count=fact_count,
                )
            )
        except Exception as exc:
            raise StageExecutionError(
                f"VERIFY scoring failed: {exc}",
                stage="verify",
                reason="scoring_failed",
            ) from exc
        ctx.score = score
        ctx.completed_stages.append("verify")
        logger.info(
            "VERIFY complete scan_id=%s f_score=%.2f contradictions=%s",
            ctx.scan_id,
            score.f_score,
            len(ctx.contradictions),
        )

    async def _run_reflect(self, ctx: ScanContext) -> None:
        ctx.stage_trace.append("reflect")
        if ctx.score is None or ctx.schema_report is None:
            raise MissingStageInputError(
                "score/schema_report required for REFLECT", stage="reflect"
            )

        try:
            prioritization = self._prioritizer.prioritize(
                PatchPrioritizerInput(
                    intent_evaluations=ctx.evaluations,
                    contradictions=ctx.contradictions,
                    score_breakdown=ctx.score,
                    schema_report=ctx.schema_report,
                )
            )
        except Exception as exc:
            raise StageExecutionError(
                f"REFLECT prioritization failed: {exc}",
                stage="reflect",
                reason="prioritization_failed",
            ) from exc

        ctx.prioritization = prioritization
        ctx.opportunities = list(prioritization.opportunities)

        if prioritization.selected_count == 0:
            ctx.remediation_available = False
            ctx.completed_stages.append("reflect")
            logger.info(
                "REFLECT complete scan_id=%s no actionable remediation",
                ctx.scan_id,
            )
            return

        try:
            generation = self._jsonld.generate(
                prioritization,
                facts=ctx.business_facts,
                intent_evaluations=ctx.evaluations,
            )
        except Exception as exc:
            raise StageExecutionError(
                f"REFLECT JSON-LD generation failed: {exc}",
                stage="reflect",
                reason="jsonld_failed",
            ) from exc
        ctx.generated_jsonld = list(generation.generated)
        ctx.jsonld_skipped = list(generation.skipped)

        if not ctx.generated_jsonld:
            ctx.remediation_available = False
            ctx.completed_stages.append("reflect")
            logger.info(
                "REFLECT complete scan_id=%s no JSON-LD generated (insufficient evidence)",
                ctx.scan_id,
            )
            return

        html = (
            ctx.html_documents[0]
            if ctx.html_documents
            else ("<!DOCTYPE html><html><head></head><body></body></html>")
        )
        try:
            format_result = self._formatter.format_all(
                ctx.generated_jsonld,
                html=html,
                file_path=ctx.html_file_path,
            )
        except Exception as exc:
            raise StageExecutionError(
                f"REFLECT patch formatting failed: {exc}",
                stage="reflect",
                reason="format_failed",
            ) from exc
        ctx.patches = list(format_result.patches)

        applied = [p for p in ctx.patches if p.status is PatchFormatStatus.APPLIED]
        if not applied:
            ctx.remediation_available = False
            ctx.completed_stages.append("reflect")
            logger.info(
                "REFLECT complete scan_id=%s no APPLIED patches",
                ctx.scan_id,
            )
            return

        ctx.remediation_available = True
        try:
            batch = self._projected.project(
                ctx.generated_jsonld,
                score_inputs=ScoreInputs(
                    intent_evaluations=ctx.evaluations,
                    contradictions=ctx.contradictions,
                    html_documents=ctx.html_documents or [html],
                    chunks=ctx.chunks,
                ),
                current_breakdown=ctx.score,
                file_path=ctx.html_file_path,
            )
        except Exception as exc:
            raise StageExecutionError(
                f"REFLECT projected score failed: {exc}",
                stage="reflect",
                reason="projected_score_failed",
            ) from exc
        ctx.projected_scores = list(batch.projections)

        report = self._build_pr_report(ctx)
        try:
            ctx.pr_body = self._markdown(report)
        except Exception as exc:
            raise StageExecutionError(
                f"REFLECT PR markdown failed: {exc}",
                stage="reflect",
                reason="markdown_failed",
            ) from exc

        if ctx.create_pr:
            if self._pr_engine is None:
                raise StageExecutionError(
                    "create_pr=True but no pr_engine injected",
                    stage="reflect",
                    reason="missing_pr_engine",
                )
            if not ctx.source_repo:
                raise MissingStageInputError(
                    "source_repo required when create_pr=True",
                    stage="reflect",
                )
            try:
                ctx.pr_result = self._pr_engine.create_remediation_pr(
                    PREngineRequest(
                        source_repo=ctx.source_repo,
                        target_branch=ctx.target_branch,
                        scan_id=ctx.scan_id,
                        patches=applied,
                        projections=ctx.projected_scores,
                        opportunities=ctx.opportunities,
                        intent_evaluations=ctx.evaluations,
                    )
                )
            except PREngineError as exc:
                raise StageExecutionError(
                    f"REFLECT GitHub PR failed: {exc}",
                    stage="reflect",
                    reason=exc.reason,
                ) from exc
            except Exception as exc:
                raise StageExecutionError(
                    f"REFLECT GitHub PR failed: {exc}",
                    stage="reflect",
                    reason="pr_failed",
                ) from exc

        ctx.completed_stages.append("reflect")
        logger.info(
            "REFLECT complete scan_id=%s opportunities=%s patches=%s create_pr=%s pr=%s",
            ctx.scan_id,
            len(ctx.opportunities),
            len(applied),
            ctx.create_pr,
            bool(ctx.pr_result),
        )

    def _build_pr_report(self, ctx: ScanContext) -> PRReportData:
        if not ctx.projected_scores or ctx.score is None:
            raise StageExecutionError(
                "projected scores required for PR report",
                stage="reflect",
                reason="missing_scores",
            )
        current = ctx.projected_scores[0].current_score
        best = max(ctx.projected_scores, key=lambda p: p.projected_score)
        projected = best.projected_score
        delta = projected - current

        gaps: list[str] = []
        for opp in ctx.opportunities:
            if opp.schema_target is not None:
                gaps.append(f"Missing {opp.schema_target.value}")
            else:
                gaps.append(opp.title)

        evidence = []
        seen: set[tuple[str, str]] = set()
        for evaluation in ctx.evaluations:
            for ref in evaluation.evidence:
                key = (ref.chunk_id, ref.dom_path)
                if key in seen:
                    continue
                seen.add(key)
                evidence.append(ref)

        file_changes = [
            PRFileChange(
                path=p.file_path,
                summary=f"Added Schema.org JSON-LD: {p.schema_type.value}",
                opportunity_ids=[p.opportunity_id],
                schema_types=[p.schema_type.value],
            )
            for p in ctx.patches
            if p.status is PatchFormatStatus.APPLIED
        ]

        return PRReportData(
            scan_id=ctx.scan_id,
            current_score=current,
            projected_score=projected,
            delta=delta,
            detected_gaps=gaps,
            intent_evaluations=list(ctx.evaluations),
            evidence_items=evidence,
            file_changes=file_changes,
            opportunity_titles=[o.title for o in ctx.opportunities],
        )

    def _build_result(
        self,
        ctx: ScanContext,
        *,
        success: bool,
        error: str | None = None,
        error_reason: str | None = None,
    ) -> OrchestrationResult:
        applied = [p for p in ctx.patches if p.status is PatchFormatStatus.APPLIED]
        return OrchestrationResult(
            scan_id=ctx.scan_id,
            final_state=ctx.state,
            success=success,
            remediation_available=ctx.remediation_available,
            pr_requested=ctx.create_pr,
            pr_created=ctx.pr_result is not None,
            stage_trace=list(ctx.stage_trace),
            intent_count=len(ctx.intents.queries) if ctx.intents else 0,
            evaluation_count=len(ctx.evaluations),
            contradiction_count=len(ctx.contradictions),
            opportunity_count=len(ctx.opportunities),
            patch_count=len(applied),
            llm_calls_made=self._llm.calls_made,
            llm_calls_remaining=self._llm.remaining_calls,
            score=ctx.score,
            schema_report=ctx.schema_report,
            evaluations=list(ctx.evaluations),
            contradictions=list(ctx.contradictions),
            opportunities=list(ctx.opportunities),
            patches=list(ctx.patches),
            projected_scores=list(ctx.projected_scores),
            pr_body=ctx.pr_body,
            pr_result=ctx.pr_result,
            error=error,
            error_reason=error_reason,
        )


# Re-export for callers expecting runner naming.
async def run_scan(
    observation: ObservationInput,
    *,
    dag: FindableAIDAG | None = None,
) -> OrchestrationResult:
    orchestrator = dag or FindableAIDAG()
    return await orchestrator.run(observation)
