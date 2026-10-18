# Known Limitations & Production-Readiness Status

**Canonical status document** for what FindableAI actually does today versus what documentation or marketing may imply.

**Evidence date:** working tree after P0 integrity + P1 persistence + pre-commit hardening. This document does **not** claim that live provider calls, production deploys, or full CI runs were executed during documentation updates.

**Related:** [ADR-001 F-Score](ARCHITECTURE_DECISIONS.md#adr-001-canonical-f-score-weight-formulation) · [DURABLE_JOBS.md](DURABLE_JOBS.md) · [SYSTEM_FLOW.md](SYSTEM_FLOW.md) · [FRONTEND_INTEGRITY_CONTRACT.md](FRONTEND_INTEGRITY_CONTRACT.md) · [ROADMAP.md](ROADMAP.md) · [docs/04 §10](../04_TEAM_TASK_ALLOCATION.md#10-production-readiness-roadmap)

---

## Release readiness (summary)

| Tier | Status | Meaning |
| :--- | :--- | :--- |
| **Hackathon / demo** | Conditionally ready | Viable with a working `GROQ_API_KEY`, Postgres + migration `0002`, and honest incomplete/failed presentation when intelligence does not run. |
| **Public beta** | Not ready | Needs disposable-Postgres migration proof, live provider/GitHub verification, multi-worker durability. |
| **Production** | Not ready | Missing verified deploy/migration automation, adversarial suites, and live E2E of verify-after-PR. |

Do **not** describe the product as production-ready solely because Dockerfiles, CI workflows, or unit tests exist.

---

## Status table

| Area | Current status | Evidence | Remaining gap |
| :--- | :--- | :--- | :--- |
| **Real LLM execution** | Implemented (when provider configured) | `LLMClient` + DAG; `decide_scan_integrity` requires DAG evaluations **and** `llm_calls_made > 0` **and** no synthetic/mock intelligence for `real_llm` | Live Groq success **unverified** without credentials. |
| **Synthetic / mock demo** | **Opt-in only** (`ALLOW_SYNTHETIC_DEMO=true`, never production) | `should_inject_synthetic_*` gated by flag; default **false**. Demo placeholders have no fabricated evidence; no audit-grade F-Score; mock patches `is_synthetic=True`; never `remediation_eligible=true` | Leaving the flag on in shared envs still shows demo rows in-memory — keep off for normal scans. |
| **Retrieval / RRF** | Implemented (Stage 3) | ACT uses `build_act_retriever` → `hybrid_search` (dense + lexical fused by `reciprocal_rank_fusion`). Formula: `score(d)=Σ 1/(k+rank)` with **1-based** ranks, `k=RETRIEVAL_RRF_K` (default 60), equal list weights, within-list UUID dedupe, tie-break `(-score, str(uuid))`, top-N=`RETRIEVAL_TOP_K`. Modes: `rrf_hybrid` / `dense_only` / `lexical_only` / `memory_fallback`. Falls back to first-*k* OBSERVE only when retrieval returns empty. | Live pgvector ANN **unverified** without disposable Postgres. |
| **Evidence persistence** | Implemented (Stage 2) | `evidence_persistence.py` writes `Evidence` rows for real DAG evals when cites resolve to persisted `DOMChunk` UUIDs; stores provenance; cold hydrate; unique `(intent_id, chunk_id, observation_phase)`. | Live Postgres apply of `0003`/`0004` **BLOCKED** without disposable DB. |
| **Scan-result hydration** | Implemented for integrity contract | Alembic `0002_scan_integrity` + `Scan` columns + `apply_integrity_to_scan_row` / `unpack_integrity_from_scan_row`; cold `GET /scans/{id}` restores integrity | Full crawled-page detail list still thin on cold hydrate; multi-worker still process-local for SSE/cache. **Postgres migration apply not verified in every environment.** |
| **F-Score consistency** | Implemented | `F = 0.40*S_ans + 0.30*S_con + 0.20*S_str + 0.10*S_acc` (components already 0–100; **no** outer ×100) | `ScoreWeights` still labeled provisional in schema. Authoritative score only when `score_source=deterministic_scorer` on real evaluations. |
| **Remediation authorization** | Fail-closed (cache-only SSOT) | Apply/validate go through `evaluate_cache_only_remediation` / `decide_cache_only_for_scan`: tenant + completed/audited status + provenance (hash/fingerprint/URL/timestamp) + `EVIDENCE_TTL_SECONDS` freshness + validated evidence. Zero provider calls / zero budget. Reason codes in 409/422. | Live GitHub PR success **unverified** without `GITHUB_TOKEN`. |
| **GitHub PR creation** | Credential-gated + lifecycle | Real PyGithub path; `remediation_runs` + idempotency (`0004`); deterministic validation before mutation | Live GitHub **unverified** without `GITHUB_TOKEN`. Opening a PR ≠ verified fix. |
| **Post-PR verification** | Implemented (heuristic) | `POST .../remediation/verify` binds an immutable `head_sha`, keyword/content heuristic; `fully_verified` always false for `heuristic_post_pr` | Full website re-scan **not implemented**. Live verify **unverified** without token + PR. |
| **Remediation lifecycle concurrency** | Implemented (CAS) | `remediation_runs.state_revision` + transition graph; idempotency key scoped to scan\|repo\|branch | Multi-worker load under production traffic **not load-tested**. |
| **Remediation LLM budget** | Scan BudgetGuard + remediation helpers | Apply/verify are non-LLM; optional remediation LLM must `reserve()` first; exhaustion blocks mutation when LLM required | No separate USD ledger for GitHub API calls (rate limit only). |
| **Hard-failure handling** | Implemented | `_finalize_hard_failure` sets failed/partial integrity, `remediation_eligible=False`, sanitized public/SSE errors, best-effort DB persist | If DB is down during failure, durability is best-effort (logged); in-memory/API state still fail-closed. |
| **Deployment & ops** | Partial (Phase 3 queue in code) | `scan_jobs` + `python -m app.worker`; Compose `worker` service; `/ready` | Live multi-worker deploy **unverified**. Redis still unused as broker. `SCAN_JOB_INLINE_FALLBACK` must be false in production. PG SKIP LOCKED tests require `FINDABLE_PG_INTEGRATION=1`. |

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
| Intent evaluations | Yes | Yes for **real** DAG evals only (demo rows not persisted) | |
| Contradictions | Yes | Yes for non-synthetic | |
| Patches | Yes | Assembler non-synthetic only | `pr_url` column exists; apply path still may not persist it |
| Evidence rows | Yes (on evaluations) | Yes when cite → persisted `DOMChunk` UUID | Provenance + `content_hash`/`cache_fingerprint` (0017); unique `(intent, chunk, phase)` in `0003`; ACT prefers hybrid+RRF when index hits, else first-k |
| Lighthouse | `LIGHTHOUSE_DB` | Not a scan column | |

---

## Actual runtime retrieval path

```
Crawl → DOMChunker → store_dom_chunks (+ embeddings when available)
     → FindableAIDAG ACT via build_act_retriever
          preferred: hybrid_search(dense ANN + lexical) → reciprocal_rank_fusion
            k = RETRIEVAL_RRF_K (default 60), ranks 1-based, top-N = RETRIEVAL_TOP_K
            lists: dense_ids then lexical_ids (equal weight, no per-list weights)
          fallback when empty: first-k OBSERVE chunks (query ignored)
```

SSE label `HYBRID_RETRIEVAL` is a progress milestone name; check `RetrievalMeta.mode` for whether RRF actually ran.

---

## GitHub remediation lifecycle

| Step | Status |
| :--- | :--- |
| Generate proposed remediation | Implemented (assembler) |
| Backend eligibility gate | Fail-closed (`remediation_eligible is True` + Stage 2 evidence refine) |
| Deterministic patch validation | Path/boundary/secrets/evidence checks before GitHub writes |
| Durable lifecycle FSM | `remediation_runs.lifecycle_state` with enforced transitions |
| Create branch / commit / open PR | When token + permissions allow; idempotent + timeout reconcile |
| Post-PR verification | Implemented (`POST …/remediation/verify`); heuristic on PR head only |
| Full website re-scan verification | **Not implemented** — `fully_verified` stays false for heuristic checks |

**Honesty:** Opening a PR (`lifecycle_state=pr_open`) is **not** a verified fix. Heuristic keyword/content checks may yield `issue_outcome=fixed` with `fully_verified=false`. Projected F-Score improvements are never treated as verification.

---

## Next engineering tasks (pointers)

| Priority | Task | Remaining problem |
| :--- | :--- | :--- |
| P0 | Retrieval truth | Wire hybrid or keep first-k explicit in product UX |
| P0 | Evidence row persistence | Stage 2 writes/hydrates when cites resolve; remaining: live PG migrate proof + ACT retrieval |
| P0 | Intelligence regression fixtures | Broader CI without live providers |
| P1 | Post-PR verification | PR ≠ fix |
| P1 | Postgres migration CI | Prove `alembic upgrade head` on disposable PG |

---

## What this document is not

- Not a guarantee of CI green on GitHub Actions.
- Not a record of a successful cloud production deploy.
- Not proof that Groq, embeddings, or GitHub PRs work in your environment without running them.
