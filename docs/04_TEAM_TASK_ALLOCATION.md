# FindableAI — Team Task Allocation

> **Document Version:** 1.0  
> **Classification:** Internal Team Reference  
> **Authors:** FindableAI Core Team  
> **Last Updated:** September 2026  

---

## Table of Contents

1. [Team Structure & Roles](#1-team-structure--roles)
2. [Ownership Map](#2-ownership-map)
3. [Detailed Task Breakdown by Person](#3-detailed-task-breakdown-by-person)
   - [Himanshu Raj: Backend & Data Engine Lead](#himanshu-raj-backend--data-engine-lead)
   - [Shiv Raj Singh: AI/ML & Intelligence Pipeline Lead](#shiv-raj-singh-aiml--intelligence-pipeline-lead)
   - [Chirag Dwivedi: Frontend & Integration Lead](#chirag-dwivedi-frontend--integration-lead)
4. [Shared Responsibilities](#4-shared-responsibilities)
5. [Collaboration Touchpoints](#5-collaboration-touchpoints)
6. [Interface Contracts](#6-interface-contracts)
7. [Code Review Policy](#7-code-review-policy)
8. [Communication Protocol](#8-communication-protocol)
9. [Dependency Chain & Parallel Tracks](#9-dependency-chain--parallel-tracks)
10. [Production Readiness Roadmap](#10-production-readiness-roadmap)
11. [Summary: One-Page Task Count](#summary-one-page-task-count)

---

## 1. Team Structure & Roles

| Role | Alias | Primary Domain | Secondary Domain |
| :--- | :--- | :--- | :--- |
| **Himanshu Raj** | Backend & Data Engine Lead | Crawler, DOM Chunker, Database, API | Security, DevOps |
| **Shiv Raj Singh** | AI/ML & Intelligence Pipeline Lead | Intent Generator, NLI Engine, Scorer, Patch Generator | LLM Prompt Engineering, GitHub PR Engine |
| **Chirag Dwivedi** | Frontend & Integration Lead | Next.js Dashboard, UI Components, SSE | End-to-End Integration, Demo Polish |

### Role Selection Guidance

> **Note:** There is **no fixed time restriction**. Each person should complete their tasks thoroughly, communicate blockers early, and coordinate at defined touchpoints.

| If your strength is... | You should be... |
| :--- | :--- |
| Python, async programming, databases, web scraping | **Himanshu Raj** |
| AI/ML, prompt engineering, NLI/NLP, data pipelines | **Shiv Raj Singh** |
| React/Next.js, TypeScript, CSS, UI/UX design | **Chirag Dwivedi** |

---

## 2. Ownership Map

### By File/Directory

```
FindableAI/
├── backend/
│   ├── app/
│   │   ├── main.py                  ← Himanshu Raj (owns), Shiv Raj Singh (contributes routes)
│   │   ├── config.py                ← Himanshu Raj
│   │   │
│   │   ├── api/
│   │   │   ├── scans.py             ← Himanshu Raj (owns endpoints + SSE stream)
│   │   │   ├── evidence.py          ← Shiv Raj Singh
│   │   │   └── patches.py           ← Shiv Raj Singh
│   │   │
│   │   ├── core/
│   │   │   ├── security.py          ← Himanshu Raj (SSRF validator)
│   │   │   ├── llm.py               ← Shiv Raj Singh (Instructor client + budget)
│   │   │   └── embeddings.py        ← Himanshu Raj
│   │   │
│   │   ├── crawler/
│   │   │   ├── crawler.py           ← Himanshu Raj
│   │   │   └── dom_chunker.py       ← Himanshu Raj
│   │   │
│   │   ├── engines/
│   │   │   ├── intent_generator.py  ← Shiv Raj Singh
│   │   │   ├── entailment_engine.py ← Shiv Raj Singh
│   │   │   ├── contradiction.py     ← Shiv Raj Singh
│   │   │   ├── scorer.py            ← Shiv Raj Singh
│   │   │   └── patch_generator.py   ← Shiv Raj Singh
│   │   │
│   │   ├── github/
│   │   │   └── pr_engine.py         ← Shiv Raj Singh
│   │   │
│   │   ├── models/
│   │   │   ├── database.py          ← Himanshu Raj (schema), Shiv Raj Singh (reviews)
│   │   │   └── schemas.py           ← Himanshu Raj + Shiv Raj Singh (shared contract)
│   │   │
│   │   └── db.py                    ← Himanshu Raj
│   │
│   ├── alembic/                     ← Himanshu Raj
│   ├── requirements.txt             ← Himanshu Raj (maintains), All (contribute)
│   └── Dockerfile                   ← Himanshu Raj
│
├── frontend/                        ← Chirag Dwivedi (owns entire directory)
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx           ← Chirag Dwivedi
│   │   │   ├── page.tsx             ← Chirag Dwivedi
│   │   │   └── scans/[id]/page.tsx  ← Chirag Dwivedi
│   │   ├── components/              ← Chirag Dwivedi
│   │   ├── hooks/                   ← Chirag Dwivedi
│   │   └── lib/                     ← Chirag Dwivedi
│   └── ...
│
├── demo-site/                       ← Himanshu Raj (creates), Shiv Raj Singh (validates flaws)
├── docker-compose.yml               ← Himanshu Raj
├── docs/                            ← All (shared)
└── README.md                        ← Chirag Dwivedi (maintains)
```

### By System Component

```
┌─────────────────────────────────────────────────────────────┐
│                  CHIRAG DWIVEDI (Frontend)                  │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐  │
│  │ Landing  │ │ Score    │ │ Intent   │ │ Patch Modal │  │
│  │ Page     │ │ Gauge   │ │ Matrix   │ │ + Diff View │  │
│  └────┬─────┘ └────┬─────┘ └─────┬─────┘ └──────┬───────┘  │
│       │             │             │               │          │
│       └─────────────┴─────────────┴───────────────┘          │
│                          SSE / REST                          │
├─────────────────────────────────────────────────────────────┤
│                 HIMANSHU RAJ (Backend Core)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ SSRF Shield  │  │ BFS Crawler  │  │ DOM Chunker +    │   │
│  │ (security.py)│  │ (crawler.py) │  │ CSS Path Gen     │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
│         │                 │                     │             │
│  ┌──────┴─────────────────┴─────────────────────┴──────┐     │
│  │  PostgreSQL + pgvector + BM25 + Embeddings          │     │
│  │  API Routes + SSE Streaming + Docker                │     │
│  └─────────────────────────────────────────────────────┘     │
├─────────────────────────────────────────────────────────────┤
│                SHIV RAJ SINGH (Intelligence)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Intent Gen   │  │ NLI Engine   │  │ Contradiction    │   │
│  │ (30 queries) │  │ (Entailment) │  │ Detector         │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
│         │                 │                     │             │
│  ┌──────┴─────────────────┴─────────────────────┴──────┐     │
│  │  F-Score Calculator + Patch Generator + GitHub PR   │     │
│  └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Task Breakdown by Person

---

### Himanshu Raj: Backend & Data Engine Lead

**Primary Responsibility:** Everything from URL input to stored, indexed DOM chunks. The API surface. Infrastructure.

**Skill Requirements:** Python (asyncio), FastAPI, PostgreSQL, Docker, web scraping, network security.

#### Phase 0: Foundation

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P1-0.1 | Initialize monorepo structure | Critical | Create all directories, `.gitignore`, `LICENSE`, initial `README.md` |
| P1-0.2 | FastAPI scaffold | Critical | Create `main.py` with CORS, lifespan, health check. Create `config.py` with pydantic-settings |
| P1-0.3 | Docker Compose | Critical | PostgreSQL 16 + pgvector. Ensure `CREATE EXTENSION vector;` runs on init |
| P1-0.4 | Database models | Critical | SQLAlchemy models for `businesses`, `scans`, `dom_chunks` (with `vector(1536)` and `tsvector`). Alembic initial migration |
| P1-0.5 | Demo site creation | High | Build "Bistro 2026" HTML files with intentional flaws (conflicting hours, image-only menu, no schema) |

#### Phase 1: Crawler & Chunker

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P1-1.1 | SSRF Validator | Critical | `security.py`: URL scheme validation, DNS resolution, private IP blocklist. Unit tests for blocked/allowed IPs |
| P1-1.2 | Async BFS Crawler | Critical | `crawler.py`: httpx-based, semaphore-limited (5 concurrent), discovers internal `<a>` links, respects `MAX_PAGES_PER_SCAN` |
| P1-1.3 | SPA Detection & Playwright Fallback | High | Detect empty `<div id="root">` and auto-switch to headless Playwright |
| P1-1.4 | Structural DOM Chunker | Critical | `dom_chunker.py`: Chunk at semantic HTML boundaries (`section`, `article`, `table`, `h2`-`h6`). Generate CSS selector path for each chunk |
| P1-1.5 | Embedding Pipeline | Critical | `embeddings.py`: Batch embed chunk contents using `text-embedding-3-small`. Store in `dom_chunks.embedding` |
| P1-1.6 | BM25 Index Verification | High | Ensure `content_tsv` auto-populates; verify GIN index; test keyword queries |

#### Phase 2: API & Database Support

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P1-2.1 | Scan API Endpoints | Critical | `POST /api/scans` (create scan, trigger pipeline), `GET /api/scans/{id}` (get results) |
| P1-2.2 | SSE Streaming Endpoint | Critical | `GET /api/scans/{id}/stream`: Stream DAG phase transitions to frontend |
| P1-2.3 | Evidence API | High | `GET /api/scans/{id}/intents`, `GET /api/scans/{id}/contradictions` |
| P1-2.4 | Patches API | High | `GET /api/scans/{id}/patches`, `POST /api/scans/{id}/patches/apply` |
| P1-2.5 | Database query helpers | High | Hybrid search function (vector + BM25 + RRF), chunk retrieval by IDs |

#### Phase 5-6: DevOps & Deployment

| Task ID | Task | Priority | Status | Details |
| :--- | :--- | :--- | :--- | :--- |
| P1-5.1 | Backend Dockerfile | P0 | ❌ Not started | No `Dockerfile` in repo. Required for production image. See **PROD-7.1**. |
| P1-5.2 | CI/CD pipeline | P0 | ❌ Not started | No `.github/workflows/`. Required: pytest + ruff + mypy + frontend `tsc`/build. See **PROD-7.2**. |
| P1-5.3 | Production deployment | P0 | ❌ Not started | No production deploy config. Provider TBD (Railway/Render/etc.). See **PROD-7.3**. |
| P1-5.4 | CORS & security headers | P1 | ⚠️ Partial | CORS middleware exists in `main.py` via `CORS_ORIGINS`. Security headers and prod origin lockdown remaining. See **PROD-6.2**. |

#### Deliverables Checklist

- [x] `backend/app/core/security.py` — SSRF validator with unit tests
- [x] `backend/app/crawler/crawler.py` — Async BFS crawler
- [x] `backend/app/crawler/dom_chunker.py` — DOM chunker with CSS path generator
- [x] `backend/app/core/embeddings.py` — Embedding pipeline
- [x] `backend/app/db.py` — Database engine and session management
- [x] `backend/app/models/database.py` — All SQLAlchemy models
- [x] `backend/app/api/v1/scans.py` — Scan create/get/stream + patches routes **(crawl/chunk real; intelligence still mocked — see PROD-5.1)**
- [x] `docker-compose.yml` — Local Postgres + Redis only (no app Dockerfile)
- [x] `backend/alembic/` — Database migrations
- [x] `demo-site/` — Bistro 2026 with intentional flaws
- [x] Unit tests for: SSRF validator, DOM chunker, CSS path generator, embeddings pipeline, scans API
- [ ] Backend `Dockerfile` / production image
- [ ] GitHub Actions CI
- [ ] Wire `FindableAIDAG` into `run_scan_pipeline` (replace mock F-score/patches)

---

### Shiv Raj Singh: AI/ML & Intelligence Pipeline Lead

**Primary Responsibility:** Everything from raw chunks to intelligence outputs — intent generation, entailment verification, contradiction detection, scoring, patch generation, and GitHub PR creation.

**Skill Requirements:** Python, LLM prompt engineering, Pydantic, NLI concepts, Schema.org knowledge.

#### Phase 0: Foundation

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P2-0.1 | LLM Client Setup | Critical | ✅ **DONE** — `backend/app/core/llm.py` + `budget.py`: Instructor + LiteLLM; shared `BudgetGuard`; `BudgetExhausted` / `LLMBudgetExceededError`; default max 35 (`MAX_LLM_CALLS_PER_SCAN`) |
| P2-0.2 | Pydantic Schemas | Critical | ✅ **DONE** — AI contracts in `backend/app/schemas/intelligence.py` (`IntentQuery`, `IntentBatch`, `EntailmentStatus`, `IntentEvaluation`, `Contradiction`, `Patch`, `ScanResult`); coexist with API schemas |

#### Phase 2: Intelligence Pipeline

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P2-2.1 | Intent Generator | Critical | ✅ **DONE** — `intent_generator.py`: **ONE LLM call** → exactly 30 `IntentQuery` across 10 categories (3 each), structured `IntentBatch`, deterministic validation (duplicates, distribution, answer-like rejection). Architecture: `business_context → IntentGenerator → LLMClient → IntentBatch → validation` |
| P2-2.2 | Hybrid Retrieval | Critical | ✅ **DONE (consumer)** — `entailment_engine.py` calls Contract-1 `hybrid_search(query, scan_id, k=5)` from `app.crawler.search`. Does **not** re-implement vector/BM25/RRF (still owned by crawler/search). |
| P2-2.3 | NLI Entailment Engine | Critical | ✅ **DONE** — `backend/app/engines/entailment_engine.py`. Flow: `Intent → hybrid_search(..., k=5) → top-5 chunks → LLMClient NLI → IntentEvaluation`. Concurrent `evaluate_intents` via `asyncio.gather`; shared `LLMClient` budget preserved. |
| P2-2.4 | Anti-Hallucination Guardrails | Critical | ✅ **DONE** — evidence-only `NLI_SYSTEM_PROMPT`; zero-chunk → deterministic UNKNOWN (0 LLM calls); non-UNKNOWN must cite retrieved IDs; fabricated IDs rejected; no LLM repair/retry (`max_retries=0`) |
| P2-2.5 | Contradiction Detector | High | ✅ **DONE** — `backend/app/engines/contradiction.py`. Hybrid: deterministic structured facts first; LLM only for semantic ambiguity. Severities: HARD_CONTRADICTION / SOFT_INCONSISTENCY. Flow: chunks → extract → normalize → compare → optional semantic LLM → deduped `Contradiction`. |
| P2-2.6 | F-Score Calculator | Critical | ✅ **DONE** — `backend/app/engines/scorer.py`. Deterministic `S_ans` / `S_con` / `S_str` / `S_acc` with canonical confirmed weights `0.40 / 0.30 / 0.20 / 0.10` via `ScoreWeights`. |
| P2-2.7 | Schema.org Checker | High | ✅ **DONE** — JSON-LD parse via BeautifulSoup + `json.loads`; checks LocalBusiness (subtypes), PostalAddress, OpeningHoursSpecification, GeoCoordinates, Menu/hasMenu, FAQPage; `@graph` / arrays / `@type` arrays; malformed blocks reported safely. |

#### Phase 3: Patch Engine & GitHub

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P2-3.1 | Patch Prioritizer | High | ✅ **DONE** — `patch_prioritizer.py` + `schemas/patching.py`. Deterministic `Priority = (Impact × Confidence) / Difficulty`; Impact 0–100, Confidence 0–1, Difficulty 1–5 (never 0); dedupe; provenance preserved; top 3 with tie-break `priority↓ impact↓ confidence↓ difficulty↑ id↑`. Kinds: `INFORMATION_GAP`, `MISSING_SCHEMA`, `CONTRADICTION`. No LLM/JSON-LD/diffs/GitHub. Tests: `tests/test_patch_prioritizer.py` |
| P2-3.2 | JSON-LD Generator | Critical | ✅ **DONE** — `jsonld_generator.py`: evidence-backed Schema.org JSON-LD (`FAQPage`, `LocalBusiness`, `PostalAddress`, `OpeningHoursSpecification`, `GeoCoordinates`, `Menu`); validated via Phase E `analyze_schema_org`; no LLM/invention |
| P2-3.3 | Patch Formatter | High | ✅ **DONE** — `patch_formatter.py`: deterministic unified diffs; insert before `</head>` else `</body>`; identical=noop; conflict refuses overwrite |
| P2-3.4 | Projected Score Calculator | High | ✅ **DONE** — `projected_score.py`: in-memory HTML simulation; reuses Phase E `Scorer`; per-opportunity `current`/`projected`/`delta` (non-cumulative) |
| P2-3.5 | GitHub PR Engine | High | ✅ **DONE** — `github/pr_engine.py` + injectable `FakeGitHubClient`/`PyGithubClient`. Flow: validate patch set → fork → branch `findableai/remediation/<scan>` → apply validated HTML updates → commit → PR. Path traversal rejected; duplicate open PR reused; no real API in tests |
| P2-3.6 | PR Markdown Generator | Medium | ✅ **DONE** — `github/pr_markdown.py` pure deterministic renderer (scores/delta/gaps/intents/evidence/files). No GitHub/network/LLM |

#### Phase 4: DAG Orchestrator & Budget Guard

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P2-4.1 | DAG State Machine | Critical | ✅ **DONE** — `app/orchestration/`: `ScanPhase` transitions, `ScanContext`, `FindableAIDAG` orchestrates existing engines (no logic duplication). Shared `LLMClient` per scan; `create_pr` isolates GitHub. SSE deferred to P1 streaming. Tests: `test_dag_state.py`, `test_dag_runner.py`, `test_end_to_end_orchestration.py` |
| P2-4.2 | Budget Guard | Critical | ✅ **DONE** — `app/core/budget.py` + `LLMClient(budget_guard=...)`. One scan-scoped `BudgetGuard(limit=35)`; atomic `reserve()` before every provider attempt; retries consume individually; asyncio-safe under NLI `gather`; DAG injects shared guard. Tests: `tests/test_budget_guard.py` |

#### Deliverables Checklist

- [x] `backend/app/core/llm.py` — Instructor client + budget tracker
- [x] `backend/app/core/budget.py` — P2-4.2 scan-scoped `BudgetGuard` (hard 35-call cap)
- [x] Unit tests for budget guard (`tests/test_budget_guard.py`)
- [x] `backend/app/schemas/intelligence.py` — AI Pydantic schemas (`IntentQuery`, `IntentBatch`, …); API schemas remain in `schemas/scan.py` / `fscore.py` / `patch.py`
- [x] `backend/app/engines/intent_generator.py` — 30-query generator (**ONE LLM call per generation**; 10 taxonomy categories × 3; deterministic validation + unit tests in `tests/test_intent_generator.py`)
- [x] `backend/app/engines/entailment_engine.py` — NLI classifier consuming `hybrid_search` (k=5); statuses SUPPORTED / PARTIALLY_SUPPORTED / CONTRADICTED / UNKNOWN; citation validation; tests in `tests/test_entailment_engine.py`
- [x] `backend/app/engines/contradiction.py` — Cross-page entity diffing (deterministic + semantic); tests in `tests/test_contradiction.py`
- [x] `backend/app/engines/scorer.py` — F-Score calculator + Schema.org checker; tests in `tests/test_scorer.py`
- [x] `backend/app/engines/patch_prioritizer.py` — P2-3.1 prioritization only (`Priority = (Impact × Confidence) / Difficulty`, top 3)
- [x] `backend/app/schemas/patching.py` — prioritization + generation/format/projection contracts
- [x] `backend/app/engines/jsonld_generator.py` — P2-3.2 controlled evidence-backed JSON-LD
- [x] `backend/app/engines/patch_formatter.py` — P2-3.3 unified diff formatter
- [x] `backend/app/engines/projected_score.py` — P2-3.4 in-memory projection via Phase E scorer
- [x] `backend/app/github/pr_engine.py` — P2-3.5 GitHub PR automation (mocked in tests)
- [x] `backend/app/github/pr_markdown.py` — P2-3.6 deterministic PR body
- [x] `backend/app/orchestration/` — P2-4.1 DAG state machine (`state.py`, `dag.py`, `errors.py`, `result.py`)
- [x] Unit tests for DAG orchestrator (`tests/test_dag_state.py`, `test_dag_runner.py`, `test_end_to_end_orchestration.py`)
- [x] Unit tests for GitHub PR flow (`tests/test_pr_engine.py`, `test_pr_markdown.py`, `test_pr_engine_integration.py`)

##### Scorer / Schema.org — implemented notes

| Item | Status |
| :--- | :--- |
| Deterministic S_ans / S_con / S_str / S_acc + F aggregation | ✅ |
| Configurable `ScoreWeights` (centralized); canonical confirmed weights | ✅ |
| Canonical production formula (0.40/0.30/0.20/0.10) | ✅ Finalized |
| Schema.org JSON-LD offline checker (6 required types) | ✅ |
| No LLM / network / DB in scorer | ✅ |
| Patches / GitHub PR | ✅ P2-3.1–3.6 |
| DAG | ✅ P2-4.1 (`app/orchestration/`) |
| Global LLM Budget Guard | ✅ P2-4.2 (`app/core/budget.py`) |

##### Intent Generator — implemented notes

| Item | Status |
| :--- | :--- |
| Single LLM call via `LLMClient.create(..., response_model=IntentBatch, max_retries=0)` | ✅ |
| Exactly 30 generated intents / 10 categories / 3 per category | ✅ |
| Structured `IntentBatch` output | ✅ |
| Deterministic validation (count, distribution, duplicates, empty, answer-like) | ✅ |
| Test coverage (`tests/test_intent_generator.py`) | ✅ |

##### Entailment / NLI Engine — implemented notes

| Item | Status |
| :--- | :--- |
| `Intent → hybrid_search(..., k=5) → top-5 DOM chunks → structured NLI → IntentEvaluation` | ✅ |
| Outcomes: SUPPORTED / PARTIALLY_SUPPORTED / CONTRADICTED / UNKNOWN | ✅ |
| Evidence-only reasoning; UNKNOWN when insufficient; non-UNKNOWN must cite retrieved chunk IDs | ✅ |
| Fabricated chunk IDs rejected; no LLM repair call | ✅ |
| Zero retrieved chunks → deterministic UNKNOWN (no LLM call) | ✅ |
| Concurrent batch via `asyncio.gather`; shared Phase A `LLMClient` budget (default 35) | ✅ |
| Retrieval algorithm ownership remains `app.crawler.search` | ✅ |

##### Contradiction Detector — implemented notes

| Item | Status |
| :--- | :--- |
| `DOM chunks → fact extraction → normalization → deterministic compare → semantic LLM (ambiguous only) → Contradiction` | ✅ |
| HARD_CONTRADICTION / SOFT_INCONSISTENCY | ✅ |
| Structured facts: phone, email, address, price, opening_hours, coordinates | ✅ |
| Phone normalization: IN 10-digit / `91` / `+91` equivalents collapse | ✅ |
| Email entity scoping: reservations / support / billing / primary | ✅ |
| Address comparison: conservative (incomplete≠HARD; clear conflicts=HARD) | ✅ |
| Conservative false-positive policy; same-entity grouping | ✅ |
| Source provenance rebuilt from input chunks (LLM cannot fabricate metadata) | ✅ |
| Shared `LLMClient`, `max_retries=0`, `BudgetExhausted` propagates | ✅ |
| No duplicate retrieval implementation | ✅ |
| Scoring / patches / GitHub PR | ✅ |
| DAG | ✅ P2-4.1 |
| Global LLM Budget Guard | ✅ P2-4.2 |

---

> **Shiv status (implementation-verified on `main`):** all **17** assigned intelligence/orchestration tasks are complete (Phase 0: 2, Phase 2: 7, Phase 3: 6, Phase 4: 2). This is **Shiv's assigned roadmap only** — it does **not** mean FindableAI is production-ready. Remaining project work includes other owners' tasks (frontend Phase 4–5, backend deployment Phase 5, shared Phase 6), end-to-end product integration, and team decisions such as canonical F-score weights.
>
> **Shiv's highest-value next work (do not build another engine):** see **PROD-5.1**, **PROD-5.2**, **PROD-5.3**, **PROD-5.4**, **PROD-6.3** in [§10 Production Readiness Roadmap](#10-production-readiness-roadmap) — wire DAG into the scan API, canonicalize F-score, add a small intelligence regression suite, and harden prompt-injection / failure isolation.

---

### Chirag Dwivedi: Frontend & Integration Lead

**Primary Responsibility:** The entire Next.js frontend, all UI components, SSE integration, and the final demo experience.

**Skill Requirements:** TypeScript, React, Next.js, Tailwind CSS, data visualization, UI/UX design.

#### Phase 0: Foundation

| Task ID | Task | Priority | Status | Details |
| :--- | :--- | :--- | :--- | :--- |
| P3-0.1 | Next.js scaffold | Critical | [x] Done | Initialize Next.js 14+ with App Router, TypeScript, Tailwind CSS. Installed Lucide Icons, Recharts, clsx, tailwind-merge, Geist font |
| P3-0.2 | Design system | Critical | [x] Done | Dark theme with Geist typography (custom dark theme), custom CSS variables in `globals.css` (not the originally planned system) |
| P3-0.3 | shadcn/ui components | High | [x] Done | Custom components built instead of shadcn/ui by design decision |
| P3-0.4 | API client | High | [x] Done | `lib/api.ts`: Typed functions for all backend endpoints (`createScan`, `getScan`, `getIntents`, `getContradictions`, `getPatches`, `applyPatches`) |

#### Phase 4: Dashboard UI

| Task ID | Task | Priority | Status | Details |
| :--- | :--- | :--- | :--- | :--- |
| P3-4.1 | Landing Page | Critical | [x] Done | Hero section with: animated gradient background, prominent URL input field, "Test Your Site" CTA button, value proposition copy, dark mode by default |
| P3-4.2 | SSE Hook | Critical | [x] Done | `hooks/useScanStream.ts`: EventSource connection, event parsing, phase tracking, auto-cleanup on unmount, polling fallback |
| P3-4.3 | Scan Progress Component | Critical | [x] Done | `ScanProgress.tsx`: Stepper showing active and completed pipeline phases with status indicators |
| P3-4.4 | Score Gauge | Critical | [x] Done | `ScoreGauge.tsx`: Circular score gauge with animated number count-up and sub-score metrics |
| P3-4.5 | Intent Matrix | Critical | [x] Done | `IntentMatrix.tsx`: Sortable/filterable table of 30 queries across 10 categories with category tabs, search, expandable evidence citations |
| P3-4.6 | Contradiction Cards | High | [x] Done | `ContradictionCard.tsx`: Cards showing conflicting claims side-by-side with severity badges, source URLs, and copyable DOM selector paths |
| P3-4.7 | Evidence Viewer | High | [x] Done | `EvidenceViewer.tsx`: Slide-out panel showing extracted chunk text, source URL, CSS selector path with copy button |
| P3-4.8 | Patch Modal | High | [x] Done | `PatchModal.tsx`: Full-width dialog with unified diff view, projected score improvement badge, and GitHub PR trigger |
| P3-4.9 | Responsive layout | Medium | [x] Done | Dashboard responsive layout across desktop, tablet, and mobile |
| P3-4.10 | Loading & empty states | Medium | [x] Done | `Skeletons.tsx`, `EmptyState.tsx`, `ErrorState.tsx` loaders and empty state representations |

#### Phase 5: Integration & Polish

| Task ID | Task | Priority | Status | Details |
| :--- | :--- | :--- | :--- | :--- |
| P3-5.1 | End-to-end integration | P0 | ⚠️ Partial | UI is fully wired to the API contract via a normalizer that handles both mock and real backend response shapes, but full integration is pending backend wiring of the real scorer/intent/contradiction engines into the live API (see scans.py) |
| P3-5.2 | Error handling UI | P1 | [x] Done | Error boundaries and fallback states (`ErrorState.tsx`, `error.tsx`, `not-found.tsx`) |
| P3-5.3 | Micro-animations | P2 | [x] Done | Smooth gauge count-up (`useCountUp`), hover transitions, modal animations |
| P3-5.4 | Demo pre-cache fallback | P1 | [x] Done | SSE with polling fallback (`useScanStream.ts`), offline mock data fallbacks |
| P3-5.5 | README & screenshots | P1 | ❌ Not started | Production URLs/screenshots pending **PROD-8.2**. |
| P3-5.6 | Browser testing | P2 | ❌ Not started | Chrome/Firefox/Safari smoke after UI components exist. |

#### Deliverables Checklist

- [x] `frontend/` Next.js scaffold (`package.json`, Tailwind, `src/app/`)
- [x] `frontend/src/types/scan.ts` - initial TS scan types
- [x] `frontend/src/app/page.tsx` - landing page + full UI
- [x] `frontend/src/hooks/useScanStream.ts` - dedicated SSE hook with polling fallback
- [x] `frontend/src/lib/api.ts` - typed API client
- [x] `frontend/src/components/ScoreGauge.tsx`, `IntentMatrix.tsx`, `ContradictionCard.tsx`, `EvidenceViewer.tsx`, `PatchModal.tsx`, `ScanProgress.tsx`, `SummaryStats.tsx`, `StatusBadge.tsx`, `Skeletons.tsx`, `EmptyState.tsx`, `ErrorState.tsx`, `CopyButton.tsx`
- [x] `frontend/src/app/scans/[id]/page.tsx` - full scan results dashboard
- [x] Dark mode / responsive polish (Geist typography + custom dark theme)
- [x] Vitest + React Testing Library test suite (267 tests, covering lib/hooks/components)
- [ ] Live E2E against non-mock backend intelligence (pending backend wiring)

#### Frontend Integration Notes for Shiv/Himanshu

- The frontend normalizer (`src/lib/normalize.ts`) already handles both the current mock response shapes and the real `IntentEvaluation`/`Contradiction` schemas, so no frontend changes are needed once real data is wired into `scans.py`
- The frontend expects `FScoreBreakdown` (from `schemas/fscore.py`) on the score endpoint, not the scorer's internal `ScoreBreakdown` (from `schemas/scoring.py`) - an adapter is needed to convert one to the other before wiring `Scorer.score()` into the API. The mapping is not a simple rename: `s_ans` maps to `coverage`, `s_con` maps to `contradiction_penalty`, `s_str` maps to `structural_clarity`, and `s_acc` has no corresponding field in the API schema yet
- The frontend expects a `grade` field (A-F) on the score response, which does not currently exist in the scorer's output and needs to be derived somewhere
- The F-score weights are canonically finalized as 0.40 * S_ans + 0.30 * S_con + 0.20 * S_str + 0.10 * S_acc (Coverage 40%, Consistency 30%, Structure 20%, Extractability 10%)

---

## 4. Shared Responsibilities

These tasks are **jointly owned** by all three team members:

| Task | Description | All Contribute |
| :--- | :--- | :--- |
| **Pydantic schemas** (`schemas.py`) | The API contract between backend and frontend. Any schema change must be communicated. | Himanshu Raj creates, Shiv Raj Singh adds AI schemas, Chirag Dwivedi validates frontend compatibility |
| **Documentation** (`docs/`) | All 4 docs files. Each person documents their own components. | All review, Chirag Dwivedi maintains README |
| **Code reviews** | Every PR must be reviewed by at least one other team member. | Round-robin assignment |
| **Demo rehearsal** | Full end-to-end demo run-through before presentation. | All participate |
| **Bug fixes** | Cross-cutting bugs (e.g., CORS, data format mismatches). | Whoever is closest to the issue |

---

## 5. Collaboration Touchpoints

### Mandatory Sync Points

These are moments where two or more team members MUST coordinate before proceeding:

| Touchpoint | Who | When | Purpose |
| :--- | :--- | :--- | :--- |
| **TP-1: Schema Contract** | Himanshu Raj + Shiv Raj Singh | After Phase 0 | Agree on Pydantic schemas for all DB models and API responses |
| **TP-2: Chunk Output Verified** | Himanshu Raj → Shiv Raj Singh | After Phase 1 | Shiv Raj Singh cannot build retrieval/entailment without verified chunk data in DB |
| **TP-3: API Endpoints Ready** | Himanshu Raj → Chirag Dwivedi | After P1-2.1, P1-2.2 | Chirag Dwivedi needs working API endpoints (even with mock data) to build frontend |
| **TP-4: Intelligence Pipeline Done** | Shiv Raj Singh → Chirag Dwivedi | After Phase 2 | Chirag Dwivedi can finalize data-driven components (IntentMatrix, ScoreGauge) |
| **TP-5: Full Integration** | All | After Phase 4 | End-to-end test: URL input → backend scan → SSE stream → dashboard renders |
| **TP-6: Demo Rehearsal** | All | Before presentation | Full run-through with Bistro 2026. Identify and fix any issues |

### Handoff Protocol

When a dependency is ready, the producing person must:

1. **Commit and push** the code to the shared branch.
2. **Notify** the downstream person with: what's ready, how to test it, and any known limitations.
3. **Provide a test command** (e.g., `curl http://localhost:8000/api/scans/test-id` or `pytest tests/test_chunker.py`).

---

## 6. Interface Contracts

### Contract 1: Crawler Output → Intelligence Pipeline

**Producer:** Himanshu Raj  
**Consumer:** Shiv Raj Singh

```python
# Himanshu Raj produces this in the database:
class DOMChunkDB(SQLModel):
    id: UUID
    scan_id: UUID
    url: str                     # e.g., "https://bistro2026.com/menu"
    dom_path: str                # e.g., "body > main > section#menu > tr:nth-of-type(3)"
    content: str                 # e.g., "Vegan Burger — $14 — Beyond Meat patty"
    tag: str                     # e.g., "tr"
    word_count: int
    embedding: Vector(1536)      # Pre-computed embedding
    content_tsv: str             # Auto-generated tsvector

# Himanshu Raj provides this function for Shiv Raj Singh:
async def hybrid_search(query: str, scan_id: UUID, k: int = 5) -> list[DOMChunkDB]:
    """Returns top-k chunks by RRF-fused vector + BM25 search."""
    ...
```

### Contract 2: Intelligence Pipeline → API → Frontend

**Producer:** Shiv Raj Singh  
**Router:** Himanshu Raj  
**Consumer:** Chirag Dwivedi

```python
# Shiv Raj Singh produces these Pydantic models:
class ScanResult(BaseModel):
    scan_id: str
    status: str                  # "completed" | "in_progress" | "failed"
    f_score: float               # 0.0 – 100.0
    s_ans: float
    s_con: float
    s_str: float
    s_acc: float
    intents: list[IntentEvaluation]  # 30 items
    contradictions: list[Contradiction]
    patches: list[Patch]
    
# Himanshu Raj exposes these via API:
# GET /api/scans/{id}         → ScanResult
# GET /api/scans/{id}/stream  → SSE events with phase data

# Chirag Dwivedi consumes via:
# TypeScript types mirroring the Pydantic models
interface ScanResult {
    scan_id: string;
    status: "completed" | "in_progress" | "failed";
    f_score: number;
    s_ans: number;
    s_con: number;
    s_str: number;
    s_acc: number;
    intents: IntentEvaluation[];
    contradictions: Contradiction[];
    patches: Patch[];
}
```

### Contract 3: SSE Event Format

**Producer:** Himanshu Raj (endpoint) + Shiv Raj Singh (orchestrator)  
**Consumer:** Chirag Dwivedi

```typescript
// Each SSE message has this format:
interface SSEEvent {
    phase: "OBSERVE" | "PLAN" | "ACT" | "VERIFY" | "REFLECT" | "STOP";
    data: {
        message: string;          // Human-readable progress message
        progress: number;         // 0.0 – 1.0
        detail?: any;             // Phase-specific data
    };
}

// Examples:
// { phase: "OBSERVE", data: { message: "Crawling page 3 of 5...", progress: 0.15 } }
// { phase: "ACT", data: { message: "Evaluating intent 12/30...", progress: 0.55 } }
// { phase: "STOP", data: { message: "Scan complete.", progress: 1.0, detail: { scan_id: "..." } } }
```

---

## 7. Code Review Policy

| Rule | Details |
| :--- | :--- |
| **Every PR needs 1 reviewer** | The reviewer should be from a different domain (e.g., backend reviews frontend, AI reviews backend) |
| **Review turnaround** | Within same working session if possible |
| **Blocking reviews** | Only for: security issues, breaking API contracts, or data loss risks |
| **Non-blocking feedback** | Style suggestions, naming conventions, minor refactors — approve with comments |
| **Self-merge allowed** | For: documentation updates, typo fixes, config changes. Tag the team for awareness |

---

## 8. Communication Protocol

| Channel | Purpose | Frequency |
| :--- | :--- | :--- |
| **Team chat** (Slack/Discord) | Quick questions, status updates, blockers | Continuous |
| **Sync standup** | What I did, what I'm doing, what's blocking me | Once per day (or as needed) |
| **PR comments** | Code-level feedback and discussion | Per PR |
| **Touchpoint meetings** | Formal handoffs at TP-1 through TP-6 | At defined milestones |

### Blocker Escalation

If you are **blocked** by another person's incomplete work:

1. **Immediately** communicate in team chat with specifics (what you need, what's missing).
2. **Use mock data** to unblock yourself if possible (e.g., Chirag Dwivedi can use hardcoded JSON while APIs are being built).
3. **Pair program** if the blocker is a shared interface issue.

---

## 9. Dependency Chain & Parallel Tracks

### What Can Run in Parallel

```
                    ┌────────────────────────────┐
                    │     Phase 0: Foundation     │
                    │  (ALL — collaborative setup)│
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────┼──────────────┐
                    │             │              │
                    ▼             │              ▼
    ┌───────────────────┐        │  ┌───────────────────────┐
    │ Himanshu Raj:     │        │  │ Chirag Dwivedi:       │
    │ Phase 1           │        │  │ Phase 0 UI            │
    │ Crawler + Chunker │        │  │ Next.js scaffold +    │
    │                   │        │  │ Design system + Shell │
    └────────┬──────────┘        │  └───────────┬───────────┘
             │                   │              │
             │ TP-2: Chunks      │              │
             │ verified ─────────┤              │
             │                   │              │
             ▼                   ▼              │
    ┌───────────────────┐  ┌──────────────┐     │
    │ Himanshu Raj:     │  │ Shiv Raj     │     │
    │ Phase 2           │  │ Singh:       │     │
    │ API + SSE + DB    │  │ Phase 2:     │     │
    │ helpers           │  │ Intelligence │     │
    │                   │  │ Pipeline     │     │
    └────────┬──────────┘  └──────┬───────┘     │
             │                    │              │
             │ TP-3: API ready ───┤──────────────┤
             │                    │              │
             │                    │              ▼
             │                    │  ┌───────────────────────┐
             │                    │  │ Chirag Dwivedi:       │
             │                    │  │ Phase 4               │
             │                    │  │ Dashboard UI (uses    │
             │                    │  │ mock data initially)  │
             │                    │  └───────────┬───────────┘
             │                    │              │
             │ TP-4: Pipeline ────┤              │
             │ done               │              │
             │                    ▼              │
             │           ┌──────────────┐        │
             │           │ Shiv Raj     │        │
             │           │ Singh:       │        │
             │           │ Phase 3:     │        │
             │           │ Patches + PR │        │
             │           └──────┬───────┘        │
             │                  │                │
             └──────────────────┼────────────────┘
                                │
                    ┌───────────┴──────────────┐
                    │   Phase 5: Integration   │
                    │   (ALL — collaborative)  │
                    └───────────┬──────────────┘
                                │
                    ┌───────────┴──────────────┐
                    │   Phase 6: Deployment    │
                    │   (ALL — collaborative)  │
                    └──────────────────────────┘
```

### Key Insight: Chirag Dwivedi Can Start Early

Chirag Dwivedi should **not wait** for the backend to be complete. Instead:

1. **Phase 0:** Scaffold the entire Next.js app with design system, layout, and all component shells.
2. **Phase 4 (early):** Build all UI components using **hardcoded mock data** that matches the Pydantic schema contract. This means the Score Gauge, Intent Matrix, Contradiction Cards, and Patch Modal can all be built and visually polished before the backend is ready.
3. **Phase 4 (late):** Once APIs are ready (TP-3), swap mock data for live API calls. This should be a <1 hour change if the TypeScript types match the Pydantic schemas.

---

## 10. Production Readiness Roadmap

> **Audit basis (`main`, Sep 2026):** Shiv's intelligence/orchestration engines are **17/17 complete**. The system is **not** production-ready because the scan API still uses **mock F-score/patches**, the frontend is largely a **shell**, and **CI/Docker/deploy** are missing. This section is the single production roadmap. It **does not** recreate P2-0.* / P2-2.* / P2-3.* / P2-4.*.

### Current state (evidence-based)

| Area | State | Evidence |
| :--- | :--- | :--- |
| LLM + BudgetGuard + engines + DAG | ✅ Implemented | `app/core/llm.py`, `budget.py`, `engines/*`, `orchestration/*`, extensive unit tests |
| Crawler / chunker / SSRF / embeddings / hybrid_search | ✅ Largely implemented | `crawler/*`, `security.py`, `embeddings.py`, `search.py`, `demo-site/` |
| Scan API + SSE | ✅ Implemented | Real crawl→chunk→store; FindableAIDAG orchestrates real intent, entailment, contradiction, scorer and patch generation (`api/v1/scans.py`) |
| Frontend dashboard | ⚠️ Shell | `page.tsx` + types only; no ScoreGauge/IntentMatrix/PatchModal components |
| Redis/Celery workers | ❌ Not used in app | `docker-compose` has Redis; no Celery/ARQ code path (BackgroundTasks only) |
| CI/CD | ❌ Missing | No `.github/workflows/` |
| App Dockerfile | ❌ Missing | Compose = Postgres+Redis only |
| Canonical F-score | ✅ Finalized | Implementation and README unified at `0.40/0.30/0.20/0.10` |

### Priorities

- **P0** — required before calling FindableAI production-ready  
- **P1** — important hardening  
- **P2** — useful, not blocking  

### Phase 5 — Integration & Validation

| ID | Task | Owner | Pri | Acceptance criteria | Merges / replaces |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PROD-5.1** | Wire `FindableAIDAG` into scan pipeline | Himanshu + **Shiv** | P0 | `run_scan_pipeline` calls real OBSERVE→…→STOP (or `ObservationInput` after crawl). Persist real score/intents/contradictions/patches. Remove mock F-score/patch generators from the happy path. SSE still emits progress. | Unblocks P3-5.1 / playbook 5.1 |
| **PROD-5.2** | Canonical F-score specification | Shared (Shiv drafts) | P0 | One formula + weights chosen by team; `ScoreWeights`, tests, README, docs/01, API response, frontend types all match. No silent dual formulas. | Resolves known docs↔README conflict |
| **PROD-5.3** | Intelligence regression fixtures | **Shiv** | P0 | Small fixture suite (not a research bench): SUPPORTED / PARTIAL / UNKNOWN / HARD+SOFT contradiction / missing schema / malformed JSON-LD / insufficient evidence → skip patch / no false PR. Runs in CI without live providers (fakes OK). | Extends existing engine tests |
| **PROD-5.4** | API ↔ intelligence contract alignment | Himanshu + **Shiv** + Chirag | P0 | OpenAPI/`ScanResponse` exposes fields needed by UI from real `OrchestrationResult` (or mapped DTO). Frontend types updated. No second competing score schema in the live path. | TP-1 / Contract 2 |
| **PROD-5.5** | Failure isolation | Himanshu + **Shiv** | P0 | Documented + tested: budget exhaustion, LLM failure, retrieval failure, GitHub PR failure. **PR failure must not wipe already-computed scan intelligence.** Frontend shows typed errors (P3-5.2). | Extends playbook 5.3 |
| **PROD-5.6** | Frontend dashboard against live API | Chirag | P0 | ScoreGauge, IntentMatrix, contradictions, patches, ScanProgress consume **real** scan payloads; SSE phases coherent. | P3-4.* + P3-5.1 |

### Phase 6 — Security & Hardening

| ID | Task | Owner | Pri | Acceptance criteria | Merges / replaces |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PROD-6.1** | SSRF / crawler security audit | Himanshu | P0 | Re-verify redirects, DNS, private IP, timeouts, `MAX_SCAN_PAGES`. Tests remain green; document residual risks. | Extends P1-1.1 (already implemented — audit, don't rebuild) |
| **PROD-6.2** | API abuse controls + security headers | Himanshu | P1 | Basic per-IP scan rate limit; production CORS allowlist; standard security headers. | Extends P1-5.4; architecture “5 scans/hour” note |
| **PROD-6.3** | Prompt-injection / untrusted HTML regression | **Shiv** | P1 | Fixtures with adversarial page text cannot force fabricated citations or invented JSON-LD; existing anti-hallucination + evidence gates still hold. | Extends P2-2.4 / JSON-LD rules |
| **PROD-6.4** | Secrets & GitHub safety review | Himanshu + **Shiv** | P1 | No tokens in logs; PR path traversal tests still pass; env template documents required secrets. | Extends P2-3.5 + `.env.example` |

### Phase 7 — Deployment & Operations

| ID | Task | Owner | Pri | Acceptance criteria | Merges / replaces |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PROD-7.1** | Production container image | Himanshu | P0 | Multi-stage backend Dockerfile; uvicorn prod settings; builds cleanly. | **Is** P1-5.1 |
| **PROD-7.2** | CI pipeline | Himanshu (+ Chirag frontend job) | P0 | GitHub Actions: backend `pytest` + `ruff` + `mypy`; frontend `tsc`/build. | **Is** P1-5.2; playbook 0.6 |
| **PROD-7.3** | Deploy + migrations | Himanshu + Chirag | P0 | Backend + frontend deployed; Alembic on prod DB; `/health` OK; CORS allows frontend origin. Provider TBD. | **Is** P1-5.3 + playbook 6.1–6.4 |
| **PROD-7.4** | Structured scan observability | Shared | P1 | Logs/metrics per scan: `scan_id`, stage, duration, pages/chunks, LLM used/remaining, contradictions, opportunities, patches, PR status, failure reason. No secrets. | Replaces vague “add structlog/monitoring”; no new APM platform |

> **Rejected for this project (do not add):** Kubernetes, service mesh, multi-region, Celery rewrite solely for prestige (BackgroundTasks OK until proven insufficient), new vector DB, enterprise IAM, large ML eval platforms.

### Phase 8 — Release Validation Gate

| ID | Task | Owner | Pri | Acceptance criteria | Merges / replaces |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PROD-8.1** | Clean-env Bistro E2E | All | P0 | Fresh env → health → scan `demo-site` → SSE → real intelligence → ≥1 remediation opportunity → optional GitHub PR with token. | Playbook 5.1 + TP-5/TP-6 |
| **PROD-8.2** | Docs & demo checklist | Chirag (+ all) | P1 | README setup/URLs accurate; Redis/Celery wording matches reality; production roadmap links; screenshots optional. | P3-5.5 + playbook 6.6 |

### Shiv's recommended next contributions (priority order)

1. **PROD-5.1** — co-own DAG↔API wiring (highest leverage)  
2. **PROD-5.2** — draft canonical F-score decision + align code/docs  
3. **PROD-5.3** — intelligence regression fixtures  
4. **PROD-5.5** — budget/LLM/GitHub failure semantics with API  
5. **PROD-6.3** — prompt-injection fixtures  

Do **not** start a new independent intelligence engine.

---

## Summary: One-Page Task Count

| Person | Phase 0 | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Phase 6 | Total Tasks | Completed |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Himanshu Raj** | 5 | 6 | 5 | — | — | 4 | — | **20** | **16** |
| **Shiv Raj Singh** | 2 | — | 7 | 6 | 2 | — | — | **17** | **17** (P2-0.1–0.2, P2-2.1–2.7, P2-3.1–3.6, P2-4.1–4.2) |
| **Chirag Dwivedi** | 4 | — | — | — | 10 | 6 | — | **20** | **4** |
| **Shared** | — | — | — | — | — | — | 6 | **6** | **0** |
| **Total** | **11** | **6** | **12** | **6** | **12** | **10** | **6** | **63** | **37** |

> **Count note:** Shiv Phase 2 = seven tasks (`P2-2.1`–`P2-2.7`). Shiv Phase 4 = two tasks (`P2-4.1`, `P2-4.2`). The prior summary that showed Phase 2 = 9 and Phase 4 = — double-counted the DAG/budget work under Phase 2 and understated completion (9/17).
>
> **Production readiness:** Shiv's **17/17** completed tasks mean the assigned AI/ML + patch + orchestration roadmap is done in-repo. They do **not** imply the full product is production-ready. See **[§10 Production Readiness Roadmap](#10-production-readiness-roadmap)** (`PROD-5.*`–`PROD-8.*`). Critical gap today: scan API still returns **mock** F-score/patches until **PROD-5.1**.

---

> **End of Document — Team Task Allocation v1.0**
