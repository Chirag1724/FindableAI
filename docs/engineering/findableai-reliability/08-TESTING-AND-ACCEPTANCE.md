# 08 — Testing and Acceptance

**Important:** Listing a test here does **not** mean it was executed for this documentation task. Commands are taken from project conventions; confirm scripts in `backend` / CI before relying on them.

---

## 1. Layers

| Layer | Purpose | Needs |
| :--- | :--- | :--- |
| Unit | Classifier, budget math, resume rules, fingerprints | Mocks |
| API contract | Create scan, status shape | TestClient + SQLite/PG |
| PG integration | Leases, fencing, SKIP LOCKED | Disposable Postgres |
| Worker fault | Crash/reclaim/resume | PG + controlled kills |
| Provider | Timeouts/429 | Mocks or sandbox keys |
| Frontend contract | Progress fields / SSE | Mock API or Compose |
| GitHub | Idempotent PR / timeout reconcile | Recorded fixtures or sandbox |
| E2E | Full path | Compose; avoid paid LLM in CI |

---

## 2. Commands (verify against repo before use)

From historical project layout (confirm locally):

```bash
# Backend unit / default CI-like (from backend/)
pytest -q

# Opt-in PostgreSQL job concurrency
FINDABLE_PG_INTEGRATION=1 pytest tests/test_scan_jobs_pg.py -q

# Lint / types (as used in CI — confirm workflow files)
ruff check .
mypy app
```

Frontend:

```bash
# from frontend/ — confirm package.json scripts
npm test
# or npm run lint
```

**Unverified here:** Exact CI workflow job names and whether `npm test` exists.

Do **not** run live paid LLM scans or production GitHub remediation as part of routine acceptance.

---

## 3. Required coverage matrix

### 3.1 Unit

| Case | Class |
| :--- | :--- |
| BudgetGuard call cap reject | Existing + extend for USD |
| Error classifier mapping | Proposed |
| Fingerprint stability / mismatch | Proposed |
| `evaluate_verification_outcome` branches | Existing (`test_remediation_gate` family) |
| Resume skip vs recompute rules | Proposed |

### 3.2 PostgreSQL integration

| Case | Notes |
| :--- | :--- |
| Dual worker claim uniqueness | Opt-in today |
| Lease expiry reclaim | Opt-in |
| Stale fence cannot complete | Opt-in / extend |
| Crash mid-stage resume | Proposed Stage 1 |
| Concurrent budget reserve | Proposed |

### 3.3 Provider resilience

| Case | Mock vs live |
| :--- | :--- |
| Timeout → retry | Mock |
| 429 → backoff | Mock |
| Schema validation failure | Mock |
| Budget exhaustion | Mock |

### 3.4 Cache (Stage 2)

| Case | Expect |
| :--- | :--- |
| Hit same fingerprint | No provider call |
| Miss on prompt version bump | Recompute |
| Miss on evidence hash change | Recompute |

### 3.5 SSE / progress (Stage 3)

| Case | Expect |
| :--- | :--- |
| API≠worker | Events visible via DB-backed SSE |
| Reconnect with Last-Event-ID | No gaps / controlled dupes |
| Snapshot recovery | UI shows last stage |

### 3.6 GitHub / remediation

| Case | Expect |
| :--- | :--- |
| Idempotent PR | Single PR for scan/remediation key |
| Timeout reconcile | No duplicate PR |
| Verify heuristic outcomes | fixed / unresolved / inconclusive |

### 3.7 Frontend / backend contract

| Case | Expect |
| :--- | :--- |
| Status fields | stage/percent/message present when Stage 1 ships |
| Integrity contract | Matches `FRONTEND_INTEGRITY_CONTRACT.md` |

---

## 4. Acceptance criteria by stage

### Stage 1

- Resume skips completed durable stages in automated fault test.  
- Budget call+USD enforced under concurrency.  
- Pollable progress with separate API/worker.  
- Remediation tests still green.

### Stage 2

- Version mismatch never serves cache.  
- Measurable call reduction on repeated identical scan inputs (fixture).

### Stage 3

- SSE replay after disconnect in Compose.  
- Metrics/logs include correlation ids without secrets.

---

## 5. What ordinary CI does **not** prove today

- Multi-worker PG races (opt-in only).  
- Live provider behavior.  
- Live GitHub.  
- Split-process SSE (no e2e asserted as green in this audit).

---

## 6. Evidence standard

| Claim type | Required evidence |
| :--- | :--- |
| Implemented | Code + test name + (when run) pass log |
| Proposed | Spec only |
| Unverified | Explicit label |

Never mark FindableAI “production-ready” solely because unit tests exist.