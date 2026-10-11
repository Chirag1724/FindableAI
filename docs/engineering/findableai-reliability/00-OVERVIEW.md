# FindableAI Reliability Documentation Set — Overview

**Status:** Documentation-only package (additive)  
**Checked-out reference:** `main` @ `1aba352` (verify with `git rev-parse HEAD`)  
**Working-tree expectation at authoring:** clean (no application changes)  
**Scope:** Current system (code-verified) + proposed Durable Scan Execution Engine (explicitly proposed)

This directory is a **self-contained** engineering package. It does **not** replace or modify existing files under `docs/engineering/` or the root `README.md`. Those remain the historical project docs; where they disagree with source, this package records the discrepancy and treats **checked-out source** as authoritative for *current* behavior.

---

## Objectives

1. Document the **code-verified** architecture, workflows, and limitations.
2. Record problems that matter for reliability, demo quality, and submission readiness (~8 days).
3. Specify a **proposed** Durable Scan Execution Engine that extends PostgreSQL jobs, BudgetGuard, evidence, and remediation—not a greenfield rewrite.
4. Provide a phased implementation, test, and operations plan with clear acceptance criteria.
5. Separate **Verified / Inferred / Unverified / Proposed** claims.

---

## Document index

| Doc | Purpose |
| :--- | :--- |
| [00-OVERVIEW.md](./00-OVERVIEW.md) | This index and executive summary |
| [01-CURRENT-STATE-AUDIT.md](./01-CURRENT-STATE-AUDIT.md) | Verified current architecture, workflow, gaps |
| [02-PROBLEM-ANALYSIS.md](./02-PROBLEM-ANALYSIS.md) | Problems with evidence, impact, proposed fixes |
| [03-CURRENT-ARCHITECTURE.md](./03-CURRENT-ARCHITECTURE.md) | Current components, stack, deployment topology |
| [04-PROPOSED-ARCHITECTURE.md](./04-PROPOSED-ARCHITECTURE.md) | Target reliability architecture (proposed) |
| [05-SYSTEM-DESIGN.md](./05-SYSTEM-DESIGN.md) | Detailed design: jobs, budgets, cache, progress, safety |
| [06-END-TO-END-WORKFLOWS.md](./06-END-TO-END-WORKFLOWS.md) | Current vs proposed workflows + Mermaid |
| [07-IMPLEMENTATION-PLAN.md](./07-IMPLEMENTATION-PLAN.md) | Three-stage plan, files, effort, acceptance |
| [08-TESTING-AND-ACCEPTANCE.md](./08-TESTING-AND-ACCEPTANCE.md) | Test strategy and commands (not results) |
| [09-DEPLOYMENT-AND-OPERATIONS.md](./09-DEPLOYMENT-AND-OPERATIONS.md) | Ops topology, env vars (names only), runbooks |
| [10-DECISIONS-AND-OPEN-QUESTIONS.md](./10-DECISIONS-AND-OPEN-QUESTIONS.md) | ADRs, rejected alternatives, open questions |

### Related existing docs (read-only references)

- [LIMITATIONS_AND_READINESS.md](../LIMITATIONS_AND_READINESS.md)
- [DURABLE_JOBS.md](../DURABLE_JOBS.md)
- [SYSTEM_FLOW.md](../SYSTEM_FLOW.md)
- [DEPLOYMENT.md](../DEPLOYMENT.md)
- [TESTING.md](../TESTING.md)
- [ENVIRONMENT.md](../ENVIRONMENT.md)
- [FRONTEND_INTEGRITY_CONTRACT.md](../FRONTEND_INTEGRITY_CONTRACT.md)

---

## Executive summary

### What FindableAI is (current)

A FastAPI + Next.js Machine Discoverability Optimization product:

1. Accept a website URL (`POST /api/v1/scans`).
2. Persist a scan and durable `scan_jobs` row when PostgreSQL is available.
3. Execute crawl → DOM chunk → embed → intent/evidence/LLM evaluation (`FindableAIDAG`) → score/patches → integrity contract.
4. Optionally open a GitHub remediation PR and run a **narrow** post-PR verification check.

### What is already strong (Verified)

- PostgreSQL-backed job queue with leases, fencing tokens, retries (`backend/app/jobs/`).
- Fail-closed remediation eligibility and patch validation before GitHub mutation.
- Hybrid retrieval with dense + lexical + RRF when the index is available (`crawler/search.py`, `orchestration/dag.py`).
- Evidence uniqueness and provenance (`0003_evidence_provenance`).
- Per-scan LLM **call** budget via `BudgetGuard` (reserve-before-call).
- Compose topology with separate `backend` and `worker` services (`docker-compose.yml`).

### What blocks reliability / demo quality (Verified or high-confidence)

| Issue | Impact |
| :--- | :--- |
| Progress/`SCANS_DB`/`EVENT_*` are process-local | Live SSE breaks when API ≠ worker |
| Job retries re-run the full pipeline | Cost/time; no stage resume |
| `update_llm_checkpoint` has no mid-pipeline callers | Mid-crash budget under-accounting |
| `LLM_BUDGET_CAP_USD` is observational, not enforced as spend | Monetary ceiling not hard |
| Redis is configured but unused by app code | Ops confusion only |
| Post-PR verify is keyword/file heuristics, not a full re-scan | Overclaim risk |
| PG concurrency tests are opt-in (`FINDABLE_PG_INTEGRATION=1`) | Ordinary CI uses SQLite |
| Existing docs partially contradict code (RRF / verify / BackgroundTasks) | See [01](./01-CURRENT-STATE-AUDIT.md) |

### Proposed direction (Proposed — not implemented)

A **Durable Scan Execution Engine** layered on existing Postgres jobs:

1. **Stage 1:** Checkpoints + safe resume + durable progress fields + budget durability.  
2. **Stage 2:** Versioned content/retrieval/eval caches (Postgres or local store first—not Redis by default).  
3. **Stage 3:** Ordered progress events + SSE replay + metrics.

Priority for the ~8-day submission window: Stage 1 correctness and demo-visible progress, not a broker rewrite.

### Classification legend (used throughout)

| Label | Meaning |
| :--- | :--- |
| **Verified** | Confirmed in checked-out source (or tests when named and known to exist) |
| **Inferred** | Reasonable interpretation not fully demonstrated |
| **Unverified** | Needs runtime, disposable PG, or credentials |
| **Proposed** | Future design; not present as behavior today |

**Tests:** This documentation package was authored from static inspection. No pytest/ruff/mypy run is claimed as part of this documentation task.

---

## Decision for readers

1. Review this package for accuracy.  
2. Authorize Stage 1 implementation separately.  
3. Do **not** treat proposed diagrams as current production behavior.  
4. Do **not** edit existing engineering docs until a dedicated reconciliation PR is approved.