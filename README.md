<div align="center">

<img src="assets/logo.svg" alt="FindableAI Logo" width="150" height="150" />

# FindableAI

### Evidence-Grounded Autonomous Machine-Discoverability Optimization (MDO) Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js: 14 App Router](https://img.shields.io/badge/Next.js-14_App_Router-black.svg?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![PostgreSQL + pgvector](https://img.shields.io/badge/PostgreSQL-pgvector-336791.svg?style=for-the-badge&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Status: Active Development](https://img.shields.io/badge/Status-Active_Architecture-success.svg?style=for-the-badge)](docs/)
[![Backend CI](https://github.com/Chirag1724/FindableAI/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/Chirag1724/FindableAI/actions/workflows/backend-ci.yml)
[![Frontend CI](https://github.com/Chirag1724/FindableAI/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/Chirag1724/FindableAI/actions/workflows/frontend-ci.yml)

<p align="center">
  <b>Bridging the gap between the modern web and AI search engines.</b><br/>
  FindableAI autonomously audits web content against AI answer engines (Perplexity, SearchGPT, Gemini, ChatGPT Search), computes an evidence-grounded Findability F-Score, and generates precise, zero-hallucination GitHub pull requests with DOM-anchored patches.
</p>

[Architecture Deep Dive](docs/01_ARCHITECTURE_AND_SYSTEM_DESIGN.md) •
[Tech Stack & Implementation](docs/02_TECH_STACK_AND_IMPLEMENTATION.md) •
[Execution Playbook](docs/03_EXECUTION_PLAYBOOK.md) •
[Team Task Allocation](docs/04_TEAM_TASK_ALLOCATION.md)

</div>

## 📌 The Problem: SEO is Dying. GEO & MDO is Born.

Search is fundamentally mutating. Millions of users no longer click ten blue links—they prompt **AI Answer Engines** like Perplexity, ChatGPT Search, Gemini, and Claude.

| Traditional SEO | Machine Discoverability (GEO / MDO) |
| :--- | :--- |
| Focuses on keywords, backlinks, and meta tags | Focuses on factual clarity, semantic density, and authoritative entity graph grounding |
| Optimized for Web Crawlers (Googlebot) | Optimized for LLM RAG Retrieval (Vector embeddings + BM25 hybrid search) |
| Success metric: Search Engine Result Page (SERP) ranking | Success metric: Inclusion, Citation & Entailment in LLM-synthesized answers |
| Manual keyword stuffing & link-building | Grounded Natural Language Inference (NLI) & Citation-rate optimization |

**If an AI engine cannot reliably extract, verify, and cite your product facts, your business is effectively invisible to modern searchers.**

FindableAI is the first autonomous engine designed to diagnose, score, and remediate machine invisibility.

## 🚀 Key Innovations & Core Features

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 FINDABLE.AI PIPELINE                                   │
└────────────────────────────────────────────────────────────────────────────────────────┘
 [ URL / Repo ] ──► [ Playwright Crawler ] ──► [ DOM-Aware Chunker (CSS Paths) ]
                            │
                            ▼
              [ Synthetic Intent Engine ] (Persona & Query Generation)
                            │
                            ▼
           [ Hybrid Retrieval ] (pgvector dense + BM25 sparse + RRF)
                            │
                            ▼
         [ NLI Entailment & Contradiction Engine ] (DeBERTa-v3 / LLM Judge)
                            │
                            ▼
    ┌───────────────────────┴───────────────────────┐
    ▼                                               ▼
[ F-Score Engine (0-100) ]              [ Autonomous Patch Generator ]
  • Coverage Score (40%)                  • DOM-anchored diffs
  • Entailment Score (35%)                • Schema.org JSON-LD microdata
  • Contradiction Penalty (15%)           • Zero-hallucination guarantee
  • Structural Clarity (10%)                        │
                                                    ▼
                                      [ GitHub PR Automated Engine ]
```

1. **DOM-Aware Structural Chunking with CSS Path Traceability**
   - Traditional RAG chunks blindly by character count. FindableAI parses semantic DOM elements (`h1-h6`, `article`, `table`, `code`, `meta`), preserving strict CSS selectors (`div.pricing > table > tbody > tr:nth-child(2)`) so every detected gap maps directly to an exact line in code.

2. **Synthetic Intent Simulation**
   - Simulates diverse buyer personas (skeptical CTO, procurement officer, developer evaluator) generating realistic high-intent queries that AI search users ask.

3. **Hybrid Retrieval with Reciprocal Rank Fusion (RRF)**
   - Combines dense vector similarity (`text-embedding-3-small` / pgvector) with lexical BM25 retrieval to mirror how state-of-the-art AI answer engines assemble context windows.

4. **Natural Language Inference (NLI) & Contradiction Detection**
   - Assesses retrieved page context against target queries using NLI:
     - **Entailment:** Page provides clear, verifiable answers.
     - **Neutral:** Information is missing or ambiguous.
     - **Contradiction:** Page contains conflicting claims (e.g. outdated pricing vs FAQ).

5. **Findability F-Score (0–100 Mathematical Metric)**
   - Transparent, deterministic formula balancing query coverage, entailment ratio, contradiction penalties, and structured data completeness.

6. **Autonomous Code Remediations (Direct GitHub PRs)**
   - Instead of generic marketing advice, FindableAI generates actionable unified diffs (DOM additions, content clarifications, Schema.org JSON-LD) and opens ready-to-merge GitHub Pull Requests.

## 🏗️ Repository Architecture & Engineering Documentation

The project includes an elite-tier engineering specification suite:

```
FindableAI/
├── assets/                                    # Official branding & vector assets
│   ├── logo.png                               # Transparent RGBA high-res logo
│   └── logo.svg                               # Scalable vector logo mark
├── backend/                                   # FastAPI asynchronous core API
│   ├── app/
│   │   ├── api/v1/                            # Route controllers (health, scans, SSE stream, patches)
│   │   ├── core/                              # Config (Pydantic Settings), lifespan management
│   │   ├── schemas/                           # Shared Pydantic data contracts (scan, fscore, patch)
│   │   └── main.py                            # Application entrypoint with CORS & router mounting
│   ├── pyproject.toml                         # Ruff linter, formatter & Mypy type-checking config
│   └── requirements.txt                       # Python dependencies (Groq, LiteLLM, Playwright, pgvector)
├── docs/                                      # Comprehensive engineering specification suite
│   ├── 01_ARCHITECTURE_AND_SYSTEM_DESIGN.md   # Complete system blueprints & component math
│   ├── 02_TECH_STACK_AND_IMPLEMENTATION.md    # Tech choices, trade-offs & library configs
│   ├── 03_EXECUTION_PLAYBOOK.md               # 7-phase step-by-step engineering roadmap
│   └── 04_TEAM_TASK_ALLOCATION.md             # 3-person role breakdown, contracts & deliverables
├── frontend/                                  # Next.js 14 App Router real-time dashboard
│   ├── public/                                # Web assets (favicons, SVGs)
│   ├── src/
│   │   ├── app/                               # Pages (page.tsx, layout.tsx, not-found.tsx, globals.css)
│   │   └── types/                             # TypeScript interface contracts mirroring backend
│   ├── .eslintrc.json                         # ESLint configuration for Next.js Core Web Vitals
│   ├── package.json                           # Frontend scripts and dependencies
│   └── tailwind.config.ts                     # Cybernetic design tokens & glassmorphism utilities
├── .env.example                               # Unified environment configuration template
├── .gitignore                                 # Git hygiene covering Python, Node, Docker, and IDEs
├── docker-compose.yml                         # Local PostgreSQL 16 (pgvector) + Redis 7 services
├── LICENSE                                    # Open source MIT license (Findable AI)
└── README.md                                  # Repository overview and onboarding
```

### 📚 Detailed Documentation Guide

| Document | Focus & Highlights |
| :--- | :--- |
| **[01. Architecture & System Design](docs/01_ARCHITECTURE_AND_SYSTEM_DESIGN.md)** | • End-to-end dataflow pipeline<br/>• 9 component deep-dives (Crawler, DOM chunker, NLI engine, PR engine)<br/>• F-Score formal mathematical formulation<br/>• Cost & latency model (<$0.01 per scan, ~10s runtime) |
| **[02. Tech Stack & Implementation](docs/02_TECH_STACK_AND_IMPLEMENTATION.md)** | • Python 3.11 + FastAPI async core<br/>• Next.js 14 App Router + TailwindCSS dashboard<br/>• PostgreSQL 16 + pgvector with HNSW indexing<br/>• Instructor + Pydantic validation<br/>• Server-Sent Events (SSE) realtime streaming protocol |
| **[03. Execution Playbook](docs/03_EXECUTION_PLAYBOOK.md)** | • Phases from foundation through production release gates<br/>• Concrete code snippets and database migrations<br/>• Quality gates and unit/integration test specifications<br/>• Points to the canonical production roadmap in doc 04 |
| **[04. Team Task Allocation](docs/04_TEAM_TASK_ALLOCATION.md)** | • 3-person ownership map<br/>• Shiv intelligence/orchestration **17/17 complete**<br/>• **§10 Production Readiness Roadmap** (`PROD-5.*`–`PROD-8.*`) — integration, security, deploy, release |

## 💻 Tech Stack Summary

| Layer | Primary Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend** | Next.js 14 (App Router), TypeScript, TailwindCSS, Lucide Icons | High-performance dashboard, interactive F-Score visualizer, unified diff viewer |
| **Realtime Stream** | Server-Sent Events (SSE) via `EventSource` | Realtime progress updates during 10-second audits |
| **Backend API** | FastAPI (Python 3.11), Pydantic v2, Instructor | Async API, schema enforcement, structured LLM outputs |
| **Crawler & Extraction** | Playwright (Python async), BeautifulSoup4 | JavaScript-rendered DOM harvesting with CSS path derivation |
| **Database & Vector Store** | PostgreSQL 16 + pgvector, SQLAlchemy 2.0 (async), Alembic | Relational audit storage + hybrid BM25 / vector embeddings |
| **Job Queue & Cache** | Redis 7 in `docker-compose` (optional local service) | Reserved for cache/rate-limit; **scans currently use FastAPI `BackgroundTasks`** (no Celery/ARQ worker in-repo yet) |
| **AI / LLM Orchestration** | Groq (Qwen 2.5 72B) via LiteLLM & Instructor | Ultra-fast (~500 tps) synthetic intent generation, NLI classification, patch creation |
| **VCS Automation** | PyGithub / GitHub REST API | Automated branch creation, patch application, and Pull Request opening |

## 👥 Team Roles & Ownership

This project is architected for seamless execution across three dedicated roles:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                               TEAM RESPONSIBILITIES                             │
├──────────────────────┬───────────────────────────────┬──────────────────────────┤
│ Himanshu Raj         │ Shiv Raj Singh                │ Chirag Dwivedi           │
│ Systems & Data Lead  │ AI/ML & Pipeline Lead         │ Frontend & PR Lead       │
├──────────────────────┼───────────────────────────────┼──────────────────────────┤
│ • FastAPI Backend    │ • Synthetic Query Generator   │ • Next.js 14 App         │
│ • Playwright Crawler │ • NLI Entailment Classifier   │ • SSE Realtime Feed      │
│ • DOM-Aware Chunker  │ • Findability F-Score Engine  │ • Diff & Patch Viewer    │
│ • PostgreSQL+pgvector│ • Unified Patch Synthesizer   │ • GitHub PR Integration  │
│ • Redis & Workers    │ • LLM Evaluation Benchmarks   │ • Demo & Presentation    │
└──────────────────────┴───────────────────────────────┴──────────────────────────┘
```
*For complete task matrices, contract definitions, and milestone checklists, see [docs/04_TEAM_TASK_ALLOCATION.md](docs/04_TEAM_TASK_ALLOCATION.md).*


## 🛠️ Quickstart & Local Setup

### Prerequisites

- **Python:** 3.11+
- **Node.js:** 20+ & `npm` / `pnpm`
- **Docker & Docker Compose** (for PostgreSQL + pgvector + Redis)
- **API Keys:** Groq API Key (`GROQ_API_KEY`) (optional fallbacks: OpenAI / Gemini / Anthropic)

### 1. Clone & Environment Configuration

```bash
git clone https://github.com/Chirag1724/FindableAI.git
cd FindableAI

# Copy environment template
cp .env.example .env
```

### 2. Start Infrastructure Services

```bash
docker compose up -d postgres redis
```

### 3. Backend Setup

```bash
cd backend
python -m venv venv

# Windows
.\venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000` to access the FindableAI Scan Console.

## 📈 Findability F-Score Breakdown

FindableAI evaluates content across four mathematically rigorous sub-scores:

$$\text{F-Score} = 100 \times \left( 0.40 \cdot S_{\text{ans}} + 0.30 \cdot S_{\text{con}} + 0.20 \cdot S_{\text{str}} + 0.10 \cdot S_{\text{acc}} \right)$$

1. **Answerability ($S_{\text{ans}}$, 40%)**: Ratio and depth of critical synthetic buyer and researcher queries answered by crawled content.
2. **Consistency ($S_{\text{con}}$, 30%)**: Absence of factual conflicts across pages (operating hours, pricing, policies, contact details).
3. **Structure ($S_{\text{str}}$, 20%)**: Coverage and syntactic validity of Schema.org JSON-LD microdata across core entity types.
4. **Extractability & Accessibility ($S_{\text{acc}}$, 10%)**: Clean machine readability and DOM structural clarity of key entity metadata.

## 🤝 Contributing

We welcome contributions from the community. Please review our [Execution Playbook](docs/03_EXECUTION_PLAYBOOK.md) and [Architecture Specifications](docs/01_ARCHITECTURE_AND_SYSTEM_DESIGN.md) before submitting pull requests.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/InnovativeFeature`)
3. Commit your Changes (`git commit -m 'Add some InnovativeFeature'`)
4. Push to the Branch (`git push origin feature/InnovativeFeature`)
5. Open a Pull Request

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for complete legal terms.

<div align="center">
  <sub>Built with precision for the next generation of AI search and discoverability.</sub>
</div>
