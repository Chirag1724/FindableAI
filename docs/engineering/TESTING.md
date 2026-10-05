# Testing Strategy & Verification Guide

This document outlines the testing philosophy, test suite organization, mock fixture patterns, and execution commands across the FindableAI codebase.

---

## Test Suite Summary

FindableAI maintains a comprehensive test suite across the backend and frontend.

| Test Suite | Framework | Total Tests | Pass Count | Failure Count | Execution Time |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Backend Test Suite** | pytest / pytest-asyncio | **319** | **319** | **0** | ~236s |
| **Backend Type Checker** | Mypy (strict) | **48 files** | **48 files** | **0** | ~10s |
| **Frontend Test Suite** | Vitest / Testing Library | **273** | **273** | **0** | ~170s |
| **Total Test Surface** | pytest + Vitest | **592** | **592** | **0** | ~416s |

---

## Testing Philosophy & Core Patterns

1. **Zero External Network Dependencies in Unit Tests:**
   - Tests never invoke live LLM endpoints (Groq, OpenAI, Anthropic), public websites, or live GitHub APIs.
   - LLM interactions are isolated via deterministic fixtures, structured Pydantic responses, or mock clients.

2. **In-Memory GitHub Client Simulation (`FakeGitHubClient`):**
   - Implemented in [backend/tests/test_pr_engine.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/tests/test_pr_engine.py#L30-L115).
   - Simulates repository creation, branches, file content trees, pull requests, permissions (`push: True/False`), and forking behavior entirely in memory.
   - Asserts exact GitHub API calls (e.g. `create_pull:acme/repo:branch->main`) and verifies no token leaks occur in log captures.

3. **Deterministic Scorer Tolerance:**
   - Float assertions in scoring engines utilize floating-point tolerances (`abs(delta - expected) < 1e-9`) to prevent precision mismatches across Python runtime environments.

4. **Security & SSRF Boundaries:**
   - [backend/tests/test_security.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/tests/test_security.py) executes automated attack vectors covering loopback IPs (`127.0.0.1`), private subnets (`10.0.0.0/8`, `192.168.0.0/16`), AWS cloud metadata endpoints (`169.254.169.254`), and non-HTTP URL schemes (`file://`, `ftp://`).

5. **Motion Isolation in Frontend Tests:**
   - [frontend/src/lib/motion.ts](file:///c:/Users/LENOVO/Desktop/FindableAI/frontend/src/lib/motion.ts) detects `process.env.NODE_ENV === "test"` and automatically disables heavy CSS animations to ensure fast, deterministic Vitest renders.

---

## Backend Test Structure ([backend/tests/](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/tests/))

| Test File | Category | Focus Areas |
| :--- | :--- | :--- |
| `test_security.py` | Security | SSRF validation, private IP blocking, cloud metadata protections, environment bypass rules. |
| `test_budget_guard.py` | Cost & Guardrails | Monetary dollar cap enforcement, max call limits, sliding window tracking. |
| `test_production_readiness.py` | API Security | Sliding-window rate limiting, API key enforcement (`X-API-Key`), security headers, health check DB ping. |
| `test_crawler.py` | Crawler | Async HTML fetching, domain normalization, redirect limits. |
| `test_chunker.py` | Extraction | Semantic DOM chunking, heading hierarchy tracking, word count validation. |
| `test_intent_generator.py` | Intelligence | Persona query generation, category distribution, Pydantic validation. |
| `test_entailment_engine.py` | NLI | Claim verification, evidence reference extraction, confidence thresholding. |
| `test_contradiction.py` | NLI | Cross-page conflict detection, severity weighting (hard vs soft), duplicate deduplication. |
| `test_scorer.py` | Scoring | Canonical 40/30/20/10 weight validation, letter grade derivation, bounds checking. |
| `test_projected_score.py` | Scoring | Per-opportunity non-cumulative projected score calculations. |
| `test_jsonld_generator.py` | Remediation | Evidence-backed Schema.org JSON-LD generation without invented facts. |
| `test_patch_prioritizer.py` | Remediation | Top-3 candidate opportunity ranking, priority formula `(impact * confidence) / difficulty`. |
| `test_patch_formatter.py` | Remediation | Unified diff formatting, DOM anchor insertion points (`before_head`, `before_body`). |
| `test_dag_state.py` | Orchestration | `OrchestrationState` transitions, immutable artifact accumulation. |
| `test_dag_runner.py` | Orchestration | Full `FindableAIDAG` execution across PLAN, OBSERVE, ORIENT, DECIDE, ACT, REFLECT, STOP. |
| `test_end_to_end_orchestration.py` | Orchestration | Comprehensive pipeline run against static HTML corpus. |
| `test_real_patch_pipeline.py` | Remediation | Fact extraction from HTML chunks and end-to-end patch generation. |
| `test_pr_engine.py` | GitHub Integration | Direct push, fork fallback, forking disabled errors, framework route matching, path traversal rejection. |
| `test_pr_engine_integration.py` | GitHub Integration | End-to-end flow from crawl extraction to pull request generation. |
| `test_pr_markdown.py` | Reporting | Deterministic PR report Markdown generation, table escaping, secret redaction. |
| `test_scans_api.py` | API Endpoints | REST endpoints, SSE event streams, 404 handling, parameter validations. |

---

## Frontend Test Structure ([frontend/src/](file:///c:/Users/LENOVO/Desktop/FindableAI/frontend/src/))

| Test File | Category | Focus Areas |
| :--- | :--- | :--- |
| `src/lib/api.test.ts` | API Client | Fetch wrapper, abort signals, error parsing (`status`, `detail`). |
| `src/lib/phases.test.ts` | Utilities | Scan lifecycle phase mappings and state transitions. |
| `src/lib/format.test.ts` | Utilities | Number formatting, grade color classes, timestamp displays. |
| `src/lib/diff.test.ts` | Utilities | Unified diff parsing into additions and deletions. |
| `src/hooks/useScanStream.test.ts` | Hooks | Server-Sent Events (SSE) connection, auto-reconnect, stream completion. |
| `src/hooks/useScanData.test.ts` | Hooks | Parallel resource fetching (`intents`, `contradictions`, `patches`). |
| `src/hooks/useCountUp.test.ts` | Hooks | Smooth score gauge animated counter hooks. |
| `src/components/ScoreGauge.test.tsx` | Components | Radial SVG gauge rendering, sub-score bars, grade badge colors. |
| `src/components/ContradictionCard.test.tsx` | Components | Contradiction conflict comparison, severity badges, DOM path copy. |
| `src/components/EvidenceViewer.test.tsx` | Components | Evidence modal, dialog accessibility (`role="dialog"`), keyboard focus trap. |
| `src/components/PatchModal.test.tsx` | Components | Unified diff view, DOM snippet inspection, PR trigger submission. |
| `src/components/StatusBadge.test.tsx` | Components | Entailment status pills (Supported, Partially Supported, Unknown, Contradicted). |
| `src/components/CopyButton.test.tsx` | Components | Clipboard API integration and visual copied feedback. |
| `src/app/page.test.tsx` | Pages | Marketing landing page, telemetry preview widgets, FAQ accordion. |
| `src/app/audit/AuditPage.test.tsx` | Pages | Real-time audit dashboard, URL input form, persona toggles, SSE progress bars. |

---

## Test Execution Commands

### Run All Backend Tests
```bash
cd backend
pytest tests -v
```

### Run Specific Backend Test Module
```bash
cd backend
pytest tests/test_pr_engine.py -v
```

### Run Backend Tests with Coverage Report
```bash
cd backend
pytest --cov=app --cov-report=term-missing tests
```

### Run All Frontend Tests
```bash
cd frontend
npm run test
```

### Run Frontend Tests in Watch Mode
```bash
cd frontend
npx vitest
```
