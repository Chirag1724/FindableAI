# Known Limitations & Production-Readiness Status

**Canonical status document** for what FindableAI actually does today versus what documentation or marketing may imply.

**Evidence date:** working tree after P0 integrity + P1 persistence + pre-commit hardening. This document does **not** claim that live provider calls, production deploys, or full CI runs were executed during documentation updates.

**Related:** [ADR-001 F-Score](ARCHITECTURE_DECISIONS.md#adr-001-canonical-f-score-weight-formulation) · [SYSTEM_FLOW.md](SYSTEM_FLOW.md) · [FRONTEND_INTEGRITY_CONTRACT.md](FRONTEND_INTEGRITY_CONTRACT.md) · [ROADMAP.md](ROADMAP.md) · [docs/04 §10](../04_TEAM_TASK_ALLOCATION.md#10-production-readiness-roadmap)

---

## Release readiness (summary)

| Tier | Status | Meaning |
| :--- | :--- | :--- |
| **Hackathon / demo** | Conditionally ready | Viable with a working `GROQ_API_KEY`, Postgres + migration `0002`, and honest incomplete/failed presentation when intelligence does not run. |
| **Public beta** | Not ready | Needs real retrieval wiring, evidence-row persistence, multi-worker durability proof, and broader regression fixtures. |
| **Production** | Not ready | Missing verified deploy/migration automation, adversarial suites, and post-PR verification. |

Do **not** describe the product as production-ready solely because Dockerfiles, CI workflows, or unit tests exist.

---

## Status table

| Area | Current status | Evidence | Remaining gap |
| :--- | :--- | :--- | :--- |
| **Real LLM execution** | Implemented (when provider configured) | `LLMClient` + DAG; `decide_scan_integrity` requires DAG evaluations **and** `llm_calls_made > 0` **and** no synthetic/mock intelligence for `real_llm` | Live Groq success **unverified** without credentials. |
| **Synthetic / mock demo** | **Opt-in only** (`ALLOW_SYNTHETIC_DEMO=true`, never production) | `should_inject_synthetic_*` gated by flag; default **false**. Demo placeholders have no fabricated evidence; no audit-grade F-Score; mock patches `is_synthetic=True`; never `remediation_eligible=true` | Leaving the flag on in shared envs still shows demo rows in-memory — keep off for normal scans. |
| **Retrieval / RRF** | Partially implemented | Default ACT = first-*k* OBSERVE chunks. `hybrid_search` = FTS / keyword; **no RRF**; embeddings stored but not queried at scan time | Wire hybrid or keep docs honest (this doc is honest). |
| **Evidence persistence** | Partially implemented | `Evidence` ORM exists; NLI builds in-memory refs | Persist loop **still does not write `Evidence` rows**; cold hydrate returns `evidence: []`. |
| **Scan-result hydration** | Implemented for integrity contract | Alembic `0002_scan_integrity` + `Scan` columns + `apply_integrity_to_scan_row` / `unpack_integrity_from_scan_row`; cold `GET /scans/{id}` restores integrity | Full crawled-page detail list still thin on cold hydrate; multi-worker still process-local for SSE/cache. **Postgres migration apply not verified in every environment.** |
| **F-Score consistency** | Implemented | `F = 0.40*S_ans + 0.30*S_con + 0.20*S_str + 0.10*S_acc` (components already 0–100; **no** outer ×100) | `ScoreWeights` still labeled provisional in schema. Authoritative score only when `score_source=deterministic_scorer` on real evaluations. |
| **Remediation authorization** | Fail-closed | Apply requires `remediation_eligible is True`; rejects `None`/`False`; rejects `is_synthetic` patches **before** GitHub mutation | Live GitHub PR success **unverified** without `GITHUB_TOKEN`. |
| **GitHub PR creation** | Credential-gated | Real PyGithub path; tests use `FakeGitHubClient` only | Opening a PR ≠ verified fix. |
| **Post-PR verification** | Missing | — | Still missing. |
| **Hard-failure handling** | Implemented | `_finalize_hard_failure` sets failed/partial integrity, `remediation_eligible=False`, sanitized public/SSE errors, best-effort DB persist | If DB is down during failure, durability is best-effort (logged); in-memory/API state still fail-closed. |
| **Deployment & ops** | Partial | Docker/Compose/CI exist | Live deploy **unverified**. Redis composed but unused. Scans use `BackgroundTasks`, not Celery. |

---

## Execution-mode semantics (authoritative)

Decided by `backend/app/orchestration/scan_integrity.py` and applied in `run_scan_pipeline`:

| Field | Values | Meaning |
| :--- | :--- | :--- |
| `execution_mode` | `real_llm` / `synthetic_fallback` / `deterministic` / `unknown` (legacy hydrate) | `real_llm` only with real DAG evals + LLM calls + no synthetic/mock intelligence. |
| `result_source` | `real_pipeline` / `partial_real` / `synthetic_fallback` / `inconclusive` | Provenance of intent evaluations. |
| `outcome` | `success` / `partial` / `inconclusive` / `failed` | Overall audit conclusion. |
| `score_source` | `deterministic_scorer` / `mock` / `none` | Only `deterministic_scorer` on real evals is audit-grade. |
| `patches_source` | `assembler` / `mock` / `none` | Assembler-only for remediation eligibility. |
| `remediation_eligible` | bool \| null pending | Backend apply requires **explicit `true`**. |

Normal scans (default): **no** synthetic intent/score/patch injection when DAG returns zero evaluations → inconclusive/failed with empty real intents and no authoritative F-Score.

Frontend: “No fixes required” only when `remediation_eligible === true` and there are zero non-synthetic patches. Score gauge only for authoritative real scores.

---

## Persistence map

| Artifact | In-memory | Postgres | Notes |
| :--- | :--- | :--- | :--- |
| Scan status / URL | Yes | Yes | |
| F-score floats | Yes | Yes (`f_score`, `s_*`) when real score exists | |
| Integrity contract (`execution_mode`, `outcome`, `result_source`, `remediation_eligible`, warnings, counts, …) | Yes | Yes (migration `0002`) | Legacy rows hydrate as `unknown` / inconclusive / not eligible |
| `completed_at`, `error` | Yes | Yes | Hard-fail path persists when DB available |
| DOM chunks + embeddings | Yes + DB | Yes if store succeeds | |
| Intent evaluations | Yes | Yes for **real** DAG evals only (demo rows not persisted) | Evidence citations not stored as `Evidence` rows |
| Contradictions | Yes | Yes for non-synthetic | |
| Patches | Yes | Assembler non-synthetic only | |
| Evidence rows | Transient | **Not written** | Remaining gap |
| Lighthouse | `LIGHTHOUSE_DB` | Not a scan column | |

---

## Actual runtime retrieval path

```
Crawl → DOMChunker → (optional) store_dom_chunks + embeddings
     → FindableAIDAG ACT
          default retriever = first k OBSERVE chunks
          optional hybrid_search = tsvector / keyword (no dense ANN, no RRF)
```

SSE label `HYBRID_RETRIEVAL` is a progress milestone name, not proof that hybrid/RRF ran.

---

## GitHub remediation lifecycle

| Step | Status |
| :--- | :--- |
| Generate proposed remediation | Implemented (assembler) |
| Backend eligibility gate | Fail-closed (`remediation_eligible is True`) |
| Create branch / commit / open PR | When token + permissions allow |
| Re-scan / verify defect fixed | **Missing** |

---

## Next engineering tasks (pointers)

| Priority | Task | Remaining problem |
| :--- | :--- | :--- |
| P0 | Retrieval truth | Wire hybrid or keep first-k explicit in product UX |
| P0 | Evidence row persistence | Cold hydrate loses citation graph |
| P0 | Intelligence regression fixtures | Broader CI without live providers |
| P1 | Post-PR verification | PR ≠ fix |
| P1 | Postgres migration CI | Prove `alembic upgrade head` on disposable PG |

---

## What this document is not

- Not a guarantee of CI green on GitHub Actions.
- Not a record of a successful cloud production deploy.
- Not proof that Groq, embeddings, or GitHub PRs work in your environment without running them.
