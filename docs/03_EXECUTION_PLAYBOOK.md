# FindableAI — Execution Playbook

> **Document Version:** 1.0  
> **Classification:** Internal Engineering Reference  
> **Authors:** FindableAI Core Team  
> **Last Updated:** September 2026  

---

## Table of Contents

1. [Playbook Overview](#1-playbook-overview)
2. [Phase 0: Foundation & Environment](#2-phase-0-foundation--environment)
3. [Phase 1: Data Engine — Crawler & Chunker](#3-phase-1-data-engine--crawler--chunker)
4. [Phase 2: Intelligence Pipeline](#4-phase-2-intelligence-pipeline)
5. [Phase 3: Patch Engine & GitHub Integration](#5-phase-3-patch-engine--github-integration)
6. [Phase 4: Frontend Dashboard](#6-phase-4-frontend-dashboard)
7. [Phase 5: Integration, Testing & Demo Polish](#7-phase-5-integration-testing--demo-polish)
8. [Phase 6: Deployment & Launch](#8-phase-6-deployment--launch)
9. [Definition of Done (DoD)](#9-definition-of-done-dod)
10. [Risk Register & Mitigations](#10-risk-register--mitigations)
11. [Quality Checklist](#11-quality-checklist)

---

## 1. Playbook Overview

This document is a **phase-by-phase execution guide** — every task specifies **what** to build, **how** to build it, **when** it should be completed relative to other tasks, and **which acceptance criteria** must be met before moving on.

> **Important:** There is **no fixed time restriction** for the team. Each phase should be completed thoroughly before moving to the next. Quality over speed.

### Phase Summary

```
Phase 0: Foundation & Environment
    │   Setup repo, Docker, database, project scaffolds
    ▼
Phase 1: Data Engine
    │   Async crawler, SSRF shield, DOM chunker, CSS paths
    ▼
Phase 2: Intelligence Pipeline
    │   Intent generator, hybrid retrieval, NLI entailment,
    │   contradiction detector, F-Score calculator
    ▼
Phase 3: Patch Engine & GitHub
    │   Schema.org JSON-LD generator, PR automation
    ▼
Phase 4: Frontend Dashboard
    │   Next.js app, SSE streaming, all UI components
    ▼
Phase 5: Integration & Demo Polish
    │   End-to-end testing, demo pre-caching, rehearsal
    ▼
Phase 6: Deployment & Launch
        Production deployment, monitoring, documentation
```

### Dependency Graph

```
Phase 0 ─────────────────────────────────────────────────────▶ ALL
Phase 1 ─────────────────────────────────────────────────────▶ Phase 2
Phase 2 ─────────────────────────────────────────────────────▶ Phase 3
Phase 2 ─────────────────────────────────────────────────────▶ Phase 4 (can start UI shell in parallel)
Phase 3 ─────────────────────────────────────────────────────▶ Phase 5
Phase 4 ─────────────────────────────────────────────────────▶ Phase 5
Phase 5 ─────────────────────────────────────────────────────▶ Phase 6
```

---

## 2. Phase 0: Foundation & Environment

### Objective
Set up the monorepo, development environment, database, and project scaffolds so all team members can start coding independently.

### Tasks

| # | Task | Details | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| 0.1 | **Initialize monorepo** | Create `backend/`, `frontend/`, `demo-site/`, `docs/` directories. Initialize git, add `.gitignore`, `LICENSE`, `README.md`. | `git log` shows initial commit with correct structure |
| 0.2 | **Backend scaffold** | Create FastAPI app with health check endpoint. Setup `requirements.txt`, `Dockerfile`, `.env.example`. | `GET /health` returns `{"status": "ok"}` |
| 0.3 | **Database setup** | Docker Compose with `pgvector/pgvector:pg16`. Create initial Alembic migration with `businesses` and `scans` tables. | `alembic upgrade head` runs without errors; tables exist in DB |
| 0.4 | **Frontend scaffold** | `npx -y create-next-app@latest ./` with TypeScript, Tailwind, App Router. Install shadcn/ui, next-themes, Recharts. | `npm run dev` serves landing page at localhost:3000 |
| 0.5 | **Demo site** | Create "Bistro 2026" with `index.html`, `menu.html`, `about.html`. Intentionally include: (a) conflicting hours (10 PM vs 9 PM), (b) menu as PNG image, (c) no JSON-LD schema. | Site serves on `python -m http.server 8080` |
| 0.6 | **CI/CD baseline** | Setup GitHub Actions for: backend `pytest`, frontend `tsc --noEmit`. | CI passes on push to main |

### How to Build: Demo Site ("Bistro 2026")

The demo site is **intentionally imperfect** — it's the test subject that FindableAI will audit. Include these deliberate flaws:

```html
<!-- index.html — Homepage -->
<!-- FLAW 1: Hours say "Open until 10 PM" in header -->
<header>
  <span class="hours">Mon-Sun: 11 AM - 10 PM</span>
</header>

<!-- FLAW 2: No JSON-LD structured data anywhere -->
<!-- FLAW 3: Menu section has an image-only version -->
<section id="menu">
  <h2>Our Menu</h2>
  <img src="menu-photo.png" alt="menu">  <!-- No alt text or text content -->
</section>
```

```html
<!-- about.html — About Page -->
<!-- FLAW 4: Hours CONTRADICT homepage (9 PM vs 10 PM) -->
<footer>
  <div class="info">
    <p>Hours: Monday - Sunday, 11:00 AM - 9:00 PM</p>
  </div>
</footer>
```

---

## 3. Phase 1: Data Engine — Crawler & Chunker

### Objective
Build the async web crawler with SSRF protection and the structural DOM chunker that outputs CSS-selector-tagged text chunks.

### Tasks

| # | Task | Details | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| 1.1 | **SSRF Validator** | Implement `security.py`: URL scheme validation, DNS resolution, IP blocklist check (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.169.254). | Unit tests: blocks `http://127.0.0.1`, `http://169.254.169.254`, allows `https://example.com` |
| 1.2 | **Async BFS Crawler** | Implement `crawler.py`: Start from root URL, discover internal links via `<a href>` tags, BFS crawl up to `MAX_PAGES_PER_SCAN` (default 20). Semaphore-limited concurrency. | Crawling `demo-site` discovers 3 pages (index, menu, about) |
| 1.3 | **SPA Detection** | In crawler, detect empty `<div id="root">` and fall back to Playwright. | Test with a React SPA returns rendered HTML |
| 1.4 | **DOM Chunker** | Implement `dom_chunker.py`: Parse HTML, split at semantic boundaries, compute CSS selector path for each chunk. | Chunking `demo-site/menu.html` produces chunks with valid CSS paths. Paths are verifiable in browser DevTools. |
| 1.5 | **Embedding Pipeline** | Embed each chunk's content using `text-embedding-3-small`. Store embeddings in `dom_chunks.embedding` column. | Each chunk in DB has a non-null 1536-dim vector |
| 1.6 | **BM25 Index** | Ensure `content_tsv` column auto-populates via `GENERATED ALWAYS AS`. Verify GIN index exists. | `SELECT * FROM dom_chunks WHERE content_tsv @@ to_tsquery('vegan')` returns relevant chunks |

### How to Build: The CSS Selector Generator

This is the most critical piece of novel engineering. Here is the step-by-step implementation:

**Step 1:** Parse the HTML with BeautifulSoup4 using lxml backend:
```python
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, "lxml")
```

**Step 2:** Define semantic boundary tags for chunking:
```python
SEMANTIC_TAGS = {'section', 'article', 'main', 'table', 'dl', 'ul', 'ol',
                 'header', 'footer', 'nav', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
```

**Step 3:** Walk the DOM tree and extract chunks at semantic boundaries:
```python
def extract_chunks(soup, url: str) -> list[DOMChunk]:
    chunks = []
    for element in soup.find_all(SEMANTIC_TAGS):
        text = element.get_text(separator=" ", strip=True)
        if len(text.split()) < 3:  # Skip near-empty elements
            continue
        chunks.append(DOMChunk(
            url=url,
            dom_path=get_css_selector(element),
            content=text,
            tag=element.name,
            word_count=len(text.split())
        ))
    return chunks
```

**Step 4:** Implement CSS path generation via recursive parent traversal:
```python
def get_css_selector(element) -> str:
    path_parts = []
    current = element
    while current and current.name and current.name != '[document]':
        selector = current.name
        if current.get('id'):
            selector += f"#{current['id']}"
            path_parts.insert(0, selector)
            break  # IDs are unique — stop here
        classes = current.get('class', [])
        if classes:
            selector += '.' + '.'.join(classes)
        else:
            siblings = [s for s in current.parent.children
                       if hasattr(s, 'name') and s.name == current.name]
            if len(siblings) > 1:
                index = siblings.index(current) + 1
                selector += f":nth-of-type({index})"
        path_parts.insert(0, selector)
        current = current.parent
    return " > ".join(path_parts)
```

**Step 5:** Verify by opening the page in Chrome DevTools and running:
```javascript
document.querySelector("body > main > section#menu > table.menu-grid > tr:nth-of-type(3)")
```
The returned element should match the chunk content.

---

## 4. Phase 2: Intelligence Pipeline

### Objective
Build the core AI reasoning pipeline: intent generation, hybrid retrieval, NLI entailment, contradiction detection, and F-Score computation.

### Tasks

| # | Task | Details | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| 2.1 | **LLM Client Factory** | Implement `llm.py`: Instructor-patched AsyncOpenAI client with budget tracker (counts calls, enforces MAX_LLM_CALLS_PER_SCAN). | Budget tracker raises `BudgetExhausted` at call #36 |
| 2.2 | **Intent Generator** | Implement `intent_generator.py`: Takes business category (inferred from crawl), generates 30 queries across 10 taxonomy classes via single LLM call. | Output has exactly 30 `IntentQuery` objects, 3 per category |
| 2.3 | **Hybrid Search** | Implement retrieval in `entailment_engine.py`: For each query, run parallel vector search + BM25, fuse via RRF, return top 5 chunks. | For query "Are you open on Thanksgiving?", retrieves chunks containing hours info |
| 2.4 | **NLI Entailment** | Implement entailment classification: For each (query, top-5 chunks) pair, LLM classifies as SUPPORTED / PARTIALLY_SUPPORTED / CONTRADICTED / UNKNOWN. | For Bistro 2026: "vegan burger" query → SUPPORTED; "wheelchair access" → UNKNOWN |
| 2.5 | **Contradiction Detector** | Implement `contradiction.py`: Extract entity-value pairs, diff across pages. | Detects hours contradiction: 10 PM (index.html) vs 9 PM (about.html) |
| 2.6 | **F-Score Calculator** | Implement `scorer.py`: Apply formula `F = 0.40*S_ans + 0.30*S_con + 0.20*S_str + 0.10*S_acc`. | Bistro 2026 scores approximately 30-50% (imperfect by design) |
| 2.7 | **DAG Orchestrator** | Implement the OBSERVE → PLAN → ACT → VERIFY → REFLECT → STOP state machine with SSE event emission at each phase transition. | Full pipeline runs end-to-end on Bistro 2026 in <15 seconds |

### How to Build: The NLI Entailment Prompt

The system prompt is the most sensitive piece of the pipeline. It must:
1. **Prevent hallucination** — the model must never invent information.
2. **Force citation** — every claim must reference specific chunk IDs.
3. **Be deterministic** — same evidence should yield same classification.

```python
NLI_SYSTEM_PROMPT = """You are a strict evidence verification judge. Your task is to determine 
whether a set of evidence chunks from a website can answer a customer's question.

RULES:
1. You are NOT a creative writer. You are a JUDGE.
2. You can ONLY use information explicitly stated in the provided evidence chunks.
3. If the evidence does not contain enough information to answer the question, 
   you MUST return status "UNKNOWN". Never guess or infer.
4. If the evidence contains conflicting information, return "CONTRADICTED".
5. If the evidence partially answers the question, return "PARTIALLY_SUPPORTED".
6. If the evidence clearly and fully answers the question, return "SUPPORTED".
7. You MUST cite the specific chunk_ids that support your classification.
8. Your reasoning must be a factual chain — no speculation.

CLASSIFICATION GUIDE:
- SUPPORTED: The evidence directly and completely answers the question.
- PARTIALLY_SUPPORTED: The evidence addresses the topic but lacks specifics.
- CONTRADICTED: The evidence contains conflicting statements about the same fact.
- UNKNOWN: The evidence does not address this question at all."""
```

### How to Build: Hybrid Retrieval (Step-by-Step)

```python
async def evaluate_intent(intent: IntentQuery, scan_id: str) -> IntentEvaluation:
    # Step 1: Hybrid search for relevant chunks
    chunks = await hybrid_search(intent.query, scan_id, k=5)
    
    # Step 2: Format evidence for LLM
    evidence_text = "\n\n".join([
        f"[CHUNK {c.chunk_id}] (Source: {c.url} | Path: {c.dom_path})\n{c.content}"
        for c in chunks
    ])
    
    # Step 3: NLI classification via Instructor
    result = await llm_client.chat.completions.create(
        model="gpt-4o-mini",
        response_model=IntentEvaluation,
        messages=[
            {"role": "system", "content": NLI_SYSTEM_PROMPT},
            {"role": "user", "content": f"QUESTION: {intent.query}\n\nEVIDENCE:\n{evidence_text}"}
        ]
    )
    
    return result
```

---

## 5. Phase 3: Patch Engine & GitHub Integration

### Objective
Build the autonomous code remediation system that generates Schema.org JSON-LD patches and creates GitHub Pull Requests.

### Tasks

| # | Task | Details | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| 3.1 | **Patch Prioritizer** | Sort gaps by `Priority = (Impact * Confidence) / Difficulty`. Select top 3 for remediation. | Top gaps for Bistro 2026: (1) Missing FAQ schema, (2) Hours contradiction, (3) Missing LocalBusiness schema |
| 3.2 | **JSON-LD Generator** | Generate valid `LocalBusiness`, `FAQPage`, `OpeningHoursSpecification` JSON-LD from entailment results. | Output passes Schema.org Validator |
| 3.3 | **Patch Formatter** | Format patches as unified diffs applicable to the target HTML files. | `diff` output is syntactically valid |
| 3.4 | **GitHub PR Engine** | Implement `pr_engine.py`: Fork repo, create branch `findable-ai/geo-optimizations`, commit patches, create PR with markdown summary. | PR appears on target repo with correct diff |
| 3.5 | **Score Projection** | Calculate projected F-Score after patches are applied (re-run scorer on patched content). | PR body shows "F-Score: 42% → 95%" |

### How to Build: Schema.org JSON-LD Generation

**Step 1:** Map UNKNOWN intents to Schema.org solutions:

| Gap Type | Schema Solution |
| :--- | :--- |
| Missing FAQ answers | `FAQPage` with Q&A pairs |
| No business identity | `LocalBusiness` with NAP |
| No hours | `OpeningHoursSpecification` |
| No location | `GeoCoordinates` + `PostalAddress` |
| No menu data | `hasMenu` with `MenuItem` |

**Step 2:** Generate JSON-LD using Pydantic models:

```python
class SchemaOrgFAQ(BaseModel):
    context: str = Field(default="https://schema.org", alias="@context")
    type: str = Field(default="FAQPage", alias="@type")
    mainEntity: list[dict]

def generate_faq_schema(unknown_intents: list[IntentEvaluation]) -> str:
    questions = []
    for intent in unknown_intents:
        # Only generate FAQ entries for questions that SHOULD have answers
        questions.append({
            "@type": "Question",
            "name": intent.query,
            "acceptedAnswer": {
                "@type": "Answer",
                "text": f"[BUSINESS: Please provide the answer to: {intent.query}]"
            }
        })
    
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": questions
    }
    return json.dumps(schema, indent=2)
```

**Step 3:** Validate against Schema.org Validator API before outputting.

### How to Build: GitHub PR Creation

```python
from github import Github

async def create_pr(repo_url: str, patches: list[Patch], scan_result: ScanResult):
    g = Github(os.getenv("GITHUB_PAT"))
    
    # 1. Get the target repo
    owner, repo_name = parse_github_url(repo_url)
    repo = g.get_repo(f"{owner}/{repo_name}")
    
    # 2. Fork if needed
    try:
        fork = g.get_user().get_repo(repo_name)
    except:
        fork = g.get_user().create_fork(repo)
    
    # 3. Create branch from default branch
    default_branch = repo.default_branch
    ref = fork.get_git_ref(f"heads/{default_branch}")
    fork.create_git_ref(
        ref=f"refs/heads/findable-ai/geo-optimizations",
        sha=ref.object.sha
    )
    
    # 4. Apply patches (create/update files)
    for patch in patches:
        try:
            contents = fork.get_contents(patch.file_path, ref="findable-ai/geo-optimizations")
            fork.update_file(
                path=patch.file_path,
                message=f"[FindableAI] {patch.description}",
                content=patch.new_content,
                sha=contents.sha,
                branch="findable-ai/geo-optimizations"
            )
        except:
            fork.create_file(
                path=patch.file_path,
                message=f"[FindableAI] {patch.description}",
                content=patch.new_content,
                branch="findable-ai/geo-optimizations"
            )
    
    # 5. Create PR
    bot_username = os.getenv("GITHUB_BOT_USERNAME")
    pr = repo.create_pull(
        title=f"[FindableAI] GEO Optimizations — F-Score {scan_result.f_score}% → {scan_result.projected_score}%",
        body=generate_pr_body(scan_result, patches),
        head=f"{bot_username}:findable-ai/geo-optimizations",
        base=default_branch
    )
    
    return pr.html_url
```

---

## 6. Phase 4: Frontend Dashboard

### Objective
Build a premium, dark-mode Next.js dashboard with real-time scan progress, score visualization, intent matrix, contradiction viewer, and patch previewer.

### Tasks

| # | Task | Details | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| 4.1 | **Landing Page** | Hero section with URL input field, animated background, value proposition copy. Dark mode by default. | Entering a URL and clicking "Scan" triggers `POST /api/scans` |
| 4.2 | **Scan Progress** | SSE-powered progress bar showing phases: Crawling → Chunking → Generating Intents → Evaluating → Scoring → Patching. | Progress updates in real-time without page reload |
| 4.3 | **ScoreGauge** | Radial SVG chart showing F-Score (0-100) with 4 colored arcs for sub-scores (S_ans, S_con, S_str, S_acc). | Gauge animates from 0 to final score on load |
| 4.4 | **IntentMatrix** | Table/grid of 30 queries with status badges (green SUPPORTED, red CONTRADICTED, amber UNKNOWN, blue PARTIAL). Click to expand reasoning. | All 30 rows render; clicking shows evidence chunks and DOM paths |
| 4.5 | **ContradictionCard** | Card component showing entity, conflicting values, source URLs, and DOM paths. | Bistro 2026's hours contradiction displays correctly |
| 4.6 | **EvidenceViewer** | Slide-out panel showing: chunk content, source URL (clickable), CSS selector path (copyable). | Clicking a chunk ID in IntentMatrix opens EvidenceViewer |
| 4.7 | **PatchModal** | Dialog with: (a) unified diff rendered via diff2html, (b) "Create Pull Request" button, (c) projected score improvement. | Diff renders correctly; clicking PR button triggers `POST /api/scans/{id}/patches/apply` |
| 4.8 | **Responsive Layout** | Dashboard works on desktop (1440px+) and tablet (768px+). Mobile is nice-to-have. | No horizontal scrolling on 768px viewport |

### How to Build: SSE Integration

**Backend (FastAPI):**

```python
from fastapi.responses import StreamingResponse
from starlette.requests import Request

@router.get("/scans/{scan_id}/stream")
async def stream_scan(scan_id: str, request: Request):
    async def event_generator():
        async for phase, data in orchestrator.run_scan(scan_id):
            if await request.is_disconnected():
                break
            event = {"phase": phase, "data": data}
            yield f"data: {json.dumps(event)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable Nginx buffering
        }
    )
```

**Frontend (Next.js):**

```tsx
// hooks/useScanStream.ts
"use client";
import { useEffect, useState, useCallback } from "react";

interface ScanEvent {
  phase: string;
  data: any;
}

export function useScanStream(scanId: string) {
  const [events, setEvents] = useState<ScanEvent[]>([]);
  const [currentPhase, setCurrentPhase] = useState<string>("idle");
  const [isComplete, setIsComplete] = useState(false);

  useEffect(() => {
    const source = new EventSource(
      `${process.env.NEXT_PUBLIC_API_URL}/api/scans/${scanId}/stream`
    );

    source.onmessage = (event) => {
      const parsed: ScanEvent = JSON.parse(event.data);
      setEvents((prev) => [...prev, parsed]);
      setCurrentPhase(parsed.phase);
      
      if (parsed.phase === "STOP") {
        setIsComplete(true);
        source.close();
      }
    };

    source.onerror = () => {
      source.close();
    };

    return () => source.close();
  }, [scanId]);

  return { events, currentPhase, isComplete };
}
```

### How to Build: ScoreGauge Component

```tsx
// components/ScoreGauge.tsx
"use client";
import { RadialBarChart, RadialBar, ResponsiveContainer, PolarAngleAxis } from "recharts";

interface ScoreGaugeProps {
  fScore: number;
  sAns: number;
  sCon: number;
  sStr: number;
  sAcc: number;
}

const COLORS = {
  ans: "#10b981",  // Emerald
  con: "#3b82f6",  // Blue
  str: "#f59e0b",  // Amber
  acc: "#8b5cf6",  // Violet
};

export function ScoreGauge({ fScore, sAns, sCon, sStr, sAcc }: ScoreGaugeProps) {
  const data = [
    { name: "Accessibility", value: sAcc, fill: COLORS.acc },
    { name: "Structure", value: sStr, fill: COLORS.str },
    { name: "Consistency", value: sCon, fill: COLORS.con },
    { name: "Answerability", value: sAns, fill: COLORS.ans },
  ];

  return (
    <div className="relative w-72 h-72">
      <ResponsiveContainer>
        <RadialBarChart
          innerRadius="30%"
          outerRadius="90%"
          data={data}
          startAngle={180}
          endAngle={0}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar dataKey="value" cornerRadius={8} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-5xl font-bold text-white">{Math.round(fScore)}</span>
      </div>
    </div>
  );
}
```

---

## 7. Phase 5: Integration, Testing & Demo Polish

### Objective
Ensure the full system works end-to-end, with a polished demo experience.

### Tasks

| # | Task | Details | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| 5.1 | **End-to-end test** | Run full scan on Bistro 2026: URL input → crawl → chunk → evaluate → score → patch → PR. | Complete pipeline runs without errors; PR is created on GitHub |
| 5.2 | **Demo pre-caching** | Cache the Bistro 2026 scan results so the demo can run instantly even if the network or OpenAI API is slow/down. | Dashboard loads pre-cached results in <2 seconds |
| 5.3 | **Error handling** | Add graceful error states: invalid URL, unreachable site, LLM timeout, GitHub auth failure. | Each error shows a user-friendly message, not a stack trace |
| 5.4 | **Performance audit** | Ensure full scan completes in <15 seconds for a 5-page site. | Measure and log timing for each DAG phase |
| 5.5 | **Visual polish** | Review all UI components for consistency: colors, spacing, typography, animations. Add micro-animations (fade-in for cards, counter animation for score). | No visual glitches on Chrome, Firefox, Safari |
| 5.6 | **README update** | Comprehensive README.md with: project description, screenshots, tech stack, setup instructions, API docs link. | README renders correctly on GitHub |

### Demo Pre-Caching Strategy

To ensure the live demo never fails:

```python
# backend/app/core/demo_cache.py
import json
from pathlib import Path

DEMO_CACHE_DIR = Path(__file__).parent.parent / "demo_cache"

async def get_or_run_scan(url: str, scan_id: str):
    cache_file = DEMO_CACHE_DIR / f"{scan_id}.json"
    
    if cache_file.exists():
        # Return pre-computed results instantly
        return json.loads(cache_file.read_text())
    
    # Run live scan
    result = await orchestrator.run_scan_full(url)
    
    # Cache for future use
    cache_file.write_text(json.dumps(result, indent=2))
    
    return result
```

---

## 8. Phase 6: Deployment & Launch

### Objective
Deploy to production with monitoring and documentation.

### Tasks

| # | Task | Details | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| 6.1 | **Database migration** | Run Alembic migrations on Supabase production database. | All tables exist; pgvector extension enabled |
| 6.2 | **Backend deploy** | Deploy FastAPI to Railway with environment variables. | `/health` endpoint responds on production URL |
| 6.3 | **Frontend deploy** | Deploy Next.js to Vercel. Set `NEXT_PUBLIC_API_URL` to backend production URL. | Landing page loads at production domain |
| 6.4 | **CORS configuration** | Ensure backend allows requests from frontend production domain. | No CORS errors in browser console |
| 6.5 | **Monitoring** | Add structured logging (structlog) and basic error tracking. | Errors are logged with scan_id context |
| 6.6 | **Documentation** | Finalize all 4 docs files. Update README with production URLs and demo GIF. | All docs render correctly |

---

## 9. Definition of Done (DoD)

A task is considered **done** when ALL of the following are true:

- [ ] Code is written and committed to the correct branch.
- [ ] Unit tests pass (where applicable).
- [ ] No type errors (`mypy` for backend, `tsc` for frontend).
- [ ] Code has been reviewed by at least one other team member.
- [ ] Acceptance criteria from the task table are met.
- [ ] No regressions in existing functionality.

---

## 10. Risk Register & Mitigations

| # | Risk | Probability | Impact | Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| R1 | OpenAI API rate limiting or downtime | Medium | High | Pre-cache demo results; implement exponential backoff with tenacity |
| R2 | SPA sites fail to render with HTTPX | Medium | Medium | Playwright fallback is automated; test with 3 known SPAs |
| R3 | pgvector HNSW index build is slow | Low | Medium | For dev, use exact search (no index); for prod, use Supabase's managed index builds |
| R4 | GitHub API rate limits (60 req/hour unauthenticated) | Low | Medium | Always use authenticated requests (PAT); implement caching |
| R5 | LLM generates invalid JSON-LD | Medium | Low | Instructor guarantees schema; additionally validate against Schema.org Validator API |
| R6 | CSS selector paths are non-unique | Low | Medium | Prefer IDs over classes; add `:nth-of-type` for disambiguation; add uniqueness assertions |
| R7 | Cross-origin issues between frontend and backend | Medium | Low | Configure CORS in FastAPI; use Next.js API routes as proxy in dev |

---

## 11. Quality Checklist

### Before Every Merge

- [ ] All tests pass (`pytest`, `tsc`)
- [ ] No new lint warnings
- [ ] Environment variables documented in `.env.example`
- [ ] API changes reflected in OpenAPI schema (`/docs`)
- [ ] Database changes have an Alembic migration

### Before Demo Day

- [ ] Full end-to-end scan works on Bistro 2026
- [ ] Demo cache is populated and tested
- [ ] Dark mode renders correctly
- [ ] Score gauge animation is smooth
- [ ] Intent matrix shows all 30 rows with correct status
- [ ] Contradiction cards display correctly
- [ ] Patch diff renders correctly
- [ ] GitHub PR button works (or is gracefully disabled if no PAT)
- [ ] No console errors in browser DevTools
- [ ] Loading states exist for all async operations

---

> **End of Document — Execution Playbook v1.0**
