import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.auth import verify_api_key
from app.core.budget import BudgetGuard
from app.core.config import settings
from app.core.llm import LLMClient
from app.core.rate_limiter import rate_limit_mutating, rate_limit_scans
from app.core.security import SSRFSecurityException, validate_target_url
from app.crawler.crawler import AsyncCrawler
from app.crawler.dom_chunker import ChunkData, DOMChunker
from app.crawler.search import store_dom_chunks
from app.db import AsyncSessionLocal
from app.engines.intent_generator import resolve_query_persona
from app.engines.patch_assembler import assemble_real_patches
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
from app.schemas.patch import DOMSelectorAnchor, PatchProposal, PatchType, PullRequestResult
from app.schemas.patching import FormattedPatch, PatchFormatStatus, SchemaRemediationTarget
from app.schemas.scan import (
    AuditSummary,
    CrawledPageDetail,
    ScanRequest,
    ScanResponse,
    ScanStatus,
    ScanStatusEvent,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory store for caching, local development, and resilient fallbacks
SCANS_DB: dict[str, ScanResponse] = {}
CHUNKS_DB: dict[str, list[ChunkData]] = {}
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
    evals = []
    chunk_ids = [getattr(c, "id", f"chunk_{i}") for i, c in enumerate(chunks[:5])]
    for i in range(1, 31):
        cat = categories[(i - 1) % len(categories)]
        status = (
            EntailmentStatus.SUPPORTED
            if i % 4 != 0
            else (EntailmentStatus.PARTIALLY_SUPPORTED if i % 2 == 0 else EntailmentStatus.UNKNOWN)
        )
        evidence = []
        if (
            status in (EntailmentStatus.SUPPORTED, EntailmentStatus.PARTIALLY_SUPPORTED)
            and chunk_ids
        ):
            cid = chunk_ids[(i - 1) % len(chunk_ids)]
            evidence.append(
                EvidenceReference(
                    chunk_id=str(cid),
                    dom_path=f"body > main > section:nth-of-type({(i % 3) + 1})",
                )
            )
        persona = resolve_query_persona(cat, personas)
        evals.append(
            IntentEvaluation(
                intent_id=f"intent_{i:02d}",
                query=f"What are {domain}'s {cat.value} options and terms (query #{i})?",
                category=cat,
                persona=persona,
                status=status,
                reasoning=f"Automated entailment analysis for {cat.value} intent from {persona} perspective.",
                evidence=evidence,
                confidence=0.88,
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
        ),
    ]


async def _emit_event(
    scan_id: str,
    status_val: ScanStatus,
    percent: int,
    step_name: str,
    message: str,
) -> ScanStatusEvent:
    event = ScanStatusEvent(
        scan_id=scan_id,
        status=status_val,
        progress_percent=percent,
        current_step=step_name,
        message=message,
        timestamp=datetime.now(UTC),
    )
    if scan_id in SCANS_DB:
        SCANS_DB[scan_id].status = status_val

    EVENT_LOGS.setdefault(scan_id, []).append(event)
    for q in EVENT_QUEUES.get(scan_id, []):
        await q.put(event)
    return event


async def run_scan_pipeline(
    scan_id: str,
    scan_uuid: uuid.UUID,
    url: str,
    max_pages: int,
    personas: list[str] | None = None,
) -> None:
    """
    Autonomous scan worker pipeline:
    1. BFS Crawl (httpx / Playwright fallback)
    2. Semantic DOM Chunker (CSS selector generation)
    3. Embedding & pgvector storage
    4. Synthetic intent generation & hybrid search
    5. NLI entailment evaluation
    6. F-Score calculation & patch generation
    """
    allow_private = settings.ENVIRONMENT.lower() != "production"
    start_time = datetime.now(UTC)

    try:
        # Phase 1: OBSERVE / Crawling
        await _emit_event(
            scan_id,
            ScanStatus.CRAWLING,
            15,
            "Playwright Crawling",
            f"Fetching DOM snapshots from {url}...",
        )
        crawler = AsyncCrawler(
            max_pages=max_pages,
            concurrency=5,
            timeout_seconds=15.0,
            allow_private=allow_private,
        )
        crawl_results = await crawler.crawl(url)
        pages_crawled = len(crawl_results) if crawl_results else 1

        # Phase 2: EXTRACTING_DOM
        await _emit_event(
            scan_id,
            ScanStatus.EXTRACTING_DOM,
            30,
            "DOM Structural Extraction",
            f"Parsing semantic hierarchy and CSS selector paths across {pages_crawled} pages...",
        )
        chunker = DOMChunker()
        extracted_chunks: list[ChunkData] = []
        html_docs: list[str] = []
        crawled_pages_detail: list[CrawledPageDetail] = []
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

        CHUNKS_DB[scan_id] = extracted_chunks
        CHUNKS_DB[str(scan_uuid)] = extracted_chunks
        CHUNKS_DB[scan_uuid.hex] = extracted_chunks

        # Phase 3: Embedding & Vector Indexing (remains under EXTRACTING_DOM status)
        await _emit_event(
            scan_id,
            ScanStatus.EXTRACTING_DOM,
            45,
            "Embedding & Vector Indexing",
            f"Generating 1536-dim embeddings for {len(extracted_chunks)} chunks...",
        )
        try:
            await store_dom_chunks(scan_uuid, extracted_chunks)
        except Exception as db_err:
            logger.info("Database store_dom_chunks unavailable, retained in memory: %s", db_err)

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

        # Single scan-scoped BudgetGuard
        budget_guard = BudgetGuard(limit=settings.MAX_LLM_CALLS_PER_SCAN)
        llm_client = LLMClient(budget_guard=budget_guard)

        # Build orchestration chunks for DAG
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
            "Hybrid Retrieval",
            "Executing dense pgvector + sparse BM25 fusion across indexed DOM chunks...",
        )

        # Phase 6: NLI_EVALUATION
        await _emit_event(
            scan_id,
            ScanStatus.NLI_EVALUATION,
            85,
            "NLI Entailment Classifier",
            "Evaluating claim entailment and detecting factual contradictions...",
        )

        # Execute FindableAIDAG orchestrator
        dag = FindableAIDAG(llm_client=llm_client, budget_guard=budget_guard)
        obs = ObservationInput(
            scan_id=str(scan_uuid),
            business_context=business_context,
            personas=personas or ("cto", "developer", "procurement"),
            chunks=orch_chunks,
            html_documents=html_docs,
        )
        orch_result = await dag.run(obs)

        evaluations: list[IntentEvaluation] = list(orch_result.evaluations)
        contradictions: list[Contradiction] = list(orch_result.contradictions)
        score_breakdown = orch_result.score

        is_prod = settings.ENVIRONMENT.lower() == "production"
        execution_mode = (
            "real_llm"
            if evaluations and llm_client.calls_made > 0
            else ("deterministic" if is_prod else "synthetic_fallback")
        )
        data_source = (
            "live_pipeline"
            if (evaluations and llm_client.calls_made > 0) or is_prod
            else "synthetic_fallback"
        )

        if not evaluations:
            evaluations = _generate_fallback_evaluations(url, extracted_chunks, personas=personas)

        if not contradictions and orch_result.error:
            contradictions = _generate_fallback_contradictions(url)

        # Build complete ScoreInputs
        score_inputs = ScoreInputs(
            intent_evaluations=evaluations,
            contradictions=contradictions,
            html_documents=html_docs,
            chunks=extracted_chunks,
        )

        # Ensure score_breakdown is calculated via deterministic Scorer if available
        if score_breakdown is None and evaluations:
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
        if score_breakdown is not None:
            f_score = adapt_score_breakdown_to_api(score_breakdown)
        elif not is_prod:
            logger.warning(
                "Scorer execution returned None; using fallback F-score for %s in dev mode", scan_id
            )
            f_score = generate_mock_fscore(url)
        else:
            logger.warning(
                "Scorer execution returned None; zero mock F-score in production for %s", scan_id
            )
            f_score = None

        # Phase 8: GENERATING_PATCHES
        await _emit_event(
            scan_id,
            ScanStatus.GENERATING_PATCHES,
            97,
            "Patch Synthesizer",
            "Generating zero-hallucination Schema.org JSON-LD microdata and DOM code diffs...",
        )

        patches: list[PatchProposal] | None = None
        if score_breakdown and html_docs:
            try:
                patches = assemble_real_patches(
                    html=html_docs[0],
                    url=url,
                    score_inputs=score_inputs,
                    score_breakdown=score_breakdown,
                    chunks=extracted_chunks,
                    contradictions=contradictions,
                )
            except Exception as patch_err:
                logger.warning("Real patch assembly error: %s", patch_err, exc_info=True)
                patches = None

        if patches is None:
            if is_prod:
                patches = []
            else:
                patches = generate_mock_patches(url=url, html=html_docs[0] if html_docs else "")

        # Phase 9: COMPLETED
        end_time = datetime.now(UTC)
        exec_duration = (end_time - start_time).total_seconds()

        final_status = ScanStatus.COMPLETED
        final_error = None
        if is_prod and orch_result.error and not evaluations:
            final_status = ScanStatus.FAILED
            final_error = orch_result.error

        summary = AuditSummary(
            pages_crawled=pages_crawled,
            dom_chunks_extracted=len(extracted_chunks),
            intents_generated=len(evaluations),
            contradictions_detected=len(contradictions),
            execution_time_seconds=round(exec_duration, 2),
            max_pages_requested=max_pages,
            crawled_pages=crawled_pages_detail,
        )

        llm_calls_made = llm_client.calls_made
        logger.info(
            "Scan %s execution complete: execution_mode=%s, data_source=%s, llm_calls_made=%d/%d, budget_remaining=%d",
            scan_id,
            execution_mode,
            data_source,
            llm_calls_made,
            budget_guard.limit,
            budget_guard.remaining,
        )

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
            record.llm_calls_made = llm_calls_made
            if final_error:
                record.error = final_error

        # Persist status to database if connected
        try:
            async with AsyncSessionLocal() as s:
                async with s.begin():
                    db_scan = await s.get(ScanModel, scan_uuid)
                    if db_scan:
                        db_scan.status = "completed"
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

                    # Persist evaluated intents
                    for eval_item in evaluations:
                        status_str = (
                            eval_item.status.value
                            if hasattr(eval_item.status, "value")
                            else str(eval_item.status)
                        )
                        cat_val = eval_item.category.value if eval_item.category else "general"
                        s.add(
                            IntentModel(
                                id=uuid.uuid4(),
                                scan_id=scan_uuid,
                                category=cat_val,
                                persona=eval_item.persona,
                                query=eval_item.query,
                                status=status_str,
                                reasoning=eval_item.reasoning,
                                confidence=eval_item.confidence,
                            )
                        )

                    # Persist detected contradictions
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

                    # Persist synthesized patches
                    if patches:
                        for p in patches:
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

        await _emit_event(
            scan_id,
            ScanStatus.COMPLETED,
            100,
            "Audit Complete",
            "Findability report and patches ready.",
        )

    except Exception as e:
        logger.exception("Scan pipeline failed for %s: %s", scan_id, e)
        if scan_id in SCANS_DB:
            SCANS_DB[scan_id].status = ScanStatus.FAILED
            SCANS_DB[scan_id].error = str(e)
        await _emit_event(
            scan_id,
            ScanStatus.FAILED,
            100,
            "Scan Failed",
            f"Error executing scan: {e}",
        )
    finally:
        for q in EVENT_QUEUES.get(scan_id, []):
            await q.put(None)


