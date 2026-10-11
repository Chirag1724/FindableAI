# 01 — Current-State Audit

**Reference:** `main` @ `1aba352`  
**Method:** Static source inspection + existing unit-test presence. Runtime/PG-integration correctness is **Unverified** unless noted.

---

## 1. Repository and documentation layout

| Item | Finding | Class |
| :--- | :--- | :--- |
| Branch | Expected `main`; confirm with `git branch --show-current` | Needs validation at read time |
| HEAD | Expected `1aba352` | Needs validation at read time |
| Existing docs | `docs/engineering/*` present; left unmodified by this package | Verified (policy) |
| This package | Additive under `docs/engineering/findableai-reliability/` | Proposed delivery |

---

## 2. Verified architecture snapshot

### 2.1 Stack and processes

| Layer | Path / artifact | Role |
| :--- | :--- | :--- |
| API | `backend/app/main.py`, `api/routes_*.py` | HTTP, enqueue, SSE, remediation |
| Worker | `backend/app/jobs/worker.py` | Claims `scan_jobs`, runs pipeline |
| Orchestration | `backend/app/orchestration/dag.py` (`FindableAIDAG`) | Crawl→eval→score→patches |
| Crawl/index | `backend/app/crawler/*` | Fetch, chunk, embed, hybrid search |
| LLM | `backend/app/core/llm.py` (`BudgetGuard`, Instructor clients) | Provider calls |
| Models | `backend/app/models/*` | SQLAlchemy entities |
| Migrations | `backend/alembic/versions/0001`…`0005` | Schema evolution |
| Frontend | `frontend/` | Scan UX, API client, SSE/poll |
| Compose | `docker-compose.yml` | `db`, `backend`, `worker`, `frontend` |

### 2.2 Scan submission and durable jobs (Verified)

1. `POST /api/v1/scans` → `create_scan` in `backend/app/api/routes_scans.py`.
2. Scan row persisted; when Postgres path is active, `enqueue_scan_job` creates `scan_jobs` (`backend/app/jobs/queue.py`).
3. Worker `claim_next_job` uses `FOR UPDATE SKIP LOCKED`, lease TTL, fencing token.
4. Default `SCAN_JOB_INLINE_FALLBACK=false` — API does **not** run the pipeline inline in production-shaped config.
5. Legacy BackgroundTasks / in-memory paths may still exist for degraded modes; durable jobs are the intended production path when DB is available (**Inferred** from Phase 3 design + code paths).

### 2.3 Pipeline stages inside `FindableAIDAG` (Verified structure)

Typical order (names may vary slightly in logs):

1. Crawl / DOM extraction  
2. Chunk persistence + embeddings  
3. Buyer-intent generation  
4. Evidence retrieval (`build_act_retriever` → hybrid search when index present)  
5. LLM evaluation + structured validation  
6. Evidence persistence + scoring  
7. Integrity checks  
8. Patch generation + validation  
9. (Optional) GitHub PR + post-PR verification  

Retries at the **job** layer re-invoke the pipeline; there is no durable stage cursor that skips completed stages (**Verified** absence of mid-pipeline checkpoint callers for resume).

### 2.4 Progress and SSE (Verified process-local)

- In-process structures such as `SCANS_DB`, `EVENT_LOGS`, `EVENT_QUEUES` live in the API/worker process memory (see `backend/app/api` scan progress helpers / event modules).
- Worker updates do not automatically appear in a separate API process memory.
- **Impact:** In Compose (`backend` + `worker` separate), live SSE progress is broken or empty unless polling reads durable DB fields that the worker actually updates.

**Unverified:** Exact UX when frontend falls back to polling against scan status columns only.

### 2.5 LLM checkpoints and BudgetGuard (Verified)

| Mechanism | Behavior | Class |
| :--- | :--- | :--- |
| `BudgetGuard` call reservation | Cap ~100 calls; reserve before provider call | Verified |
| `LLM_BUDGET_CAP_USD` | Stored/observed in budget state; **not** hard-enforced as spend ceiling | Verified (config + guard logic) |
| `update_llm_checkpoint` | Defined in `jobs/queue.py`; **no mid-pipeline callers** found | Verified (definition + absence of call sites) |
| Checkpoint durability across retries | Job row may retain last written checkpoint if something wrote it; pipeline does not resume from it | Inferred |

### 2.6 Retrieval (Verified)

- `build_act_retriever` / crawler search path uses dense + lexical fusion with **RRF** when the retrieval index exists (`backend/app/crawler/search.py`, wired from DAG).
- This **contradicts** older wording in [LIMITATIONS_AND_READINESS.md](../LIMITATIONS_AND_READINESS.md) that may still say hybrid/RRF is missing—treat source as truth; see §5.

### 2.7 Caching (Verified / Missing)

