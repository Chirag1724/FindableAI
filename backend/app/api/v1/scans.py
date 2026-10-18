import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.auth import TenantContext, verify_api_key
from app.core.budget import BudgetGuard
from app.core.config import settings
from app.core.llm import LLMClient
from app.core.permissions import OrgAction, assert_permission
from app.core.rate_limiter import rate_limit_mutating, rate_limit_scans
from app.core.security import SSRFSecurityException, validate_target_url
from app.core.tenancy import (
    assert_scan_org_access,
    clamp_list_limit,
    encode_scan_list_cursor,
    get_scan_for_org,
    list_scans_for_org,
)
from app.crawler.crawler import AsyncCrawler
from app.crawler.dom_chunker import ChunkData, DOMChunker
from app.crawler.search import store_dom_chunks
from app.db import AsyncSessionLocal
from app.engines.intent_generator import resolve_query_persona
from app.engines.lighthouse import LighthouseEngine
from app.engines.llms_txt_generator import generate_llms_txt
from app.engines.patch_assembler import assemble_real_patches
from app.engines.patch_validator import validate_patch_candidate
from app.engines.robots_analyzer import generate_optimized_robots_txt
from app.engines.scorer import ScoreInputs, Scorer, adapt_score_breakdown_to_api
from app.github.client import GitHubClientError, build_pygithub_client_from_token
from app.github.pr_engine import GitHubPRService, PREngineError
from app.models.database import (
    Contradiction as ContradictionModel,
)
from app.models.database import (
    DOMChunk as DOMChunkModel,
)
from app.models.database import (
    Intent as IntentModel,
)
from app.models.database import (
    Patch as PatchModel,
)
from app.models.database import (
    Scan as ScanModel,
)
from app.orchestration.dag import FindableAIDAG, ObservationInput
from app.orchestration.evidence_persistence import (
    HYDRATE_WARN,
    NO_DURABLE_EVIDENCE_REMEDIATION_WARN,
    PERSISTENCE_FAIL_WARN,
    apply_response_evidence_integrity,
    downgrade_unvalidated_evaluations,
    evidence_persistence_warning,
    hydrate_evidence_for_intents,
    load_chunk_id_map,
    refine_remediation_eligible,
    upsert_intent_evaluations,
)
from app.orchestration.remediation_lifecycle import (
    STATE_BLOCKED,
    STATE_FAILED,
    STATE_MUTATING,
    STATE_PR_OPEN,
    STATE_PR_PERSIST_FAILED,
    STATE_VALIDATION_FAILED,
    STATE_VERIFIED,
    STATE_VERIFYING,
    evaluate_verification_outcome,
    get_runs_for_scan,
    lifecycle_state_for_verification_outcome,
    list_verifications_for_scan,
    make_idempotency_key,
    persist_verification_run,
    upsert_remediation_run,
)
from app.orchestration.scan_integrity import (
    IntegrityInput,
    PatchesSource,
    ScoreSource,
    decide_scan_integrity,
    sanitize_public_error,
    should_inject_synthetic_contradictions,
    should_inject_synthetic_intents,
)
from app.orchestration.scan_persistence import (
    apply_integrity_to_scan_row,
    apply_observability_to_scan_row,
    observability_from_budget,
    unpack_integrity_from_scan_row,
)
from app.orchestration.state import OrchestrationChunk
from app.schemas.fscore import FScoreBreakdown, SubScoreMetric
from app.schemas.github_pr import PREngineRequest
from app.schemas.intelligence import (
    Contradiction,
    ContradictionSeverity,
    EntailmentStatus,
    EvidenceReference,
    IntentCategory,
    IntentEvaluation,
)
from app.schemas.lighthouse import LighthouseResponse
from app.schemas.patch import DOMSelectorAnchor, PatchProposal, PatchType, PullRequestResult
from app.schemas.patching import FormattedPatch, PatchFormatStatus, SchemaRemediationTarget
from app.schemas.remediation import (
    PatchValidationResponse,
    RemediationRunOut,
    ValidationCheckOut,
    VerificationRunOut,
    VerifyRemediationRequest,
)
from app.schemas.scan import (
    AuditSummary,
    CrawledPageDetail,
    ScanJobStatusResponse,
    ScanRequest,
    ScanResponse,
    ScanStatus,
    ScanStatusEvent,
)

logger = logging.getLogger(__name__)

# Fail closed: every scan route requires auth. Newly added routes inherit this.
router = APIRouter(dependencies=[Depends(verify_api_key)])

# In-memory store for caching, local development, and resilient fallbacks
SCANS_DB: dict[str, ScanResponse] = {}


def _tenant_from_request(request: Request) -> TenantContext:
    """Read TenantContext attached by verify_api_key (router dependency)."""
    tenant = getattr(request.state, "tenant", None)
    if isinstance(tenant, TenantContext):
        return tenant
    # Fail closed if dependency did not run / attach context.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing API Key. Provide via 'X-API-Key' header or 'Authorization: Bearer <key>'.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _org_id_str(org_id: uuid.UUID | None) -> str | None:
    return str(org_id) if org_id is not None else None


async def _authorize_scan_ref(scan_id: str, tenant: TenantContext) -> uuid.UUID | None:
    """Authorize access to a scan by public id. Returns UUID when durable row exists.

    In-memory-only stubs (no DB row yet) are authorized against the stamped
    ``ScanResponse.org_id``. Missing scans raise 404.
    """
    scan_uuid = resolve_scan_uuid(scan_id)
    if scan_uuid is not None:
        try:
            async with AsyncSessionLocal() as s:
                await get_scan_for_org(s, scan_uuid, tenant)
                return scan_uuid
        except HTTPException:
            raise
        except Exception:
            # DB unavailable: fall through to in-memory auth for local/dev.
            pass

    record = SCANS_DB.get(scan_id)
    if record is None and scan_uuid is not None:
        record = SCANS_DB.get(str(scan_uuid)) or SCANS_DB.get(f"scan_{scan_uuid.hex}")
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    mem_org: uuid.UUID | None = None
    if getattr(record, "org_id", None):
        try:
            mem_org = uuid.UUID(str(record.org_id))
        except ValueError:
            mem_org = None
    assert_scan_org_access(scan_org_id=mem_org, tenant=tenant)
    return scan_uuid
CHUNKS_DB: dict[str, list[ChunkData]] = {}
LIGHTHOUSE_DB: dict[str, LighthouseResponse] = {}
ROBOTS_DB: dict[str, str] = {}
HTML_DB: dict[str, list[str]] = {}
SCORE_INPUTS_DB: dict[str, Any] = {}
SCORE_BREAKDOWN_DB: dict[str, Any] = {}
EVENT_LOGS: dict[str, list[ScanStatusEvent]] = {}
EVENT_QUEUES: dict[str, list[asyncio.Queue[ScanStatusEvent | None]]] = {}


def resolve_scan_uuid(scan_id: str) -> uuid.UUID | None:
    raw = scan_id.strip()
    if raw.startswith("scan_"):
        raw = raw[5:]
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError):
        return None


def _generate_fallback_evaluations(
    url: str,
    chunks: Sequence[Any],
    personas: Sequence[str] | None = None,
) -> list[IntentEvaluation]:
    parsed = urlparse(url)
    domain = parsed.netloc or "Target Business"
    categories = [
        IntentCategory.ELIGIBILITY,
        IntentCategory.POLICY,
        IntentCategory.AVAILABILITY,
        IntentCategory.PRICING,
        IntentCategory.ACCESSIBILITY,
        IntentCategory.COMMERCIAL,
        IntentCategory.LOCAL,
        IntentCategory.TRANSACTIONAL,
        IntentCategory.TRUST,
        IntentCategory.EDGE_CASES,
    ]
    # Demo-only placeholders: never attach fabricated DOM evidence or retrieved chunks.
    _ = chunks  # retained for call-site compatibility; unused intentionally
    evals = []
    for i in range(1, 31):
        cat = categories[(i - 1) % len(categories)]
        status = EntailmentStatus.UNKNOWN
        persona = resolve_query_persona(cat, personas)
        evals.append(
            IntentEvaluation(
                intent_id=f"intent_{i:02d}",
                query=f"[DEMO] Sample {cat.value} query #{i} for {domain}",
                category=cat,
                persona=persona,
                status=status,
                reasoning=(
                    "Synthetic demo placeholder — not an NLI evaluation of retrieved website evidence."
                ),
                evidence=[],
                confidence=0.0,
            )
        )
    return evals


def _generate_fallback_contradictions(url: str) -> list[Contradiction]:
    parsed = urlparse(url)
    domain = parsed.netloc or "Target Business"
    return [
        Contradiction(
            contradiction_id=f"con_{uuid.uuid4().hex[:6]}",
            entity="availability",
            conflict=f"Service and contact availability specifications differ across {domain} pages",
            values=["Standard business hours", "Extended online support"],
            severity=ContradictionSeverity.SOFT_INCONSISTENCY,
            source_urls=[url],
            dom_paths=["body > main > section:first-of-type", "body > footer"],
        )
    ]


def generate_mock_fscore(url: str) -> FScoreBreakdown:
    parsed = urlparse(url)
    domain = parsed.netloc or "Target Business"
    return FScoreBreakdown(
        overall_score=78.4,
        grade="B+",
        coverage=SubScoreMetric(
            name="Query Intent Coverage",
            weight=0.40,
            score=82.0,
            details=f"Answers 14 of 17 simulated high-intent buyer queries for {domain}.",
            strengths=["Clear brand identification", "Extractable capabilities"],
            gaps=["Missing security compliance details (SOC2 / GDPR)"],
        ),
        contradiction_penalty=SubScoreMetric(
            name="Contradiction Penalty",
            weight=0.30,
            score=10.0,
            details=f"Minor claim variation detected across {domain} sections.",
            strengths=["Consistent product positioning"],
            gaps=["Availability and contact channels vary across pages"],
        ),
        structural_clarity=SubScoreMetric(
            name="DOM & Schema Structure",
            weight=0.20,
            score=85.0,
            details=f"Semantic HTML elements present for {domain}, missing Schema.org JSON-LD.",
            strengths=["Clean H1-H3 heading hierarchy", "Proper HTML5 semantic elements"],
            gaps=["Missing Schema.org WebSite or Organization JSON-LD microdata"],
        ),
        entailment=SubScoreMetric(
            name="Extractability & Accessibility",
            weight=0.10,
            score=76.5,
            details="Machine accessibility of core business metadata (hours, address, phone).",
            strengths=["Key product and service specifications present"],
            gaps=["Vague enterprise SLA claims lacking exact numbers"],
        ),
    )


def generate_mock_patches(url: str = "https://example.com", html: str = "") -> list[PatchProposal]:
    parsed = urlparse(url)
    domain = parsed.netloc or "Target Business"
    clean_name = domain.replace("www.", "").split(".")[0].replace("-", " ").capitalize()

    head_snippet = f"<head>\n  <title>{clean_name}</title>\n</head>"
    if html:
        soup = BeautifulSoup(html, "lxml")
        head = soup.find("head")
        if head and head.title and head.title.string:
            head_snippet = f"<head>\n  <title>{head.title.string.strip()}</title>\n</head>"

    suggested_head = head_snippet.replace(
        "</head>",
        f'  <script type="application/ld+json">\n  {{"@context": "https://schema.org", "@type": "Organization", "name": "{clean_name}", "url": "{url}"}}\n  </script>\n</head>',
    )
    if "</head>" not in head_snippet:
        suggested_head = f'{head_snippet}\n<script type="application/ld+json">\n{{"@context": "https://schema.org", "@type": "Organization", "name": "{clean_name}", "url": "{url}"}}\n</script>'

    return [
        PatchProposal(
            patch_id=f"patch_{uuid.uuid4().hex[:8]}",
            patch_type=PatchType.SCHEMA_MICRODATA,
            title=f"Inject Schema.org {clean_name} WebSite & Organization JSON-LD",
            rationale=(
                f"AI search engines (SearchGPT, Perplexity, Google AI Overviews) rely heavily on "
                f"structured Schema.org JSON-LD microdata to index entity identity for {domain}."
            ),
            impact_score_delta=6.5,
            dom_anchor=DOMSelectorAnchor(
                css_selector="head",
                tag_name="head",
                original_snippet=head_snippet,
                suggested_snippet=suggested_head,
            ),
            unified_diff=(
                f"--- a/index.html\n+++ b/index.html\n@@ -2,3 +2,6 @@\n{head_snippet}\n"
                f'+  <script type="application/ld+json">\n'
                f'+  {{"@context": "https://schema.org", "@type": "Organization", "name": "{clean_name}", "url": "{url}"}}\n'
                f"+  </script>\n</head>"
            ),
            applied=False,
            is_synthetic=True,
        ),
    ]


def _stage_to_scan_status(stage: str | None) -> ScanStatus | None:
    """Best-effort map of progress stage labels onto ScanStatus for live UI."""
    if not stage:
        return None
    s = stage.strip().lower()
    if any(tok in s for tok in ("audit complete", "scan finished")):
        return ScanStatus.COMPLETED
    if "patch" in s:
        return ScanStatus.GENERATING_PATCHES
    if "f-score" in s or "fscore" in s or "reflect" in s:
        return ScanStatus.COMPUTING_FSCORE
    if "nli" in s or "entailment" in s or "contradiction" in s:
        return ScanStatus.NLI_EVALUATION
    if "retrieval" in s or "evidence" in s or "hybrid" in s:
        return ScanStatus.HYBRID_RETRIEVAL
    if "intent" in s or "persona" in s or "synthetic intent" in s:
        return ScanStatus.SYNTHESIZING_INTENTS
    if "dom" in s or "chunk" in s or "structural extraction" in s:
        return ScanStatus.EXTRACTING_DOM
    if "crawl" in s or "playwright" in s or "observe" in s:
        return ScanStatus.CRAWLING
    return None


def _db_status_to_scan_status(status_raw: str | None, *, stage: str | None = None) -> ScanStatus:
    """Map durable DB status strings onto the API ScanStatus enum."""
    if status_raw and status_raw in [e.value for e in ScanStatus]:
        return ScanStatus(status_raw)
    if status_raw == "completed":
        return ScanStatus.COMPLETED
    if status_raw == "failed":
        return ScanStatus.FAILED
    if status_raw == "cancelled":
        return ScanStatus.CANCELLED
    if status_raw == "cancelling":
        return ScanStatus.CANCELLING
    # Coarse in_progress/pending rows: recover fine-grained UI status from stage.
    staged = _stage_to_scan_status(stage)
    if staged is not None:
        return staged
    return ScanStatus.PENDING


async def _emit_event(
    scan_id: str,
    status_val: ScanStatus,
    percent: int,
    step_name: str,
    message: str,
    *,
    current: int | None = None,
    total: int | None = None,
    scan_uuid: uuid.UUID | None = None,
) -> ScanStatusEvent:
    """Emit progress to process-local subscribers and durable PostgreSQL (best-effort).

    Durable DB state is authoritative across API/worker processes. Process-local
    EVENT_* mirrors remain best-effort for same-process SSE only and must not be
    treated as the source of truth.
    """
    seq: int | None = None
    resolved_uuid = scan_uuid
    if resolved_uuid is None:
        try:
            resolved_uuid = resolve_scan_uuid(scan_id)
        except Exception:
            resolved_uuid = None
    if resolved_uuid is not None:
        try:
            from app.jobs.progress import best_effort_persist_progress

            # Coarse status on scans row; fine-grained ScanStatus on progress
            # events so cross-process SSE can drive the UI stepper/cards.
            if status_val == ScanStatus.COMPLETED:
                db_status = "completed"
            elif status_val == ScanStatus.FAILED:
                db_status = "failed"
            elif status_val == ScanStatus.CANCELLED:
                db_status = "cancelled"
            elif status_val == ScanStatus.CANCELLING:
                db_status = "cancelling"
            elif status_val == ScanStatus.PENDING:
                db_status = "pending"
            else:
                db_status = "in_progress"
            seq = await best_effort_persist_progress(
                scan_id=resolved_uuid,
                status=db_status,
                event_status=status_val.value,
                stage=step_name,
                message=message,
                percent=percent,
                current=current,
                total=total,
            )
        except Exception as exc:
            logger.warning("durable_progress_emit_failed scan_id=%s: %s", scan_id, exc)

    event = ScanStatusEvent(
        scan_id=scan_id,
        status=status_val,
        progress_percent=percent,
        current_step=step_name,
        message=message,
        timestamp=datetime.now(UTC),
        seq=seq,
        progress_current=current,
        progress_total=total,
    )
    if scan_id in SCANS_DB:
        record = SCANS_DB[scan_id]
        record.status = status_val
        record.progress_percent = percent
        record.progress_stage = step_name
        record.progress_message = message
        record.progress_current = current
        record.progress_total = total
        if seq is not None:
            record.progress_seq = seq

    EVENT_LOGS.setdefault(scan_id, []).append(event)
    for q in EVENT_QUEUES.get(scan_id, []):
        await q.put(event)
    return event


