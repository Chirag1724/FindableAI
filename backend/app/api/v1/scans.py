import asyncio
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...schemas.fscore import FScoreBreakdown, SubScoreMetric
from ...schemas.patch import DOMSelectorAnchor, PatchProposal, PatchType
from ...schemas.scan import (
    AuditSummary,
    ScanRequest,
    ScanResponse,
    ScanStatus,
    ScanStatusEvent,
)

router = APIRouter()

# In-memory store for scaffolding development (swapped with PostgreSQL/Redis in Phase 2)
SCANS_DB: dict[str, ScanResponse] = {}


def generate_mock_fscore(url: str) -> FScoreBreakdown:
    return FScoreBreakdown(
        overall_score=78.4,
        grade="B+",
        coverage=SubScoreMetric(
            name="Query Intent Coverage",
            weight=0.40,
            score=82.0,
            details="Answers 14 of 17 simulated high-intent buyer queries.",
            strengths=["Strong pricing transparency", "Clear API documentation links"],
            gaps=["Missing security compliance details (SOC2 / GDPR)"],
        ),
        entailment=SubScoreMetric(
            name="Evidence Grounding & Entailment",
            weight=0.35,
            score=76.5,
            details="Claims show high factual entailment in LLM answer extraction.",
            strengths=["Specific performance latency benchmarks listed"],
            gaps=["Vague enterprise SLA claims lacking exact numbers"],
        ),
        contradiction_penalty=SubScoreMetric(
            name="Contradiction Penalty",
            weight=0.15,
            score=10.0,
            details="Minor contradictory claim detected between landing page and FAQ.",
            strengths=["Consistent pricing across tiers"],
            gaps=["Landing page states 'Unlimited free tier' while FAQ limits to 1,000 requests"],
        ),
        structural_clarity=SubScoreMetric(
            name="DOM & Schema Structure",
            weight=0.10,
            score=85.0,
            details="Semantic HTML headers and tables present, missing FAQPage JSON-LD.",
            strengths=["Clean H1-H3 heading hierarchy", "Proper HTML5 article elements"],
            gaps=["Missing Schema.org SoftwareApplication JSON-LD microdata"],
        ),
    )


def generate_mock_patches() -> list[PatchProposal]:
    return [
        PatchProposal(
            patch_id=f"patch_{uuid.uuid4().hex[:8]}",
            patch_type=PatchType.SCHEMA_MICRODATA,
            title="Inject Schema.org SoftwareApplication JSON-LD",
            rationale="AI search engines (SearchGPT, Perplexity) rely heavily on JSON-LD microdata to identify software categories, pricing tiers, and capabilities.",
            impact_score_delta=6.5,
            dom_anchor=DOMSelectorAnchor(
                css_selector="head",
                tag_name="head",
                original_snippet="<head>\n  <title>Acme AI</title>\n</head>",
                suggested_snippet='<head>\n  <title>Acme AI</title>\n  <script type="application/ld+json">{"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "Acme AI", "applicationCategory": "BusinessApplication"}</script>\n</head>',
            ),
            unified_diff='--- a/index.html\n+++ b/index.html\n@@ -2,3 +2,6 @@\n <head>\n   <title>Acme AI</title>\n+  <script type="application/ld+json">\n+  {"@context": "https://schema.org", "@type": "SoftwareApplication"}\n+  </script>\n </head>',
            applied=False,
        ),
        PatchProposal(
            patch_id=f"patch_{uuid.uuid4().hex[:8]}",
            patch_type=PatchType.FACTUAL_CONFLICT_RESOLUTION,
            title="Reconcile Free Tier Usage Limit Contradiction",
            rationale="Landing hero claims 'Unlimited free tier' while FAQ section states '1,000 free requests per month'. Conflicting claims degrade LLM confidence score.",
            impact_score_delta=8.2,
            dom_anchor=DOMSelectorAnchor(
                css_selector="section#hero > div.subheadline",
                tag_name="div",
                original_snippet='<div class="subheadline">Enjoy our unlimited free tier with no credit card required.</div>',
                suggested_snippet='<div class="subheadline">Get started with 1,000 free API requests every month, no credit card required.</div>',
            ),
            unified_diff='--- a/components/Hero.tsx\n+++ b/components/Hero.tsx\n@@ -12,3 +12,3 @@\n-<div className="subheadline">Enjoy our unlimited free tier with no credit card required.</div>\n+<div className="subheadline">Get started with 1,000 free API requests every month, no credit card required.</div>',
            applied=False,
        ),
    ]