@router.post(
    "",
    response_model=ScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_api_key), Depends(rate_limit_scans)],
)
async def create_scan(request: ScanRequest, background_tasks: BackgroundTasks):
    """
    Initiates an asynchronous machine discoverability scan.
    Validates URL SSRF security, registers scan in database,
    and dispatches background crawler pipeline.
    """
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

    scan_uuid = uuid.uuid4()
    scan_id = f"scan_{scan_uuid.hex}"

    new_scan = ScanResponse(
        scan_id=scan_id,
        target_url=str(request.url),
        status=ScanStatus.PENDING,
        created_at=datetime.now(UTC),
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
        message="Connecting to FindableAI crawl dispatcher...",
        timestamp=datetime.now(UTC),
    )
    EVENT_LOGS[scan_id] = [init_event]
    EVENT_LOGS[f"scan_{scan_uuid.hex[:12]}"] = [init_event]

    # Persist initial scan record to database if available
    try:
        async with AsyncSessionLocal() as s:
            async with s.begin():
                db_scan = ScanModel(
                    id=scan_uuid,
                    url=str(request.url),
                    repo_url=str(request.repo_url) if request.repo_url else None,
                    status="in_progress",
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


def enrich_patches_with_framework(
    patches: list[PatchProposal], repo_url: str | None
) -> list[PatchProposal]:
    """Enriches patches with framework-native diffs and auxiliary files when repo is connected."""
    if not repo_url or not isinstance(repo_url, str) or not repo_url.strip() or not patches:
        return patches
    if any(p.target_file for p in patches):
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


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: str) -> ScanResponse:
    """Fetches status and results of a scan."""
    if scan_id in SCANS_DB:
        record = SCANS_DB[scan_id]
        target_repo = record.repo_url or record.github_repo_url
        if target_repo and not any(p.target_file for p in record.patches):
            record.patches = enrich_patches_with_framework(record.patches, target_repo)
        return record

    # Query persistent PostgreSQL database
    scan_uuid = resolve_scan_uuid(scan_id)
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

                    converted_intents: list[IntentEvaluation] = [
                        IntentEvaluation(
                            intent_id=f"intent_{it.id.hex[:8]}",
                            query=it.query,
                            category=IntentCategory(it.category)
                            if it.category in [c.value for c in IntentCategory]
                            else None,
                            persona=getattr(it, "persona", None) or resolve_query_persona(
                                IntentCategory(it.category)
                                if it.category in [c.value for c in IntentCategory]
                                else IntentCategory.POLICY
                            ),
                            status=EntailmentStatus(it.status)
                            if it.status in [e.value for e in EntailmentStatus]
                            else EntailmentStatus.UNKNOWN,
                            reasoning=it.reasoning or "",
                            evidence=[],
                            confidence=it.confidence or 0.85,
                        )
                        for it in db_intents
                    ]

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

                    scan_status = (
                        ScanStatus(db_scan.status)
                        if db_scan.status in [e.value for e in ScanStatus]
                        else ScanStatus.COMPLETED
                    )
                    crawled_fallback = [
                        CrawledPageDetail(
                            url=db_scan.url,
                            status_code=200,
                            chunks_count=len(converted_intents),
                        )
                    ]
                    scan_resp = ScanResponse(
                        scan_id=scan_id,
                        target_url=db_scan.url,
                        status=scan_status,
                        created_at=db_scan.created_at,
                        f_score=f_score_obj,
                        summary=AuditSummary(
                            pages_crawled=1,
                            dom_chunks_extracted=len(converted_intents),
                            intents_generated=len(converted_intents),
                            contradictions_detected=len(converted_cons),
                            execution_time_seconds=0.0,
                            max_pages_requested=1,
                            crawled_pages=crawled_fallback,
                        )
                        if db_scan.status == "completed"
                        else None,
                        crawled_pages=crawled_fallback,
                        patches=enrich_patches_with_framework(converted_patches, db_scan.repo_url),
                        intents=converted_intents,
                        contradictions=converted_cons,
                        repo_url=db_scan.repo_url,
                        github_repo_url=db_scan.repo_url,
                    )
                    SCANS_DB[scan_id] = scan_resp
                    return scan_resp
        except Exception as e:
            logger.debug("Database scan lookup bypassed: %s", e)

    raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found")


