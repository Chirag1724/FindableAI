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

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P1-5.1 | Backend Dockerfile | Medium | Multi-stage build, production Uvicorn config |
| P1-5.2 | CI/CD pipeline | Medium | GitHub Actions: pytest on push, Docker build on merge to main |
| P1-5.3 | Production deployment | Medium | Deploy to Railway/Render. Setup Supabase for production DB |
| P1-5.4 | CORS & security headers | Medium | Configure allowed origins for production frontend domain |

#### Deliverables Checklist

- [x] `backend/app/core/security.py` — SSRF validator with unit tests
- [x] `backend/app/crawler/crawler.py` — Async BFS crawler
- [x] `backend/app/crawler/dom_chunker.py` — DOM chunker with CSS path generator
- [x] `backend/app/core/embeddings.py` — Embedding pipeline
- [x] `backend/app/db.py` — Database engine and session management
- [x] `backend/app/models/database.py` — All SQLAlchemy models
- [x] `backend/app/api/scans.py` — All scan endpoints including SSE
- [x] `docker-compose.yml` — Working Docker setup
- [x] `backend/alembic/` — Database migrations
- [x] `demo-site/` — Bistro 2026 with intentional flaws
- [x] Unit tests for: SSRF validator, DOM chunker, CSS path generator, embeddings pipeline, scans API

---

### Shiv Raj Singh: AI/ML & Intelligence Pipeline Lead

**Primary Responsibility:** Everything from raw chunks to intelligence outputs — intent generation, entailment verification, contradiction detection, scoring, patch generation, and GitHub PR creation.

**Skill Requirements:** Python, LLM prompt engineering, Pydantic, NLI concepts, Schema.org knowledge.

#### Phase 0: Foundation

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P2-0.1 | LLM Client Setup | Critical | ✅ **DONE** — `backend/app/core/llm.py`: Instructor + LiteLLM client, `BudgetExhausted`, default max 35 calls (`MAX_LLM_CALLS_PER_SCAN`) |
| P2-0.2 | Pydantic Schemas | Critical | ✅ **DONE** — AI contracts in `backend/app/schemas/intelligence.py` (`IntentQuery`, `IntentBatch`, `EntailmentStatus`, `IntentEvaluation`, `Contradiction`, `Patch`, `ScanResult`); coexist with API schemas |

#### Phase 2: Intelligence Pipeline

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P2-2.1 | Intent Generator | Critical | ✅ **DONE** — `intent_generator.py`: **ONE LLM call** → exactly 30 `IntentQuery` across 10 categories (3 each), structured `IntentBatch`, deterministic validation (duplicates, distribution, answer-like rejection). Architecture: `business_context → IntentGenerator → LLMClient → IntentBatch → validation` |
| P2-2.2 | Hybrid Retrieval | Critical | ✅ **DONE (consumer)** — `entailment_engine.py` calls Contract-1 `hybrid_search(query, scan_id, k=5)` from `app.crawler.search`. Does **not** re-implement vector/BM25/RRF (still owned by crawler/search). |
| P2-2.3 | NLI Entailment Engine | Critical | ✅ **DONE** — `backend/app/engines/entailment_engine.py`. Flow: `Intent → hybrid_search(..., k=5) → top-5 chunks → LLMClient NLI → IntentEvaluation`. Concurrent `evaluate_intents` via `asyncio.gather`; shared `LLMClient` budget preserved. |
| P2-2.4 | Anti-Hallucination Guardrails | Critical | ✅ **DONE** — evidence-only `NLI_SYSTEM_PROMPT`; zero-chunk → deterministic UNKNOWN (0 LLM calls); non-UNKNOWN must cite retrieved IDs; fabricated IDs rejected; no LLM repair/retry (`max_retries=0`) |
| P2-2.5 | Contradiction Detector | High | ✅ **DONE** — `backend/app/engines/contradiction.py`. Hybrid: deterministic structured facts first; LLM only for semantic ambiguity. Severities: HARD_CONTRADICTION / SOFT_INCONSISTENCY. Flow: chunks → extract → normalize → compare → optional semantic LLM → deduped `Contradiction`. |
| P2-2.6 | F-Score Calculator | Critical | ✅ **DONE** — `backend/app/engines/scorer.py`. Deterministic `S_ans` / `S_con` / `S_str` / `S_acc` + configurable `ScoreWeights` aggregation. **Production weights remain configuration-driven pending team confirmation** (docs Option A vs README Option B). Provisional defaults mirror docs `0.40/0.30/0.20/0.10`. |
| P2-2.7 | Schema.org Checker | High | ✅ **DONE** — JSON-LD parse via BeautifulSoup + `json.loads`; checks LocalBusiness (subtypes), PostalAddress, OpeningHoursSpecification, GeoCoordinates, Menu/hasMenu, FAQPage; `@graph` / arrays / `@type` arrays; malformed blocks reported safely. |

