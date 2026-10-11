# 02 — Problem Analysis

Each problem includes evidence, impact, proposed fix (Proposed), and acceptance hooks. Severity: **P0** demo/split-deploy breakers → **P3** hygiene.

---

## F-01 — Process-local progress breaks split API/worker

| Field | Detail |
| :--- | :--- |
| **Severity** | P0 |
| **Classification** | Verified implemented (insufficient for multi-process) |
| **Actual behavior** | Progress events and in-memory scan mirrors (`SCANS_DB` / `EVENT_LOGS` / `EVENT_QUEUES`) live in the process that wrote them. Worker writes do not populate API memory. |
| **Evidence** | Scan progress / event modules under `backend/app/api/`; worker in `backend/app/jobs/worker.py`; Compose separates `backend` and `worker`. |
| **Impact** | SSE clients attached to API see no live events; demos look “stuck” despite job progress in DB. |
| **Reproduction** | Run Compose with separate worker; submit scan; watch SSE while worker runs. Expect empty/stale events; DB job/scan status may still advance. |
| **Proposed fix** | Persist progress snapshot + ordered events in Postgres; SSE reads/replays from DB (Stage 3; minimal Stage 1: durable status fields the UI already polls). |
| **Affected** | API routes, worker progress emitters, frontend SSE/poll hooks |
| **Tests** | Disconnect/reconnect SSE; API≠worker process test |
| **Confidence** | High (architecture); exact frontend fallback **Unverified** without UI run |

---

## F-02 — Retries re-run the entire pipeline

| Field | Detail |
| :--- | :--- |
| **Severity** | P1 |
| **Classification** | Verified |
| **Actual behavior** | Job retry re-claims and re-executes `FindableAIDAG` (or equivalent entry) without stage-level resume. |
| **Evidence** | `jobs/queue.py` retry/lease paths; DAG entry from worker; no durable stage cursor consumed on start. |
| **Impact** | Extra crawl/embed/LLM cost and latency after transient failures near the end of a run. |
| **Proposed fix** | Stage/batch checkpoints; resume rules that skip completed durable stages (Stage 1). |
| **Risks** | Incorrect resume could skip needed recomputation; caches must be versioned (Stage 2). |
| **Confidence** | High |

---

## F-03 — Mid-run LLM usage checkpoints unused

| Field | Detail |
| :--- | :--- |
| **Severity** | P1 |
| **Classification** | Verified (function exists; callers absent) |
| **Actual behavior** | `update_llm_checkpoint` in `backend/app/jobs/queue.py` is not called from mid-pipeline code paths. Crash/retry may under-account prior LLM usage. |
| **Evidence** | Definition at ~line 507 in `queue.py`; repository search shows no other call sites. |
| **Impact** | BudgetGuard state may reset or undercount across worker death; cost/abuse controls weaken. |
| **Proposed fix** | Call checkpoint after each reserved/completed provider batch; restore on job start (Stage 1). |
| **Confidence** | High for absence of callers; restore semantics **Inferred** until tested |

---

## F-04 — Monetary budget not hard-enforced

| Field | Detail |
| :--- | :--- |
| **Severity** | P2 |
| **Classification** | Verified |
| **Actual behavior** | `BudgetGuard` enforces **call** reservations (order ~100). `LLM_BUDGET_CAP_USD` (default in `core/config.py`) is tracked/observable but not used as a hard spend stop. |
| **Evidence** | `backend/app/core/llm.py` (`budget_cap_usd`, budget state); `LLM_BUDGET_CAP_USD` in config. |
| **Impact** | Expensive models/retries can exceed intended USD ceilings. |
| **Proposed fix** | Atomic reserve of estimated USD + calls; reject when either ceiling exceeded (Stage 1). |
| **Confidence** | High |

---

## F-05 — Missing versioned crawl / retrieval / eval caches

| Field | Detail |
| :--- | :--- |
| **Severity** | P2 |
| **Classification** | Missing |
| **Actual behavior** | Each run recomputes crawl chunks, retrieval, and evaluations; no versioned fingerprint cache. |
| **Impact** | Retries and repeated URLs burn provider/crawl quota. |
| **Proposed fix** | Stage 2 caches with content/prompt/schema/model/retrieval version keys; no Redis required initially. |
| **Constraint** | Never reuse cache if evidence, content, prompt, schema, model, or retrieval versions differ. |
| **Confidence** | High (absence) |