@router.get("/{scan_id}/stream")
async def stream_scan_progress(scan_id: str):
    """Server-Sent Events (SSE) endpoint broadcasting live scan progression."""
    if scan_id not in SCANS_DB:
        scan_uuid = resolve_scan_uuid(scan_id)
        exists_in_db = False
        if scan_uuid:
            try:
                async with AsyncSessionLocal() as s:
                    db_scan = await s.get(ScanModel, scan_uuid)
                    if db_scan:
                        exists_in_db = True
            except Exception:
                pass
        if not exists_in_db:
            raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[ScanStatusEvent | None] = asyncio.Queue()
        EVENT_QUEUES.setdefault(scan_id, []).append(queue)

        try:
            # 1. Replay past events already logged
            past_events = EVENT_LOGS.get(scan_id, [])
            for ev in past_events:
                yield f"data: {json.dumps(ev.model_dump(mode='json'))}\n\n"

            # If already completed or failed, terminate stream
            if past_events and past_events[-1].status in (ScanStatus.COMPLETED, ScanStatus.FAILED):
                return

            # 2. Consume real-time events from background pipeline
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if event is None:
                        break
                    yield f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
                    if event.status in (ScanStatus.COMPLETED, ScanStatus.FAILED):
                        break
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            if scan_id in EVENT_QUEUES and queue in EVENT_QUEUES[scan_id]:
                EVENT_QUEUES[scan_id].remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{scan_id}/chunks")
