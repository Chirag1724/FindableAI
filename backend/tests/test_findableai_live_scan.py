"""Integration and live tests for FindableAI scan pipeline on https://findableai.vercel.app/."""

import pytest

from app.core.budget import BudgetGuard
from app.core.llm import LLMClient
from app.crawler.crawler import AsyncCrawler
from app.engines.intent_generator import IntentGenerator
from app.orchestration.dag import FindableAIDAG, ObservationInput, OrchestrationChunk
from app.schemas.intelligence import (
    EntailmentStatus,
    EvidenceReference,
    IntentBatch,
    IntentCategory,
    IntentEvaluation,
    IntentEvaluationBatch,
    IntentQuery,
)

TARGET_URL = "https://findableai.vercel.app/"


@pytest.fixture(autouse=True)
def reset_llm_state():
    LLMClient.reset_tripped_providers()
    yield
    LLMClient.reset_tripped_providers()


@pytest.mark.asyncio
async def test_findableai_live_crawler():
    """Verify live crawler successfully fetches and extracts content from https://findableai.vercel.app/."""
    crawler = AsyncCrawler(max_pages=2, timeout_seconds=15.0, allow_private=True)
    crawl_results = await crawler.crawl(TARGET_URL)

    assert len(crawl_results) >= 1
    page = crawl_results[0]
    assert page.status_code == 200
    assert page.html is not None
    assert len(page.html.strip()) > 100
    assert "findable" in page.html.lower() or "ai" in page.html.lower()


@pytest.mark.asyncio
async def test_findableai_live_crawl_and_intent_generation():
    """Verify crawler and parallel 3-batch intent generation on findableai.vercel.app."""
    # 1. Crawl target URL
    crawler = AsyncCrawler(max_pages=2, timeout_seconds=15.0, allow_private=True)
    crawl_results = await crawler.crawl(TARGET_URL)
    assert len(crawl_results) >= 1

    context = f"Business URL: {TARGET_URL}\nFindableAI - Website discoverability audit platform for AI search and agents."

    # 2. Generate intents via parallel 3-batch
    generator = IntentGenerator()
    try:
        intent_batch = await generator.generate_intents(business_context=context)
    except Exception as exc:
        full_err = (
            f"{exc!r} {getattr(exc, '__cause__', '')!r} {getattr(exc, '__context__', '')!r}".lower()
        )
        if any(
            k in full_err
            for k in (
                "rate limit",
                "429",
                "quota",
                "402",
                "credits",
                "budget",
                "invalid api key",
                "valid api key",
                "api_key",
                "exhausted",
                "unauthorized",
                "max_tokens",
            )
        ):
            pytest.skip(f"Live LLM provider daily quota/credits reached: {exc}")
        raise

    assert len(intent_batch.queries) == 30
    assert intent_batch.business_type

    # 3. Verify taxonomy distribution: exactly 3 queries per category
    category_counts = {c.value: 0 for c in IntentCategory}
    for q in intent_batch.queries:
        category_counts[q.category.value] += 1
    assert set(category_counts.values()) == {3}

    # 4. Verify all 3 active personas are represented
    personas = {q.persona for q in intent_batch.queries}
    assert personas == {"cto", "developer", "procurement"}