async def _finalize_hard_failure(
    scan_id: str,
    scan_uuid: uuid.UUID,
    exc: BaseException,
) -> None:
    """Fail-closed integrity for unexpected pipeline crashes; sanitize public errors."""
    public_error = sanitize_public_error(str(exc)) or "Scan pipeline failed unexpectedly."
    end_time = datetime.now(UTC)

    prior = SCANS_DB.get(scan_id)
    prior_dag = None
    if prior and prior.summary:
        prior_dag = prior.summary.dag_evaluations_count
    if prior_dag is None and prior and prior.intents:
        if getattr(prior, "result_source", None) != "synthetic_fallback":
            prior_dag = len(prior.intents)

    has_partial_real = bool(prior_dag and prior_dag > 0)
    outcome = "partial" if has_partial_real else "failed"
    result_source = "partial_real" if has_partial_real else "inconclusive"
    # prior may be None (crash before SCANS_DB insert completed); never attribute-access blindly.
    prior_llm_calls = (prior.llm_calls_made or 0) if prior is not None else 0
    execution_mode = "real_llm" if has_partial_real and prior_llm_calls > 0 else "deterministic"
    warnings = [
        "Scan terminated by an unexpected error; remediation is not eligible.",
    ]
    if has_partial_real:
        warnings.append(
            "Preserved prior real evaluations are partial and unverified for remediation."
        )

    if scan_id in SCANS_DB:
        record = SCANS_DB[scan_id]
        record.status = ScanStatus.FAILED
        record.completed_at = end_time
        record.error = public_error
        record.execution_mode = execution_mode
        record.data_source = "live_pipeline" if has_partial_real else "synthetic_fallback"
        record.result_source = result_source
        record.outcome = outcome
        record.score_source = record.score_source or "none"
        record.patches_source = "none"
        record.remediation_eligible = False
        record.intelligence_warnings = warnings
        if record.patches and any(getattr(p, "is_synthetic", False) for p in record.patches):
            record.patches = []

    try:
        async with AsyncSessionLocal() as s:
            async with s.begin():
                db_scan = await s.get(ScanModel, scan_uuid)
                if db_scan:
                    db_scan.status = "failed"
                    db_scan.completed_at = end_time
                    apply_integrity_to_scan_row(
                        db_scan,
                        execution_mode=execution_mode,
                        result_source=result_source,
                        outcome=outcome,
                        score_source="none",
                        patches_source="none",
                        remediation_eligible=False,
                        intelligence_warnings=warnings,
                        llm_calls_made=getattr(prior, "llm_calls_made", None) if prior else None,
                        dag_evaluations_count=prior_dag,
                        synthetic_intents_count=0,
                        pages_crawled=(
                            getattr(prior.summary, "pages_crawled", None)
                            if prior and prior.summary
                            else None
                        ),
                        dom_chunks_extracted=(
                            getattr(prior.summary, "dom_chunks_extracted", None)
                            if prior and prior.summary
                            else None
                        ),
                        data_source="live_pipeline" if has_partial_real else "synthetic_fallback",
                        error=public_error,
                    )
    except Exception as db_err:
        logger.warning(
            "Hard-failure integrity persist skipped for %s (DB unavailable): %s",
            scan_id,
            db_err,
        )

    await _emit_event(
        scan_id,
        ScanStatus.FAILED,
        100,
        "Scan Failed",
        public_error,
    )