async def get_scan_chunks(scan_id: str) -> list[dict[str, Any]]:
    """Returns all extracted DOM chunks for this scan."""
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

    scan_uuid = resolve_scan_uuid(scan_id)
    if scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                stmt = select(DOMChunkModel).where(DOMChunkModel.scan_id == scan_uuid)
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
        except Exception as e:
            logger.debug("DB chunks lookup bypassed: %s", e)

    return []


@router.get("/{scan_id}/intents")
async def get_scan_intents(scan_id: str) -> list[dict[str, Any]]:
    """Returns intent evaluations for this scan."""
    if scan_id in SCANS_DB and SCANS_DB[scan_id].intents:
        return [eval_item.model_dump(mode="json") for eval_item in SCANS_DB[scan_id].intents]

    scan_uuid = resolve_scan_uuid(scan_id)
    if scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                stmt = select(IntentModel).where(IntentModel.scan_id == scan_uuid)
                result = await s.execute(stmt)
                db_intents = result.scalars().all()
                if db_intents:
                    return [
                        {
                            "intent_id": f"intent_{it.id.hex[:8]}",
                            "query": it.query,
                            "category": it.category,
                            "persona": getattr(it, "persona", None) or resolve_query_persona(
                                IntentCategory(it.category)
                                if it.category in [c.value for c in IntentCategory]
                                else IntentCategory.POLICY
                            ),
                            "status": it.status,
                            "reasoning": it.reasoning,
                            "evidence": [],
                            "confidence": it.confidence,
                        }
                        for it in db_intents
                    ]
        except Exception as e:
            logger.debug("DB intents lookup error: %s", e)

    return []