@pytest.mark.asyncio
async def test_findableai_deterministic_dag_with_live_content():
    """Verify full DAG orchestration against live scraped content from findableai.vercel.app with mock LLM.
    Guarantees CI and deterministic local validation without external token quota flakiness.
    """
    # 1. Crawl live target URL
    crawler = AsyncCrawler(max_pages=1, timeout_seconds=15.0, allow_private=True)
    crawl_results = await crawler.crawl(TARGET_URL)
    html_docs = [p.html for p in crawl_results if p.html]
    assert len(html_docs) >= 1

    # 2. Build live chunks
    chunks = [
        OrchestrationChunk(
            id=f"chunk_{i}",
            url=TARGET_URL,
            dom_path=f"html > body > main > div:nth-child({i + 1})",
            content=f"FindableAI audits machine-discoverability for LLMs and buyer agents. Live section {i + 1}",
            tag="div",
            word_count=15,
        )
        for i in range(5)
    ]

    # 3. Generate 30 queries across 10 categories & 3 personas
    queries = []
    categories = list(IntentCategory)
    personas = ["cto", "developer", "procurement"]
    for cat_idx, cat in enumerate(categories):
        for q_idx in range(3):
            persona = personas[(cat_idx + q_idx) % 3]
            queries.append(
                IntentQuery(
                    intent_id=f"{cat.value}_{q_idx + 1:02d}",
                    query=f"What is the {cat.value} policy and feature specification for {persona}?",
                    category=cat,
                    difficulty="medium",
                    expected_evidence_type="documentation and schema markup",
                    persona=persona,
                )
            )
    assert len(queries) == 30

    # 4. Mock Instructor Client that returns valid evaluations & batch
    class DeterministicInstructor:
        class chat:
            class completions:
                @staticmethod
                async def create(*args, response_model=None, **kwargs):
                    if response_model is IntentBatch:
                        return IntentBatch(
                            business_type="AI Discoverability Audit", queries=queries
                        )
                    if response_model is IntentEvaluationBatch:
                        msg_content = kwargs.get("messages", [{}])[-1].get("content", "")
                        import re

                        ids = re.findall(r"INTENT ID: ([^\n]+)", msg_content)
                        return IntentEvaluationBatch(
                            evaluations=[
                                IntentEvaluation(
                                    intent_id=iid.strip(),
                                    query="Sample query?",
                                    category=IntentCategory.PRICING,
                                    persona="cto",
                                    status=EntailmentStatus.SUPPORTED,
                                    reasoning="Found corresponding evidence chunk.",
                                    evidence=[
                                        EvidenceReference(
                                            chunk_id="chunk_0",
                                            dom_path="html > body > main > div:nth-child(1)",
                                        )
                                    ],
                                    confidence=0.95,
                                )
                                for iid in ids
                            ]
                        )
                    if response_model is IntentEvaluation:
                        msg_content = kwargs.get("messages", [{}])[-1].get("content", "")
                        intent_id = "eval_01"
                        if "INTENT ID:" in msg_content:
                            intent_id = msg_content.split("INTENT ID:")[1].split("\n")[0].strip()
                        return IntentEvaluation(
                            intent_id=intent_id,
                            query="Sample query?",
                            category=IntentCategory.PRICING,
                            persona="cto",
                            status=EntailmentStatus.SUPPORTED,
                            reasoning="Found corresponding evidence chunk.",
                            evidence=[],
                            confidence=0.95,
                        )
                    if hasattr(response_model, "__fields__"):
                        # pyrefly: ignore [not-callable]
                        return response_model()
                    return None

    budget = BudgetGuard(limit=60)
    llm = LLMClient(budget_guard=budget, instructor_client=DeterministicInstructor())
    dag = FindableAIDAG(llm_client=llm, budget_guard=budget)

    obs = ObservationInput(
        scan_id="test_findableai_live_scraped",
        business_context=f"Business URL: {TARGET_URL}\nFindableAI platform.",
        personas=["cto", "developer", "procurement"],
        chunks=chunks,
        html_documents=html_docs[:1],
    )

    result = await dag.run(obs)
    assert result.error is None
    assert result.success is True
    assert result.final_state.value == "STOP"
    assert result.intent_count == 30
    assert len(result.evaluations) == 30
    assert result.score is not None
    assert 0.0 <= result.score.f_score <= 100.0


@pytest.mark.asyncio
async def test_findableai_live_dag_orchestration():
    """Verify live DAG orchestration end-to-end against live providers and findableai.vercel.app."""
    crawler = AsyncCrawler(max_pages=1, timeout_seconds=15.0, allow_private=True)
    crawl_results = await crawler.crawl(TARGET_URL)
    html_docs = [p.html for p in crawl_results if p.html]

    chunks = [
        OrchestrationChunk(
            id=f"chunk_{i}",
            url=TARGET_URL,
            dom_path=f"html > body > main > div:nth-child({i + 1})",
            content=f"FindableAI audits website machine-discoverability, evaluating synthetic buyer intents across CTO, Developer, and Procurement personas. Section {i + 1}",
            tag="div",
            word_count=20,
        )
        for i in range(5)
    ]

    budget_guard = BudgetGuard(limit=60)
    llm_client = LLMClient(budget_guard=budget_guard)

    dag = FindableAIDAG(llm_client=llm_client, budget_guard=budget_guard)
    obs = ObservationInput(
        scan_id="test_findableai_live_scan",
        business_context=f"Business URL: {TARGET_URL}\nFindableAI MDO Platform.",
        personas=["cto", "developer", "procurement"],
        chunks=chunks,
        html_documents=html_docs[:1],
    )

    try:
        result = await dag.run(obs)
    except Exception as exc:
        full_err = (
            f"{exc!r} {getattr(exc, '__cause__', '')!r} {getattr(exc, '__context__', '')!r}".lower()
        )
        if any(
            k in full_err
            for k in (
                "rate limit",
                "429",
                "quota",
                "402",
                "credits",
                "budget",
                "invalid api key",
                "valid api key",
                "api_key",
                "exhausted",
                "unauthorized",
                "max_tokens",
            )
        ):
            pytest.skip(f"Live LLM provider daily quota/credits reached: {exc}")
        raise

    if result.error and any(
        k in result.error.lower()
        for k in (
            "rate limit",
            "429",
            "quota",
            "402",
            "credits",
            "budget",
            "invalid api key",
            "valid api key",
            "api_key",
            "exhausted",
            "unauthorized",
            "max_tokens",
        )
    ):
        pytest.skip(f"Live LLM provider limit reached during DAG: {result.error}")

    assert result.error is None
    assert result.success is True
    assert result.final_state.value == "STOP"
    assert result.intent_count == 30
    assert len(result.evaluations) == 30
    assert result.score is not None
    assert 0.0 <= result.score.f_score <= 100.0