async def run_scan_pipeline(
    scan_id: str,
    scan_uuid: uuid.UUID,
    url: str,
    max_pages: int,
    personas: list[str] | None = None,
    initial_llm_calls: int = 0,
    initial_llm_usd: float = 0.0,
    resume_checkpoint: dict[str, Any] | None = None,
    cancel_check: Any | None = None,
) -> int:
    """
    Autonomous scan worker pipeline:
    1. BFS Crawl (httpx / Playwright fallback)
    2. Semantic DOM Chunker (CSS selector generation)
    3. Embedding & pgvector storage
    4. Synthetic intent generation & hybrid search
    5. NLI entailment evaluation
    6. F-Score calculation & patch generation

    When a compatible crawl/chunks checkpoint exists, crawl+embed are skipped and
    persisted DOMChunks are reloaded. LLM budget is restored from durable
    checkpoints and re-checkpointed after each reservation.
    """
    from app.jobs.cancel import reset_cancel_check, set_cancel_check
    from app.jobs.checkpoints import (
        best_effort_save_checkpoint,
        checkpoint_compatible,
        empty_checkpoint,
        mark_stage,
        request_stage_fingerprint,
        stage_done,
    )
    from app.jobs.execution_context import get_job_execution_context
    from app.jobs.queue import update_llm_checkpoint

    allow_private = settings.ENVIRONMENT.lower() != "production"
    start_time = datetime.now(UTC)
    calls_made = max(0, int(initial_llm_calls or 0))
    stage_fp = request_stage_fingerprint(url=url, max_pages=max_pages, personas=personas)
    checkpoint: dict[str, Any] = (
        {**resume_checkpoint}
        if checkpoint_compatible(resume_checkpoint, fingerprint=stage_fp)
        and isinstance(resume_checkpoint, dict)
        else empty_checkpoint(fingerprint=stage_fp)
    )
    job_ctx = get_job_execution_context()
    _cancel_token = set_cancel_check(cancel_check) if cancel_check is not None else None

    async def _checkpoint_cancel() -> None:
        if cancel_check is not None:
            await cancel_check()

    async def _durable_budget_hook(used: int, usd: float) -> None:
        if job_ctx is None:
            return
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await update_llm_checkpoint(
                        session,
                        job_id=job_ctx.job_id,
                        fencing_token=job_ctx.fencing_token,
                        worker_id=job_ctx.worker_id,
                        llm_calls=used,
                        llm_usd=usd,
                    )
        except Exception as exc:
            logger.warning("mid_pipeline_llm_checkpoint_failed: %s", exc)

    async def _save_checkpoint(updated: dict[str, Any]) -> None:
        nonlocal checkpoint
        checkpoint = updated
        if job_ctx is None:
            return
        await best_effort_save_checkpoint(
            job_id=job_ctx.job_id,
            fencing_token=job_ctx.fencing_token,
            worker_id=job_ctx.worker_id,
            checkpoint=checkpoint,
        )

    try:
        await _checkpoint_cancel()
        skip_crawl = False
        persisted_chunks = None
        extracted_chunks: list[ChunkData] = []
        html_docs: list[str] = []
        crawled_pages_detail: list[CrawledPageDetail] = []
        pages_crawled = 1
        robots_txt_content = ""

        if stage_done(checkpoint, "chunks"):
            try:
                async with AsyncSessionLocal() as session:
                    stmt = select(DOMChunkModel).where(DOMChunkModel.scan_id == scan_uuid)
                    rows = list((await session.execute(stmt)).scalars().all())
                if rows:
                    skip_crawl = True
                    pages_crawled = int(
                        (checkpoint.get("stages") or {}).get("chunks", {}).get("pages") or 1
                    )
                    extracted_chunks = [
                        ChunkData(
                            url=r.url,
                            dom_path=r.dom_path,
                            content=r.content,
                            tag=r.tag,
                            word_count=r.word_count,
                        )
                        for r in rows
                    ]
                    persisted_chunks = rows
                    html_docs = [
                        f"<html><body><main>{c.content}</main></body></html>"
                        for c in extracted_chunks[: max(1, min(len(extracted_chunks), 5))]
                    ]
                    crawled_pages_detail = [
                        CrawledPageDetail(
                            url=url,
                            status_code=200,
                            chunks_count=len(extracted_chunks),
                            is_spa=False,
                        )
                    ]
                    await _emit_event(
                        scan_id,
                        ScanStatus.EXTRACTING_DOM,
                        45,
                        "Resume from checkpoint",
                        f"Reusing {len(extracted_chunks)} persisted chunks (compatible fingerprint).",
                        scan_uuid=scan_uuid,
                    )
            except Exception as resume_err:
                logger.info("checkpoint_resume_skipped: %s", resume_err)
                skip_crawl = False

        if not skip_crawl:
            await _checkpoint_cancel()
            # Phase 1: OBSERVE / Crawling
            await _emit_event(
                scan_id,
                ScanStatus.CRAWLING,
                15,
                "Playwright Crawling",
                f"Fetching DOM snapshots from {url}...",
                scan_uuid=scan_uuid,
            )
            crawler = AsyncCrawler(
                max_pages=max_pages,
                concurrency=5,
                timeout_seconds=15.0,
                allow_private=allow_private,
            )
            crawl_results = await crawler.crawl(url)
            pages_crawled = len(crawl_results) if crawl_results else 1
            robots_txt_content = (
                crawl_results[0].robots_txt if crawl_results and crawl_results[0].robots_txt else ""
            )
            await _save_checkpoint(mark_stage(checkpoint, "crawl", meta={"pages": pages_crawled}))

            # Phase 2: EXTRACTING_DOM
            await _emit_event(
                scan_id,
                ScanStatus.EXTRACTING_DOM,
                30,
                "DOM Structural Extraction",
                f"Parsing semantic hierarchy and CSS selector paths across {pages_crawled} pages...",
                scan_uuid=scan_uuid,
            )
            chunker = DOMChunker()
            if crawl_results:
                for page in crawl_results:
                    chunks = chunker.chunk(page.html, page.url) if page.html else []
                    extracted_chunks.extend(chunks)
                    if page.html:
                        html_docs.append(page.html)
                    crawled_pages_detail.append(
                        CrawledPageDetail(
                            url=page.url,
                            status_code=page.status_code,
                            chunks_count=len(chunks),
                            is_spa=page.is_spa,
                        )
                    )
            else:
                default_html = (
                    "<html><body><main><h1>Welcome</h1><p>Findable content</p></main></body></html>"
                )
                extracted_chunks = chunker.chunk(default_html, url)
                html_docs = [default_html]
                crawled_pages_detail = [
                    CrawledPageDetail(
                        url=url,
                        status_code=200,
                        chunks_count=len(extracted_chunks),
                        is_spa=False,
                    )
                ]

            if not html_docs:
                html_docs = [
                    "<html><body><main><h1>Welcome</h1><p>Findable content</p></main></body></html>"
                ]

            # Phase 3: Embedding & Vector Indexing (remains under EXTRACTING_DOM status)
            await _emit_event(
                scan_id,
                ScanStatus.EXTRACTING_DOM,
                45,
                "Embedding & Vector Indexing",
                f"Generating 1536-dim embeddings for {len(extracted_chunks)} chunks...",
                scan_uuid=scan_uuid,
            )
            try:
                persisted_chunks = await store_dom_chunks(scan_uuid, extracted_chunks)
                await _save_checkpoint(
                    mark_stage(
                        checkpoint,
                        "chunks",
                        meta={
                            "count": len(extracted_chunks),
                            "pages": pages_crawled,
                            "persisted": bool(persisted_chunks),
                        },
                    )
                )
            except Exception as db_err:
                logger.info("Database store_dom_chunks unavailable, retained in memory: %s", db_err)

        ROBOTS_DB[scan_id] = robots_txt_content
        ROBOTS_DB[str(scan_uuid)] = robots_txt_content
        ROBOTS_DB[scan_uuid.hex] = robots_txt_content
        CHUNKS_DB[scan_id] = extracted_chunks
        CHUNKS_DB[str(scan_uuid)] = extracted_chunks
        CHUNKS_DB[scan_uuid.hex] = extracted_chunks
        HTML_DB[scan_id] = html_docs
        HTML_DB[str(scan_uuid)] = html_docs
        HTML_DB[scan_uuid.hex] = html_docs

        # Derive business context from extracted chunks
        sample_texts = [
            c.content.strip()
            for c in extracted_chunks[:15]
            if c.content and len(c.content.strip()) > 10
        ]
        context_body = "\n".join(sample_texts[:8])
        business_context = (
            f"Business URL: {url}\nPage excerpt:\n{context_body}"
            if context_body
            else f"Business URL: {url}\nGeneral commercial business website."
        )

        # Dual-tier LLM clients sharing single scan-scoped BudgetGuard — restore
        # checkpoint so job retries never reset the per-scan completion-call budget.
        # Worker path: PostgreSQL fenced increment is the source of truth.
        durable_reserve = None
        if job_ctx is not None:
            from app.jobs.budget_reserve import reserve_scan_llm_call

            async def _pg_reserve(limit: int, usd_delta: float) -> int:
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        return await reserve_scan_llm_call(
                            session,
                            scan_id=scan_uuid,
                            job_id=job_ctx.job_id,
                            fencing_token=job_ctx.fencing_token,
                            worker_id=job_ctx.worker_id,
                            limit=limit,
                            usd_delta=usd_delta,
                        )

            durable_reserve = _pg_reserve

        budget_guard = BudgetGuard(
            limit=settings.MAX_LLM_CALLS_PER_SCAN,
            initial_used=max(0, int(initial_llm_calls or 0)),
            initial_usd=max(0.0, float(initial_llm_usd or 0.0)),
            on_reserve=_durable_budget_hook if durable_reserve is None else None,
            durable_reserve=durable_reserve,
        )
        heavy_llm = LLMClient(model=settings.HEAVY_LLM_MODEL, budget_guard=budget_guard)
        fast_llm = LLMClient(model=settings.FAST_LLM_MODEL, budget_guard=budget_guard)

        # Build orchestration chunks for DAG.
        # Prefer persisted DOMChunk UUIDs so evidence citations are durable FKs.
        orch_chunks: list[OrchestrationChunk] = []
        if persisted_chunks and len(persisted_chunks) == len(extracted_chunks):
            for db_c, c in zip(persisted_chunks, extracted_chunks, strict=True):
                orch_chunks.append(
                    OrchestrationChunk(
                        id=str(db_c.id),
                        url=c.url,
                        dom_path=c.dom_path,
                        content=c.content,
                        tag=c.tag,
                        word_count=c.word_count,
                    )
                )
        else:
            orch_chunks = [
                OrchestrationChunk(
                    id=f"chunk_{i}",
                    url=c.url,
                    dom_path=c.dom_path,
                    content=c.content,
                    tag=c.tag,
                    word_count=c.word_count,
                )
                for i, c in enumerate(extracted_chunks)
            ]

        # Phase 4: SYNTHESIZING_INTENTS
        await _emit_event(
            scan_id,
            ScanStatus.SYNTHESIZING_INTENTS,
            60,
            "Synthetic Intent Engine",
            "Simulating 30 high-intent buyer and researcher queries across 10 taxonomies...",
        )

        # Phase 5: HYBRID_RETRIEVAL
        await _emit_event(
            scan_id,
            ScanStatus.HYBRID_RETRIEVAL,
            75,
            "Evidence Selection",
            "Query-time dense + lexical retrieval with RRF (falls back to first-k if index unavailable).",
        )

        # Phase 6: NLI_EVALUATION
        await _emit_event(
            scan_id,
            ScanStatus.NLI_EVALUATION,
            85,
            "NLI Entailment Classifier",
            "Evaluating claim entailment and detecting factual contradictions...",
        )

        async def _persist_batch(batch_evals: list[IntentEvaluation]) -> None:
            """Write a validated persona batch immediately (idempotent on intent_key)."""
            try:
                async with AsyncSessionLocal() as s:
                    async with s.begin():
                        chunk_map = await load_chunk_id_map(s, scan_uuid)
                        await upsert_intent_evaluations(
                            s,
                            scan_id=scan_uuid,
                            evaluations=batch_evals,
                            chunk_map=chunk_map,
                        )
            except Exception:
                logger.exception(
                    "batch_persist_failed scan_id=%s size=%s", scan_id, len(batch_evals)
                )

        async def _on_nli_progress(completed: int, total: int, item: Any) -> None:
            pct = min(90, 80 + int((completed / max(total, 1)) * 10))
            query_preview = getattr(item, "query", "")[:45]
            obs_snap = budget_guard.observability.snapshot()
            batches_done = obs_snap.get("batches_completed")
            batches_total = obs_snap.get("batches_total")
            batch_note = ""
            if batches_total is not None:
                batch_note = f" batches={batches_done}/{batches_total}"
            await _emit_event(
                scan_id,
                ScanStatus.NLI_EVALUATION,
                pct,
                "NLI Entailment Classifier",
                f'[{completed}/{total}] Grounded claim: "{query_preview}..."{batch_note}',
                current=completed,
                total=total,
            )
            # Best-effort mid-scan observability columns (never blocks pipeline).
            try:
                async with AsyncSessionLocal() as s:
                    async with s.begin():
                        db_scan = await s.get(ScanModel, scan_uuid)
                        if db_scan is not None:
                            apply_observability_to_scan_row(
                                db_scan,
                                **{
                                    k: v
                                    for k, v in observability_from_budget(budget_guard).items()
                                    if k
                                    not in (
                                        "llm_usd_provider_reported",
                                        "cost_basis",
                                    )
                                },
                            )
            except Exception:
                pass

        # Execute FindableAIDAG orchestrator with dual-tier clients & live progress
        dag = FindableAIDAG(
            llm_client=heavy_llm,
            fast_llm_client=fast_llm,
            budget_guard=budget_guard,
            progress_callback=_on_nli_progress,
            persist_batch_callback=_persist_batch,
        )
        obs = ObservationInput(
            scan_id=str(scan_uuid),
            business_context=business_context,
            personas=personas or ("cto", "developer", "procurement"),
            chunks=orch_chunks,
            html_documents=html_docs,
        )
        orch_result = await dag.run(obs)
        await _save_checkpoint(
            mark_stage(
                checkpoint,
                "dag",
                meta={"evaluations": len(orch_result.evaluations or [])},
            )
        )

        # Preserve DAG outputs before any synthetic substitution.
        dag_evaluations: list[IntentEvaluation] = list(orch_result.evaluations)
        contradictions: list[Contradiction] = list(orch_result.contradictions)
        score_breakdown = orch_result.score
        dag_eval_count = len(dag_evaluations)

        is_prod = settings.ENVIRONMENT.lower() == "production"
        allow_demo = bool(getattr(settings, "ALLOW_SYNTHETIC_DEMO", False))
        used_synthetic_intents = False
        used_synthetic_contradictions = False
        synthetic_intents_count = 0

        evaluations: list[IntentEvaluation] = list(dag_evaluations)
        if should_inject_synthetic_intents(
            is_production=is_prod,
            dag_evaluation_count=dag_eval_count,
            allow_synthetic_demo=allow_demo,
        ):
            # Explicit opt-in demo only — never on the normal scan path.
            evaluations = _generate_fallback_evaluations(url, extracted_chunks, personas=personas)
            used_synthetic_intents = True
            synthetic_intents_count = len(evaluations)

        if should_inject_synthetic_contradictions(
            is_production=is_prod,
            contradiction_count=len(contradictions),
            dag_error=orch_result.error,
            allow_synthetic_demo=allow_demo,
        ):
            contradictions = _generate_fallback_contradictions(url)
            used_synthetic_contradictions = True

        # Build ScoreInputs from real DAG evaluations only for audit-grade scoring.
        score_inputs = ScoreInputs(
            intent_evaluations=dag_evaluations,
            contradictions=contradictions if not used_synthetic_contradictions else [],
            html_documents=html_docs,
            chunks=extracted_chunks,
        )

        # Never run the deterministic scorer on synthetic demo intents.
        SCORE_INPUTS_DB[scan_id] = score_inputs
        SCORE_INPUTS_DB[str(scan_uuid)] = score_inputs
        if score_breakdown is not None:
            SCORE_BREAKDOWN_DB[scan_id] = score_breakdown
            SCORE_BREAKDOWN_DB[str(scan_uuid)] = score_breakdown

        if score_breakdown is None and dag_evaluations and not used_synthetic_intents:
            try:
                score_breakdown = Scorer().score(score_inputs)
            except Exception as scorer_err:
                logger.warning("Deterministic scorer calculation error: %s", scorer_err)

        # Phase 7: COMPUTING_FSCORE
        await _emit_event(
            scan_id,
            ScanStatus.COMPUTING_FSCORE,
            92,
            "F-Score Engine",
            "Calculating weighted Findability metrics (Coverage, Entailment, Contradiction, Structure)...",
        )

        f_score: FScoreBreakdown | None = None
        score_source = ScoreSource.NONE
        if used_synthetic_intents:
            # Demo path: no authoritative F-Score (do not label as deterministic_scorer).
            if score_breakdown is not None:
                logger.warning(
                    "Discarding scorer output for synthetic demo scan %s (not audit-grade)",
                    scan_id,
                )
            score_breakdown = None
            f_score = None
            score_source = ScoreSource.NONE
        elif score_breakdown is not None:
            f_score = adapt_score_breakdown_to_api(score_breakdown)
            score_source = ScoreSource.DETERMINISTIC_SCORER
        else:
            logger.warning("No F-score available for %s (scorer empty; mock suppressed)", scan_id)
            f_score = None
            score_source = ScoreSource.NONE

        # Phase 8: GENERATING_PATCHES
        await _emit_event(
            scan_id,
            ScanStatus.GENERATING_PATCHES,
            97,
            "Patch Synthesizer",
            "Generating Schema.org JSON-LD microdata and DOM code diffs...",
        )

        patches: list[PatchProposal] = []
        patches_source = PatchesSource.NONE
        if (
            score_breakdown
            and html_docs
            and not used_synthetic_intents
            and score_source is ScoreSource.DETERMINISTIC_SCORER
        ):
            try:
                assembled = assemble_real_patches(
                    html=html_docs[0],
                    url=url,
                    score_inputs=score_inputs,
                    score_breakdown=score_breakdown,
                    chunks=extracted_chunks,
                    contradictions=contradictions,
                )
                patches = list(assembled) if assembled is not None else []
                patches_source = PatchesSource.ASSEMBLER
            except Exception as patch_err:
                logger.warning("Real patch assembly error: %s", patch_err, exc_info=True)
                patches = []
                patches_source = PatchesSource.NONE
        elif used_synthetic_intents and allow_demo:
            # Explicit demo mocks only — marked is_synthetic; never remediation_eligible.
            patches = generate_mock_patches(url=url, html=html_docs[0] if html_docs else "")
            patches_source = PatchesSource.MOCK
        else:
            patches = []
            patches_source = PatchesSource.NONE

        llm_calls_made = budget_guard.used
        integrity = decide_scan_integrity(
            IntegrityInput(
                dag_evaluation_count=dag_eval_count,
                dag_success=bool(orch_result.success),
                dag_error=orch_result.error,
                dag_error_reason=orch_result.error_reason,
                llm_calls_made=llm_calls_made,
                used_synthetic_intents=used_synthetic_intents,
                used_synthetic_contradictions=used_synthetic_contradictions,
                final_evaluation_count=len(evaluations),
                score_source=score_source,
                patches_source=patches_source,
                is_production=is_prod,
                failed_intent_ids=tuple(orch_result.failed_intent_ids or ()),
                cache_hits=int(budget_guard.observability.cache_hits or 0),
            )
        )

        # Phase 9: terminal status
        end_time = datetime.now(UTC)
        exec_duration = (end_time - start_time).total_seconds()

        final_status = ScanStatus.FAILED if integrity.mark_status_failed else ScanStatus.COMPLETED
        final_error = integrity.error_message

        execution_mode = integrity.execution_mode.value
        data_source = integrity.data_source

        summary = AuditSummary(
            pages_crawled=pages_crawled,
            dom_chunks_extracted=len(extracted_chunks),
            # Real DAG evaluations only — synthetic demo rows are not "generated" intents.
            intents_generated=dag_eval_count,
            contradictions_detected=(
                len(contradictions) if not used_synthetic_contradictions else 0
            ),
            execution_time_seconds=round(exec_duration, 2),
            max_pages_requested=max_pages,
            crawled_pages=crawled_pages_detail,
            dag_evaluations_count=dag_eval_count,
            synthetic_intents_count=synthetic_intents_count,
        )

        calls_made = llm_calls_made
        logger.info(
            "Scan %s execution complete: execution_mode=%s, result_source=%s, outcome=%s, "
            "data_source=%s, remediation_eligible=%s, llm_calls_made=%d/%d, budget_remaining=%d",
            scan_id,
            execution_mode,
            integrity.result_source.value,
            integrity.outcome.value,
            data_source,
            integrity.remediation_eligible,
            llm_calls_made,
            budget_guard.limit,
            budget_guard.remaining,
        )

        # Phase 9.5: AI Lighthouse Readiness Scoring & Governance
        try:
            lighthouse_engine = LighthouseEngine(
                url=url,
                html_documents=html_docs,
                chunks=extracted_chunks,
                evaluations=evaluations,
                contradictions=contradictions,
                robots_txt=robots_txt_content,
                scan_id=scan_id,
            )
            lighthouse_resp = lighthouse_engine.evaluate()
            LIGHTHOUSE_DB[scan_id] = lighthouse_resp
            LIGHTHOUSE_DB[str(scan_uuid)] = lighthouse_resp
            LIGHTHOUSE_DB[scan_uuid.hex] = lighthouse_resp
            LIGHTHOUSE_DB[f"scan_{scan_uuid.hex[:12]}"] = lighthouse_resp
        except Exception as lh_err:
            logger.warning("Lighthouse evaluation error for %s: %s", scan_id, lh_err)

        # Persist status + integrity contract to database if connected.
        # Evidence integrity runs at this authoritative boundary before process-local
        # intents are treated as durable / evidence-backed.
        evidence_durably_validated = False
        try:
            async with AsyncSessionLocal() as s:
                async with s.begin():
                    db_scan = await s.get(ScanModel, scan_uuid)
                    if db_scan:
                        db_scan.status = (
                            "failed" if final_status is ScanStatus.FAILED else "completed"
                        )
                        db_scan.completed_at = end_time
                        if score_breakdown:
                            db_scan.f_score = score_breakdown.f_score
                            db_scan.s_ans = score_breakdown.s_ans
                            db_scan.s_con = score_breakdown.s_con
                            db_scan.s_str = score_breakdown.s_str
                            db_scan.s_acc = score_breakdown.s_acc
                        elif f_score:
                            db_scan.f_score = f_score.overall_score
                            db_scan.s_ans = f_score.coverage.score
                            db_scan.s_con = 100.0 - f_score.contradiction_penalty.score
                            db_scan.s_str = f_score.structural_clarity.score
                            db_scan.s_acc = f_score.entailment.score
                        apply_integrity_to_scan_row(
                            db_scan,
                            execution_mode=execution_mode,
                            result_source=integrity.result_source.value,
                            outcome=integrity.outcome.value,
                            score_source=integrity.score_source.value,
                            patches_source=integrity.patches_source.value,
                            remediation_eligible=integrity.remediation_eligible,
                            intelligence_warnings=list(integrity.warnings),
                            llm_calls_made=llm_calls_made,
                            dag_evaluations_count=dag_eval_count,
                            synthetic_intents_count=synthetic_intents_count,
                            pages_crawled=pages_crawled,
                            dom_chunks_extracted=len(extracted_chunks),
                            data_source=data_source,
                            error=final_error,
                        )
                        apply_observability_to_scan_row(
                            db_scan,
                            **{
                                k: v
                                for k, v in observability_from_budget(budget_guard).items()
                                if k not in ("llm_usd_provider_reported", "cost_basis")
                            },
                        )

                    # Persist only real DAG evaluations + durable evidence (never synthetic).
                    # Idempotent on (scan_id, intent_key); failed-batch IDs stay unresolved.
                    if not used_synthetic_intents:
                        chunk_map = await load_chunk_id_map(s, scan_uuid)
                        skip_keys = list(orch_result.failed_intent_ids or [])
                        sanitized_evaluations, _inserted = await upsert_intent_evaluations(
                            s,
                            scan_id=scan_uuid,
                            evaluations=dag_evaluations,
                            chunk_map=chunk_map,
                            skip_keys=skip_keys,
                        )
                        cite_total = sum(len(e.evidence or []) for e in sanitized_evaluations)
                        cite_persisted = cite_total
                        evaluations = sanitized_evaluations
                        dag_evaluations = sanitized_evaluations
                        evidence_durably_validated = True
                        if db_scan is not None:
                            db_scan.failed_intent_ids = skip_keys or None
                            if skip_keys:
                                db_scan.failure_reason = (
                                    f"partial_act:{len(skip_keys)}_intents_unresolved"
                                )

                        # Recompute eligibility from final validated findings (not pre-sanitize).
                        refined = refine_remediation_eligible(
                            integrity.remediation_eligible, evaluations
                        )
                        if integrity.remediation_eligible and not refined:
                            warns = list(integrity.warnings)
                            if NO_DURABLE_EVIDENCE_REMEDIATION_WARN not in warns:
                                warns.append(NO_DURABLE_EVIDENCE_REMEDIATION_WARN)
                            integrity.warnings = warns
                        integrity.remediation_eligible = refined
                        if db_scan is not None:
                            db_scan.remediation_eligible = refined
                            db_scan.intelligence_warnings = list(integrity.warnings)

                        ev_warn = evidence_persistence_warning(cite_total, cite_persisted)
                        if ev_warn and db_scan:
                            warns = list(db_scan.intelligence_warnings or [])
                            if ev_warn not in warns:
                                warns.append(ev_warn)
                            db_scan.intelligence_warnings = warns
                            integrity.warnings = list(warns)

                    # Persist only non-synthetic contradictions
                    if not used_synthetic_contradictions:
                        for con in contradictions:
                            sev_str = (
                                con.severity.value
                                if hasattr(con.severity, "value")
                                else str(con.severity)
                            )
                            s.add(
                                ContradictionModel(
                                    id=uuid.uuid4(),
                                    scan_id=scan_uuid,
                                    entity=con.entity,
                                    conflict=con.conflict,
                                    values=con.values if isinstance(con.values, list) else [],
                                    severity=sev_str,
                                )
                            )

                    # Persist only non-synthetic assembler patches
                    if patches and patches_source is PatchesSource.ASSEMBLER:
                        for p in patches:
                            if getattr(p, "is_synthetic", False):
                                continue
                            pt_str = (
                                p.patch_type.value
                                if hasattr(p.patch_type, "value")
                                else str(p.patch_type)
                            )
                            s.add(
                                PatchModel(
                                    id=uuid.uuid4(),
                                    scan_id=scan_uuid,
                                    file_path="index.html",
                                    patch_type=pt_str,
                                    content=p.unified_diff or "",
                                    priority=1,
                                )
                            )
        except Exception as db_err:
            logger.info("Scan record DB update skipped (offline DB): %s", db_err)
            evidence_durably_validated = False

        # Never publish process-local evidence-backed intents without durable validation.
        publish_remediation_eligible = integrity.remediation_eligible
        publish_warnings = list(integrity.warnings)
        if not evidence_durably_validated and not used_synthetic_intents:
            evaluations = downgrade_unvalidated_evaluations(evaluations, reason="persistence")
            dag_evaluations = evaluations
            publish_remediation_eligible = False
            if PERSISTENCE_FAIL_WARN not in publish_warnings:
                publish_warnings.append(PERSISTENCE_FAIL_WARN)
            integrity.warnings = list(publish_warnings)
            # Fail closed: unverified cites cannot authorize remediation.
            integrity.remediation_eligible = False

        if scan_id in SCANS_DB:
            record = SCANS_DB[scan_id]
            record.status = final_status
            record.completed_at = end_time
            record.f_score = f_score
            record.summary = summary
            record.crawled_pages = crawled_pages_detail
            record.patches = patches
            record.intents = evaluations
            record.contradictions = contradictions
            record.execution_mode = execution_mode
            record.data_source = data_source
            record.result_source = integrity.result_source.value
            record.outcome = integrity.outcome.value
            record.score_source = integrity.score_source.value
            record.patches_source = integrity.patches_source.value
            record.remediation_eligible = publish_remediation_eligible
            record.intelligence_warnings = list(publish_warnings)
            record.llm_calls_made = llm_calls_made
            record.error = final_error
            record.failed_intent_ids = list(orch_result.failed_intent_ids or [])
            if orch_result.failed_intent_ids:
                record.failure_reason = (
                    f"partial_act:{len(orch_result.failed_intent_ids)}_intents_unresolved"
                )
            obs_fields = observability_from_budget(budget_guard)
            for key, value in obs_fields.items():
                if hasattr(record, key):
                    setattr(record, key, value)

        if final_status is ScanStatus.FAILED:
            await _emit_event(
                scan_id,
                ScanStatus.FAILED,
                100,
                "Scan Failed",
                final_error or "Intelligence pipeline failed without real evaluations.",
            )
        else:
            warn_note = (
                f" ({integrity.outcome.value}; {integrity.result_source.value})"
                if integrity.outcome.value != "success"
                else ""
            )
            await _emit_event(
                scan_id,
                ScanStatus.COMPLETED,
                100,
                "Audit Complete",
                f"Scan finished{warn_note}.",
            )

    except Exception as e:
        from app.jobs.cancel import ScanCancelled

        if isinstance(e, ScanCancelled):
            # Preserve validated partial results; worker finalizes cancelled.
            raise
        logger.exception("Scan pipeline failed for %s: %s", scan_id, e)
        await _finalize_hard_failure(scan_id, scan_uuid, e)
        # Re-raise so the durable worker can classify retry vs permanent failure.
        raise
    finally:
        if _cancel_token is not None:
            reset_cancel_check(_cancel_token)
        for q in EVENT_QUEUES.get(scan_id, []):
            await q.put(None)
    return calls_made