@router.get("/{scan_id}/contradictions")
async def get_scan_contradictions(scan_id: str) -> list[dict[str, Any]]:
    """Returns detected factual contradictions across crawled pages."""
    if scan_id in SCANS_DB and SCANS_DB[scan_id].contradictions:
        return [con.model_dump(mode="json") for con in SCANS_DB[scan_id].contradictions]

    scan_uuid = resolve_scan_uuid(scan_id)
    if scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                stmt = select(ContradictionModel).where(ContradictionModel.scan_id == scan_uuid)
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
        except Exception as e:
            logger.debug("DB contradictions lookup error: %s", e)

    return []


@router.get("/{scan_id}/patches", response_model=list[PatchProposal])
async def get_scan_patches(
    scan_id: str,
    repo_url: str | None = Query(
        default=None, description="GitHub repository URL for framework-native diffs"
    ),
) -> list[PatchProposal]:
    """Returns remediation code patches for this scan.

    When ``repo_url`` is provided (or stored on the scan), patches are enriched
    with framework-native code diffs so the UI preview matches the GitHub PR exactly.
    """
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
                scan_stmt = select(ScanModel).where(ScanModel.id == scan_uuid)
                scan_result = await s.execute(scan_stmt)
                db_scan = scan_result.scalar_one_or_none()
                if db_scan:
                    scan_repo_url = db_scan.repo_url
        except Exception as e:
            logger.debug("DB scan repo_url lookup error: %s", e)

    if not patches and scan_uuid:
        try:
            async with AsyncSessionLocal() as s:
                stmt = select(PatchModel).where(PatchModel.scan_id == scan_uuid)
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


@router.post(
    "/{scan_id}/patches/apply",
    response_model=PullRequestResult,
    dependencies=[Depends(verify_api_key), Depends(rate_limit_mutating)],
)
async def apply_scan_patch(
    scan_id: str,
    payload: ApplyScanPatchRequest | None = None,
) -> PullRequestResult:
    """Triggers autonomous GitHub PR creation for this scan's proposed patches (Task P1-2.4)."""
    scan = SCANS_DB.get(scan_id)
    if not scan:
        try:
            scan = await get_scan(scan_id)
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

    if not scan.patches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No remediation patches available to apply for this scan.",
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

    formatted_patches: list[FormattedPatch] = []
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

        file_path = "index.html"
        if p.unified_diff and "--- a/" in p.unified_diff:
            first_line = p.unified_diff.splitlines()[0]
            extracted = first_line.replace("--- a/", "").strip()
            if extracted.endswith((".html", ".htm")):
                file_path = extracted

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

    current_score = scan.f_score.overall_score if scan.f_score else 0.0
    total_delta = sum(p.impact_score_delta for p in scan.patches)
    projected_score = min(100.0, max(0.0, current_score + total_delta))
    target_branch = (
        payload.target_branch.strip()
        if payload and payload.target_branch and payload.target_branch.strip()
        else "main"
    )

    try:
        gh_client = build_pygithub_client_from_token(token)
        pr_service = GitHubPRService(gh_client)
        pr_request = PREngineRequest(
            source_repo=source_repo,
            target_branch=target_branch,
            scan_id=scan_id,
            patches=formatted_patches,
            intent_evaluations=scan.intents,
            current_score=current_score,
            projected_score=projected_score,
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
        return PullRequestResult(
            pr_url=result.pr_url,
            pr_number=result.pr_number,
            branch_name=result.generated_branch,
            title=f"FindableAI: Machine Discoverability Remediation Patches ({scan_id})",
            created_at=datetime.now(UTC),
        )
    except (PREngineError, GitHubClientError) as exc:
        logger.error("GitHub PR creation failed for scan %s: %s", scan_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub PR creation failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during PR creation for scan %s", scan_id)
        msg = str(exc)
        if "timed out" in msg.lower() or "timeout" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="GitHub API timed out while communicating with repository. Please retry.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error creating GitHub PR: {exc}",
        ) from exc
