# FindableAI — Tech Stack & Implementation Guide

> **Document Version:** 1.0  
> **Classification:** Internal Engineering Reference  
> **Authors:** FindableAI Core Team  
> **Last Updated:** September 2026  

---

## Table of Contents

1. [Tech Stack Overview](#1-tech-stack-overview)
2. [Backend Stack Deep-Dive](#2-backend-stack-deep-dive)
3. [Frontend Stack Deep-Dive](#3-frontend-stack-deep-dive)
4. [Infrastructure & DevOps](#4-infrastructure--devops)
5. [Development Environment Setup](#5-development-environment-setup)
6. [Dependency Manifest](#6-dependency-manifest)
7. [Monorepo Structure](#7-monorepo-structure)
8. [Configuration & Environment Variables](#8-configuration--environment-variables)
9. [Local Development Workflow](#9-local-development-workflow)
10. [Production Deployment Guide](#10-production-deployment-guide)

---

## 1. Tech Stack Overview

### Selection Criteria

Every technology choice in FindableAI was evaluated against 5 criteria:

| Criterion | Weight | Rationale |
| :--- | :--- | :--- |
| **DOM Parsing Accuracy** | Critical | CSS selector preservation is our core differentiator |
| **LLM Integration Quality** | Critical | Structured NLI output must be 100% schema-compliant |
| **Development Speed** | High | Maximize output with a 3-person team |
| **Demo Stability** | High | Live demo must never fail due to tech instability |
| **Cost Efficiency** | Medium | LLM costs must stay under $0.01/scan |

### Stack at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND                                  │
│  Next.js 14+ (App Router) · TypeScript · Tailwind CSS v4        │
│  shadcn/ui · Lucide Icons · Recharts · diff2html                │
│  next-themes (dark mode) · EventSource (SSE)                    │
├─────────────────────────────────────────────────────────────────┤
│                        BACKEND                                   │
│  Python 3.11+ · FastAPI · Pydantic v2 · Uvicorn (ASGI)         │
│  HTTPX (async) · BeautifulSoup4 · lxml · Playwright (fallback) │
│  Instructor · OpenAI SDK · rank-bm25                            │
├─────────────────────────────────────────────────────────────────┤
│                        DATA LAYER                                │
│  PostgreSQL 16+ · pgvector extension · SQLAlchemy 2.0           │
│  Alembic (migrations) · OpenAI text-embedding-3-small           │
│  [Dev Fallback: SQLite + ChromaDB/FAISS]                        │
├─────────────────────────────────────────────────────────────────┤
│                      INTEGRATIONS                                │
│  PyGithub (PR engine) · GitHub REST API v3                      │
│  OpenAI API (gpt-4o-mini) · Schema.org Validator                │
├─────────────────────────────────────────────────────────────────┤
│                      INFRASTRUCTURE                              │
│  Docker · Docker Compose · Supabase (managed Postgres)          │
│  Vercel (frontend) · Railway/Render (backend)                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Backend Stack Deep-Dive

### 2.1 Python 3.11+ & FastAPI

**Why Python?**
- **Gold standard for HTML AST parsing**: `lxml` and `BeautifulSoup4` are the most mature DOM traversal libraries in any language. Node.js has `cheerio`, but it lacks `lxml`'s XPath power and BeautifulSoup's recursive parent traversal.
- **Native NLI/ML ecosystem**: If we ever need to run local NLI models (e.g., `cross-encoder/nli-deberta-v3-base`), Python's HuggingFace `transformers` and `sentence-transformers` libraries are immediately available.
- **Async-native**: Python 3.11's `asyncio` with `httpx` handles concurrent crawling of 20+ pages effortlessly.

**Why FastAPI?**
- Automatic OpenAPI documentation (free Swagger UI at `/docs`).
- Native Pydantic v2 integration for request/response validation.
- First-class `async` support with Uvicorn (ASGI server).
- Built-in SSE streaming via `StreamingResponse`.

```python
# Example: SSE endpoint for live scan progress
from fastapi.responses import StreamingResponse

@app.get("/api/scans/{scan_id}/stream")
async def stream_scan(scan_id: str):
    async def event_generator():
        async for event in orchestrator.run(scan_id):
            yield f"data: {event.json()}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 2.2 HTTPX (Async HTTP Client)

**Why not `requests` or `aiohttp`?**
- `httpx` provides a unified sync/async API with the same interface.
- Native HTTP/2 support.
- Excellent timeout and redirect control.
- Drop-in compatibility with SSRF protection wrappers (`safehttpx`, `httpx-secure`).

```python
# Configuration
import httpx

CRAWLER_CONFIG = {
    "timeout": httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0),
    "limits": httpx.Limits(max_connections=20, max_keepalive_connections=5),
    "follow_redirects": True,
    "max_redirects": 5,
    "headers": {
        "User-Agent": "FindableAI-Crawler/1.0 (+https://findable.ai/bot)"
    }
}
```

### 2.3 BeautifulSoup4 + lxml

**Why this combination?**
- `lxml` as the parser backend provides C-speed parsing (10-50x faster than `html.parser`).
- `BeautifulSoup4` provides the recursive `.parent` traversal needed for CSS path generation.
- The `SoupSieve` library (built into BS4) enables CSS selector queries via `.select()` and `.select_one()`.

**Critical Capability — CSS Path Generation:**

BeautifulSoup does NOT have a built-in `get_css_path()` function. We implement it via recursive parent traversal:

```python
def get_css_selector(element) -> str:
    path_parts = []
    current = element
    while current and current.name and current.name != '[document]':
        selector = current.name
        if current.get('id'):
            selector += f"#{current['id']}"
            path_parts.insert(0, selector)
            break
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

### 2.4 Playwright (SPA Fallback)

**When triggered:** Only if the initial `httpx` fetch returns a page with `<div id="root"></div>` containing no text children (React/Vue/Angular SPA).

**Why Playwright over Selenium?**
- Modern async API designed for automation.
- Faster browser launch time.
- Built-in auto-wait for DOM elements.
- Multi-browser support (Chromium, Firefox, WebKit).

```python
from playwright.async_api import async_playwright

async def crawl_with_playwright(url: str) -> CrawlResult:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        html = await page.content()
        await browser.close()
    return CrawlResult(url=url, html=html, status=200)
```

### 2.5 Groq (Qwen 2.5) + Instructor (Primary LLM Engine)

**Why Groq with Qwen 2.5 (`qwen-2.5-72b-instruct`)?**
- **Speed**: ~500+ tokens/sec on Groq LPUs (sub-second completions for full JSON schemas).
- **Cost**: Exceptional cost-to-performance ratio (< $0.005 per scan).
- **Quality**: Qwen 2.5 achieves industry-leading benchmark results in structured reasoning, extraction, and code diff synthesis.
- **Flexibility**: Fallback support for OpenAI (`gpt-4o-mini`), Anthropic, and Gemini via LiteLLM.

**Why Instructor?**
- Guarantees 100% Pydantic schema compliance with auto-retry loops on validation errors.
- Single source of truth: define structure once in Python, Instructor handles structured output.
- Provider-agnostic: seamless switching between Groq, OpenAI, or local models.

```python
import instructor
from groq import AsyncGroq
from pydantic import BaseModel
from app.core.config import settings

# Initialize Instructor with Groq client
client = instructor.from_groq(AsyncGroq(api_key=settings.GROQ_API_KEY))

class IntentEvaluation(BaseModel):
    intent_id: str
    status: EntailmentStatus
    reasoning: str
    evidence_chunk_ids: list[str]
    confidence: float

result = await client.chat.completions.create(
    model=settings.DEFAULT_LLM_MODEL,
    response_model=IntentEvaluation,
    messages=[
        {"role": "system", "content": NLI_SYSTEM_PROMPT},
        {"role": "user", "content": f"Query: {query}\nEvidence:\n{evidence}"}
    ]
)
```

### 2.6 PostgreSQL + pgvector

**Why PostgreSQL as the unified store?**

The alternative is a split architecture: PostgreSQL for relational data + Pinecone/Qdrant/Chroma for vectors. This introduces:
- Distributed ID synchronization complexity.
- Additional infrastructure cost and operational overhead.
- Network latency between services.

With `pgvector`, embeddings live directly in the `dom_chunks` table alongside all relational data. A single `JOIN` query can fetch chunks with their parent scan, business info, and vector similarity — impossible with a separate vector DB.

**Indexing Strategy:**

| Index Type | Column | Purpose |
| :--- | :--- | :--- |
| **HNSW** | `embedding vector(1536)` | Fast approximate nearest neighbor for semantic search |
| **GIN** | `content_tsv tsvector` | Full-text keyword search (BM25-style) |
| **B-tree** | `scan_id`, `url` | Relational lookups |

**Dev Fallback:** For zero-config local development, use SQLite + ChromaDB (in-memory) or `sqlite-vec`. This avoids the need for a running PostgreSQL instance during early development.

### 2.7 rank-bm25 (Keyword Search)

For the BM25 component of hybrid search, we use the `rank-bm25` Python library. It provides an in-memory BM25Okapi implementation that operates on tokenized documents.

```python
from rank_bm25 import BM25Okapi

# Build index from chunk texts
tokenized_corpus = [chunk.content.lower().split() for chunk in chunks]
bm25 = BM25Okapi(tokenized_corpus)

# Query
tokenized_query = query.lower().split()
scores = bm25.get_scores(tokenized_query)
top_indices = scores.argsort()[-20:][::-1]
```

> **Note:** For production at scale, replace in-memory BM25 with PostgreSQL's `ts_rank()` operating on the `content_tsv` column. This eliminates the need to load all chunks into memory.

### 2.8 PyGithub

**Why PyGithub over raw REST API calls?**
- Type-safe Python objects for repos, branches, commits, and PRs.
- Handles pagination, rate limiting, and authentication automatically.
- Well-maintained with 6k+ GitHub stars.

**Key Implementation Detail:**

When creating a PR from a fork to an upstream repo, the `head` parameter MUST include the fork owner:

```python
from github import Github

g = Github("GITHUB_PAT")
upstream = g.get_repo("target_owner/target_repo")

pr = upstream.create_pull(
    title="[FindableAI] GEO Optimizations — F-Score 42% → 95%",
    body=pr_markdown_body,
    head="findable-ai-bot:findable-ai/geo-optimizations",
    base="main"
)
```

---

## 3. Frontend Stack Deep-Dive

### 3.1 Next.js 14+ (App Router)

**Why Next.js?**
- **App Router** provides a clean file-based routing system.
- **Server Components** reduce client-side JavaScript bundle.
- **Route Handlers** enable SSE endpoints directly in the Next.js app (eliminating CORS issues during dev).
- Massive ecosystem and community support.

**Key Patterns:**

| Pattern | Implementation |
| :--- | :--- |
| **SSE Consumption** | `useEffect` + `EventSource` in a client component |
| **Data Fetching** | `fetch` with `cache: 'no-store'` for real-time scan data |
| **Route Structure** | `/` (landing + URL input), `/scans/[id]` (dashboard) |
| **Error Boundaries** | `error.tsx` at route level for graceful failure handling |

### 3.2 Tailwind CSS v4 + shadcn/ui

**Why Tailwind CSS?**
- Utility-first approach enables rapid UI iteration.
- Consistent design token system via `tailwind.config.ts`.
- Zero-runtime CSS — all styles are compiled at build time.

**Why shadcn/ui?**
- **Not a component library** — it's a collection of copy-paste components built on Radix UI primitives.
- Full ownership: components live in your codebase, not in `node_modules`.
- Accessible by default (WAI-ARIA compliant).
- CSS-variable-driven theming makes dark mode trivial with `next-themes`.

**Core Components Used:**

| shadcn/ui Component | FindableAI Usage |
| :--- | :--- |
| `Card` | Intent result cards, contradiction cards |
| `Badge` | Status pills (SUPPORTED, CONTRADICTED, UNKNOWN) |
| `Table` | Intent matrix grid |
| `Dialog` / `Sheet` | Patch preview modal |
| `Tabs` | Dashboard section navigation |
| `Progress` | Scan progress indicator |
| `Tooltip` | DOM path hover previews |

### 3.3 Recharts (Data Visualization)

**Why Recharts over Chart.js or D3?**
- React-native components (no imperative DOM manipulation).
- Built-in responsive containers.
- `RadialBarChart` component for the F-Score gauge.

```tsx
<RadialBarChart
  width={300} height={300}
  innerRadius="60%" outerRadius="90%"
  data={[
    { name: "S_ans", value: 75, fill: "#10b981" },
    { name: "S_con", value: 90, fill: "#3b82f6" },
    { name: "S_str", value: 40, fill: "#f59e0b" },
    { name: "S_acc", value: 85, fill: "#8b5cf6" }
  ]}
  startAngle={180} endAngle={0}
>
  <RadialBar dataKey="value" />
</RadialBarChart>
```

### 3.4 diff2html (Patch Viewer)

**Purpose:** Render unified diffs of generated code patches in a side-by-side or inline format.

```tsx
import { html } from 'diff2html';

const diffHtml = html(unifiedDiffString, {
  drawFileList: false,
  outputFormat: 'side-by-side',
  matching: 'lines'
});
```

### 3.5 Real-Time: Server-Sent Events (SSE)

**Why SSE over WebSockets?**
- **Unidirectional**: The scan pipeline only streams server → client. WebSockets add bidirectional complexity that is unused.
- **Auto-reconnect**: The browser's native `EventSource` API automatically reconnects on network drops.
- **Standard HTTP**: Works through proxies, CDNs, and firewalls without special configuration.
- **Simpler backend**: FastAPI's `StreamingResponse` is all we need.

**Client-side pattern:**

```tsx
"use client";
import { useEffect, useState } from "react";

export function useScanStream(scanId: string) {
  const [events, setEvents] = useState<ScanEvent[]>([]);

  useEffect(() => {
    const source = new EventSource(`/api/scans/${scanId}/stream`);
    source.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setEvents((prev) => [...prev, data]);
    };
    source.onerror = () => source.close();
    return () => source.close();
  }, [scanId]);

  return events;
}
```

---

## 4. Infrastructure & DevOps

### 4.1 Development: Docker Compose

```yaml
# docker-compose.yml
version: "3.9"
services:
  db:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: findableai
      POSTGRES_USER: findableai
      POSTGRES_PASSWORD: dev_password
    volumes:
      - pgdata:/var/lib/postgresql/data

  backend:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [db]
    env_file: .env
    volumes:
      - ./backend:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    depends_on: [backend]
    volumes:
      - ./frontend:/app
    command: npm run dev

volumes:
  pgdata:
```

### 4.2 Production Deployment

| Component | Service | Rationale |
| :--- | :--- | :--- |
| **Frontend** | Vercel | Native Next.js support, global CDN, free tier |
| **Backend** | Railway or Render | Docker container hosting, easy scaling |
| **Database** | Supabase | Managed PostgreSQL with pgvector pre-installed |
| **Secrets** | Environment variables | GitHub PATs, OpenAI keys — never committed to repo |

### 4.3 CI/CD Pipeline

```
Push to main
    │
    ├── Backend: Run pytest → Build Docker → Deploy to Railway
    │
    └── Frontend: Run next build → Deploy to Vercel (auto via Git integration)
```

---

## 5. Development Environment Setup

### Prerequisites

| Tool | Version | Purpose |
| :--- | :--- | :--- |
| **Python** | 3.11+ | Backend runtime |
| **Node.js** | 20 LTS+ | Frontend runtime |
| **Docker** | 24+ | PostgreSQL + pgvector |
| **Git** | 2.40+ | Version control |

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/FindableAI.git
cd FindableAI

# 2. Start database
docker compose up db -d

# 3. Backend setup
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env       # Fill in OPENAI_API_KEY, DATABASE_URL

# Run migrations
alembic upgrade head

# Start backend
uvicorn app.main:app --reload --port 8000

# 4. Frontend setup (new terminal)
cd frontend
npm install
cp .env.example .env.local  # Set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev

# 5. Open http://localhost:3000
```

---

## 6. Dependency Manifest

### Backend: `requirements.txt`

```
# Core Framework
fastapi==0.115.*
uvicorn[standard]==0.32.*
pydantic==2.10.*

# HTTP & Crawling
httpx[http2]==0.28.*
beautifulsoup4==4.13.*
lxml==5.3.*
playwright==1.49.*

# LLM & AI
openai==1.58.*
instructor==1.7.*

# Database
sqlalchemy==2.0.*
asyncpg==0.30.*
pgvector==0.3.*
alembic==1.14.*

# Search
rank-bm25==0.2.*

# GitHub Integration
PyGithub==2.5.*

# Utilities
python-dotenv==1.0.*
structlog==24.4.*
tenacity==9.0.*

# Dev/Test
pytest==8.3.*
pytest-asyncio==0.24.*
httpx  # (also used for TestClient)
```

### Frontend: `package.json` (key dependencies)

```json
{
  "dependencies": {
    "next": "^14.2",
    "react": "^18.3",
    "react-dom": "^18.3",
    "recharts": "^2.13",
    "diff2html": "^3.4",
    "lucide-react": "^0.460",
    "next-themes": "^0.4",
    "class-variance-authority": "^0.7",
    "clsx": "^2.1",
    "tailwind-merge": "^2.6"
  },
  "devDependencies": {
    "typescript": "^5.6",
    "tailwindcss": "^4.0",
    "@types/react": "^18.3",
    "@types/node": "^22"
  }
}
```

---

## 7. Monorepo Structure

```
FindableAI/
│
├── docs/                                 # You are here
│   ├── 01_ARCHITECTURE_AND_SYSTEM_DESIGN.md
│   ├── 02_TECH_STACK_AND_IMPLEMENTATION.md
│   ├── 03_EXECUTION_PLAYBOOK.md
│   └── 04_TEAM_TASK_ALLOCATION.md
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                       # FastAPI app factory + CORS + lifespan
│   │   ├── config.py                     # Settings via pydantic-settings
│   │   │
│   │   ├── api/                          # Route handlers
│   │   │   ├── __init__.py
│   │   │   ├── scans.py                  # POST /scans, GET /scans/{id}, SSE stream
│   │   │   ├── evidence.py               # GET /evidence
│   │   │   └── patches.py               # GET/POST /patches
│   │   │
│   │   ├── core/                         # Shared utilities
│   │   │   ├── __init__.py
│   │   │   ├── security.py              # SSRF validator, IP blocklist
│   │   │   ├── llm.py                   # Instructor client factory + budget tracker
│   │   │   └── embeddings.py            # OpenAI embedding helper
│   │   │
│   │   ├── crawler/                      # Data acquisition
│   │   │   ├── __init__.py
│   │   │   ├── crawler.py               # HTTPX async BFS crawler
│   │   │   └── dom_chunker.py           # Structural parser + CSS path generator
│   │   │
│   │   ├── engines/                      # Intelligence pipeline
│   │   │   ├── __init__.py
│   │   │   ├── intent_generator.py      # 10 taxonomy classes, 30 queries
│   │   │   ├── entailment_engine.py     # Hybrid retrieval + NLI classification
│   │   │   ├── contradiction.py         # Cross-page entity diffing
│   │   │   ├── scorer.py               # F-Score formula computation
│   │   │   └── patch_generator.py       # Schema.org JSON-LD builder
│   │   │
│   │   ├── github/                       # PR engine
│   │   │   ├── __init__.py
│   │   │   └── pr_engine.py             # Fork, branch, commit, PR via PyGithub
│   │   │
│   │   ├── models/                       # Data models
│   │   │   ├── __init__.py
│   │   │   ├── database.py              # SQLAlchemy models
│   │   │   └── schemas.py               # Pydantic request/response schemas
│   │   │
│   │   └── db.py                         # Database engine + session factory
│   │
│   ├── alembic/                          # Database migrations
│   │   └── versions/
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx               # Root layout + ThemeProvider
│   │   │   ├── page.tsx                 # Landing page + URL input hero
│   │   │   ├── globals.css              # Tailwind base + CSS variables
│   │   │   └── scans/
│   │   │       └── [id]/
│   │   │           └── page.tsx         # Scan dashboard (results view)
│   │   │
│   │   ├── components/
│   │   │   ├── ui/                      # shadcn/ui base components
│   │   │   ├── ScoreGauge.tsx           # Radial F-Score indicator
│   │   │   ├── IntentMatrix.tsx         # 30-query evaluation grid
│   │   │   ├── ContradictionCard.tsx    # Inconsistency viewer
│   │   │   ├── EvidenceViewer.tsx       # DOM path inspector
│   │   │   ├── PatchModal.tsx           # Diff viewer + PR button
│   │   │   └── ScanProgress.tsx         # Real-time SSE progress bar
│   │   │
│   │   ├── hooks/
│   │   │   └── useScanStream.ts         # SSE EventSource hook
│   │   │
│   │   └── lib/
│   │       ├── api.ts                   # Backend API client
│   │       └── utils.ts                 # cn() helper, formatters
│   │
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── next.config.mjs
│
├── demo-site/                            # "Bistro 2026" mock target
│   ├── index.html                       # Intentionally imperfect (conflicting hours, no schema)
│   ├── menu.html                        # Menu as text (good) + menu as PNG (bad)
│   ├── about.html                       # Different hours than index.html
│   └── styles.css
│
├── docker-compose.yml
├── .gitignore
├── .env.example
├── LICENSE
└── README.md
```

---

## 8. Configuration & Environment Variables

### `.env.example`

```bash
# ═══════════════════════════════════════════
# FindableAI Configuration
# ═══════════════════════════════════════════

# ── OpenAI ──
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# ── Database ──
DATABASE_URL=postgresql+asyncpg://findableai:dev_password@localhost:5432/findableai

# ── GitHub (Optional — for PR engine) ──
GITHUB_PAT=ghp_...
GITHUB_BOT_USERNAME=findable-ai-bot

# ── Crawler ──
MAX_PAGES_PER_SCAN=20
CRAWL_TIMEOUT_SECONDS=30
CRAWL_CONCURRENCY=5

# ── Budget ──
MAX_LLM_CALLS_PER_SCAN=35

# ── Frontend ──
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 9. Local Development Workflow

### Daily Development Loop

```bash
# Terminal 1: Database
docker compose up db -d

# Terminal 2: Backend (with auto-reload)
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 3: Frontend (with HMR)
cd frontend
npm run dev

# Terminal 4: Demo site (optional — for testing)
cd demo-site
python -m http.server 8080
```

### Testing

```bash
# Backend tests
cd backend
pytest -v --asyncio-mode=auto

# Frontend type checking
cd frontend
npx tsc --noEmit
```

### Database Migrations

```bash
# Create a new migration after model changes
cd backend
alembic revision --autogenerate -m "add contradictions table"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

---

## 10. Production Deployment Guide

### Backend → Railway

```bash
# railway.toml
[build]
  builder = "DOCKERFILE"
  dockerfilePath = "backend/Dockerfile"

[deploy]
  startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
  healthcheckPath = "/health"
  healthcheckTimeout = 10
```

### Frontend → Vercel

1. Connect GitHub repository to Vercel.
2. Set root directory to `frontend/`.
3. Set environment variable: `NEXT_PUBLIC_API_URL` → Railway backend URL.
4. Deploy automatically on push to `main`.

### Database → Supabase

1. Create a new Supabase project.
2. Enable the `pgvector` extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Copy the connection string to `DATABASE_URL` in backend environment.

---

> **End of Document — Tech Stack & Implementation Guide v1.0**
