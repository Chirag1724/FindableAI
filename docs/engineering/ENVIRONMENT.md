# Environment Variable Reference

Canonical reference derived from `backend/app/core/config.py`, root `.env.example`, `docker-compose.yml`, and frontend env usage. Prefer this document over scattered README snippets.

**Secrets:** never commit real keys. Examples below use placeholders only.

---

## How to load

- Backend: Pydantic Settings reads `.env` and `../.env` (`Settings` in `backend/app/core/config.py`).
- Compose: interpolates `${VAR}` from the shell / `.env` at the repo root.
- Frontend: `NEXT_PUBLIC_*` and `BACKEND_URL` for Next.js (see `.env.example`).

---

## Variable matrix

| Variable | Purpose | Required? | Default (code / example) | Consumer | Secret? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | Runtime mode (`development` / `production`); affects SSRF localhost allowlist, mock F-score/patches, execution_mode labels | Optional | `development` | Backend | No |
| `LOG_LEVEL` | Logging verbosity | Optional | `info` | Backend | No |
| `DATABASE_URL` | Async SQLAlchemy URL (`postgresql+asyncpg://…`) | Strongly recommended for durable scans | Code default uses **port 5433**; `.env.example` / Compose typically use **5432** — align explicitly | Backend | Yes (credentials) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_PORT` | Compose Postgres service | For Compose | `findable` / `findable_secret` / `findable_db` / `5432` | Compose | Password yes |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` / `DB_POOL_RECYCLE` | SQLAlchemy pool | Optional | `10` / `20` / `30` / `1800` | Backend | No |
| `REDIS_URL` / `REDIS_PORT` | Redis URL for compose / future use | Optional | `redis://localhost:6379/0` | Compose / config only — **not used by app code today** | No |
| `GROQ_API_KEY` | Primary LLM provider key for LiteLLM/Instructor | Required for `real_llm` scans | empty | Backend `LLMClient` | Yes |
| `DEFAULT_LLM_MODEL` | LiteLLM model id | Optional | `groq/qwen/qwen3.8-27b` | Backend | No |
| `OPENAI_API_KEY` | Embeddings (`text-embedding-3-small`) and optional LLM | Optional | empty | Embeddings; LLM if selected | Yes |
| `ANTHROPIC_API_KEY` | Optional alternate LLM | Optional | empty | Backend (configured; failover not automatic) | Yes |
| `GEMINI_API_KEY` | Optional alternate LLM | Optional | empty | Backend (configured; failover not automatic) | Yes |
| `GITHUB_TOKEN` | PAT for remediation PRs | Required for live PR apply | empty | GitHub PR engine | Yes |
| `API_KEY` | If set, mutating API routes require `X-API-Key` or Bearer | Optional | empty (open in dev) | Backend auth | Yes |
| `RATE_LIMIT_ENABLED` | Toggle in-memory rate limiter | Optional | `true` | Backend | No |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | General mutating window | Optional | `60` | Backend | No |
| `RATE_LIMIT_SCANS_PER_MINUTE` | Scan-create window | Optional | `10` | Backend | No |
| `CORS_ORIGINS` | Comma-separated allowed origins | Optional | `http://localhost:3000,http://127.0.0.1:3000` | Backend | No |
| `MAX_SCAN_PAGES` | Soft global max pages setting | Optional | `15` | Backend settings | No |
| `SCAN_TIMEOUT_SECONDS` | Scan-related timeout setting | Optional | `60` | Backend settings | No |
| `LLM_BUDGET_CAP_USD` | Soft USD budget metadata | Optional | `0.01` | Backend | No |
| `MAX_LLM_CALLS_PER_SCAN` | Hard per-scan provider-call cap (`BudgetGuard`) | Optional | `35` | Backend | No |
| `ALLOW_SYNTHETIC_DEMO` | Opt-in non-production synthetic demo fill | Optional | `false` | Backend | No |
| `BACKEND_URL` | Server-side backend base (Docker frontend) | Optional | `http://localhost:8000` | Frontend container | No |
| `NEXT_PUBLIC_API_URL` | Browser-visible API base | Optional | `http://localhost:8000` | Frontend | No |
| `FRONTEND_URL` | Used in compose backend env | Optional | `http://localhost:3000` | Compose | No |

---

## Notes and pitfalls

1. **Port mismatch:** `Settings.DATABASE_URL` defaults to `localhost:5433` while Compose maps Postgres on `5432`. Always set `DATABASE_URL` explicitly for local work.
2. **Redis:** present in Compose and config for future cache/queue use. Rate limiting is **in-process memory**, not Redis. Scans use FastAPI `BackgroundTasks`, not Celery.
3. **Missing `GROQ_API_KEY`:** crawl/chunk may still succeed; intelligence completes as **inconclusive/failed** with zero real evaluations (no silent synthetic fill). Set `ALLOW_SYNTHETIC_DEMO=true` only for explicit non-production demos — never remediation-eligible. See [LIMITATIONS_AND_READINESS.md](LIMITATIONS_AND_READINESS.md).
4. **Embeddings without `OPENAI_API_KEY`:** deterministic hash embeddings are used (`embeddings.py`).
5. **Required vs optional:** only mark a variable required when the code path you need actually fails without it. Empty `API_KEY` is intentional for local demos.
6. **`ALLOW_SYNTHETIC_DEMO`:** default `false`. Ignored / blocked in `ENVIRONMENT=production`.

---

## Minimal local `.env` sketch (placeholders)

```bash
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://findable:findable_secret@localhost:5432/findable_db
GROQ_API_KEY=gsk_your_key_here
GITHUB_TOKEN=
API_KEY=
ALLOW_SYNTHETIC_DEMO=false
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
MAX_LLM_CALLS_PER_SCAN=35
NEXT_PUBLIC_API_URL=http://localhost:8000
```