@router.post(
    "",
    response_model=ScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit_scans)],
)
async def create_scan(
    request: ScanRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
):
    """
    Initiates an asynchronous machine discoverability scan.

    Persists the scan and a durable ``scan_jobs`` row before returning 202.
    Execution is performed by a worker (or optional inline fallback), not as
    the sole durability mechanism of FastAPI BackgroundTasks.
    """
    # Real mode fail-closed: never accept a scan that would silently mock LLM work.
    if not bool(getattr(settings, "ALLOW_SYNTHETIC_DEMO", False)):
        from app.core.llm_credentials import llm_credentials_for_real_scan

        ok, reason = llm_credentials_for_real_scan()
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=reason,
            )

    parsed = urlparse(str(request.url))
    allow_private = False
    if settings.ENVIRONMENT.lower() != "production" and parsed.hostname in (
        "localhost",
        "127.0.0.1",
    ):
        allow_private = True

    try:
        validate_target_url(str(request.url), allow_private=allow_private)
    except SSRFSecurityException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security rejection: {e}",
        ) from e

    from app.jobs.correlation import bind_correlation_id, new_correlation_id
    from app.jobs.queue import (
        enqueue_scan_job,
        request_fingerprint,
        resolve_idempotency_key,
    )
    from app.jobs.worker import process_job_inline

    tenant = _tenant_from_request(http_request)
    assert_permission(tenant, OrgAction.CREATE_SCAN)
    # org_id comes only from the authenticated principal — never from the body.
    stamp_org_id = tenant.org_id

    client_idem = http_request.headers.get("Idempotency-Key")
    correlation_id = (
        http_request.headers.get("X-Correlation-ID")
        or getattr(http_request.state, "request_id", None)
        or new_correlation_id()
    )
    bind_correlation_id(correlation_id)

    fingerprint = request_fingerprint(
        url=str(request.url),
        max_pages=request.max_pages,
        personas=request.personas,
        repo_url=str(request.repo_url) if request.repo_url else None,
    )
    idem_key = resolve_idempotency_key(client_idem, fingerprint=fingerprint)

    scan_uuid = uuid.uuid4()
    job_id: uuid.UUID | None = None
    durable_ok = False

    if settings.DURABLE_SCAN_JOBS:
        try:
            async with AsyncSessionLocal() as s:
                async with s.begin():
                    result = await enqueue_scan_job(
                        s,
                        scan_uuid=scan_uuid,
                        url=str(request.url),
                        max_pages=request.max_pages,
                        personas=request.personas or ["cto", "developer", "procurement"],
                        repo_url=str(request.repo_url) if request.repo_url else None,
                        idempotency_key=idem_key,
                        fingerprint=fingerprint,
                        correlation_id=correlation_id,
                        org_id=stamp_org_id,
                    )
                    if result.conflict:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail={
                                "message": "Idempotency-Key reused with a different request payload",
                                "idempotency_key": idem_key,
                                "existing_scan_id": f"scan_{result.scan.id.hex}",
                            },
                        )
                    scan_uuid = result.scan.id
                    job_id = result.job.id
                    correlation_id = result.job.correlation_id
                    durable_ok = True
                    if not result.created:
                        # Idempotent hit: still enforce tenant isolation (404 if cross-org).
                        assert_scan_org_access(
                            scan_org_id=getattr(result.scan, "org_id", None),
                            tenant=tenant,
                        )
                        existing_id = f"scan_{result.scan.id.hex}"
                        if existing_id in SCANS_DB:
                            return SCANS_DB[existing_id]
                        return ScanResponse(
                            scan_id=existing_id,
                            target_url=result.scan.url,
                            status=ScanStatus.PENDING
                            if result.scan.status == "in_progress"
                            else ScanStatus(result.scan.status)
                            if result.scan.status in {s.value for s in ScanStatus}
                            else ScanStatus.PENDING,
                            created_at=result.scan.created_at or datetime.now(UTC),
                            org_id=_org_id_str(getattr(result.scan, "org_id", None)),
                            repo_url=result.scan.repo_url,
                            github_repo_url=result.scan.repo_url,
                        )
        except HTTPException:
            raise
        except Exception as db_err:
            logger.warning(
                "Durable job enqueue failed; refusing success without persistence: %s",
                db_err,
            )
            # Production must never return 202 without a persisted durable job.
            if settings.ENVIRONMENT.lower() == "production":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "Scan could not be durably queued. "
                        "Database persistence is required before acceptance."
                    ),
                ) from db_err
            # Non-production: best-effort in-process path (CI/sqlite without migrations).
            durable_ok = False

    scan_id = f"scan_{scan_uuid.hex}"

    new_scan = ScanResponse(
        scan_id=scan_id,
        target_url=str(request.url),
        status=ScanStatus.PENDING,
        created_at=datetime.now(UTC),
        org_id=_org_id_str(stamp_org_id),
        repo_url=request.repo_url,
        github_repo_url=request.repo_url,
    )
    SCANS_DB[scan_id] = new_scan
    SCANS_DB[f"scan_{scan_uuid.hex[:12]}"] = new_scan
    SCANS_DB[str(scan_uuid)] = new_scan
    SCANS_DB[scan_uuid.hex] = new_scan
    init_event = ScanStatusEvent(
        scan_id=scan_id,
        status=ScanStatus.PENDING,
        progress_percent=5,
        current_step="Initializing Scan",
        message=(
            "Scan accepted; durable job queued..."
            if durable_ok
            else "Connecting to FindableAI crawl dispatcher..."
        ),
        timestamp=datetime.now(UTC),
    )
    EVENT_LOGS[scan_id] = [init_event]
    EVENT_LOGS[f"scan_{scan_uuid.hex[:12]}"] = [init_event]

    if not durable_ok:
        # Best-effort legacy path when DB unavailable (non-durable).
        try:
            async with AsyncSessionLocal() as s:
                async with s.begin():
                    db_scan = ScanModel(
                        id=scan_uuid,
                        url=str(request.url),
                        repo_url=str(request.repo_url) if request.repo_url else None,
                        status="in_progress",
                        org_id=stamp_org_id,
                    )
                    s.add(db_scan)
        except Exception as db_err:
            logger.info("Database initial scan record skipped (offline DB): %s", db_err)

        background_tasks.add_task(
            run_scan_pipeline,
            scan_id,
            scan_uuid,
            str(request.url),
            request.max_pages,
            request.personas or ["cto", "developer", "procurement"],
        )
        return new_scan

    # Durable path: optional in-process claim for local/test convenience.
    # Production should set SCAN_JOB_INLINE_FALLBACK=false and run `python -m app.worker`.
    if settings.SCAN_JOB_INLINE_FALLBACK and job_id is not None:
        background_tasks.add_task(process_job_inline, job_id)

    return new_scan


def enrich_patches_with_framework(
    patches: list[PatchProposal], repo_url: str | None
) -> list[PatchProposal]:
    """Enriches patches with framework-native diffs and auxiliary files when repo is connected."""
    if not repo_url or not isinstance(repo_url, str) or not repo_url.strip() or not patches:
        return patches
    if any(p.framework for p in patches):
        return patches
    try:
        from app.engines.framework_adapter import resolve_framework_patches

        token = settings.GITHUB_TOKEN
        if token:
            gh_client = build_pygithub_client_from_token(token)
            source_repo = parse_github_repo_owner_name(repo_url.strip())
            repo_ref = gh_client.get_repository(source_repo)
            tree_files = gh_client.list_files(repo_ref, ref=repo_ref.default_branch)

            def get_file_content(path: str) -> str:
                return gh_client.get_file(repo_ref, path, ref=repo_ref.default_branch).content

            return resolve_framework_patches(patches, tree_files, get_file_content)
    except Exception as fw_err:
        logger.debug("Framework patch resolution skipped: %s", fw_err)
    return patches


def _worker_heartbeat_recent(last_heartbeat_at: datetime | None) -> bool:
    """True when a worker heartbeat falls within the configured timeout window."""
    if last_heartbeat_at is None:
        return False
    hb = last_heartbeat_at
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=UTC)
    cutoff = datetime.now(UTC).timestamp() - max(
        30, int(settings.SCAN_JOB_HEARTBEAT_TIMEOUT_SECONDS)
    )
    return hb.timestamp() >= cutoff


async def _attach_job_observability(scan_resp: ScanResponse, scan_uuid: uuid.UUID) -> None:
    """Merge durable job + scan observability columns into a response (best-effort)."""
    try:
        from sqlalchemy import select as sa_select

        from app.models.database import ScanJob

        async with AsyncSessionLocal() as s:
            db_scan = await s.get(ScanModel, scan_uuid)
            if db_scan is not None:
                usd_est = db_scan.llm_usd_estimated
                if usd_est is not None:
                    scan_resp.llm_usd_estimated = float(usd_est)
                    scan_resp.cost_basis = "estimated"
                    scan_resp.llm_usd_provider_reported = None
                if db_scan.provider_successes is not None:
                    scan_resp.provider_successes = int(db_scan.provider_successes)
                if db_scan.provider_failures is not None:
                    scan_resp.provider_failures = int(db_scan.provider_failures)
                if db_scan.primary_llm_model:
                    scan_resp.primary_llm_model = db_scan.primary_llm_model
                if db_scan.fallback_provider_used is not None:
                    scan_resp.fallback_provider_used = bool(db_scan.fallback_provider_used)
                if db_scan.batches_total is not None:
                    scan_resp.batches_total = int(db_scan.batches_total)
                if db_scan.batches_completed is not None:
                    scan_resp.batches_completed = int(db_scan.batches_completed)
                if db_scan.batches_failed is not None:
                    scan_resp.batches_failed = int(db_scan.batches_failed)
                if db_scan.llm_tokens_in is not None:
                    scan_resp.llm_tokens_in = int(db_scan.llm_tokens_in)
                if db_scan.llm_tokens_out is not None:
                    scan_resp.llm_tokens_out = int(db_scan.llm_tokens_out)
                calls_made = db_scan.llm_calls_made
                if calls_made is not None:
                    # Prefer durable calls when memory is stale/empty.
                    if scan_resp.llm_calls_made is None or int(scan_resp.llm_calls_made or 0) < int(
                        calls_made
                    ):
                        scan_resp.llm_calls_made = int(calls_made)
                # Progress: prefer newer durable seq / percent for in-flight scans.
                durable_seq = None
                try:
                    from app.jobs.progress import load_progress_snapshot

                    snap = await load_progress_snapshot(s, scan_uuid)
                    if snap:
                        durable_seq = snap.get("progress_seq")
                except Exception:
                    durable_seq = None
                mem_seq = scan_resp.progress_seq
                use_durable = False
                if durable_seq is not None and (
                    mem_seq is None or int(durable_seq) >= int(mem_seq)
                ):
                    use_durable = True
                if use_durable and db_scan.status in ("in_progress", "pending", "queued"):
                    if getattr(db_scan, "progress_percent", None) is not None:
                        scan_resp.progress_percent = db_scan.progress_percent
                    if getattr(db_scan, "progress_stage", None) is not None:
                        scan_resp.progress_stage = db_scan.progress_stage
                    if getattr(db_scan, "progress_message", None) is not None:
                        scan_resp.progress_message = db_scan.progress_message
                    if getattr(db_scan, "progress_current", None) is not None:
                        scan_resp.progress_current = db_scan.progress_current
                    if getattr(db_scan, "progress_total", None) is not None:
                        scan_resp.progress_total = db_scan.progress_total
                    scan_resp.progress_seq = durable_seq

            job_row = (
                await s.execute(
                    sa_select(ScanJob)
                    .where(ScanJob.scan_id == scan_uuid)
                    .order_by(ScanJob.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if job_row is not None:
                scan_resp.job_status = job_row.status
                scan_resp.job_attempt_count = int(job_row.attempt_count or 0)
                scan_resp.job_max_attempts = int(job_row.max_attempts or 0)
                scan_resp.worker_heartbeat_recent = _worker_heartbeat_recent(
                    job_row.last_heartbeat_at
                )
                # Mid-run budget checkpoints are authoritative across workers.
                if float(getattr(job_row, "llm_usd_checkpoint", 0.0) or 0.0) > float(
                    scan_resp.llm_usd_estimated or 0.0
                ):
                    scan_resp.llm_usd_estimated = float(job_row.llm_usd_checkpoint or 0.0)
                    scan_resp.cost_basis = "estimated"
                if int(getattr(job_row, "llm_calls_checkpoint", 0) or 0) > int(
                    scan_resp.llm_calls_made or 0
                ):
                    scan_resp.llm_calls_made = int(job_row.llm_calls_checkpoint or 0)
    except Exception as exc:
        logger.debug("job_observability_attach_skipped: %s", exc)


async def get_scan_for_tenant(scan_id: str, tenant: TenantContext) -> ScanResponse:
    """Authorize then load scan response (shared by routes and internal callers)."""
    await _authorize_scan_ref(scan_id, tenant)
    return await _load_scan_response(scan_id)


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: str, request: Request) -> ScanResponse:
    """Fetches status and results of a scan (tenant-scoped)."""
    tenant = _tenant_from_request(request)
    return await get_scan_for_tenant(scan_id, tenant)


class CancelScanRequest(BaseModel):
    reason: str | None = None


@router.post(
    "/{scan_id}/cancel",
    dependencies=[Depends(rate_limit_mutating)],
)
async def cancel_scan(
    scan_id: str,
    request: Request,
    body: CancelScanRequest | None = None,
) -> dict[str, Any]:
    """Cancel a queued or running scan (idempotent; terminal conflict → 409).

    Authorization uses the central tenant helper plus the role permission matrix
    (viewers cannot cancel).
    """
    from app.jobs.cancel import cancel_result_payload, request_scan_cancel

    tenant = _tenant_from_request(request)
    assert_permission(tenant, OrgAction.CANCEL_SCAN)
    scan_uuid = await _authorize_scan_ref(scan_id, tenant)
    if scan_uuid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    actor = (
        f"org:{tenant.org_id}"
        if tenant.org_id is not None
        else ("system_admin" if tenant.is_system_admin else "unknown")
    )
    reason = (body.reason if body else None) or "cancelled_by_user"

    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                result = await request_scan_cancel(
                    session,
                    scan_id=scan_uuid,
                    actor=actor,
                    reason=reason,
                )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found"
        ) from exc
    except Exception as exc:
        logger.warning("cancel_scan_failed scan_id=%s: %s", scan_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cancel unavailable",
        ) from exc

    if result.conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=cancel_result_payload(result),
        )

    # Keep process-local cache consistent for same-process pollers.
    mem = SCANS_DB.get(scan_id)
    if mem is not None:
        mem.status = (
            ScanStatus.CANCELLED
            if result.scan_status == "cancelled"
            else ScanStatus.CANCELLING
        )
        mem.error = reason

    return cancel_result_payload(result)


