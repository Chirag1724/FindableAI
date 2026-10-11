# 10 — Decisions and Open Questions

---

## 1. Architecture decisions (Proposed package)

| ID | Decision | Status | Rationale |
| :--- | :--- | :--- | :--- |
| ADR-R1 | Extend Postgres jobs; no Celery/RQ | Accepted (docs) | Jobs/leases/fencing already exist |
| ADR-R2 | No Redis required for Stages 1–2 | Accepted (docs) | App unused Redis; avoid infra sprawl |
| ADR-R3 | Stage 1 before caches/SSE polish | Accepted (docs) | Submission window; correctness first |
| ADR-R4 | Keep heuristic post-PR verify; label honestly | Accepted (docs) | Full re-scan is costly/out of critical path |
| ADR-R5 | Additive docs only; do not rewrite old docs in this task | Accepted | Preserve historical docs; avoid drive-by edits |
| ADR-R6 | Prefer column/JSON reuse before new migrations | Accepted (docs) | Lower migration risk |

---

## 2. Alternatives rejected (for now)

| Alternative | Why rejected |
| :--- | :--- |
| Redis + pub/sub for progress | Extra moving part; Postgres events sufficient initially |
| Full DAG rewrite | High risk before demo |
| Always inline API execution | Breaks worker model; `INLINE_FALLBACK` stays off |
| Treat verify as full re-scan in product copy | False claim vs `evaluate_verification_outcome` |
| Blindly copying prior audit claims | This package re-verifies against source |

---

## 3. Assumptions

| Assumption | Class |
| :--- | :--- |
| `main` @ `1aba352` is the documentation baseline | Needs validation at read time |
| Durable enqueue path is used when Postgres is configured | Verified intent; edge cases Inferred |
| Compose runs API and worker as separate containers | Verified from typical `docker-compose.yml` layout — re-confirm locally |
| Judges/demo will use split topology | Inferred |

---

## 4. Unverified / needs validation

| Item | Why unverified | How to validate |
| :--- | :--- | :--- |
| Multi-worker lease races under load | Opt-in tests not run in this task | `FINDABLE_PG_INTEGRATION=1` |
| Exact SSE UX with poll fallback | No browser run here | Compose + browser |
| Production auth posture | Settings vary | Review deploy env |
| Whether Redis service appears in compose | May vary by file revision | Inspect `docker-compose.yml` |
| Live provider 429 behavior | Needs sandbox keys | Controlled soak |
| Exact Alembic revision filename for jobs | Confirm in `alembic/versions/` | `ls` / `alembic history` |
| Signal handling on worker SIGTERM | Not traced line-by-line here | Read `worker.py` shutdown |

---

## 5. Documentation conflicts (for future reconciliation)

Do **not** edit these files in this task; track for a later PR:

| Source | Conflict |
| :--- | :--- |
| [LIMITATIONS_AND_READINESS.md](../LIMITATIONS_AND_READINESS.md) | May understate hybrid/RRF; may overstate readiness in places |
| [SYSTEM_FLOW.md](../SYSTEM_FLOW.md) | May emphasize older BackgroundTasks narrative |
| Root `README.md` | May simplify architecture vs worker split |
| Phase 2 / Phase 3 docs | Historical; may predate post-merge main |

Authoritative for **current** behavior: checked-out source under `backend/app/`.

---

## 6. Risks

| Risk | Mitigation |
| :--- | :--- |
| Resume skips incorrectly | Fail open to recompute; heavy tests |
| Migration breaks demos | Nullable columns; feature flags |
| Scope creep into Redis/rewrite | Stick to ADR-R1/R2 |
| Overclaiming “production-ready” | Gate on [08-TESTING-AND-ACCEPTANCE.md](./08-TESTING-AND-ACCEPTANCE.md) |
| Secret leakage in progress events | Redaction checklist |

---

## 7. Decisions requiring confirmation before Stage 1 coding

1. Approve this documentation package as the implementation baseline.  
2. Confirm whether Stage 1 may add an Alembic revision or must reuse columns only.  
3. Confirm demo UX: poll-only vs investing in Stage 3 SSE in the same window.  
4. Confirm remediation enabled or sandbox-only for public demo.  
5. Confirm budget USD defaults acceptable for demos (`LLM_BUDGET_CAP_USD` name only).  

---

## 8. Recommended next step

**Review and approve this documentation set, then authorize Stage 1 implementation in a separate change.**  
Do not treat proposed diagrams as shipped behavior.  
Do not modify existing engineering docs until a dedicated reconciliation PR is scheduled.