@router.post("", response_model=ScanResponse, status_code=202)
async def create_scan(request: ScanRequest):
    """Initiates an asynchronous machine discoverability scan."""
    scan_id = f"scan_{uuid.uuid4().hex[:12]}"
    new_scan = ScanResponse(
        scan_id=scan_id,
        target_url=str(request.url),
        status=ScanStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    SCANS_DB[scan_id] = new_scan
    return new_scan


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: str):
    """Fetches status and results of a scan."""
    if scan_id not in SCANS_DB:
        # Generate on-demand mock scan for development ease
        SCANS_DB[scan_id] = ScanResponse(
            scan_id=scan_id,
            target_url="https://example.com",
            status=ScanStatus.COMPLETED,
            created_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            f_score=generate_mock_fscore("https://example.com"),
            summary=AuditSummary(
                pages_crawled=4,
                dom_chunks_extracted=48,
                intents_generated=17,
                contradictions_detected=1,
                execution_time_seconds=8.4,
            ),
            patches=generate_mock_patches(),
        )
    return SCANS_DB[scan_id]


@router.get("/{scan_id}/stream")
async def stream_scan_progress(scan_id: str):
    """Server-Sent Events (SSE) endpoint broadcasting live scan progression."""
    if scan_id not in SCANS_DB:
        SCANS_DB[scan_id] = ScanResponse(
            scan_id=scan_id,
            target_url="https://example.com",
            status=ScanStatus.PENDING,
            created_at=datetime.now(UTC),
        )

    async def event_generator():
        steps = [
            (
                ScanStatus.CRAWLING,
                15,
                "Playwright Crawling",
                "Fetching JavaScript-rendered DOM snapshots...",
            ),
            (
                ScanStatus.EXTRACTING_DOM,
                30,
                "DOM Structural Extraction",
                "Parsing semantic hierarchy and CSS selector paths...",
            ),
            (
                ScanStatus.SYNTHESIZING_INTENTS,
                45,
                "Synthetic Intent Engine",
                "Simulating high-intent buyer and researcher queries...",
            ),
            (
                ScanStatus.HYBRID_RETRIEVAL,
                60,
                "Hybrid Retrieval",
                "Executing dense pgvector + sparse BM25 fusion...",
            ),
            (
                ScanStatus.NLI_EVALUATION,
                75,
                "NLI Entailment Classifier",
                "Evaluating claim entailment and detecting factual contradictions...",
            ),
            (
                ScanStatus.COMPUTING_FSCORE,
                88,
                "F-Score Engine",
                "Calculating weighted Findability metrics...",
            ),
            (
                ScanStatus.GENERATING_PATCHES,
                95,
                "Patch Synthesizer",
                "Generating zero-hallucination code diffs...",
            ),
            (ScanStatus.COMPLETED, 100, "Audit Complete", "Findability report and patches ready."),
        ]

        for status, percent, step_name, msg in steps:
            event = ScanStatusEvent(
                scan_id=scan_id,
                status=status,
                progress_percent=percent,
                current_step=step_name,
                message=msg,
            )
            # Update in-memory record
            if scan_id in SCANS_DB:
                SCANS_DB[scan_id].status = status
                if status == ScanStatus.COMPLETED:
                    SCANS_DB[scan_id].completed_at = datetime.now(UTC)
                    SCANS_DB[scan_id].f_score = generate_mock_fscore(SCANS_DB[scan_id].target_url)
                    SCANS_DB[scan_id].summary = AuditSummary(
                        pages_crawled=5,
                        dom_chunks_extracted=52,
                        intents_generated=20,
                        contradictions_detected=1,
                        execution_time_seconds=9.8,
                    )
                    SCANS_DB[scan_id].patches = generate_mock_patches()

            yield f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