async def _load_scan_response(scan_id: str) -> ScanResponse:
    """Hydrate ScanResponse from memory or Postgres (caller must authorize)."""
    scan_uuid = resolve_scan_uuid(scan_id)

    if scan_id in SCANS_DB:
        record = SCANS_DB[scan_id]
        target_repo = record.repo_url or record.github_repo_url
        if target_repo and not any(p.framework for p in record.patches):
            record.patches = enrich_patches_with_framework(record.patches, target_repo)
        # Cross-process: when the worker finished in Postgres but this API process still
        # holds a pending stub, fall through to durable hydration instead of returning
        # a stale in-memory snapshot (missing intents / wrong status).
        prefer_db = False
        if scan_uuid and record.status not in (
            ScanStatus.COMPLETED,
            ScanStatus.FAILED,
            ScanStatus.CANCELLED,
        ):
            try:
                async with AsyncSessionLocal() as s:
                    db_probe = await s.get(ScanModel, scan_uuid)
                    if db_probe is not None and db_probe.status in ("completed", "failed"):
                        prefer_db = True
            except Exception:
                prefer_db = False
        if not prefer_db:
            if scan_uuid:
                await _attach_job_observability(record, scan_uuid)
            return record

    # Query persistent PostgreSQL database
    if scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                db_scan = await s.get(ScanModel, scan_uuid)
                if db_scan:
                    stmt_patches = select(PatchModel).where(PatchModel.scan_id == scan_uuid)
                    res_patches = await s.execute(stmt_patches)
                    db_patches = res_patches.scalars().all()

                    stmt_intents = select(IntentModel).where(IntentModel.scan_id == scan_uuid)
                    res_intents = await s.execute(stmt_intents)
                    db_intents = res_intents.scalars().all()

                    stmt_cons = select(ContradictionModel).where(
                        ContradictionModel.scan_id == scan_uuid
                    )
                    res_cons = await s.execute(stmt_cons)
                    db_cons = res_cons.scalars().all()

                    converted_patches: list[PatchProposal] = [
                        PatchProposal(
                            patch_id=f"patch_{p.id.hex[:8]}",
                            patch_type=PatchType(p.patch_type)
                            if p.patch_type in [e.value for e in PatchType]
                            else PatchType.SCHEMA_MICRODATA,
                            title="Remediation Patch",
                            rationale="Automated discoverability patch",
                            impact_score_delta=5.0,
                            dom_anchor=DOMSelectorAnchor(
                                css_selector="head",
                                tag_name="head",
                                original_snippet="",
                                suggested_snippet="",
                            ),
                            unified_diff=p.content,
                            applied=False,
                        )
                        for p in db_patches
                    ]

                    # Hydrate failures must not masquerade as a missing scan (404).
                    evidence_by_intent: dict[uuid.UUID, list[EvidenceReference]] = {}
                    hydrate_failed = False
                    try:
                        evidence_by_intent = await hydrate_evidence_for_intents(s, list(db_intents))
                    except Exception as hydrate_err:
                        hydrate_failed = True
                        logger.warning(
                            "Evidence hydration failed for scan %s: %s",
                            scan_id,
                            hydrate_err,
                        )
                    converted_intents: list[IntentEvaluation] = [
                        IntentEvaluation(
                            intent_id=f"intent_{it.id.hex[:8]}",
                            query=it.query,
                            category=IntentCategory(it.category)
                            if it.category in [c.value for c in IntentCategory]
                            else None,
                            persona=getattr(it, "persona", None)
                            or resolve_query_persona(
                                IntentCategory(it.category)
                                if it.category in [c.value for c in IntentCategory]
                                else IntentCategory.POLICY
                            ),
                            status=EntailmentStatus(it.status)
                            if it.status in [e.value for e in EntailmentStatus]
                            else EntailmentStatus.UNKNOWN,
                            reasoning=it.reasoning or "",
                            evidence=evidence_by_intent.get(it.id, []),
                            confidence=it.confidence or 0.85,
                        )
                        for it in db_intents
                    ]
                    converted_intents = apply_response_evidence_integrity(
                        converted_intents, hydrate_failed=hydrate_failed
                    )

                    converted_cons: list[Contradiction] = [
                        Contradiction(
                            contradiction_id=f"con_{c.id.hex[:6]}",
                            entity=c.entity,
                            conflict=c.conflict,
                            values=c.values if isinstance(c.values, list) else [],
                            severity=ContradictionSeverity(c.severity)
                            if c.severity in [e.value for e in ContradictionSeverity]
                            else ContradictionSeverity.SOFT_INCONSISTENCY,
                            source_urls=[db_scan.url],
                            dom_paths=[],
                        )
                        for c in db_cons
                    ]

                    f_score_obj = None
                    if db_scan.f_score is not None:
                        f_score_obj = FScoreBreakdown(
                            overall_score=db_scan.f_score,
                            grade="A"
                            if db_scan.f_score >= 90
                            else ("B" if db_scan.f_score >= 80 else "C"),
                            coverage=SubScoreMetric(
                                name="Query Intent Coverage",
                                weight=0.40,
                                score=db_scan.s_ans or 0.0,
                                details="Query coverage score",
                                strengths=[],
                                gaps=[],
                            ),
                            contradiction_penalty=SubScoreMetric(
                                name="Contradiction Penalty",
                                weight=0.30,
                                score=db_scan.s_con or 0.0,
                                details="Contradiction penalty score",
                                strengths=[],
                                gaps=[],
                            ),
                            structural_clarity=SubScoreMetric(
                                name="DOM & Schema Structure",
                                weight=0.20,
                                score=db_scan.s_str or 0.0,
                                details="Structure score",
                                strengths=[],
                                gaps=[],
                            ),
                            entailment=SubScoreMetric(
                                name="Extractability & Accessibility",
                                weight=0.10,
                                score=db_scan.s_acc or 0.0,
                                details="Extractability score",
                                strengths=[],
                                gaps=[],
                            ),
                        )

                    integrity = unpack_integrity_from_scan_row(db_scan)
                    response_warnings = list(integrity.intelligence_warnings)
                    if hydrate_failed:
                        if HYDRATE_WARN not in response_warnings:
                            response_warnings.append(HYDRATE_WARN)
                    # Eligibility must reflect post-hydration evidence integrity, not
                    # a stale pre-sanitize persisted flag alone.
                    response_remediation_eligible = refine_remediation_eligible(
                        bool(integrity.remediation_eligible) and not hydrate_failed,
                        converted_intents,
                    )
                    if integrity.remediation_eligible and not response_remediation_eligible:
                        if hydrate_failed:
                            pass  # HYDRATE_WARN already recorded
                        elif NO_DURABLE_EVIDENCE_REMEDIATION_WARN not in response_warnings:
                            response_warnings.append(NO_DURABLE_EVIDENCE_REMEDIATION_WARN)

                    scan_status = _db_status_to_scan_status(
                        db_scan.status, stage=getattr(db_scan, "progress_stage", None)
                    )
                    pages_crawled = integrity.pages_crawled
                    if pages_crawled is None:
                        pages_crawled = 1 if scan_status == ScanStatus.COMPLETED else 0
                    dom_chunks = integrity.dom_chunks_extracted
                    if dom_chunks is None:
                        dom_chunks = len(converted_intents)
                    crawled_fallback = [
                        CrawledPageDetail(
                            url=db_scan.url,
                            status_code=200,
                            chunks_count=dom_chunks,
                        )
                    ]
                    summary = None
                    if db_scan.status in ("completed", "failed"):
                        exec_secs = 0.0
                        completed_at = getattr(db_scan, "completed_at", None)
                        created_at = getattr(db_scan, "created_at", None)
                        if completed_at is not None and created_at is not None:
                            try:
                                exec_secs = max(0.0, (completed_at - created_at).total_seconds())
                            except Exception:
                                exec_secs = 0.0
                        summary = AuditSummary(
                            pages_crawled=pages_crawled,
                            dom_chunks_extracted=dom_chunks,
                            intents_generated=len(converted_intents),
                            contradictions_detected=len(converted_cons),
                            execution_time_seconds=round(exec_secs, 1),
                            max_pages_requested=pages_crawled or 1,
                            crawled_pages=crawled_fallback,
                            dag_evaluations_count=integrity.dag_evaluations_count,
                            synthetic_intents_count=integrity.synthetic_intents_count,
                        )
                    progress_seq = None
                    try:
                        from app.jobs.progress import load_progress_snapshot

                        snap = await load_progress_snapshot(s, scan_uuid)
                        if snap:
                            progress_seq = snap.get("progress_seq")
                    except Exception:
                        progress_seq = None
                    # Prefer durable progress for in-flight scans; terminal scans use 100.
                    durable_percent = getattr(db_scan, "progress_percent", None)
                    if scan_status in (
                        ScanStatus.COMPLETED,
                        ScanStatus.FAILED,
                        ScanStatus.CANCELLED,
                    ):
                        durable_percent = 100 if durable_percent is None else durable_percent
                    scan_resp = ScanResponse(
                        scan_id=scan_id,
                        target_url=db_scan.url,
                        status=scan_status,
                        created_at=db_scan.created_at,
                        org_id=_org_id_str(getattr(db_scan, "org_id", None)),
                        cancel_reason=getattr(db_scan, "cancel_reason", None),
                        cancelled_by=getattr(db_scan, "cancelled_by", None),
                        completed_at=getattr(db_scan, "completed_at", None),
                        f_score=f_score_obj,
                        summary=summary,
                        crawled_pages=crawled_fallback,
                        patches=enrich_patches_with_framework(converted_patches, db_scan.repo_url),
                        intents=converted_intents,
                        contradictions=converted_cons,
                        error=integrity.error,
                        execution_mode=integrity.execution_mode,
                        data_source=integrity.data_source,
                        result_source=integrity.result_source,
                        outcome=integrity.outcome,
                        score_source=integrity.score_source,
                        patches_source=integrity.patches_source,
                        remediation_eligible=response_remediation_eligible,
                        intelligence_warnings=response_warnings,
                        llm_calls_made=integrity.llm_calls_made,
                        requests_attempted=integrity.llm_calls_made,
                        requests_succeeded=getattr(db_scan, "provider_successes", None),
                        requests_failed=getattr(db_scan, "provider_failures", None),
                        retries=getattr(db_scan, "provider_retries", None),
                        failovers=getattr(db_scan, "provider_failovers", None),
                        recovery_requests=getattr(db_scan, "recovery_requests", None),
                        llm_usd_estimated=getattr(db_scan, "llm_usd_estimated", None),
                        llm_usd_provider_reported=None,
                        cost_basis=(
                            "estimated"
                            if getattr(db_scan, "llm_usd_estimated", None) is not None
                            else None
                        ),
                        provider_successes=getattr(db_scan, "provider_successes", None),
                        provider_failures=getattr(db_scan, "provider_failures", None),
                        primary_llm_model=getattr(db_scan, "primary_llm_model", None),
                        fallback_provider_used=getattr(db_scan, "fallback_provider_used", None),
                        batches_total=getattr(db_scan, "batches_total", None),
                        batches_completed=getattr(db_scan, "batches_completed", None),
                        batches_failed=getattr(db_scan, "batches_failed", None),
                        llm_tokens_in=getattr(db_scan, "llm_tokens_in", None),
                        llm_tokens_out=getattr(db_scan, "llm_tokens_out", None),
                        failed_intent_ids=list(getattr(db_scan, "failed_intent_ids", None) or []),
                        failure_reason=getattr(db_scan, "failure_reason", None),
                        provider_retries=getattr(db_scan, "provider_retries", None),
                        provider_failovers=getattr(db_scan, "provider_failovers", None),
                        duplicate_requests_joined=getattr(
                            db_scan, "duplicate_requests_joined", None
                        ),
                        cache_hits=getattr(db_scan, "cache_hits", None),
                        evaluations_valid=getattr(db_scan, "evaluations_valid", None),
                        repo_url=db_scan.repo_url,
                        github_repo_url=db_scan.repo_url,
                        progress_percent=durable_percent,
                        progress_stage=getattr(db_scan, "progress_stage", None),
                        progress_message=getattr(db_scan, "progress_message", None),
                        progress_current=getattr(db_scan, "progress_current", None),
                        progress_total=getattr(db_scan, "progress_total", None),
                        progress_seq=progress_seq,
                    )
                    await _attach_job_observability(scan_resp, scan_uuid)
                    SCANS_DB[scan_id] = scan_resp
                    return scan_resp
        except Exception as e:
            logger.debug("Database scan lookup bypassed: %s", e)

    raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found")