#### Phase 3: Patch Engine & GitHub

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P2-3.1 | Patch Prioritizer | High | Rank gaps by `Priority = (Impact * Confidence) / Difficulty`. Select top 3 for remediation |
| P2-3.2 | JSON-LD Generator | Critical | `patch_generator.py`: Generate valid Schema.org JSON-LD for `FAQPage`, `LocalBusiness`, `OpeningHoursSpecification`. Validate against Schema.org spec |
| P2-3.3 | Patch Formatter | High | Format generated code as unified diffs applicable to target HTML files |
| P2-3.4 | Projected Score Calculator | High | Re-run F-Score calculation assuming patches are applied. Output delta (e.g., 42% → 95%) |
| P2-3.5 | GitHub PR Engine | High | `pr_engine.py`: Fork repo via PyGithub, create branch, commit patches, create PR with detailed markdown body |
| P2-3.6 | PR Markdown Generator | Medium | Generate PR body with: score before/after, per-file changes, intent evaluation summary, links to evidence |

#### Phase 2 (Parallel): DAG Orchestrator

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P2-4.1 | DAG State Machine | Critical | Implement OBSERVE → PLAN → ACT → VERIFY → REFLECT → STOP. Each phase emits SSE events. Budget guard enforces 35-call max |
| P2-4.2 | Budget Guard | Critical | Decorator/middleware that wraps every LLM call, increments counter, raises on exceed |

#### Deliverables Checklist

- [x] `backend/app/core/llm.py` — Instructor client + budget tracker
- [x] `backend/app/schemas/intelligence.py` — AI Pydantic schemas (`IntentQuery`, `IntentBatch`, …); API schemas remain in `schemas/scan.py` / `fscore.py` / `patch.py`
- [x] `backend/app/engines/intent_generator.py` — 30-query generator (**ONE LLM call per generation**; 10 taxonomy categories × 3; deterministic validation + unit tests in `tests/test_intent_generator.py`)
- [x] `backend/app/engines/entailment_engine.py` — NLI classifier consuming `hybrid_search` (k=5); statuses SUPPORTED / PARTIALLY_SUPPORTED / CONTRADICTED / UNKNOWN; citation validation; tests in `tests/test_entailment_engine.py`
- [x] `backend/app/engines/contradiction.py` — Cross-page entity diffing (deterministic + semantic); tests in `tests/test_contradiction.py`
- [x] `backend/app/engines/scorer.py` — F-Score calculator + Schema.org checker; tests in `tests/test_scorer.py`
- [ ] `backend/app/engines/patch_generator.py` — JSON-LD generator + formatter *(not started)*
- [ ] `backend/app/github/pr_engine.py` — Full PR automation *(not started)*
- [x] NLI system prompt (version-controlled in `entailment_engine.py` as `NLI_SYSTEM_PROMPT`)
- [x] Unit tests for F-Score / Schema.org (`tests/test_scorer.py`); contradiction tests in `tests/test_contradiction.py`
- [ ] Unit tests for: JSON-LD patch validation *(not started)*

##### Scorer / Schema.org — implemented notes

| Item | Status |
| :--- | :--- |
| Deterministic S_ans / S_con / S_str / S_acc + F aggregation | ✅ |
| Configurable `ScoreWeights` (centralized); provisional docs weights | ✅ |
| Canonical production formula **not** silently finalized (docs vs README) | ⚠️ team decision |
| Schema.org JSON-LD offline checker (6 required types) | ✅ |
| No LLM / network / DB in scorer | ✅ |
| Patches / GitHub PR / DAG | ❌ intentionally unimplemented |

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
| Scoring / patches / GitHub PR / DAG | ❌ intentionally unimplemented |

---

### Chirag Dwivedi: Frontend & Integration Lead

**Primary Responsibility:** The entire Next.js frontend, all UI components, SSE integration, and the final demo experience.

**Skill Requirements:** TypeScript, React, Next.js, Tailwind CSS, data visualization, UI/UX design.

#### Phase 0: Foundation

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P3-0.1 | Next.js scaffold | Critical | Initialize Next.js 14+ with App Router, TypeScript, Tailwind CSS. Install shadcn/ui, next-themes, Recharts, diff2html, Lucide Icons |
| P3-0.2 | Design system | Critical | Setup `globals.css` with CSS variables for dark/light mode. Define color palette (emerald for SUPPORTED, red for CONTRADICTED, amber for UNKNOWN, violet for scores). Configure `tailwind.config.ts` |
| P3-0.3 | shadcn/ui components | High | Initialize and install required components: Card, Badge, Table, Dialog, Sheet, Tabs, Progress, Tooltip, Button, Input |
| P3-0.4 | API client | High | `lib/api.ts`: Typed functions for all backend endpoints (`createScan`, `getScan`, `getIntents`, `getContradictions`, `getPatches`, `applyPatches`) |

