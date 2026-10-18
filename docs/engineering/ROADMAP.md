# Engineering Roadmap & Production Readiness

This document tracks near-term engineering priorities. For the **authoritative** description of what is implemented versus overstated, see [LIMITATIONS_AND_READINESS.md](LIMITATIONS_AND_READINESS.md). For task IDs and owners, see [docs/04_TEAM_TASK_ALLOCATION.md §10](../04_TEAM_TASK_ALLOCATION.md#10-production-readiness-roadmap).

**Rule:** Existence of a module, Dockerfile, CI workflow, or unit test ≠ production-ready product capability.

---

## 1. Honest delivery snapshot (documentation audit)

| Milestone | Claim historically | Current evidence-based status |
| :--- | :--- | :--- |
| **PROD-5.1** DAG in scan API | “Delivered” | **Partial.** `FindableAIDAG` is called from `run_scan_pipeline`, but mock F-score/patches and synthetic intents remain on failure / non-prod paths. AC “remove mocks from happy path” **not met**. |
| **PROD-5.2** Canonical F-Score | “Unified across README” | **Partial.** Code uses `0.40/0.30/0.20/0.10` without outer ×100. Docs updated to match; `ScoreWeights` still says *provisional*. |
| **PROD-5.3** Intelligence regression fixtures | Open | **Missing** as a dedicated suite (engine unit tests exist). |
| **PROD-5.4** API ↔ UI contract | Partial | ScanResponse exposes scores/intents/patches; hydrate after restart is lossy. |
| **PROD-5.5** Failure isolation | Partial | DAG error results + separate PR apply; UI can still present fallback as a completed audit. |
| **PROD-5.6** Frontend dashboard | Largely present | Components exist; honesty of Fallback Mode / empty intents still weak. |
| **PROD-6.1** SSRF | Implemented | `backend/app/core/security.py` + tests. |
| **PROD-6.2** Rate limit / API key / headers | Partial | In-memory rate limit + optional API key; review prod CORS/headers separately. |
| **PROD-6.3** Prompt-injection fixtures | Open | Instructional NLI gates exist; adversarial suite **missing**. |
| **PROD-6.4** Secrets / GitHub safety | Partial | Log sanitization in LLM client; PR path tests with fakes. |
| **PROD-7.1** Dockerfiles | Files exist | `backend/Dockerfile`, `frontend/Dockerfile`, Compose — **deploy success unverified**. |
| **PROD-7.2** CI workflows | Files exist | `.github/workflows/backend-ci.yml`, `frontend-ci.yml` — **CI green status unverified in doc pass**. |
| **PROD-7.3** Migrations on deploy | Open | Alembic present; auto-migrate on container start not established. |
| **PROD-7.4** Structured observability | Open | Request IDs / logs partial; no full per-stage telemetry product. |
| **PROD-8.1** Clean-env demo-site E2E gate | Open | `demo-site/` exists; automated release E2E gate not established. |

---

## 2. Near-term priorities (do these in engineering tasks, not docs)

1. Honest execution modes + UI (synthetic ≠ real).
2. Persist `execution_mode`, summary, evidence; fix cold hydrate.
3. Hybrid retrieval + RRF are implemented (`hybrid_search` / `reciprocal_rank_fusion`); keep docs and readiness checks aligned with `RetrievalMeta.mode`.
4. Intelligence regression fixtures (PROD-5.3) and prompt-injection fixtures (PROD-6.3).
5. Alembic-on-boot + verified deploy runbook execution (PROD-7.3).
6. Optional post-PR re-audit (verification loop).

---

## 3. Medium-term ideas (planned only)

### Distributed workers (Celery / ARQ)
- **Status:** Planned. Scans today use FastAPI `BackgroundTasks`. Redis is composed but unused by app code.
- **docs/04** explicitly rejects a Celery rewrite “for prestige” until BackgroundTasks is proven insufficient.

### Dynamic multi-provider LLM failover
- **Status:** Planned. Env keys exist; automatic Groq→OpenAI→Anthropic→Gemini chain is **not** implemented. Current degradation is synthetic/heuristic fallback after LLM failure / budget exhaustion.

### Webhook notification dispatcher
- **Status:** Planned. Not implemented.

---

## 4. Explicit non-goals

- Kubernetes / service mesh for this project scope.
- Standalone vector DB (pgvector remains the store; query-time ANN still incomplete).
- Heavy proprietary APM as a prerequisite.
- Claiming guaranteed AI-search ranking or citations.