@router.get(
    "/{scan_id}/job",
    response_model=ScanJobStatusResponse,
)
async def get_scan_job_status(scan_id: str, request: Request) -> ScanJobStatusResponse:
    """Durable job + progress/observability snapshot for an authorized scan."""
    tenant = _tenant_from_request(request)
    scan_uuid = await _authorize_scan_ref(scan_id, tenant)
    if scan_uuid is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    from sqlalchemy import select as sa_select

    from app.models.database import ScanJob

    try:
        async with AsyncSessionLocal() as s:
            db_scan = await get_scan_for_org(s, scan_uuid, tenant)

            job_row = (
                await s.execute(
                    sa_select(ScanJob)
                    .where(ScanJob.scan_id == scan_uuid)
                    .order_by(ScanJob.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            progress_seq = None
            try:
                from app.jobs.progress import load_progress_snapshot

                snap = await load_progress_snapshot(s, scan_uuid)
                if snap:
                    progress_seq = snap.get("progress_seq")
            except Exception:
                progress_seq = None

            public_error = None
            if job_row is not None and job_row.error_detail:
                public_error = sanitize_public_error(str(job_row.error_detail))

            return ScanJobStatusResponse(
                scan_id=scan_id if scan_id.startswith("scan_") else f"scan_{scan_uuid.hex}",
                job_id=str(job_row.id) if job_row else None,
                job_status=job_row.status if job_row else None,
                job_type=job_row.job_type if job_row else None,
                attempt_count=int(job_row.attempt_count or 0) if job_row else None,
                max_attempts=int(job_row.max_attempts or 0) if job_row else None,
                fencing_token=int(job_row.fencing_token or 0) if job_row else None,
                started_at=job_row.started_at if job_row else None,
                finished_at=job_row.finished_at if job_row else None,
                last_heartbeat_at=job_row.last_heartbeat_at if job_row else None,
                worker_heartbeat_recent=(
                    _worker_heartbeat_recent(job_row.last_heartbeat_at) if job_row else False
                ),
                error_code=job_row.error_code if job_row else None,
                error_detail=public_error,
                failure_category=job_row.failure_category if job_row else None,
                llm_calls_checkpoint=(int(job_row.llm_calls_checkpoint or 0) if job_row else None),
                llm_usd_checkpoint=(float(job_row.llm_usd_checkpoint or 0.0) if job_row else None),
                cost_basis="estimated",
                progress_percent=getattr(db_scan, "progress_percent", None) if db_scan else None,
                progress_stage=getattr(db_scan, "progress_stage", None) if db_scan else None,
                progress_message=getattr(db_scan, "progress_message", None) if db_scan else None,
                progress_current=getattr(db_scan, "progress_current", None) if db_scan else None,
                progress_total=getattr(db_scan, "progress_total", None) if db_scan else None,
                progress_seq=progress_seq,
                batches_total=getattr(db_scan, "batches_total", None) if db_scan else None,
                batches_completed=getattr(db_scan, "batches_completed", None) if db_scan else None,
                batches_failed=getattr(db_scan, "batches_failed", None) if db_scan else None,
                provider_successes=getattr(db_scan, "provider_successes", None)
                if db_scan
                else None,
                provider_failures=getattr(db_scan, "provider_failures", None) if db_scan else None,
                primary_llm_model=getattr(db_scan, "primary_llm_model", None) if db_scan else None,
                fallback_provider_used=(
                    getattr(db_scan, "fallback_provider_used", None) if db_scan else None
                ),
                llm_tokens_in=getattr(db_scan, "llm_tokens_in", None) if db_scan else None,
                llm_tokens_out=getattr(db_scan, "llm_tokens_out", None) if db_scan else None,
                correlation_id=job_row.correlation_id if job_row else None,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("get_scan_job_status_failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Durable job status unavailable",
        ) from exc


@router.get("/{scan_id}/stream")
async def stream_scan_progress(
    scan_id: str,
    request: Request,
    last_event_id: int | None = Query(default=None, alias="last_event_id", ge=0),
):
    """SSE progress stream with durable DB replay (cross-process safe).

    Auth is required before the stream opens (router ``verify_api_key``).
    Browsers must use a fetch-based stream that sends ``X-API-Key`` /
    ``Authorization`` headers — native EventSource cannot. Each reconnect is a
    new HTTP request, so auth is re-validated automatically.

    Prefer ``Last-Event-ID`` header or ``last_event_id`` query for reconnect.
    Process-local EVENT_* is best-effort only; PostgreSQL events/snapshot are
    authoritative. Polling GET /scans/{id} remains the reliable fallback.
    """
    tenant = _tenant_from_request(request)
    scan_uuid = await _authorize_scan_ref(scan_id, tenant)

    header_leid = request.headers.get("last-event-id") or request.headers.get("Last-Event-ID")
    after_seq = int(last_event_id or 0)
    if header_leid:
        try:
            after_seq = max(after_seq, int(header_leid))
        except ValueError:
            pass

    async def event_generator() -> AsyncGenerator[str, None]:
        from app.jobs.progress import list_progress_events_after, load_progress_snapshot

        cursor = after_seq
        # Same-process subscribers still get live pushes when available.
        queue: asyncio.Queue[ScanStatusEvent | None] = asyncio.Queue()
        EVENT_QUEUES.setdefault(scan_id, []).append(queue)
        try:
            if scan_uuid is not None:
                try:
                    async with AsyncSessionLocal() as s:
                        rows = await list_progress_events_after(
                            s, scan_uuid, after_seq=cursor, limit=500
                        )
                        snap = await load_progress_snapshot(s, scan_uuid)
                    if not rows and snap and cursor == 0:
                        # Snapshot fallback when event history is empty/unavailable.
                        status_raw = str(snap.get("status") or "in_progress")
                        stage_raw = str(snap.get("progress_stage") or "") or None
                        status_enum = _db_status_to_scan_status(status_raw, stage=stage_raw)
                        synth = ScanStatusEvent(
                            scan_id=scan_id,
                            status=status_enum,
                            progress_percent=int(snap.get("progress_percent") or 0),
                            current_step=str(snap.get("progress_stage") or status_raw),
                            message=str(
                                snap.get("progress_message") or "Restored progress snapshot"
                            ),
                            timestamp=datetime.now(UTC),
                            seq=int(snap.get("progress_seq") or 0) or None,
                            progress_current=snap.get("progress_current"),
                            progress_total=snap.get("progress_total"),
                        )
                        if synth.seq:
                            yield f"id: {synth.seq}\n"
                        yield f"data: {json.dumps(synth.model_dump(mode='json'))}\n\n"
                        if status_enum in (ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED):
                            return
                    for row in rows:
                        st = _db_status_to_scan_status(row.status, stage=row.stage)
                        ev = ScanStatusEvent(
                            scan_id=scan_id,
                            status=st,
                            progress_percent=int(row.percent or 0),
                            current_step=str(row.stage or row.status or "progress"),
                            message=str(row.message or ""),
                            timestamp=row.created_at or datetime.now(UTC),
                            seq=row.seq,
                            progress_current=row.current,
                            progress_total=row.total,
                        )
                        cursor = max(cursor, int(row.seq))
                        yield f"id: {row.seq}\n"
                        yield f"data: {json.dumps(ev.model_dump(mode='json'))}\n\n"
                        if st in (ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED):
                            return
                except Exception as exc:
                    logger.warning("sse_durable_replay_failed scan_id=%s: %s", scan_id, exc)

            # Live tail: merge durable polling with optional same-process queue.
            idle_rounds = 0
            while True:
                delivered = False
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                    if event is None:
                        break
                    if event.seq:
                        yield f"id: {event.seq}\n"
                        cursor = max(cursor, int(event.seq))
                    yield f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
                    delivered = True
                    if event.status in (ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED):
                        return
                except TimeoutError:
                    pass

                if scan_uuid is not None and not delivered:
                    try:
                        async with AsyncSessionLocal() as s:
                            rows = await list_progress_events_after(
                                s, scan_uuid, after_seq=cursor, limit=50
                            )
                            snap = await load_progress_snapshot(s, scan_uuid)
                        for row in rows:
                            st = _db_status_to_scan_status(row.status, stage=row.stage)
                            ev = ScanStatusEvent(
                                scan_id=scan_id,
                                status=st,
                                progress_percent=int(row.percent or 0),
                                current_step=str(row.stage or "progress"),
                                message=str(row.message or ""),
                                timestamp=row.created_at or datetime.now(UTC),
                                seq=row.seq,
                                progress_current=row.current,
                                progress_total=row.total,
                            )
                            cursor = max(cursor, int(row.seq))
                            yield f"id: {row.seq}\n"
                            yield f"data: {json.dumps(ev.model_dump(mode='json'))}\n\n"
                            delivered = True
                            if st in (ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED):
                                return
                        if snap and (snap.get("status") in ("completed", "failed")) and not rows:
                            st = _db_status_to_scan_status(
                                str(snap.get("status")),
                                stage=str(snap.get("progress_stage") or "") or None,
                            )
                            synth = ScanStatusEvent(
                                scan_id=scan_id,
                                status=st,
                                progress_percent=100,
                                current_step=str(snap.get("progress_stage") or snap.get("status")),
                                message=str(
                                    snap.get("progress_message")
                                    or snap.get("error")
                                    or f"Scan {snap.get('status')}"
                                ),
                                timestamp=datetime.now(UTC),
                                seq=int(snap.get("progress_seq") or cursor) or None,
                            )
                            if synth.seq:
                                yield f"id: {synth.seq}\n"
                            yield f"data: {json.dumps(synth.model_dump(mode='json'))}\n\n"
                            return
                    except Exception:
                        pass

                if not delivered:
                    idle_rounds += 1
                    if idle_rounds % 10 == 0:
                        # Re-validate principal still has access (revoked key / removed member).
                        if not tenant.is_system_admin and tenant.api_key_id is not None:
                            try:
                                from app.core.membership import api_key_still_active

                                async with AsyncSessionLocal() as s:
                                    still = await api_key_still_active(s, tenant.api_key_id)
                                    if not still:
                                        yield 'event: error\ndata: {"reason":"access_revoked"}\n\n'
                                        return
                                    if scan_uuid is not None:
                                        await get_scan_for_org(s, scan_uuid, tenant)
                            except HTTPException:
                                yield 'event: error\ndata: {"reason":"access_revoked"}\n\n'
                                return
                            except Exception:
                                pass
                        yield ": heartbeat\n\n"
                else:
                    idle_rounds = 0
        finally:
            if scan_id in EVENT_QUEUES and queue in EVENT_QUEUES[scan_id]:
                EVENT_QUEUES[scan_id].remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{scan_id}/chunks")
async def get_scan_chunks(scan_id: str, request: Request) -> list[dict[str, Any]]:
    """Returns all extracted DOM chunks for this scan (parent-scan org scoped)."""
    tenant = _tenant_from_request(request)
    scan_uuid = await _authorize_scan_ref(scan_id, tenant)
    if scan_id in CHUNKS_DB:
        return [
            {
                "url": c.url,
                "dom_path": c.dom_path,
                "tag": c.tag,
                "word_count": c.word_count,
                "content": c.content,
            }
            for c in CHUNKS_DB[scan_id]
        ]

    if scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                await get_scan_for_org(s, scan_uuid, tenant)
                stmt = (
                    select(DOMChunkModel)
                    .join(ScanModel, DOMChunkModel.scan_id == ScanModel.id)
                    .where(DOMChunkModel.scan_id == scan_uuid)
                )
                if not tenant.is_system_admin:
                    if tenant.org_id is None:
                        return []
                    stmt = stmt.where(ScanModel.org_id == tenant.org_id)
                result = await s.execute(stmt)
                db_chunks = result.scalars().all()
                if db_chunks:
                    return [
                        {
                            "id": str(c.id),
                            "url": c.url,
                            "dom_path": c.dom_path,
                            "tag": c.tag,
                            "word_count": c.word_count,
                            "content": c.content,
                        }
                        for c in db_chunks
                    ]
        except HTTPException:
            raise
        except Exception as e:
            logger.debug("DB chunks lookup bypassed: %s", e)

    return []


@router.get("/{scan_id}/intents")
async def get_scan_intents(scan_id: str, request: Request) -> list[dict[str, Any]]:
    """Returns intent evaluations for this scan (cold-path hydrates durable evidence)."""
    tenant = _tenant_from_request(request)
    await _authorize_scan_ref(scan_id, tenant)
    if scan_id in SCANS_DB and SCANS_DB[scan_id].intents:
        return [eval_item.model_dump(mode="json") for eval_item in SCANS_DB[scan_id].intents]

    scan_uuid = resolve_scan_uuid(scan_id)
    if scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                await get_scan_for_org(s, scan_uuid, tenant)
                stmt = (
                    select(IntentModel)
                    .join(ScanModel, IntentModel.scan_id == ScanModel.id)
                    .where(IntentModel.scan_id == scan_uuid)
                )
                if not tenant.is_system_admin:
                    if tenant.org_id is None:
                        return []
                    stmt = stmt.where(ScanModel.org_id == tenant.org_id)
                result = await s.execute(stmt)
                db_intents = result.scalars().all()
                if db_intents:
                    evidence_by_intent: dict[uuid.UUID, list[EvidenceReference]] = {}
                    hydrate_failed = False
                    try:
                        evidence_by_intent = await hydrate_evidence_for_intents(s, list(db_intents))
                    except Exception as hydrate_err:
                        hydrate_failed = True
                        logger.warning(
                            "Evidence hydration failed for GET intents scan %s: %s",
                            scan_id,
                            hydrate_err,
                        )
                    converted: list[IntentEvaluation] = [
                        IntentEvaluation(
                            intent_id=f"intent_{it.id.hex[:8]}",
                            query=it.query,
                            category=IntentCategory(it.category)
                            if it.category in [c.value for c in IntentCategory]
                            else None,
                            persona=getattr(it, "persona", None)
                            or resolve_query_persona(
                                IntentCategory(it.category)
                                if it.category in [c.value for c in IntentCategory]
                                else IntentCategory.POLICY
                            ),
                            status=EntailmentStatus(it.status)
                            if it.status in [e.value for e in EntailmentStatus]
                            else EntailmentStatus.UNKNOWN,
                            reasoning=it.reasoning or "",
                            evidence=evidence_by_intent.get(it.id, []),
                            confidence=it.confidence if it.confidence is not None else 0.0,
                        )
                        for it in db_intents
                    ]
                    converted = apply_response_evidence_integrity(
                        converted, hydrate_failed=hydrate_failed
                    )
                    return [item.model_dump(mode="json") for item in converted]
        except HTTPException:
            raise
        except Exception as e:
            logger.debug("DB intents lookup error: %s", e)

    return []


@router.get("/{scan_id}/contradictions")
async def get_scan_contradictions(scan_id: str, request: Request) -> list[dict[str, Any]]:
    """Returns detected factual contradictions across crawled pages."""
    tenant = _tenant_from_request(request)
    await _authorize_scan_ref(scan_id, tenant)
    if scan_id in SCANS_DB and SCANS_DB[scan_id].contradictions:
        return [con.model_dump(mode="json") for con in SCANS_DB[scan_id].contradictions]

    scan_uuid = resolve_scan_uuid(scan_id)
    if scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                await get_scan_for_org(s, scan_uuid, tenant)
                stmt = (
                    select(ContradictionModel)
                    .join(ScanModel, ContradictionModel.scan_id == ScanModel.id)
                    .where(ContradictionModel.scan_id == scan_uuid)
                )
                if not tenant.is_system_admin:
                    if tenant.org_id is None:
                        return []
                    stmt = stmt.where(ScanModel.org_id == tenant.org_id)
                result = await s.execute(stmt)
                db_cons = result.scalars().all()
                if db_cons:
                    return [
                        {
                            "contradiction_id": f"con_{c.id.hex[:6]}",
                            "entity": c.entity,
                            "conflict": c.conflict,
                            "values": c.values if isinstance(c.values, list) else [],
                            "severity": c.severity,
                            "source_urls": [],
                            "dom_paths": [],
                        }
                        for c in db_cons
                    ]
        except HTTPException:
            raise
        except Exception as e:
            logger.debug("DB contradictions lookup error: %s", e)

    return []


@router.get(
    "/{scan_id}/patches",
    response_model=list[PatchProposal],
)
async def get_scan_patches(
    scan_id: str,
    request: Request,
    repo_url: str | None = Query(
        default=None, description="GitHub repository URL for framework-native diffs"
    ),
) -> list[PatchProposal]:
    """Returns remediation code patches for this scan.

    When ``repo_url`` is provided (or stored on the scan), patches are enriched
    with framework-native code diffs so the UI preview matches the GitHub PR exactly.
    Auth follows the same fail-closed contract as other remediation reads.
    """
    tenant = _tenant_from_request(request)
    await _authorize_scan_ref(scan_id, tenant)
    patches: list[PatchProposal] = []
    scan_repo_url: str | None = repo_url if isinstance(repo_url, str) else None

    if scan_id in SCANS_DB and SCANS_DB[scan_id].patches:
        patches = SCANS_DB[scan_id].patches
        if not scan_repo_url:
            scan_repo_url = getattr(SCANS_DB[scan_id], "repo_url", None) or getattr(
                SCANS_DB[scan_id], "github_repo_url", None
            )

    scan_uuid = resolve_scan_uuid(scan_id)
    if not scan_repo_url and scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                db_scan = await get_scan_for_org(s, scan_uuid, tenant)
                scan_repo_url = db_scan.repo_url
        except HTTPException:
            raise
        except Exception as e:
            logger.debug("DB scan repo_url lookup error: %s", e)

    if not patches and scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                await get_scan_for_org(s, scan_uuid, tenant)
                stmt = (
                    select(PatchModel)
                    .join(ScanModel, PatchModel.scan_id == ScanModel.id)
                    .where(PatchModel.scan_id == scan_uuid)
                )
                if not tenant.is_system_admin and tenant.org_id is not None:
                    stmt = stmt.where(ScanModel.org_id == tenant.org_id)
                result = await s.execute(stmt)
                db_patches = result.scalars().all()
                if db_patches:
                    patches = [
                        PatchProposal(
                            patch_id=f"patch_{p.id.hex[:8]}",
                            patch_type=PatchType(p.patch_type)
                            if p.patch_type in [e.value for e in PatchType]
                            else PatchType.SCHEMA_MICRODATA,
                            title="Remediation Patch",
                            rationale="Automated discoverability patch",
                            impact_score_delta=5.0,
                            dom_anchor=DOMSelectorAnchor(
                                css_selector="head",
                                tag_name="head",
                                original_snippet="",
                                suggested_snippet="",
                            ),
                            unified_diff=p.content,
                            applied=False,
                        )
                        for p in db_patches
                    ]
        except Exception as e:
            logger.debug("DB patches lookup error: %s", e)

    if not patches:
        return []

    return enrich_patches_with_framework(patches, scan_repo_url)


def parse_github_repo_owner_name(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if "github.com/" in cleaned:
        cleaned = cleaned.split("github.com/")[-1]
    cleaned = cleaned.strip("/")
    parts = [p for p in cleaned.split("/") if p]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Invalid GitHub repository URL format: '{url}'. Expected format: 'owner/repo' or 'https://github.com/owner/repo'"
        )
    return f"{parts[0]}/{parts[1]}"


class ApplyScanPatchRequest(BaseModel):
    repo_url: str | None = None
    target_branch: str = "main"


async def _reconcile_github_pr_after_timeout(
    *,
    gh_client: Any,
    source_repo: str,
    target_branch: str,
    scan_id: str,
    scan_uuid: uuid.UUID | None,
    idem_key: str,
    formatted_patches: list[Any],
    all_validation_checks: list[Any],
    base_sha: str | None,
) -> PullRequestResult | None:
    """If GitHub accepted a PR before a client timeout, recover without opening a second PR."""
    if gh_client is None:
        return None
    try:
        from app.github.pr_engine import build_feature_branch_name

        branch_name = build_feature_branch_name(scan_id)
        source = gh_client.get_repository(source_repo)
        login = gh_client.get_authenticated_login()
        find_labels = [
            f"{source.owner_login}:{branch_name}",
            f"{login}:{branch_name}",
            branch_name,
        ]
        existing = None
        for label in find_labels:
            existing = gh_client.find_open_pull(source, head_full=label, base=target_branch)
            if existing is not None:
                break
        if existing is None:
            logger.info(
                "github_timeout_reconcile_miss scan_id=%s repo=%s branch=%s",
                scan_id,
                source_repo,
                branch_name,
            )
            return None

        remediation_run_id: str | None = None
        if scan_uuid:
            try:
                async with AsyncSessionLocal() as s:
                    async with s.begin():
                        run = await upsert_remediation_run(
                            s,
                            scan_id=scan_uuid,
                            idempotency_key=idem_key,
                            repo_full_name=source_repo,
                            base_branch=target_branch,
                            base_sha=base_sha,
                            head_branch=branch_name,
                            pr_number=existing.number,
                            pr_url=existing.url,
                            lifecycle_state=STATE_PR_OPEN,
                            changed_files=[fp.file_path for fp in formatted_patches],
                            validation_results=all_validation_checks,
                        )
                        remediation_run_id = str(run.id)
            except Exception as persist_err:
                logger.warning(
                    "github_timeout_reconcile_persist_failed scan_id=%s: %s",
                    scan_id,
                    persist_err,
                )

        logger.info(
            "github_timeout_reconcile_hit scan_id=%s pr=%s url=%s",
            scan_id,
            existing.number,
            existing.url,
        )
        return PullRequestResult(
            pr_url=existing.url,
            pr_number=existing.number,
            branch_name=branch_name,
            title=f"FindableAI: Machine Discoverability Remediation Patches ({scan_id})",
            created_at=datetime.now(UTC),
            remediation_run_id=remediation_run_id,
            lifecycle_state=STATE_PR_OPEN,
            validation_checks=all_validation_checks,
            base_sha=base_sha,
            head_sha=None,
        )
    except Exception as reconcile_err:
        logger.warning(
            "github_timeout_reconcile_error scan_id=%s: %s",
            scan_id,
            reconcile_err,
        )
        return None


@router.post(
    "/{scan_id}/patches/apply",
    response_model=PullRequestResult,
    dependencies=[Depends(rate_limit_mutating)],
)
async def apply_scan_patch(
    scan_id: str,
    request: Request,
    payload: ApplyScanPatchRequest | None = None,
) -> PullRequestResult:
    """Triggers autonomous GitHub PR creation for this scan's proposed patches (Task P1-2.4).

    Cache-only path: eligibility is decided by
    ``decide_cache_only_for_scan`` (tenant, scan state, provenance, freshness,
    integrity). Zero new provider calls and zero budget consumption.
    """
    tenant = _tenant_from_request(request)
    assert_permission(tenant, OrgAction.RUN_REMEDIATION)
    await _authorize_scan_ref(scan_id, tenant)
    scan = SCANS_DB.get(scan_id)
    if not scan:
        try:
            scan = await get_scan_for_tenant(scan_id, tenant)
            SCANS_DB[scan_id] = scan
        except HTTPException:
            raise
        except Exception as err:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found") from err

    # Check payload repo_url override
    if payload and payload.repo_url and payload.repo_url.strip():
        scan.repo_url = payload.repo_url.strip()
        scan.github_repo_url = payload.repo_url.strip()

    repo_url = scan.repo_url or scan.github_repo_url
    if not repo_url or not str(repo_url).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No GitHub repository configured for this scan. Provide a repo URL when starting the scan to enable automated PR creation.",
        )

    try:
        source_repo = parse_github_repo_owner_name(str(repo_url))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Persist repo_url back to DB if scan_uuid is valid
    scan_uuid = resolve_scan_uuid(scan_id)
    if scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                async with s.begin():
                    db_s = await s.get(ScanModel, scan_uuid)
                    if db_s:
                        db_s.repo_url = str(repo_url)
        except Exception as db_e:
            logger.debug("Failed saving updated repo_url in database: %s", db_e)

    # Deterministic GitHub apply must not depend on an LLM call; block if a caller
    # incorrectly wires mutation to an exhausted remediation LLM path.
    from app.orchestration.remediation_budget import (
        assert_github_mutation_not_tied_to_llm_budget,
        budget_guard_from_scan_usage,
    )

    assert_github_mutation_not_tied_to_llm_budget(
        would_call_llm=False,
        guard=budget_guard_from_scan_usage(llm_calls_made=scan.llm_calls_made),
    )

    if not scan.patches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No remediation patches available to apply for this scan.",
        )
    if any(getattr(p, "is_synthetic", False) for p in scan.patches):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scan patches are marked synthetic/mock and cannot be applied as remediations.",
        )

    # Required scopes for Personal Access Token (PAT):
    # - Classic PAT: 'repo' (or 'public_repo' for public repositories)
    # - Fine-Grained PAT: 'Pull requests' (Read & Write), 'Contents' (Read & Write), 'Metadata' (Read-only)
    token = settings.GITHUB_TOKEN.strip() if settings.GITHUB_TOKEN else ""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub integration token is not configured on server (GITHUB_TOKEN). Add a GitHub Personal Access Token (PAT with 'repo' scope) to environment variables to enable automated PR creation.",
        )

    # Single source of truth: cache-only remediation eligibility (Phase 3).
    # Runs after cheap input checks, before any GitHub I/O or provider use.
    from app.orchestration.cache_remediation import (
        decide_cache_only_for_scan,
        eligibility_http_exception,
    )

    intents_for_elig = list(scan.intents or [])
    if scan_uuid is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": "no_validated_evidence",
                "detail": "Scan has no durable UUID; cache-only remediation requires persisted evidence.",
                "hint": "Re-run a fresh scan, then retry remediation.",
            },
        )
    try:
        async with AsyncSessionLocal() as s:
            db_s = await get_scan_for_org(s, scan_uuid, tenant)
            decision = await decide_cache_only_for_scan(
                s,
                scan=db_s,
                tenant_org_id=tenant.org_id,
                is_system_admin=tenant.is_system_admin,
                evaluations=intents_for_elig or None,
            )
            budget_before = int(getattr(db_s, "llm_calls_made", 0) or 0)
    except HTTPException:
        raise
    except Exception as elig_err:
        # Fail closed: cannot verify durable provenance → refuse remediation
        # (do not fall back to the in-memory flag alone).
        logger.warning("cache_only_eligibility_unavailable scan_id=%s: %s", scan_id, elig_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": "eligibility_unavailable",
                "detail": "Could not verify cache-only remediation eligibility from durable storage.",
                "hint": "Ensure migrations are applied and the scan has persisted evidence, then retry.",
            },
        ) from elig_err

    if not decision.eligible:
        raise eligibility_http_exception(decision)

    # Structural guarantee: cache-only path must not touch providers / budget.
    request.state.cache_only_remediation = True
    request.state.budget_before_remediation = budget_before

    # Collect durable evidence cites from evaluations (Stage 4 grounding).
    evidence_chunk_ids: list[str] = []
    for intent in scan.intents or []:
        for ref in getattr(intent, "evidence", None) or []:
            cid = getattr(ref, "chunk_id", None)
            if cid:
                evidence_chunk_ids.append(str(cid))
    known_chunk_ids: set[str] | None = None
    if scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                chunk_map = await load_chunk_id_map(s, scan_uuid)
                known_chunk_ids = {str(cid) for cid in chunk_map}
        except Exception as chunk_err:
            logger.debug("Could not load scan chunks for validation: %s", chunk_err)
            known_chunk_ids = None

    formatted_patches: list[FormattedPatch] = []
    all_validation_checks: list[dict[str, Any]] = []
    for p in scan.patches:
        target_type = SchemaRemediationTarget.LOCAL_BUSINESS
        title_lower = p.title.lower()
        if "faq" in title_lower:
            target_type = SchemaRemediationTarget.FAQ_PAGE
        elif "menu" in title_lower:
            target_type = SchemaRemediationTarget.MENU
        elif "hour" in title_lower or "opening" in title_lower:
            target_type = SchemaRemediationTarget.OPENING_HOURS
        elif "website" in title_lower or "organization" in title_lower:
            target_type = SchemaRemediationTarget.LOCAL_BUSINESS

        file_path = p.target_file or "index.html"
        if p.unified_diff and "--- a/" in p.unified_diff:
            first_line = p.unified_diff.splitlines()[0]
            extracted = first_line.replace("--- a/", "").strip()
            if extracted.endswith((".html", ".htm")):
                file_path = extracted

        pre = validate_patch_candidate(
            file_path=file_path,
            patch_text=p.unified_diff or "",
            is_synthetic=bool(getattr(p, "is_synthetic", False)),
            current_file_content=None,
            original_snippet=getattr(p.dom_anchor, "original_snippet", None),
            evidence_chunk_ids=evidence_chunk_ids,
            known_scan_chunk_ids=known_chunk_ids,
            require_evidence=True,
        )
        all_validation_checks.extend(pre.as_dicts())

        formatted_patches.append(
            FormattedPatch(
                opportunity_id=p.patch_id,
                schema_type=target_type,
                file_path=file_path,
                patch_text=p.unified_diff,
                changed_lines=len(
                    [line for line in p.unified_diff.splitlines() if line.startswith(("+", "-"))]
                ),
                status=PatchFormatStatus.APPLIED,
                message=p.rationale,
                patched_html=p.dom_anchor.suggested_snippet,
            )
        )

    # Path/synthetic/size/evidence must pass before any GitHub mutation.
    critical_blocked = any(
        c.get("safety_critical")
        and c.get("status") in ("failed", "inconclusive")
        and c.get("name")
        in (
            "not_synthetic",
            "path_safe",
            "path_traversal",
            "path_suffix",
            "path_present",
            "path_policy",
            "patch_nonempty",
            "patch_size",
            "no_secrets",
            "no_binary",
            "evidence_grounding",
        )
        for c in all_validation_checks
    )
    # file_content inconclusive is expected pre-fetch — re-check after GitHub read.
    target_branch = (
        payload.target_branch.strip()
        if payload and payload.target_branch and payload.target_branch.strip()
        else "main"
    )
    idem_key = make_idempotency_key(scan_id, source_repo, target_branch)
    remediation_run_id: str | None = None

    if critical_blocked:
        if scan_uuid:
            try:
                async with AsyncSessionLocal() as s:
                    async with s.begin():
                        run = await upsert_remediation_run(
                            s,
                            scan_id=scan_uuid,
                            idempotency_key=idem_key,
                            repo_full_name=source_repo,
                            base_branch=target_branch,
                            lifecycle_state=STATE_VALIDATION_FAILED,
                            validation_results=all_validation_checks,
                            error="Deterministic validation blocked PR creation",
                        )
                        remediation_run_id = str(run.id)
            except Exception as persist_err:
                logger.debug("Validation-failure persist skipped: %s", persist_err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Patch validation failed; validated PR creation blocked",
                "checks": all_validation_checks,
                "remediation_run_id": remediation_run_id,
                "lifecycle_state": STATE_VALIDATION_FAILED,
            },
        )

    current_score = scan.f_score.overall_score if scan.f_score else 0.0
    total_delta = sum(p.impact_score_delta for p in scan.patches)
    projected_score = min(100.0, max(0.0, current_score + total_delta))

    # Generate optional llms.txt and robots.txt manifests for PR integration
    llms_manifest: str | None = None
    robots_manifest: str | None = None
    try:
        parsed_target = urlparse(scan.target_url)
        domain = parsed_target.netloc or "example.com"
        crawled_urls = [p.url for p in (scan.crawled_pages or []) if p.url] or [scan.target_url]
        llms_manifest = generate_llms_txt(
            domain=domain,
            crawled_urls=crawled_urls,
        )
        robots_manifest = generate_optimized_robots_txt(
            domain=domain,
        )
    except Exception as manifest_err:
        logger.debug("Manifest generation skipped for PR on scan %s: %s", scan_id, manifest_err)

    gh_client: Any = None
    base_sha: str | None = None
    try:
        gh_client = build_pygithub_client_from_token(token)
        # Re-validate against live base file content when readable.
        try:
            repo_ref = gh_client.get_repository(source_repo)
            base_sha = None
            for fp in {fp.file_path for fp in formatted_patches}:
                try:
                    file_obj = gh_client.get_file(repo_ref, fp, ref=target_branch)
                    content = file_obj.content
                    post = validate_patch_candidate(
                        file_path=fp,
                        patch_text="x",  # size already validated
                        is_synthetic=False,
                        current_file_content=content,
                        original_snippet=None,
                        evidence_chunk_ids=evidence_chunk_ids,
                        known_scan_chunk_ids=known_chunk_ids,
                        require_evidence=True,
                    )
                    # Keep path/content checks; ignore redundant patch_nonempty on placeholder.
                    for chk in post.as_dicts():
                        if chk["name"] in (
                            "html_parse",
                            "jsonld_syntax",
                            "json_parse",
                            "base_freshness",
                        ):
                            all_validation_checks.append(chk)
                            if chk["safety_critical"] and chk["status"] in (
                                "failed",
                                "inconclusive",
                            ):
                                raise HTTPException(
                                    status_code=status.HTTP_400_BAD_REQUEST,
                                    detail={
                                        "message": "Live file validation blocked PR",
                                        "checks": all_validation_checks,
                                    },
                                )
                except HTTPException:
                    raise
                except Exception as file_err:
                    logger.debug("Live file fetch for %s skipped: %s", fp, file_err)
        except HTTPException:
            raise
        except Exception as repo_err:
            logger.debug("Base repo preflight skipped: %s", repo_err)

        if scan_uuid:
            try:
                async with AsyncSessionLocal() as s:
                    async with s.begin():
                        run = await upsert_remediation_run(
                            s,
                            scan_id=scan_uuid,
                            idempotency_key=idem_key,
                            repo_full_name=source_repo,
                            base_branch=target_branch,
                            base_sha=base_sha,
                            lifecycle_state=STATE_MUTATING,
                            validation_results=all_validation_checks,
                        )
                        # Idempotent: existing PR_OPEN returns without remutation.
                        if run.lifecycle_state == STATE_PR_OPEN and run.pr_url and run.pr_number:
                            return PullRequestResult(
                                pr_url=run.pr_url,
                                pr_number=run.pr_number,
                                branch_name=run.head_branch or "",
                                title=f"FindableAI: Machine Discoverability Remediation Patches ({scan_id})",
                                created_at=run.updated_at or datetime.now(UTC),
                                remediation_run_id=str(run.id),
                                lifecycle_state=run.lifecycle_state,
                                validation_checks=all_validation_checks,
                                base_sha=run.base_sha,
                                head_sha=run.head_sha,
                            )
                        remediation_run_id = str(run.id)
            except Exception as persist_err:
                logger.debug("Remediation mutating state persist skipped: %s", persist_err)

        pr_service = GitHubPRService(gh_client)
        pr_request = PREngineRequest(
            source_repo=source_repo,
            target_branch=target_branch,
            scan_id=scan_id,
            patches=formatted_patches,
            intent_evaluations=scan.intents,
            current_score=current_score,
            projected_score=projected_score,
            llms_txt_content=llms_manifest,
            robots_txt_content=robots_manifest,
            commit_message=f"fix(discoverability): apply FindableAI remediation patches for {scan_id}",
            pr_title=f"FindableAI: Machine Discoverability Remediation Patches ({scan_id})",
        )
        try:
            result = pr_service.create_remediation_pr(pr_request)
        except PREngineError as p_err:
            if p_err.reason == "branch_exists":
                suffix = datetime.now(UTC).strftime("%m%d%H%M")
                pr_request.scan_id = f"{scan_id}-{suffix}"
                result = pr_service.create_remediation_pr(pr_request)
            else:
                raise
        logger.info("GitHub PR created successfully: PR #%s at %s", result.pr_number, result.pr_url)

        lifecycle_state = STATE_PR_OPEN
        if scan_uuid:
            try:
                async with AsyncSessionLocal() as s:
                    async with s.begin():
                        run = await upsert_remediation_run(
                            s,
                            scan_id=scan_uuid,
                            idempotency_key=idem_key,
                            repo_full_name=source_repo,
                            base_branch=target_branch,
                            base_sha=base_sha,
                            head_branch=result.generated_branch,
                            head_sha=getattr(result, "head_sha", None),
                            pr_number=result.pr_number,
                            pr_url=result.pr_url,
                            lifecycle_state=STATE_PR_OPEN,
                            changed_files=[fp.file_path for fp in formatted_patches],
                            validation_results=all_validation_checks,
                        )
                        remediation_run_id = str(run.id)
                        # Persist PR URL onto scan patch rows when present.
                        patch_rows = (
                            (
                                await s.execute(
                                    select(PatchModel).where(PatchModel.scan_id == scan_uuid)
                                )
                            )
                            .scalars()
                            .all()
                        )
                        for patch_row in patch_rows:
                            patch_row.pr_url = result.pr_url
            except Exception as persist_err:
                lifecycle_state = STATE_PR_PERSIST_FAILED
                logger.warning(
                    "GitHub PR succeeded but lifecycle persist failed for %s: %s",
                    scan_id,
                    persist_err,
                )

        return PullRequestResult(
            pr_url=result.pr_url,
            pr_number=result.pr_number,
            branch_name=result.generated_branch,
            title=f"FindableAI: Machine Discoverability Remediation Patches ({scan_id})",
            created_at=datetime.now(UTC),
            remediation_run_id=remediation_run_id,
            lifecycle_state=lifecycle_state,
            validation_checks=all_validation_checks,
            base_sha=base_sha,
            head_sha=getattr(result, "head_sha", None),
        )
    except HTTPException:
        raise
    except (PREngineError, GitHubClientError) as exc:
        # Ambiguous timeout: GitHub may have accepted the PR before the client
        # saw a response. Reconcile via open-PR lookup before surfacing failure.
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            reconciled = await _reconcile_github_pr_after_timeout(
                gh_client=gh_client,
                source_repo=source_repo,
                target_branch=target_branch,
                scan_id=scan_id,
                scan_uuid=scan_uuid,
                idem_key=idem_key,
                formatted_patches=formatted_patches,
                all_validation_checks=all_validation_checks,
                base_sha=base_sha,
            )
            if reconciled is not None:
                return reconciled
        if scan_uuid:
            try:
                async with AsyncSessionLocal() as s:
                    async with s.begin():
                        await upsert_remediation_run(
                            s,
                            scan_id=scan_uuid,
                            idempotency_key=idem_key,
                            repo_full_name=source_repo,
                            base_branch=target_branch,
                            base_sha=base_sha,
                            lifecycle_state=STATE_FAILED,
                            validation_results=all_validation_checks,
                            error=sanitize_public_error(str(exc)),
                        )
            except Exception as persist_err:
                logger.debug("GitHub failure state persist skipped: %s", persist_err)
        logger.error("GitHub PR creation failed for scan %s: %s", scan_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub PR creation failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during PR creation for scan %s", scan_id)
        msg = str(exc)
        if "timed out" in msg.lower() or "timeout" in msg.lower():
            reconciled = await _reconcile_github_pr_after_timeout(
                gh_client=gh_client,
                source_repo=source_repo,
                target_branch=target_branch,
                scan_id=scan_id,
                scan_uuid=scan_uuid,
                idem_key=idem_key,
                formatted_patches=formatted_patches,
                all_validation_checks=all_validation_checks,
                base_sha=base_sha,
            )
            if reconciled is not None:
                return reconciled
            if scan_uuid:
                try:
                    async with AsyncSessionLocal() as s:
                        async with s.begin():
                            await upsert_remediation_run(
                                s,
                                scan_id=scan_uuid,
                                idempotency_key=idem_key,
                                repo_full_name=source_repo,
                                base_branch=target_branch,
                                base_sha=base_sha,
                                lifecycle_state=STATE_FAILED,
                                validation_results=all_validation_checks,
                                error="GitHub API timed out",
                            )
                except Exception as persist_err:
                    logger.debug("Timeout failure state persist skipped: %s", persist_err)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="GitHub API timed out while communicating with repository. Please retry.",
            ) from exc
        if scan_uuid:
            try:
                async with AsyncSessionLocal() as s:
                    async with s.begin():
                        await upsert_remediation_run(
                            s,
                            scan_id=scan_uuid,
                            idempotency_key=idem_key,
                            repo_full_name=source_repo,
                            base_branch=target_branch,
                            base_sha=base_sha,
                            lifecycle_state=STATE_FAILED,
                            validation_results=all_validation_checks,
                            error=sanitize_public_error(str(exc)),
                        )
            except Exception as persist_err:
                logger.debug("Unexpected failure state persist skipped: %s", persist_err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error creating GitHub PR: {exc}",
        ) from exc


