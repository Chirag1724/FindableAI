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
| `GEMINI_API_KEY` | Optional alternate LLM; also **3rd** fallback key for AI Website Health Brief | Optional | empty | Backend LLM; summary key chain | Yes |
| `GEMINI_API_KEY_AI_SUMMARY` | Primary dedicated key for on-demand AI Website Health Brief | Optional (required to generate briefs without falling back) | empty | `scan_summary._summary_api_keys` | Yes |
| `GEMINI_API_KEY_AI_SUMMARY1` | Secondary dedicated Health Brief key | Optional | empty | Summary key chain | Yes |
| `SUMMARY_LLM_MODEL` | LiteLLM model id for Health Brief (use `gemini/…` prefix) | Optional | `gemini/gemini-3.5-flash-lite` | Summary generation | No |
| `SUMMARY_MAX_FINDINGS` | Max findings packed into summary snapshot | Optional | `25` | Snapshot builder | No |
| `SUMMARY_MAX_OUTPUT_TOKENS` | Primary max output tokens for summary LLM | Optional | `8192` | Summary LLM | No |
| `SUMMARY_MAX_OUTPUT_TOKENS_REPAIR` | Raised token budget after truncation | Optional | `12288` | Summary repair path | No |
| `SUMMARY_LLM_TIMEOUT_SECONDS` | Per-call timeout; stale `generating` reclaim uses `2×` | Optional | `60` | Summary LLM / single-flight | No |
| `SUMMARY_LLM_MAX_CALLS` | Max LLM attempts per generate (incl. repairs) | Optional | `4` | Summary LLM | No |
| `SUMMARY_PROVIDER_BACKOFF_SECONDS` | Backoff between summary key retries | Optional | `1.5` | Summary failover | No |
| `SUMMARY_RATE_LIMIT_PER_SCAN_PER_HOUR` | Generation attempts per scan per hour | Optional | `3` | Summary rate limit | No |
| `SUMMARY_RATE_LIMIT_PER_ORG_PER_DAY` | Generation attempts per org per day | Optional | `30` | Summary rate limit | No |
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
3. **Missing LLM credentials:** with `ALLOW_SYNTHETIC_DEMO=false`, `POST /api/v1/scans` fails closed (**503**) before queueing. Set at least one of `GROQ_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY`. Set `ALLOW_SYNTHETIC_DEMO=true` only for explicit non-production demos — never remediation-eligible. See [LIMITATIONS_AND_READINESS.md](LIMITATIONS_AND_READINESS.md) and [TESTING.md](TESTING.md).
4. **Embeddings without `OPENAI_API_KEY`:** deterministic hash embeddings are used (`embeddings.py`).
5. **Required vs optional:** only mark a variable required when the code path you need actually fails without it. Empty `API_KEY` is intentional for local demos.
6. **`ALLOW_SYNTHETIC_DEMO`:** default `false`. Ignored / blocked in `ENVIRONMENT=production`.
7. **AI Website Health Brief keys:** ordered unique list `GEMINI_API_KEY_AI_SUMMARY` → `GEMINI_API_KEY_AI_SUMMARY1` → `GEMINI_API_KEY` → `GROQ_API_KEY`. Summary client sets `allow_provider_failover=False` (key-list failover only). Full feature doc: [AI_WEBSITE_HEALTH_BRIEF.md](AI_WEBSITE_HEALTH_BRIEF.md).
8. **Model naming:** prefer `SUMMARY_LLM_MODEL=gemini/gemini-3.5-flash-lite`. New Gemini keys often 404 older ids such as `gemini-2.5-flash`. This is separate from scan `GEMINI_MODEL`.

---

## Minimal local `.env` sketch (placeholders)

```bash
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://findable:findable_secret@localhost:5432/findable_db
GROQ_API_KEY=gsk_your_key_here
GEMINI_API_KEY_AI_SUMMARY=your_gemini_summary_key
GEMINI_API_KEY_AI_SUMMARY1=
SUMMARY_LLM_MODEL=gemini/gemini-3.5-flash-lite
SUMMARY_MAX_OUTPUT_TOKENS=8192
GITHUB_TOKEN=
API_KEY=
ALLOW_SYNTHETIC_DEMO=false
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
MAX_LLM_CALLS_PER_SCAN=35
NEXT_PUBLIC_API_URL=http://localhost:8000
```