| Cache | Status |
| :--- | :--- |
| Redis | Env/compose may define Redis; **application code does not use Redis** as a runtime cache for scans |
| Crawl/content cache | No durable versioned cache layer for pipeline reuse |
| Retrieval cache | Missing as a dedicated versioned store |
| Evaluation cache | Missing |

### 2.8 Remediation and post-PR verification (Verified)

- Remediation lifecycle: eligibility, idempotency, PR timeout reconciliation (`orchestration/remediation_lifecycle.py`, GitHub client modules).
- `evaluate_verification_outcome` (~lines 130–172): operational errors → inconclusive; failed deterministic checks → unresolved; keyword hits in patched content → fixed/unresolved. **Not** a full website re-scan.
- Overclaiming “verification = re-scan” in docs or UI would be incorrect.

### 2.9 Auth and tenancy (Verified / Partial)

- Auth can be optional depending on settings (API keys / JWT patterns in `core` / middleware).
- Tenant isolation relies on scan ownership and DB constraints where modeled.
- **Unverified:** Production auth posture for public demos.

### 2.10 Tests and CI (Verified structure)

| Suite | Notes |
| :--- | :--- |
| Ordinary CI | Unit/API tests; often SQLite-backed |
| `tests/test_scan_jobs_pg.py` | Opt-in: `FINDABLE_PG_INTEGRATION=1` + disposable `DATABASE_URL` |
| Remediation gate | `tests/test_remediation_gate.py` and related |
| Live LLM / live GitHub | Not assumed in ordinary CI |

**This audit did not re-run the suite.** Do not treat “tests exist” as “tests passed on this machine.”

---

## 3. Finding catalog (summary)

| ID | Area | Classification | Severity |
| :--- | :--- | :--- | :--- |
| F-01 | Process-local progress vs split API/worker | Verified implemented (defect for split deploy) | P0 |
| F-02 | Full-pipeline job retries; no stage resume | Verified | P1 |
| F-03 | Mid-run LLM checkpoint not called | Verified | P1 |
| F-04 | USD budget not hard-enforced | Verified | P2 |
| F-05 | No versioned crawl/retrieval/eval cache | Missing | P2 |
| F-06 | Redis unused | Verified (config vs code) | P3 |
| F-07 | Post-PR verify heuristic | Verified | P1 (docs/product) |
| F-08 | PG concurrency tests opt-in | Verified | P1 (ops) |
| F-09 | Doc contradictions (RRF, verify, jobs path) | Verified vs existing docs | P1 |
| F-10 | Legacy inline/BackgroundTasks paths | Partially implemented / legacy | P2 |

Detailed analysis: [02-PROBLEM-ANALYSIS.md](./02-PROBLEM-ANALYSIS.md).

---

## 4. Data ownership (current)

| Data | Source of truth | Class |
| :--- | :--- | :--- |
| Scan metadata / results | PostgreSQL scan tables | Verified |
| Job lease / status | `scan_jobs` | Verified |
| Evidence rows | Evidence tables + provenance migration | Verified |
| Live progress events | Process memory (`EVENT_*`) | Verified |
| LLM usage mid-run | Incomplete without checkpoint callers | Verified gap |
| Remediations / PR ids | Remediation tables + GitHub | Verified |

---

## 5. Documentation vs code contradictions

Recorded for future reconciliation; **existing files were not edited**.

| Topic | Existing doc tendency | Code-verified reality |
| :--- | :--- | :--- |
| Hybrid retrieval / RRF | [LIMITATIONS_AND_READINESS.md](../LIMITATIONS_AND_READINESS.md) may still mark as missing/partial | Implemented when index path is used |
| Durable jobs vs BackgroundTasks | Older flow docs may emphasize BackgroundTasks | Durable `scan_jobs` is the intended production path when DB available |
| Verification | May read as full re-scan | Heuristic post-PR check (`evaluate_verification_outcome`) |
| SSE across processes | May imply live progress always works | Process-local queues break split deploy |
| Redis | Compose/env may imply caching | App code does not use Redis |

---

## 6. Verification methods (for operators)

```bash
# Branch / HEAD
git branch --show-current && git rev-parse HEAD && git status --short

# Confirm no mid-pipeline checkpoint callers
rg "update_llm_checkpoint" backend/

# Confirm PG tests are opt-in
rg "FINDABLE_PG_INTEGRATION" backend/tests

# Confirm Redis usage in app (expect none / negligible)
rg -i "redis" backend/app --glob '!**/__pycache__/**'
```

**Unverified without disposable PG:** lease contention under multi-worker load, fencing after crash, SKIP LOCKED fairness.

---

## 7. Confidence statement

Static inspection establishes **structure and control flow**. It does **not** prove:

- Production correctness under concurrent workers  
- Provider 429 behavior in the wild  
- Frontend SSE UX on a real Compose stack  

Those remain **Unverified** until executed in a safe environment.