@router.post(
    "/{scan_id}/patches/validate",
    response_model=PatchValidationResponse,
    dependencies=[Depends(rate_limit_mutating)],
)
async def validate_scan_patches(scan_id: str, request: Request) -> PatchValidationResponse:
    """Run deterministic patch validators without mutating GitHub."""
    tenant = _tenant_from_request(request)
    assert_permission(tenant, OrgAction.RUN_REMEDIATION)
    await _authorize_scan_ref(scan_id, tenant)
    scan = SCANS_DB.get(scan_id)
    if not scan:
        scan = await get_scan_for_tenant(scan_id, tenant)

    from app.orchestration.cache_remediation import (
        decide_cache_only_for_scan,
        eligibility_http_exception,
    )

    scan_uuid = resolve_scan_uuid(scan_id)
    if scan_uuid is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "no_validated_evidence", "detail": "Scan has no durable UUID."},
        )
    async with AsyncSessionLocal() as s:
        db_s = await get_scan_for_org(s, scan_uuid, tenant)
        decision = await decide_cache_only_for_scan(
            s,
            scan=db_s,
            tenant_org_id=tenant.org_id,
            is_system_admin=tenant.is_system_admin,
            evaluations=list(scan.intents or []) or None,
        )
    if not decision.eligible:
        raise eligibility_http_exception(decision)
    if not scan.patches:
        raise HTTPException(status_code=400, detail="No patches to validate.")
    if any(getattr(p, "is_synthetic", False) for p in scan.patches):
        raise HTTPException(status_code=400, detail="Synthetic patches cannot be validated for PR.")

    evidence_chunk_ids: list[str] = []
    for intent in scan.intents or []:
        for ref in getattr(intent, "evidence", None) or []:
            cid = getattr(ref, "chunk_id", None)
            if cid:
                evidence_chunk_ids.append(str(cid))
    known_chunk_ids: set[str] | None = None
    try:
        async with AsyncSessionLocal() as s:
            chunk_map = await load_chunk_id_map(s, scan_uuid)
            known_chunk_ids = {str(cid) for cid in chunk_map}
    except Exception:
        known_chunk_ids = None

    checks: list[ValidationCheckOut] = []
    eligible = True
    for p in scan.patches:
        file_path = p.target_file or "index.html"
        result = validate_patch_candidate(
            file_path=file_path,
            patch_text=p.unified_diff or "",
            is_synthetic=bool(getattr(p, "is_synthetic", False)),
            current_file_content=None,
            original_snippet=getattr(p.dom_anchor, "original_snippet", None),
            evidence_chunk_ids=evidence_chunk_ids,
            known_scan_chunk_ids=known_chunk_ids,
            require_evidence=True,
        )
        if not result.eligible_for_validated_pr:
            eligible = False
        checks.extend(ValidationCheckOut(**c) for c in result.as_dicts())
    return PatchValidationResponse(eligible_for_validated_pr=eligible, checks=checks)


