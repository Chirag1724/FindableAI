# Local smoke: one real read-only scan

Minimal path to prove API + PostgreSQL + worker + BudgetGuard + durable progress for **one** authorized target. Does **not** open a GitHub PR.

Also read: [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) · [ENVIRONMENT.md](ENVIRONMENT.md) · [LIMITATIONS_AND_READINESS.md](LIMITATIONS_AND_READINESS.md).

## Required vs optional

| Variable | Required for real read-only scan? | Notes |
| :--- | :--- | :--- |
| `DATABASE_URL` | Yes | PostgreSQL + pgvector (Compose `postgres` or local). |
| `DURABLE_SCAN_JOBS=true` | Yes | Durable `scan_jobs` queue. |
| `SCAN_JOB_INLINE_FALLBACK` | Local yes / prod no | `true` for single-process local; `false` + `python -m app.worker` for Compose prod. |
| One of `GROQ_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | Yes | Real mode fail-closed when `ALLOW_SYNTHETIC_DEMO=false`. |
| `HEAVY_LLM_MODEL` / `FAST_LLM_MODEL` | Optional | Defaults in config / `.env.example`. |
| `LLM_BUDGET_CAP_USD`, `MAX_LLM_CALLS_PER_SCAN`, `LLM_ENFORCE_USD_BUDGET` | Recommended | Bound cost; estimates via `LLM_ESTIMATED_USD_PER_CALL`. |
| `ALLOW_SYNTHETIC_DEMO` | Must be `false` for real | Never silently mock in real mode. |
| `API_KEY` | Prod / Compose yes; local open OK | Empty allowed only in non-production. |
| `GITHUB_TOKEN` | **No** for smoke | Only for remediation PR flows. Leave empty for read-only smoke. |
| `REDIS_URL` | Optional | Unused by job queue today. |

Secret files: `**/.env` and `**/.env.*` are git-ignored; `!.env.example` is tracked. Never commit real keys.

## Shortest verified startup

From repo root (`FindableAI/`):

```bash
# 1) Env (do not overwrite an existing .env)
cp -n .env.example .env 2>/dev/null || true
# Edit .env: set DATABASE_URL, one LLM key, ALLOW_SYNTHETIC_DEMO=false,
# DURABLE_SCAN_JOBS=true, SCAN_JOB_INLINE_FALLBACK=true (local), leave GITHUB_TOKEN empty.

# 2) Postgres
# If host 5432/5433 are already taken, pick a free port:
#   POSTGRES_PORT=55432 docker compose up -d postgres
docker compose up -d postgres

# 3) Migrations
cd backend
alembic current   # expect empty or a revision
alembic upgrade head

# If upgrade fails with "relation already exists" and `alembic_version` is missing:
# the schema was created outside Alembic (e.g. create_all / partial apply).
# Do **not** drop data. Inspect markers, stamp only the revision the live schema
# exactly matches, then `alembic upgrade head`. Example for a DB that matched
# 0006 with a partial 0007 (`intents.persona` present, trigger missing):
#   alembic stamp 0006_progress_checkpoints
#   alembic upgrade head   # applies 0007 (idempotent persona) → 0009

# 4) API (terminal A)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5) Optional dedicated worker when SCAN_JOB_INLINE_FALLBACK=false (terminal B)
# python -m app.worker
```

## Smoke test (read-only, no PR)

Authorize only a target you own or may crawl (e.g. bundled demo site):

```bash
# Optional demo target
cd demo-site && python -m http.server 8080
# Target: http://127.0.0.1:8080/index.html  (development SSRF allows loopback)
```

```bash
cd backend
python scripts/local_smoke_scan.py --url http://127.0.0.1:8080/index.html
```

Or manually:

```bash
# Health
curl -sS http://127.0.0.1:8000/api/v1/health

# Submit (omit repo_url — no GitHub coupling)
curl -sS -X POST http://127.0.0.1:8000/api/v1/scans \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://127.0.0.1:8080/index.html","max_pages":2}'

# Poll until terminal (use returned scan_id)
curl -sS http://127.0.0.1:8000/api/v1/scans/<scan_id>
curl -sS http://127.0.0.1:8000/api/v1/scans/<scan_id>/job
```

Missing LLM credentials with `ALLOW_SYNTHETIC_DEMO=false` → **503** with a clear message (no silent mock).

## Where metrics appear

- `GET /api/v1/scans/{id}` — `progress_*`, `llm_calls_made`, `llm_usd_estimated` (`cost_basis=estimated`), `provider_successes` / `provider_failures`, `batches_*`, `execution_mode`, `outcome`, `job_*`
- `GET /api/v1/scans/{id}/job` — durable job attempts, checkpoints, sanitized errors, same batch/provider fields
- Scan detail UI — progress units, estimated USD label, provider attempt counts

Never treat `llm_usd_estimated` as a provider invoice. `llm_usd_provider_reported` stays null unless a provider returns usage-priced cost.
