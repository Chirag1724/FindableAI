# Phase 3 — Durable Scan Jobs

**Status:** Implemented in code on the PostgreSQL-backed job queue. Not a claim of full production readiness.

## Architecture decision

**Selected backend:** PostgreSQL table `scan_jobs` with `FOR UPDATE SKIP LOCKED` claims.

| Option | Decision |
| :--- | :--- |
| PostgreSQL durable queue | **Chosen** — already required for scans/evidence; no new broker; transactional enqueue with scan rows; works with existing PgBouncer `statement_cache_size=0` |
| Redis / ARQ / Celery | Rejected for Phase 3 — Redis is composed but unused; adding a broker increases deploy surface without clear need |
| FastAPI `BackgroundTasks` alone | **Not durable** — retained only as optional `SCAN_JOB_INLINE_FALLBACK` after the job row is persisted |

**Semantics:** at-least-once job execution + idempotent side effects (scan idempotency keys, remediation `idempotency_key`, GitHub open-PR reconciliation). Not exactly-once across PostgreSQL and GitHub.

## Lifecycle

States: `queued` → `claimed` → `running` → (`succeeded` | `retry_scheduled` | `failed` | `dead_letter` | `cancelled`).

- Claims bump `fencing_token`; completions/failures require matching token + `claimed_by`.
- Expired leases are requeued; stale workers cannot overwrite newer results.
- Retries use exponential backoff + jitter; budget checkpoint (`llm_calls_checkpoint` / `scans.llm_calls_made`) is restored so retries do not reset LLM spend.

## Idempotency (scan submit)

| Source | Key | Conflict |
| :--- | :--- | :--- |
| Header `Idempotency-Key` | `client:<key>` | Same key, different fingerprint → HTTP 409 |
| None | `auto:<sha256 fingerprint>` | Identical payload returns existing scan/job |

Fingerprint covers normalized URL, `max_pages`, sorted personas, repo URL. Advisory TTL: `SCAN_JOB_IDEMPOTENCY_TTL_SECONDS` (cleanup is operational; uniqueness is permanent until row delete).

## Runbook

### Migrate

```bash
cd backend
alembic upgrade head   # includes 0005_scan_jobs
```

Safe ordering: migrate DB → deploy API (enqueue only) → start workers. Do not drop Phase 2 tables.

### API

```bash
uvicorn app.main:app --reload
```

With `DURABLE_SCAN_JOBS=true`, `POST /api/v1/scans` persists `scans` + `scan_jobs` before 202.

### Worker (required when `SCAN_JOB_INLINE_FALLBACK=false`)

```bash
python -m app.worker
```

Docker Compose service: `worker` (same image, command override).

### Health

| Endpoint | Meaning |
| :--- | :--- |
| `GET /health` / `GET /api/v1/health` | **Liveness** — process up only (no DB). Used by Docker HEALTHCHECK. |
| `GET /api/v1/ready` | **Readiness** — DB + queue probe + coarse worker activity (`idle` / `active` / `stale_or_absent`) |

No credentials or connection strings are returned.

### Recovery

1. Inspect `scan_jobs` for `status`, `error_code`, `failure_category`, `lease_expires_at`.
2. Expired leases are reclaimed automatically on the next worker poll.
3. `dead_letter` / permanent `failed` jobs need operator review; do not blindly reset without understanding side effects.
4. GitHub ambiguous timeout: apply path reconciles via `find_open_pull` before opening another PR.

## Configuration

See `.env.example` keys prefixed `SCAN_JOB_*`, `DURABLE_SCAN_JOBS`, `SCAN_JOB_INLINE_FALLBACK`, `LLM_*_TIMEOUT*`, `LLM_PROVIDER_MAX_ATTEMPTS`, `LLM_GLOBAL_CONCURRENCY`.

`SCAN_JOB_INLINE_FALLBACK` defaults to **false** (production-safe). Enable explicitly for local/CI. Compose production sets it false and runs the `worker` service.

## Tests

```bash
# Unit (SQLite in-memory for queue logic; not concurrency proof)
pytest tests/test_scan_jobs_unit.py tests/test_github_timeout_reconcile.py -q

# Disposable PostgreSQL concurrency / schema smoke
FINDABLE_PG_INTEGRATION=1 pytest tests/test_scan_jobs_pg.py -q
```

Live provider/GitHub tests remain opt-in and must not open unintended PRs.

## Known limitations

- Full pipeline resume-from-stage is not implemented; retries may re-crawl. Budget and external side-effect idempotency still apply.
- SSE/event buffers remain process-local.
- PostgreSQL SKIP LOCKED concurrency proof requires `FINDABLE_PG_INTEGRATION=1`.
- Embedding calls are not charged against `MAX_LLM_CALLS_PER_SCAN` (completion-call budget only) — unchanged from prior phases.