#### Phase 4: Dashboard UI

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P3-4.1 | Landing Page | Critical | Hero section with: animated gradient background, prominent URL input field, "Scan Now" CTA button, value proposition copy, dark mode by default |
| P3-4.2 | SSE Hook | Critical | `hooks/useScanStream.ts`: EventSource connection, event parsing, phase tracking, auto-cleanup on unmount |
| P3-4.3 | Scan Progress Component | Critical | `ScanProgress.tsx`: Horizontal stepper showing 6 phases (OBSERVE → PLAN → ACT → VERIFY → REFLECT → STOP). Active phase pulses. Completed phases show checkmark |
| P3-4.4 | Score Gauge | Critical | `ScoreGauge.tsx`: Radial bar chart (Recharts) with 4 concentric arcs for sub-scores + large center number for F-Score. Smooth counter animation from 0 to final score |
| P3-4.5 | Intent Matrix | Critical | `IntentMatrix.tsx`: Sortable/filterable table of 30 queries. Columns: Category, Query, Status (badge), Confidence. Click row to expand: reasoning, evidence chunks, DOM paths |
| P3-4.6 | Contradiction Cards | High | `ContradictionCard.tsx`: Card per contradiction showing entity name, conflicting values side-by-side, source URLs (clickable), DOM paths (copyable), severity badge |
| P3-4.7 | Evidence Viewer | High | `EvidenceViewer.tsx`: Slide-out Sheet panel. Shows: chunk content (highlighted), source URL (linked), CSS selector path (with copy button), extractability score |
| P3-4.8 | Patch Modal | High | `PatchModal.tsx`: Full-width Dialog. Content: (a) unified diff rendered with diff2html, (b) projected score improvement badge, (c) "Create Pull Request" button with loading state |
| P3-4.9 | Responsive layout | Medium | Dashboard grid: score gauge (left), intent matrix (center/right). Tablet breakpoint at 768px. Cards stack vertically on smaller screens |
| P3-4.10 | Loading & empty states | Medium | Skeleton loaders for all data-dependent components. Empty state illustrations for zero results |

#### Phase 5: Integration & Polish

| Task ID | Task | Priority | Details |
| :--- | :--- | :--- | :--- |
| P3-5.1 | End-to-end integration | Critical | Connect all frontend components to live backend API. Test full flow: URL input → scan → results |
| P3-5.2 | Error handling UI | High | User-friendly error states for: invalid URL, scan failed, API timeout, GitHub auth required |
| P3-5.3 | Micro-animations | Medium | Fade-in for cards, counter animation for score, pulse for active scan phase, slide-in for Evidence Viewer |
| P3-5.4 | Demo pre-cache fallback | Medium | If SSE stream fails, fall back to `GET /api/scans/{id}` polling with cached results |
| P3-5.5 | README & screenshots | Medium | Take screenshots of: landing page, scan progress, score gauge, intent matrix, patch modal. Update README.md |
| P3-5.6 | Browser testing | Medium | Test on Chrome, Firefox, Safari. Fix any rendering inconsistencies |

#### Deliverables Checklist

- [ ] `frontend/src/app/page.tsx` — Landing page with URL input
- [ ] `frontend/src/app/scans/[id]/page.tsx` — Scan dashboard
- [ ] `frontend/src/app/layout.tsx` — Root layout with ThemeProvider
- [ ] `frontend/src/app/globals.css` — Design system CSS variables
- [ ] `frontend/src/components/ScoreGauge.tsx` — Radial score indicator
- [ ] `frontend/src/components/IntentMatrix.tsx` — 30-query grid
- [ ] `frontend/src/components/ContradictionCard.tsx` — Inconsistency viewer
- [ ] `frontend/src/components/EvidenceViewer.tsx` — DOM path inspector
- [ ] `frontend/src/components/PatchModal.tsx` — Diff viewer + PR button
- [ ] `frontend/src/components/ScanProgress.tsx` — SSE progress stepper
- [ ] `frontend/src/hooks/useScanStream.ts` — SSE EventSource hook
- [ ] `frontend/src/lib/api.ts` — Typed API client
- [ ] Dark mode working correctly
- [ ] All components responsive at 768px+

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

## Summary: One-Page Task Count

| Person | Phase 0 | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Phase 6 | Total Tasks | Completed |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Himanshu Raj** | 5 | 6 | 5 | — | — | 4 | — | **20** | **16** |
| **Shiv Raj Singh** | 2 | — | 9 | 6 | — | — | — | **17** | **9** (… + P2-2.6, P2-2.7) |
| **Chirag Dwivedi** | 4 | — | — | — | 10 | 6 | — | **20** | **4** |
| **Shared** | — | — | — | — | — | — | 6 | **6** | **0** |
| **Total** | **11** | **6** | **14** | **6** | **10** | **10** | **6** | **63** | **29** |

---

> **End of Document — Team Task Allocation v1.0**