---

## F-06 — Redis configured but unused

| Field | Detail |
| :--- | :--- |
| **Severity** | P3 |
| **Classification** | Verified (config vs app) |
| **Actual behavior** | Compose/env may mention Redis; application scan path does not depend on Redis. |
| **Impact** | Operator confusion; false reliance in ops docs. |
| **Proposed fix** | Document non-use; only introduce Redis if Stage 2 measurements justify it (**Proposed** optional). |
| **Confidence** | High for app non-use; exact compose service set **Needs validation** against local `docker-compose.yml` |

---

## F-07 — Post-PR verification is heuristic, not a full re-scan

| Field | Detail |
| :--- | :--- |
| **Severity** | P1 (product/docs) |
| **Classification** | Verified |
| **Actual behavior** | `evaluate_verification_outcome` in `remediation_lifecycle.py` (~130–172) uses operational errors, deterministic validation, and keyword presence in patched content. |
| **Impact** | Marketing or UI that says “re-scan verified” overclaims. Issues can be marked fixed without proving live site behavior. |
| **Proposed fix** | Keep heuristic for Stage 1; label UI accurately; optional future full re-scan job (**Proposed**, out of critical path). |
| **Confidence** | High |

---

## F-08 — PostgreSQL concurrency tests are opt-in

| Field | Detail |
| :--- | :--- |
| **Severity** | P1 (ops/quality) |
| **Classification** | Verified |
| **Actual behavior** | `tests/test_scan_jobs_pg.py` skips unless `FINDABLE_PG_INTEGRATION=1`. Ordinary CI uses lighter DB backends. |
| **Impact** | Lease/fencing regressions may ship unnoticed. |
| **Proposed fix** | Document mandatory pre-release PG run; optionally add gated CI job later (**Proposed** for CI change—out of this docs task). |
| **Confidence** | High |

---

## F-09 — Existing documentation contradicts code

| Field | Detail |
| :--- | :--- |
| **Severity** | P1 |
| **Classification** | Verified discrepancy |
| **Examples** | RRF/hybrid marked missing while implemented; verification described as broader than heuristics; durable jobs vs BackgroundTasks narrative drift. |
| **Impact** | Engineers and judges misread readiness. |
| **Proposed fix** | Future reconciliation PR against existing docs; **this package does not edit those files**. |
| **Sources** | [LIMITATIONS_AND_READINESS.md](../LIMITATIONS_AND_READINESS.md), [SYSTEM_FLOW.md](../SYSTEM_FLOW.md), [DURABLE_JOBS.md](../DURABLE_JOBS.md) |

---

## F-10 — Legacy inline / BackgroundTasks execution paths

| Field | Detail |
| :--- | :--- |
| **Severity** | P2 |
| **Classification** | Partially implemented / legacy |
| **Actual behavior** | `SCAN_JOB_INLINE_FALLBACK` (default false) and historical BackgroundTasks paths can still run work inside the API process when enabled or when durable enqueue is unavailable. |
| **Impact** | Dual execution models complicate reasoning about leases and progress. |
| **Proposed fix** | Keep fail-closed durable path for production; treat inline as emergency/dev only (ops doc). |
| **Confidence** | Medium–High (**Inferred** edge cases without matrix test) |

---

## Cross-cutting root causes

1. **Progress was designed for single-process FastAPI** and never moved when workers split out.  
2. **Job durability ≠ pipeline durability** — the job survives; stage work does not checkpoint.  
3. **Budget hooks were added** (`update_llm_checkpoint`, USD fields) but not fully wired into the DAG.  
4. **Documentation lag** after Phase 3 durable jobs and retrieval improvements.

---

## Mapping to implementation stages (Proposed)

| Finding | Stage 1 | Stage 2 | Stage 3 |
| :--- | :---: | :---: | :---: |
| F-01 | Partial (durable status) | — | Full SSE/events |
| F-02 | Full | Helped by caches | — |
| F-03 | Full | — | — |
| F-04 | Full | Measurement | — |
| F-05 | — | Full | — |
| F-06 | Docs only | Optional Redis | — |
| F-07 | Labeling | Optional re-scan | — |
| F-08 | Process | — | CI gate optional |
| F-09 | Tracked | — | Reconcile later |
| F-10 | Ops clarity | — | Remove dead paths later |