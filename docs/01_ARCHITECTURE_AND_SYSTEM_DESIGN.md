# FindableAI — Architecture & System Design

> **Document Version:** 1.0  
> **Classification:** Internal Engineering Reference  
> **Authors:** FindableAI Core Team  
> **Last Updated:** October 2026  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement & Market Context](#2-problem-statement--market-context)
3. [Core Innovation: Evidence-Grounded GEO](#3-core-innovation-evidence-grounded-geo)
4. [High-Level Architecture](#4-high-level-architecture)
5. [Component Deep-Dives](#5-component-deep-dives)
   - [5.1 Async Crawler & SSRF Shield](#51-async-crawler--ssrf-shield)
   - [5.2 Structural DOM Chunker](#52-structural-dom-chunker)
   - [5.3 Synthetic Intent Generator](#53-synthetic-intent-generator)
   - [5.4 Hybrid Retrieval Engine](#54-hybrid-retrieval-engine)
   - [5.5 NLI Entailment Engine](#55-nli-entailment-engine)
   - [5.6 Cross-Page Contradiction Detector](#56-cross-page-contradiction-detector)
   - [5.7 Findability Score Calculator](#57-findability-score-calculator)
   - [5.8 Autonomous Patch Generator](#58-autonomous-patch-generator)
   - [5.9 GitHub PR Engine](#59-github-pr-engine)
6. [DAG Orchestrator & Budget Guard](#6-dag-orchestrator--budget-guard)
7. [Data Models & Schema Design](#7-data-models--schema-design)
8. [API Surface](#8-api-surface)
9. [Frontend Architecture](#9-frontend-architecture)
10. [Security Model](#10-security-model)
11. [References & Research](#11-references--research)

---

## 1. Executive Summary

**FindableAI** is an **Evidence-Grounded Autonomous Machine-Discoverability Optimization System**. It audits any website's readiness for AI-powered search engines (ChatGPT Search, Perplexity, Google AI Overviews, Claude) by:

1. **Finding** exactly what evidence an AI agent can and cannot extract from the site's DOM.
2. **Fixing** gaps by generating deterministic, syntactically validated Schema.org JSON-LD patches and semantic HTML remediation.
3. **Proving** the improvement with a quantified **Findability Score (F)** and a 1-click GitHub Pull Request.

This is **not SEO**. This is **GEO — Generative Engine Optimization** — a discipline formally introduced at KDD 2024 (Princeton / IIT Delhi) demonstrating that specific content strategies can boost AI visibility by up to **40%** ([arXiv:2311.09735](https://arxiv.org/abs/2311.09735)).

---

## 2. Problem Statement & Market Context

### The Shift: From Blue Links to Synthesized Answers

| Dimension | Traditional SEO | Generative Engine Optimization (GEO) |
| :--- | :--- | :--- |
| **Target** | SERP rankings (10 blue links) | AI-synthesized, cited answers |
| **Success Metric** | Click-through rate, position | Citation rate, "Visibility Score" |
| **Core Mechanism** | Keywords, backlinks, PageRank | Entity authority, RAG-friendly structure |
| **Failure Mode** | Low ranking → less traffic | Missing evidence → hallucination or omission |

> **Source:** The GEO framework was formally established in the paper *"GEO: Generative Engine Optimization"* presented at KDD 2024. The study introduced **GEO-bench**, the first large-scale benchmark for evaluating visibility across AI-generated responses.

### How AI Search Engines Actually Work

AI search engines use **Retrieval-Augmented Generation (RAG)** pipelines:

```
[User Query] → [Query Expansion] → [Web Retrieval] → [Chunk Ranking] → [Context Injection] → [LLM Synthesis + Citation]
```

1. **Query Understanding**: The AI rewrites the user's question into multiple search-friendly variants.
2. **Retrieval**: Refined queries are sent to search indices; candidate pages/chunks are gathered.
3. **Ranking & Evaluation**: Re-ranking filters score retrieved content by relevance, authority, and semantic completeness.
4. **Context Injection**: Top chunks are fed to the LLM alongside the original prompt as "grounding evidence."
5. **Generation & Citation**: The LLM synthesizes an answer and maps claims back to source URLs.

> **Key Insight:** If a business's website contains **no extractable text evidence** for a query (e.g., opening hours are in an unlabelled PNG, dietary info is absent), the AI either **hallucinates an answer** or **omits the business entirely**. Both outcomes are catastrophic for the business.

---

## 3. Core Innovation: Evidence-Grounded GEO

FindableAI's novelty lies in three pillars that differentiate it from traditional SEO auditors:

### Pillar 1: DOM-Aware Evidence Extraction

Unlike tools that chunk text by fixed token windows (e.g., 500 tokens), FindableAI chunks by **semantic HTML boundaries** and preserves the **exact CSS selector path** for every chunk. This means every piece of evidence is traceable to a precise location in the DOM.

### Pillar 2: NLI-Based Entailment Verification

Instead of keyword matching or heuristic scoring, FindableAI uses **Natural Language Inference (NLI)** — classifying each customer query against retrieved evidence as `SUPPORTED`, `PARTIALLY_SUPPORTED`, `CONTRADICTED`, or `UNKNOWN`. This is the same technique used in academic fact-checking pipelines (FEVER benchmark, SNLI/MultiNLI datasets).

### Pillar 3: Deterministic Code Remediation

FindableAI doesn't output vague suggestions. It generates **syntactically validated JSON-LD** and **isolated DOM patches** that can be applied via a 1-click GitHub PR.

---

## 4. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLIENT (Next.js)                          │
│  ┌──────────┐ ┌──────────────┐ ┌───────────┐ ┌───────────────┐  │
│  │ URL Input│ │ Score Gauge  │ │Intent Grid│ │ Patch Viewer  │  │
│  └────┬─────┘ └──────▲───────┘ └─────▲─────┘ └──────▲────────┘  │
│       │               │               │               │          │
│       │          SSE Stream       SSE Stream       REST API      │
└───────┼───────────────┼───────────────┼───────────────┼──────────┘
        │               │               │               │
════════╪═══════════════╪═══════════════╪═══════════════╪══════════
        ▼               │               │               │
┌──────────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI)                             │
│                                                                   │
│  ┌─────────────┐     ┌──────────────────────────────────────┐    │
│  │ API Router  │────▶│         DAG ORCHESTRATOR              │    │
│  └─────────────┘     │                                      │    │
│                      │  ┌─────────┐    ┌──────────────┐     │    │
│                      │  │ OBSERVE │───▶│    PLAN      │     │    │
│                      │  │ Crawl   │    │ Gen Intents  │     │    │
│                      │  └─────────┘    └──────┬───────┘     │    │
│                      │                        ▼             │    │
│                      │  ┌──────────────────────────────┐    │    │
│                      │  │           ACT                │    │    │
│                      │  │  Retrieve + Entailment (×30) │    │    │
│                      │  └──────────────┬───────────────┘    │    │
│                      │                 ▼                    │    │
│                      │  ┌──────────────────────────────┐    │    │
│                      │  │          VERIFY              │    │    │
│                      │  │  Contradictions + F-Score    │    │    │
│                      │  └──────────────┬───────────────┘    │    │
│                      │                 ▼                    │    │
│                      │  ┌──────────────────────────────┐    │    │
│                      │  │          REFLECT             │    │    │
│                      │  │  Generate Top Patches        │    │    │
│                      │  └──────────────┬───────────────┘    │    │
│                      │                 ▼                    │    │
│                      │  ┌──────────────────────────────┐    │    │
│                      │  │           STOP               │    │    │
│                      │  │  Finalize & Stream Results   │    │    │
│                      │  └──────────────────────────────┘    │    │
│                      └──────────────────────────────────────┘    │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │               PostgreSQL + pgvector                       │    │
│  │  businesses | scans | dom_chunks | intents | evidence |   │    │
│  │  contradictions | patches | embeddings (vector 1536)      │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. Component Deep-Dives

### 5.1 Async Crawler & SSRF Shield

**Purpose:** Fetch all discoverable HTML pages from the target URL (max 15–20 pages via BFS from the root).

**Technology:** `httpx.AsyncClient` with concurrent semaphore-limited requests.

**SSRF Protection (Critical):**

Before every outbound request, the crawler MUST:

1. **Validate the URL scheme**: Only allow `http://` and `https://`. Block `file://`, `gopher://`, `dict://`, `ftp://`.
2. **Resolve DNS to IP**: Use `socket.getaddrinfo()` to resolve the hostname.
3. **Check IP against blocklist**: Reject requests to private/internal ranges:
   ```
   127.0.0.0/8       (Loopback)
   10.0.0.0/8        (RFC 1918 Private)
   172.16.0.0/12     (RFC 1918 Private)
   192.168.0.0/16    (RFC 1918 Private)
   169.254.169.254   (Cloud Metadata — AWS, GCP, Azure)
   0.0.0.0/8         (Current Network)
   ::1               (IPv6 Loopback)
   ```
4. **Follow redirects cautiously**: Validate every redirect target before following.
5. **Enforce strict timeouts**: 10-second connection timeout, 30-second total timeout per page.

> **Research Note:** SSRF is an OWASP Top-10 vulnerability. The `safehttpx` and `httpx-secure` libraries provide drop-in DNS-rebinding mitigation for `httpx.AsyncClient`. We use a custom implementation for transparency and auditability.

**SPA Fallback:** If the crawled root page contains `<div id="root"></div>` with no text children (indicating a JavaScript-rendered SPA), the system automatically falls back to `playwright` with a headless Chromium browser to render the page before extraction.

```python
async def crawl_page(url: str) -> CrawlResult:
    validate_ssrf(url)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(url)
    soup = BeautifulSoup(response.text, "lxml")
    
    # SPA Detection
    root_div = soup.find("div", id="root")
    if root_div and not root_div.get_text(strip=True):
        return await crawl_with_playwright(url)
    
    return CrawlResult(url=url, html=response.text, status=response.status_code)
```

---

### 5.2 Structural DOM Chunker

**Purpose:** Parse the HTML DOM and extract semantically meaningful text chunks, each tagged with its exact CSS selector path.

**Why CSS Selector Paths Matter:**
- They make every evidence claim **traceable** to a specific DOM node.
- They enable the Patch Generator to target exact elements for remediation.
- They provide an audit trail that the user can verify in their browser DevTools.

**Semantic Boundaries:** Instead of chunking by fixed token counts, we chunk at natural HTML boundaries:

| Priority | HTML Elements | Rationale |
| :--- | :--- | :--- |
| **1 (Highest)** | `<section>`, `<article>`, `<main>` | Top-level semantic containers |
| **2** | `<table>`, `<dl>`, `<ul>`, `<ol>` | Structured data containers (menus, specs) |
| **3** | `<h1>` – `<h6>` + following content | Heading-delimited sections |
| **4** | `<footer>`, `<header>`, `<nav>` | Site-level metadata regions |
| **5 (Lowest)** | `<p>`, `<div>` (fallback) | Generic content blocks |

**CSS Path Generation Algorithm:**

```python
def get_css_selector(element) -> str:
    """Generate a unique CSS selector path for a BS4 element."""
    path_parts = []
    current = element
    while current and current.name and current.name != '[document]':
        selector = current.name
        # Prefer ID (unique identifier)
        if current.get('id'):
            selector += f"#{current['id']}"
            path_parts.insert(0, selector)
            break  # IDs are globally unique
        # Use class names if available
        classes = current.get('class', [])
        if classes:
            selector += '.' + '.'.join(classes)
        else:
            # Use nth-of-type for disambiguation
            siblings = [s for s in current.parent.children 
                       if hasattr(s, 'name') and s.name == current.name]
            if len(siblings) > 1:
                index = siblings.index(current) + 1
                selector += f":nth-of-type({index})"
        path_parts.insert(0, selector)
        current = current.parent
    return " > ".join(path_parts)
```

**Output Schema (per chunk):**

```json
{
  "chunk_id": "c_a3f8e1",
  "url": "https://bistro2026.com/menu",
  "dom_path": "body > main > section#menu > table.menu-grid > tr:nth-of-type(3)",
  "content": "Vegan Burger — $14 — Beyond Meat patty, cashew cheese, brioche bun.",
  "tag": "tr",
  "word_count": 12,
  "has_structured_data": false,
  "extractability_score": 0.95
}
```

---

### 5.3 Synthetic Intent Generator

**Purpose:** Generate 30 realistic customer queries across 10 distinct intent taxonomy classes, simulating the exact types of questions an AI agent would need to answer.

**Technology:** **Groq** (`qwen-2.5-72b-instruct` / `qwen-2.5-coder-32b`) with **Instructor** for rigid Pydantic schema enforcement (optional fallback: OpenAI `gpt-4o-mini`).

**Why Groq + Qwen 2.5?** Groq's LPU hardware delivers ultra-low latency inference (~500+ tokens/sec), ensuring the entire multi-stage discovery audit runs within the 10-second target window while keeping cost under <$0.01 per scan. The Instructor library wraps the API to guarantee 100% rigid Pydantic JSON output with automatic retries on validation errors.

> **Research Note:** Instructor provides a clean, type-safe interface that handles complex nested schemas gracefully. It supports custom validators (`BeforeValidator`, `AfterValidator`) and even LLM-based validators via `instructor.llm_validator`. It is provider-agnostic — switching to Anthropic, Gemini, or Ollama requires only changing the `from_provider` method.

**Intent Taxonomy (10 Classes × 3 Queries = 30 Total):**

| # | Category | Description | Example Query |
| :--- | :--- | :--- | :--- |
| 1 | **Eligibility** | Dietary, age, credential restrictions | *"Do you have a dedicated gluten-free fryer?"* |
| 2 | **Policy** | Cancellation, pet, reservation rules | *"Is the patio dog-friendly?"* |
| 3 | **Availability** | Calendar-specific, real-time slots | *"Can I book a table for 12 on a Tuesday?"* |
| 4 | **Pricing** | Hidden fees, discounts, ranges | *"Is there a corkage fee or minimum spend?"* |
| 5 | **Accessibility** | ADA, stroller, wheelchair access | *"Is the restroom wheelchair-accessible?"* |
| 6 | **Commercial** | Events, catering, corporate bookings | *"Do you offer private dining for 30 people?"* |
| 7 | **Local** | Parking, transit, neighborhood | *"Where is the nearest valet or parking garage?"* |
| 8 | **Transactional** | Payment types, booking integrations | *"Do you accept Apple Pay and Amex?"* |
| 9 | **Trust** | Licensure, hygiene, sourcing, reviews | *"Are all your meats halal-certified?"* |
| 10 | **Edge Cases** | Holidays, weather, unusual scenarios | *"Are you open on Thanksgiving Day?"* |

**Pydantic Output Schema:**

```python
class IntentQuery(BaseModel):
    intent_id: str          # e.g., "eligibility_01"
    category: IntentCategory
    query: str              # The customer question
    difficulty: Literal["easy", "medium", "hard"]
    expected_evidence_type: str  # e.g., "menu table", "FAQ section", "hours div"

class IntentBatch(BaseModel):
    business_type: str      # Inferred from crawl (e.g., "restaurant")
    queries: list[IntentQuery]  # Exactly 30 items
```

**LLM Budget:** 1 batch call → 30 queries. Total cost: ~$0.001.

---

### 5.4 Hybrid Retrieval Engine

**Purpose:** For each of the 30 generated queries, retrieve the top `k=5` most relevant DOM chunks using a combination of keyword and semantic search.

**Architecture: PostgreSQL Unified Store**

Using PostgreSQL with `pgvector` as a unified store eliminates the need for a separate vector database. Both dense embeddings and full-text search indices coexist in the same table:

```sql
CREATE TABLE dom_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID REFERENCES scans(id),
    url TEXT NOT NULL,
    dom_path TEXT NOT NULL,
    content TEXT NOT NULL,
    tag TEXT NOT NULL,
    word_count INTEGER,
    
    -- Vector embedding for semantic search
    embedding vector(1536),
    
    -- Auto-generated tsvector for BM25 keyword search
    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

-- Indices
CREATE INDEX idx_chunks_embedding ON dom_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_tsv ON dom_chunks USING gin (content_tsv);
```

**Hybrid search — current implementation (authoritative):**

> See [`backend/app/crawler/search.py`](../backend/app/crawler/search.py) and [LIMITATIONS_AND_READINESS.md](engineering/LIMITATIONS_AND_READINESS.md).
>
> - Embeddings are written on chunk store (`store_dom_chunks`).
> - `hybrid_search` runs dense candidate retrieval + lexical (`tsvector` / keyword) then fuses with `reciprocal_rank_fusion`.
> - RRF formula: `score(d) = Σ 1/(k + rank)` with **1-based** ranks; `k = RETRIEVAL_RRF_K` (default 60); equal list weights; within-list UUID dedupe; tie-break `(-score, str(uuid))`; top-N = `RETRIEVAL_TOP_K`.
> - ACT prefers `build_act_retriever` → `hybrid_search`; falls back to first-*k* OBSERVE chunks only when retrieval returns empty.

```python
# Matches reciprocal_rank_fusion (1-based ranks — note design sketches often use 0-based enumerate incorrectly)
def reciprocal_rank_fusion(ranked_id_lists, *, rrf_k=60, limit=5):
    scores = {}
    for ranked in ranked_id_lists:
        rank = 0
        seen = set()
        for cid in ranked:
            if cid in seen:
                continue
            seen.add(cid)
            rank += 1
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))[:limit]
```

---

### 5.5 NLI Entailment Engine

**Purpose:** For each (query, evidence_chunks) pair, determine whether the retrieved evidence **supports**, **partially supports**, **contradicts**, or **does not address** the customer's question.

**Approach: LLM-as-NLI-Judge**

> **Research Context:** Natural Language Inference (NLI), also called Recognizing Textual Entailment (RTE), classifies the relationship between a *premise* (evidence) and a *hypothesis* (query answer) as Entailment, Contradiction, or Neutral. Academic benchmarks include SNLI (Stanford), MultiNLI, and FEVER. While Transformer-based cross-encoders like `cross-encoder/nli-deberta-v3-base` offer high accuracy, we use an LLM-based approach for richer reasoning chains and domain flexibility.

**Anti-Hallucination Guardrail:** The LLM is explicitly instructed to act as a **strict verification judge**, never a creative writer. If evidence is absent or ambiguous, it MUST return `UNKNOWN` — never fabricate an answer.

**Pydantic Output Schema:**

```python
class EntailmentStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"  
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"

class IntentEvaluation(BaseModel):
    intent_id: str
    query: str
    status: EntailmentStatus
    reasoning: str               # Chain-of-thought explanation
    evidence_chunk_ids: list[str] # Must cite exact chunks
    cited_dom_paths: list[str]   # Traceable DOM selectors
    confidence: float            # 0.0 – 1.0
```

**LLM Budget:** 30 parallel calls (one per query). Using `gpt-4o-mini` at ~300ms/call with `asyncio.gather()`, total wall-clock time is approximately 2–3 seconds. Total cost: ~$0.005.

---

### 5.6 Cross-Page Contradiction Detector

**Purpose:** Detect inconsistencies in factual claims across different pages (e.g., Homepage says "Open until 10 PM" but Footer on /about says "Open until 9 PM").

**Algorithm:**

1. **Entity Extraction:** Extract normalized key-value pairs for critical business entities:
   - `opening_hours`, `phone_number`, `address`, `refund_policy`, `price:{item_name}`, `dietary:{claim}`
2. **Cross-Page Diffing:** For each entity type, compare all extracted values across different URLs and DOM paths.
3. **Conflict Classification:**
   - **Hard Contradiction:** Same entity, different factual values (e.g., different phone numbers).
   - **Soft Inconsistency:** Same entity, different levels of specificity (e.g., "Open late" vs "Open until 11 PM").

**Output:**

```json
{
  "entity": "opening_hours.friday",
  "conflict_type": "HARD_CONTRADICTION",
  "values": [
    { "value": "10:00 PM", "url": "/", "dom_path": "header > span.hours" },
    { "value": "9:00 PM", "url": "/about", "dom_path": "footer > div.info > p:nth-of-type(2)" }
  ],
  "severity": "HIGH"
}
```

---

### 5.7 Findability Score Calculator

**Purpose:** Compute a single quantified metric `F` (0–100) representing the site's AI-discoverability.

**Formula:**

```
F = 0.40 × S_ans + 0.30 × S_con + 0.20 × S_str + 0.10 × S_acc

(Components \(S_*\) are already on a 0–100 scale; the result is 0–100. Do **not** apply an additional outer ×100. Canonical ADR: [docs/engineering/ARCHITECTURE_DECISIONS.md](engineering/ARCHITECTURE_DECISIONS.md#adr-001-canonical-f-score-weight-formulation).)
```

| Sub-Score | Weight | Formula | What It Measures |
| :--- | :--- | :--- | :--- |
| **S_ans** (Answerability) | 40% | `(SUPPORTED count / 30) × 100` | Can AI find answers to customer queries? |
| **S_con** (Consistency) | 30% | `(1 − contradictions/entities) × 100` | Are facts consistent across pages? |
| **S_str** (Structured Data) | 20% | `% of core Schema.org types present` | Is JSON-LD properly implemented? |
| **S_acc** (Accessibility) | 10% | Text extractability score | Is content in parseable text (not images)? |

**Schema.org Types Checked for S_str:**

| Required Schema Type | Purpose |
| :--- | :--- |
| `LocalBusiness` (or specific subtype) | Core business identity |
| `PostalAddress` | Location |
| `OpeningHoursSpecification` | Operating hours |
| `GeoCoordinates` | Map pin |
| `Menu` / `hasMenu` | Menu data |
| `FAQPage` | Common questions |

> **Research Note:** Schema.org best practice (2025+) is to use the most specific subtype possible (e.g., `Restaurant`, `Dentist`, `HVACBusiness`) instead of generic `LocalBusiness`. JSON-LD is the preferred format for both Google and AI crawlers. All schema values MUST align with on-page visible content — discrepancies trigger devaluation by search engines.

---

### 5.8 Autonomous Patch Generator

**Purpose:** Generate deterministic, syntactically valid code patches for the highest-priority gaps.

**Patch Prioritization Formula:**

```
Priority(P) = (Impact × Confidence) / Difficulty
```

- **Impact:** How much would fixing this gap improve the F-Score?
- **Confidence:** How certain are we that this is a real gap (not a false positive)?
- **Difficulty:** How complex is the code change? (Lower = easier = higher priority)

**Patch Types Generated:**

| Patch Type | Target | Risk Level |
| :--- | :--- | :--- |
| **JSON-LD Injection** | `<head>` tag | Minimal — isolated, no visual impact |
| **FAQ Section Addition** | Before `</main>` or `</body>` | Low — adds new content block |
| **Hours Contradiction Fix** | Specific DOM path | Low — text replacement in known element |

**Example Generated Patch (Schema.org FAQPage):**

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "Are dogs allowed on the patio?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Yes, well-behaved dogs on leashes are welcome in our outdoor patio area."
      }
    },
    {
      "@type": "Question",
      "name": "Do you have gluten-free options?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Yes, we offer a dedicated gluten-free menu. Our kitchen uses a separate fryer for gluten-free items."
      }
    }
  ]
}
</script>
```

---

### 5.9 GitHub PR Engine

**Purpose:** Programmatically fork the user's repository, apply patches, and create a Pull Request with a detailed before/after analysis.

**Technology:** `PyGithub` (Python wrapper for GitHub REST API v3).

**Workflow:**

```
1. User provides GitHub repo URL + Personal Access Token
2. Fork the repository (or use existing fork)
3. Create branch: findable-ai/geo-optimizations
4. Apply generated patches to target files
5. Commit with structured message
6. Create Pull Request with markdown body:
   - F-Score before: 42% → after: 95%
   - Per-file diff summary
   - Linked intent evaluation results
```

> **Research Note:** When creating PRs across forks with PyGithub, the `head` parameter MUST be formatted as `username:branch_name`. The fork/branch must have commits pushed before the PR can be created. Authentication requires a Personal Access Token with repository permissions.

---

## 6. DAG Orchestrator & Budget Guard

The entire scan follows a strict **Directed Acyclic Graph (DAG)** state machine to keep execution predictable, fast, and cost-controlled:

```
OBSERVE ──▶ PLAN ──▶ ACT ──▶ VERIFY ──▶ REFLECT ──▶ STOP
```

| Phase | Action | LLM Calls | Wall Time |
| :--- | :--- | :--- | :--- |
| **OBSERVE** | Async crawl (up to 20 pages) | 0 | ~3s |
| **PLAN** | Intent generation (1 batch) | 1 | ~1s |
| **ACT** | Retrieval + Entailment (x30) | 30 | ~3s |
| **VERIFY** | Contradictions + F-Score | 1–2 | ~1s |
| **REFLECT** | Generate top patches | 2–3 | ~2s |
| **STOP** | Finalize + stream to client | 0 | <1s |
| **TOTAL** | | **35 max** | **~10s** |

**Hard Budget Cap:** The orchestrator MUST NOT exceed 35 LLM calls per scan. If the budget is exhausted, it gracefully stops at the current phase and returns partial results.

---

## 7. Data Models & Schema Design

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  businesses  │◄────│    scans     │◄────│  dom_chunks  │
│              │     │              │     │              │
│  id (PK)     │     │  id (PK)     │     │  id (PK)     │
│  name        │     │  business_id │     │  scan_id     │
│  url         │     │  status      │     │  url         │
│  category    │     │  f_score     │     │  dom_path    │
│  created_at  │     │  s_ans       │     │  content     │
└──────────────┘     │  s_con       │     │  tag         │
                     │  s_str       │     │  embedding   │
                     │  s_acc       │     │  content_tsv │
                     │  created_at  │     └──────┬───────┘
                     └──────┬───────┘            │
                            │              ┌─────┴────────┐
                     ┌──────┴───────┐      │              │
                     │   intents    │      │  evidence    │
                     │              │      │              │
                     │  id (PK)     │      │  id (PK)     │
                     │  scan_id     │      │  intent_id   │
                     │  category    │      │  chunk_id    │
                     │  query       │      │  rank        │
                     │  status      │      │  rrf_score   │
                     │  reasoning   │      └──────────────┘
                     │  confidence  │
                     └──────┬───────┘
                            │
                     ┌──────┴───────┐     ┌──────────────┐
                     │contradictions│     │   patches    │
                     │              │     │              │
                     │  id (PK)     │     │  id (PK)     │
                     │  scan_id     │     │  scan_id     │
                     │  entity      │     │  file_path   │
                     │  conflict    │     │  patch_type  │
                     │  values[]    │     │  content     │
                     │  severity    │     │  priority    │
                     └──────────────┘     │  pr_url      │
                                          └──────────────┘
```

---

## 8. API Surface

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `POST` | `/api/scans` | Start a new scan (body: `{ url: string }`) |
| `GET` | `/api/scans/{id}` | Get scan status and results |
| `GET` | `/api/scans/{id}/stream` | SSE stream for live progress |
| `GET` | `/api/scans/{id}/intents` | Get all 30 intent evaluations |
| `GET` | `/api/scans/{id}/contradictions` | Get detected contradictions |
| `GET` | `/api/scans/{id}/patches` | Get generated patches |
| `POST` | `/api/scans/{id}/patches/apply` | Create GitHub PR with patches |

---

## 9. Frontend Architecture

**Framework:** Next.js 14+ (App Router, TypeScript)  
**Styling:** Tailwind CSS v4 + shadcn/ui + Lucide Icons  
**Theme:** `next-themes` for dark/light mode toggle  
**Real-time:** Server-Sent Events (SSE) via `EventSource` API  
**Data Viz:** Recharts (radial score gauges) + `diff2html` (patch viewer)

> **Research Note:** SSE is preferred over WebSockets for this use case because the scan pipeline is strictly unidirectional (server to client). SSE runs over standard HTTP, auto-reconnects via the browser's native `EventSource` API, and avoids WebSocket reconnection complexity.

**Key UI Components:**

| Component | Purpose |
| :--- | :--- |
| `ScoreGauge` | Radial SVG meter showing F-Score (0–100) with 4 sub-score arcs |
| `IntentMatrix` | 30-row grid with pill badges (green SUPPORTED, red CONTRADICTED, amber UNKNOWN) |
| `ContradictionCard` | Side-by-side display of conflicting values with DOM paths |
| `EvidenceViewer` | Click-through to inspect exact CSS selectors and source text |
| `PatchModal` | Unified diff preview + 1-click "Create Pull Request" button |

---

## 10. Security Model

| Threat | Mitigation |
| :--- | :--- |
| **SSRF** | IP validation + DNS resolution check before every outbound request |
| **Prompt Injection** | Crawled content is treated as untrusted data; LLM prompts use delimiter-based sandboxing |
| **Token Leakage** | GitHub PATs are never stored; encrypted in-memory only for the duration of the PR creation |
| **Rate Abuse** | Per-IP rate limiting on `/api/scans` (5 scans/hour) |
| **LLM Cost Explosion** | Hard cap at 35 LLM calls per scan enforced by DAG orchestrator |

---

## 11. References & Research

| Reference | Source |
| :--- | :--- |
| GEO: Generative Engine Optimization (KDD 2024) | arXiv:2311.09735 — Princeton, IIT Delhi |
| GEO-bench: AI Visibility Benchmark | princeton.edu |
| Schema.org LocalBusiness Best Practices | schema.org, Google Rich Results Test |
| NLI: SNLI / MultiNLI / FEVER Benchmarks | nlpprogress.com |
| Instructor Library (Pydantic + LLM) | github.com/jxnl/instructor |
| pgvector (embedding storage + query-time dense/RRF hybrid) | github.com/pgvector/pgvector |
| Cross-Encoder NLI Models | Hugging Face sentence-transformers |
| SSRF Prevention (OWASP) | owasp.org |
| SSE in Next.js (Route Handlers) | Next.js Documentation |
| PyGithub PR Creation | PyGithub Documentation |

---

> **End of Document — Architecture & System Design v1.0**