@router.get(
    "/{scan_id}/remediation",
    response_model=list[RemediationRunOut],
)
async def list_scan_remediation_runs(scan_id: str, request: Request) -> list[RemediationRunOut]:
    """Return persisted PR lifecycle rows for a scan (fresh DB read)."""
    tenant = _tenant_from_request(request)
    scan_uuid = await _authorize_scan_ref(scan_id, tenant)
    if not scan_uuid:
        raise HTTPException(status_code=404, detail="Scan not found")
    try:
        async with AsyncSessionLocal() as s:
            await get_scan_for_org(s, scan_uuid, tenant)
            runs = await get_runs_for_scan(s, scan_uuid)
            return [
                RemediationRunOut(
                    id=r.id,
                    scan_id=r.scan_id,
                    idempotency_key=r.idempotency_key,
                    repo_full_name=r.repo_full_name,
                    base_branch=r.base_branch,
                    base_sha=r.base_sha,
                    head_branch=r.head_branch,
                    head_sha=r.head_sha,
                    pr_number=r.pr_number,
                    pr_url=r.pr_url,
                    lifecycle_state=r.lifecycle_state,
                    changed_files=list(r.changed_files or []),
                    validation_results=list(r.validation_results or []),
                    error=r.error,
                    state_revision=int(getattr(r, "state_revision", 0) or 0),
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
                for r in runs
            ]
    except Exception as exc:
        logger.debug("Remediation list unavailable: %s", exc)
        return []


@router.post(
    "/{scan_id}/remediation/verify",
    response_model=VerificationRunOut,
    dependencies=[Depends(rate_limit_mutating)],
)
async def verify_scan_remediation(
    scan_id: str,
    request: Request,
    payload: VerifyRemediationRequest | None = None,
) -> VerificationRunOut:
    """Post-PR verification against the PR head revision using fresh file content."""
    tenant = _tenant_from_request(request)
    scan_uuid = await _authorize_scan_ref(scan_id, tenant)
    scan = SCANS_DB.get(scan_id)
    if not scan:
        scan = await get_scan_for_tenant(scan_id, tenant)
    if not scan_uuid:
        raise HTTPException(status_code=404, detail="Scan not found")

    token = settings.GITHUB_TOKEN.strip() if settings.GITHUB_TOKEN else ""
    if not token:
        raise HTTPException(
            status_code=400,
            detail="GITHUB_TOKEN not configured; verification blocked.",
        )

    try:
        async with AsyncSessionLocal() as s:
            runs = await get_runs_for_scan(s, scan_uuid)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Database unavailable for verification"
        ) from exc

    run = None
    want_id = payload.remediation_run_id if payload else None
    for r in runs:
        if want_id and r.id == want_id:
            run = r
            break
        if want_id is None and r.lifecycle_state in (
            STATE_PR_OPEN,
            STATE_VERIFIED,
            STATE_VERIFYING,
        ):
            run = r
            break
    if run is None or not run.pr_number or not run.head_branch:
        raise HTTPException(
            status_code=400,
            detail="No recoverable PR remediation run with head branch to verify.",
        )
    # PR open / prior verify terminals only — never verify from validation_failed alone.
    if run.lifecycle_state not in (
        STATE_PR_OPEN,
        STATE_PR_PERSIST_FAILED,
        STATE_VERIFYING,
        STATE_VERIFIED,
        STATE_FAILED,
        STATE_BLOCKED,
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Remediation run is not ready for verification "
                f"(lifecycle_state={run.lifecycle_state!r})."
            ),
        )

    keywords = list(payload.acceptance_keywords) if payload and payload.acceptance_keywords else []
    if not keywords:
        for intent in scan.intents or []:
            if getattr(intent, "status", None) and str(intent.status) in (
                "CONTRADICTED",
                "UNKNOWN",
                "PARTIALLY_SUPPORTED",
            ):
                keywords.extend(str(intent.query or "").lower().split()[:6])
        keywords = [w for w in keywords if len(w) > 3][:12]

    # Mark verification in-flight before remote reads (durable, resumable).
    try:
        async with AsyncSessionLocal() as s:
            async with s.begin():
                await upsert_remediation_run(
                    s,
                    scan_id=scan_uuid,
                    idempotency_key=run.idempotency_key,
                    repo_full_name=run.repo_full_name,
                    base_branch=run.base_branch,
                    lifecycle_state=STATE_VERIFYING,
                    head_branch=run.head_branch,
                    head_sha=run.head_sha,
                    pr_number=run.pr_number,
                    pr_url=run.pr_url,
                )
    except Exception as persist_err:
        logger.warning("Could not persist verifying state for %s: %s", scan_id, persist_err)

    patched_content: str | None = None
    evaluated_rev = run.head_sha
    ops_error: str | None = None
    validation_passed = False
    try:
        gh_client = build_pygithub_client_from_token(token)
        repo_ref = gh_client.get_repository(run.repo_full_name)
        files = list(run.changed_files or ["index.html"])
        target = str(files[0]) if files else "index.html"

        # Bind verification to an immutable commit SHA — never to a mutable branch tip alone.
        bound_sha = (run.head_sha or "").strip() or None
        if not bound_sha:
            # Resolve branch tip once, persist it, then evaluate only that SHA.
            try:
                bound_sha = gh_client.get_branch_sha(repo_ref, run.head_branch)
            except Exception:
                bound_sha = None
            if not bound_sha:
                raise RuntimeError(
                    "Cannot resolve immutable head SHA for verification; refusing branch-only check"
                )
            async with AsyncSessionLocal() as s:
                async with s.begin():
                    await upsert_remediation_run(
                        s,
                        scan_id=scan_uuid,
                        idempotency_key=run.idempotency_key,
                        repo_full_name=run.repo_full_name,
                        base_branch=run.base_branch,
                        lifecycle_state=STATE_VERIFYING,
                        head_branch=run.head_branch,
                        head_sha=bound_sha,
                        pr_number=run.pr_number,
                        pr_url=run.pr_url,
                    )
            run.head_sha = bound_sha

        file_obj = gh_client.get_file(repo_ref, target, ref=bound_sha)
        patched_content = file_obj.content
        evaluated_rev = bound_sha
        # Blob/commit SHAs may differ by object type; prefer the bound commit SHA.
        blob_sha = getattr(file_obj, "sha", None)
        if blob_sha and bound_sha and str(blob_sha) == str(bound_sha):
            evaluated_rev = str(blob_sha)

        # If the PR head moved away from the recorded SHA, do not claim a fix.
        try:
            tip_sha = gh_client.get_branch_sha(repo_ref, run.head_branch)
        except Exception:
            tip_sha = None
        if tip_sha and bound_sha and str(tip_sha) != str(bound_sha):
            ops_error = (
                f"PR head moved during verification (recorded={bound_sha}, tip={tip_sha}); "
                "previous result is stale — re-verify the new revision"
            )
            patched_content = None
            validation_passed = False
        else:
            html_check = validate_patch_candidate(
                file_path=str(target),
                patch_text="verified",
                is_synthetic=False,
                current_file_content=patched_content,
                require_evidence=False,
            )
            validation_passed = not html_check.failed_critical
    except Exception as exc:
        ops_error = sanitize_public_error(str(exc))

    issue_outcome, ops_status, detail = evaluate_verification_outcome(
        original_issue_keywords=keywords,
        patched_content=patched_content,
        validation_passed=validation_passed,
        operational_error=ops_error,
    )
    # Projected score is never consulted; PR open is never treated as fixed.
    terminal_state = lifecycle_state_for_verification_outcome(issue_outcome)
    fresh_evidence = []
    if patched_content:
        excerpt = patched_content[:280]
        fresh_evidence.append(
            {
                "observation_phase": "verification",
                "source": "pr_head_file",
                "revision": evaluated_rev,
                "excerpt": excerpt,
            }
        )

    try:
        async with AsyncSessionLocal() as s:
            async with s.begin():
                await upsert_remediation_run(
                    s,
                    scan_id=scan_uuid,
                    idempotency_key=run.idempotency_key,
                    repo_full_name=run.repo_full_name,
                    base_branch=run.base_branch,
                    lifecycle_state=terminal_state,
                    head_sha=evaluated_rev,
                    error=None if issue_outcome == "fixed" else detail,
                )
                row = await persist_verification_run(
                    s,
                    scan_id=scan_uuid,
                    remediation_run_id=run.id,
                    evaluated_revision=evaluated_rev,
                    issue_outcome=issue_outcome,
                    operational_status=ops_status,
                    detail=detail,
                    fresh_evidence=fresh_evidence,
                )
                return VerificationRunOut(
                    id=row.id,
                    scan_id=row.scan_id,
                    remediation_run_id=row.remediation_run_id,
                    evaluated_revision=row.evaluated_revision,
                    issue_outcome=row.issue_outcome,
                    operational_status=row.operational_status,
                    detail=row.detail,
                    fresh_evidence=list(row.fresh_evidence or []),
                    created_at=row.created_at,
                    verification_method=getattr(row, "verification_method", "heuristic_post_pr"),
                    fully_verified=bool(getattr(row, "fully_verified", False)),
                    is_full_rescan=bool(getattr(row, "is_full_rescan", False)),
                )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to persist verification: {sanitize_public_error(str(exc))}",
        ) from exc


@router.get(
    "/{scan_id}/remediation/verifications",
    response_model=list[VerificationRunOut],
)
async def list_scan_verifications(scan_id: str, request: Request) -> list[VerificationRunOut]:
    tenant = _tenant_from_request(request)
    scan_uuid = await _authorize_scan_ref(scan_id, tenant)
    if not scan_uuid:
        raise HTTPException(status_code=404, detail="Scan not found")
    try:
        async with AsyncSessionLocal() as s:
            await get_scan_for_org(s, scan_uuid, tenant)
            rows = await list_verifications_for_scan(s, scan_uuid)
            return [
                VerificationRunOut(
                    id=r.id,
                    scan_id=r.scan_id,
                    remediation_run_id=r.remediation_run_id,
                    evaluated_revision=r.evaluated_revision,
                    issue_outcome=r.issue_outcome,
                    operational_status=r.operational_status,
                    detail=r.detail,
                    fresh_evidence=list(r.fresh_evidence or []),
                    created_at=r.created_at,
                    verification_method=getattr(r, "verification_method", "heuristic_post_pr"),
                    fully_verified=bool(getattr(r, "fully_verified", False)),
                    is_full_rescan=bool(getattr(r, "is_full_rescan", False)),
                )
                for r in rows
            ]
    except Exception as exc:
        logger.debug("Verification list unavailable: %s", exc)
        return []


@router.get("/{scan_id}/lighthouse", response_model=LighthouseResponse)
async def get_scan_lighthouse(scan_id: str, request: Request) -> LighthouseResponse:
    """
    Fetches deterministic AI Lighthouse per-engine readiness scores and crawler governance.
    Evaluates site readiness for ChatGPT, Gemini, Perplexity, and Claude per Doc 5 §4.4.
    """
    tenant = _tenant_from_request(request)
    scan_uuid = await _authorize_scan_ref(scan_id, tenant)
    # 1. Check in-memory store
    if scan_id in LIGHTHOUSE_DB:
        return LIGHTHOUSE_DB[scan_id]

    # Resolve scan UUID
    scan_uuid = resolve_scan_uuid(scan_id)
    if scan_uuid:
        if str(scan_uuid) in LIGHTHOUSE_DB:
            return LIGHTHOUSE_DB[str(scan_uuid)]
        if scan_uuid.hex in LIGHTHOUSE_DB:
            return LIGHTHOUSE_DB[scan_uuid.hex]
        short_id = f"scan_{scan_uuid.hex[:12]}"
        if short_id in LIGHTHOUSE_DB:
            return LIGHTHOUSE_DB[short_id]

    # 2. Check if scan exists in SCANS_DB to compute dynamically
    record = SCANS_DB.get(scan_id)
    if not record and scan_uuid:
        record = (
            SCANS_DB.get(str(scan_uuid))
            or SCANS_DB.get(scan_uuid.hex)
            or SCANS_DB.get(f"scan_{scan_uuid.hex[:12]}")
        )

    if record:
        chunks = (
            CHUNKS_DB.get(scan_id) or (CHUNKS_DB.get(str(scan_uuid)) if scan_uuid else None) or []
        )
        robots_txt = (
            ROBOTS_DB.get(scan_id) or (ROBOTS_DB.get(str(scan_uuid)) if scan_uuid else "") or ""
        )
        engine = LighthouseEngine(
            url=record.target_url,
            chunks=chunks,
            evaluations=record.intents or [],
            contradictions=record.contradictions or [],
            robots_txt=robots_txt,
            scan_id=scan_id,
        )
        resp = engine.evaluate()
        LIGHTHOUSE_DB[scan_id] = resp
        return resp

    # 3. Check persistent database if available
    if scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                db_scan = await get_scan_for_org(s, scan_uuid, tenant)
                engine = LighthouseEngine(
                    url=db_scan.url,
                    scan_id=scan_id,
                )
                resp = engine.evaluate()
                LIGHTHOUSE_DB[scan_id] = resp
                return resp
        except HTTPException:
            raise
        except Exception as db_err:
            logger.debug("Database lookup skipped for scan %s: %s", scan_id, db_err)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Scan not found",
    )


@router.get("", response_model=list[ScanResponse])
async def list_scans(
    request: Request,
    response: Response,
    limit: int | None = Query(
        default=None,
        ge=1,
        le=100,
        description="Page size (default 20, max 100)",
    ),
    cursor: str | None = Query(
        default=None,
        description="Opaque keyset cursor from X-Next-Cursor of the prior page",
    ),
) -> list[ScanResponse]:
    """List scans from PostgreSQL only (SQL org filter + keyset pagination).

    Does not merge process-local ``SCANS_DB``. Legacy ``org_id IS NULL`` rows stay
    hidden from non-admin tenants. Response bodies are list-appropriate fields only.
    When another page exists, ``X-Next-Cursor`` is set.
    """
    tenant = _tenant_from_request(request)
    assert_permission(tenant, OrgAction.READ_SCANS)
    page_size = clamp_list_limit(limit)

    try:
        async with AsyncSessionLocal() as s:
            rows = await list_scans_for_org(
                s, tenant, limit=page_size, cursor=cursor
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("list_scans_db_unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scan listing unavailable",
        ) from exc

    items: list[ScanResponse] = []
    for db_scan in rows:
        sid = f"scan_{db_scan.id.hex}"
        status_raw = str(db_scan.status or "")
        if status_raw in {e.value for e in ScanStatus}:
            mapped_status = ScanStatus(status_raw)
        else:
            mapped_status = _db_status_to_scan_status(status_raw)
        items.append(
            ScanResponse(
                scan_id=sid,
                target_url=db_scan.url,
                status=mapped_status,
                created_at=db_scan.created_at or datetime.now(UTC),
                org_id=_org_id_str(db_scan.org_id),
                repo_url=db_scan.repo_url,
                github_repo_url=db_scan.repo_url,
                completed_at=db_scan.completed_at,
                error=db_scan.error,
                f_score=None,
                summary=None,
                intents=[],
                contradictions=[],
                patches=[],
                crawled_pages=[],
            )
        )

    # Full page ⇒ another page may exist; emit keyset cursor for the next request.
    if len(rows) == page_size and rows:
        last = rows[-1]
        if last.created_at is not None:
            response.headers["X-Next-Cursor"] = encode_scan_list_cursor(
                created_at=last.created_at,
                scan_id=last.id,
            )
    return items


class EvaluateScanRequest(BaseModel):
    personas: list[str] | None = None


async def run_stage_crawl(
    scan_id: str,
    scan_uuid: uuid.UUID,
    url: str,
    max_pages: int,
    auto_evaluate: bool = True,
) -> bool:
    await run_scan_pipeline(
        scan_id=scan_id,
        scan_uuid=scan_uuid,
        url=url,
        max_pages=max_pages,
        personas=None,
    )
    return True


async def run_stage_evaluate(
    scan_id: str,
    scan_uuid: uuid.UUID,
    personas: list[str] | None = None,
    auto_remediate: bool = True,
) -> bool:
    record = SCANS_DB.get(scan_id) or SCANS_DB.get(str(scan_uuid))
    url = record.target_url if record else "https://example.com"
    await run_scan_pipeline(
        scan_id=scan_id,
        scan_uuid=scan_uuid,
        url=url,
        max_pages=1,
        personas=personas,
    )
    return True


async def run_stage_remediate(
    scan_id: str,
    scan_uuid: uuid.UUID,
) -> list[PatchProposal]:
    extracted_chunks = CHUNKS_DB.get(scan_id) or CHUNKS_DB.get(str(scan_uuid)) or []
    html_docs = HTML_DB.get(scan_id) or HTML_DB.get(str(scan_uuid)) or []
    score_inputs = SCORE_INPUTS_DB.get(scan_id) or SCORE_INPUTS_DB.get(str(scan_uuid))
    score_breakdown = SCORE_BREAKDOWN_DB.get(scan_id) or SCORE_BREAKDOWN_DB.get(str(scan_uuid))
    record = SCANS_DB.get(scan_id) or SCANS_DB.get(str(scan_uuid))
    url = record.target_url if record else ""

    patches: list[PatchProposal] = []
    if score_breakdown and html_docs and score_inputs:
        try:
            real_patches = assemble_real_patches(
                html=html_docs[0],
                url=url,
                score_inputs=score_inputs,
                score_breakdown=score_breakdown,
                chunks=extracted_chunks,
                contradictions=score_inputs.contradictions,
            )
            patches = list(real_patches) if real_patches else []
        except Exception as patch_err:
            logger.warning("Real patch assembly error in run_stage_remediate: %s", patch_err)
    if record:
        record.patches = patches
    return patches


@router.post(
    "/{scan_id}/evaluate",
    response_model=ScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit_scans)],
)
async def evaluate_scan(
    scan_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    payload: EvaluateScanRequest | None = None,
) -> ScanResponse:
    tenant = _tenant_from_request(request)
    scan_uuid = await _authorize_scan_ref(scan_id, tenant)
    if not scan_uuid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found",
        )

    record = SCANS_DB.get(scan_id) or SCANS_DB.get(str(scan_uuid))
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found",
        )

    personas = payload.personas if payload and payload.personas else None
    record.status = ScanStatus.SYNTHESIZING_INTENTS

    background_tasks.add_task(
        run_stage_evaluate,
        scan_id=scan_id,
        scan_uuid=scan_uuid,
        personas=personas,
        auto_remediate=True,
    )
    return record


@router.post(
    "/{scan_id}/remediate",
    response_model=list[PatchProposal],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit_mutating)],
)
async def remediate_scan(
    scan_id: str,
    request: Request,
) -> list[PatchProposal]:
    tenant = _tenant_from_request(request)
    scan_uuid = await _authorize_scan_ref(scan_id, tenant)
    if not scan_uuid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan not found",
        )
    return await run_stage_remediate(scan_id=scan_id, scan_uuid=scan_uuid)
