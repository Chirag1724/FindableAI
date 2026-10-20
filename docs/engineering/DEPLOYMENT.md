# Production Deployment Guide

This guide details the production architecture, multi-stage container builds, environment variable configuration, and operational considerations for deploying FindableAI.

---

## Infrastructure Architecture Overview

FindableAI is composed of four modular services designed for horizontal scalability:

```text
[ Web Browser Client ]
          │
          ▼
[ Frontend: Next.js 14 Standalone ] ── (Rewrites /api/*) ──┐
  - Vercel or Docker container                            │
  - Port 3000                                            │
                                                         ▼
[ Backend: FastAPI / Uvicorn ] ◄─────────────────────────┘
  - Render / Docker container (4 workers)
  - Port 8000
  - Playwright Headless Chromium Engine
          │
    ┌─────┴─────────────────────┐
    ▼                           ▼
[ PostgreSQL 16 + pgvector ]   [ Redis 7 Alpine ]
  - Persistent relational data   - Fast state cache & queues
  - Port 5432                    - Port 6379
```

---

## Environment Variable Reference Matrix

All configuration is parsed and validated at application startup using Pydantic Settings in [backend/app/core/config.py](../../backend/app/core/config.py).

| Variable | Scope | Required | Default | Purpose & Behavior if Missing |
| :--- | :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | Backend | Optional | `development` | Runtime environment mode (`development`, `production`, `test`). When set to `production`, private IP crawling is strictly prohibited. |
| `LOG_LEVEL` | Backend | Optional | `info` | Python logging verbosity (`debug`, `info`, `warning`, `error`). |
| `DATABASE_URL` | Backend | Optional | Local PostgreSQL URL | SQLAlchemy async connection string. If database is offline, system runs in resilient memory-backed mode (`SCANS_DB`). |
| `REDIS_URL` | Backend | Optional | `redis://localhost:6379/0` | Redis connection URL for caching and stream coordination. |
| `CORS_ORIGINS` | Backend | Optional | `http://localhost:3000,...` | Comma-separated list of allowed CORS browser origins. |
| `GROQ_API_KEY` | Backend | Optional | `""` | Primary LLM provider key for Groq LPUs (`qwen/qwen3.8-27b`). If omitted or exhausted, pipeline activates deterministic fallback. |
| `DEFAULT_LLM_MODEL` | Backend | Optional | `groq/qwen/qwen3.8-27b` | Model identifier string used by LiteLLM and Instructor. |
| `OPENAI_API_KEY` | Backend | Optional | `""` | Secondary fallback provider key. |
| `ANTHROPIC_API_KEY` | Backend | Optional | `""` | Secondary fallback provider key. |
| `GEMINI_API_KEY` | Backend | Optional | `""` | Secondary fallback provider key; also 3rd fallback for AI Website Health Brief. |
| `GEMINI_API_KEY_AI_SUMMARY` | Backend (web) | Optional | `""` | Primary dedicated key for on-demand AI Summary. Synced in `render.yaml` for web + worker. |
| `GEMINI_API_KEY_AI_SUMMARY1` | Backend (web) | Optional | `""` | Secondary dedicated AI Summary key. |
| `SUMMARY_LLM_MODEL` | Backend | Optional | `gemini/gemini-3.5-flash-lite` | Health Brief model id (`render.yaml` sets this explicitly). |
| `SUMMARY_MAX_OUTPUT_TOKENS` | Backend | Optional | `8192` | Health Brief max output tokens (`render.yaml` sets `"8192"`). |
| `GITHUB_TOKEN` | Backend | Optional | `""` | Personal Access Token (PAT) with `repo` or `public_repo` scope. Required only when users click "Create Pull Request". |
| `API_KEY` | Backend | Optional | `""` | Master API secret. If configured, enforces `X-API-Key` or `Bearer` authentication on mutating endpoints. |
| `RATE_LIMIT_ENABLED` | Backend | Optional | `true` | Master switch for in-memory sliding-window rate limiting. |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | Backend | Optional | `60` | Mutating operation rate limit per IP. |
| `RATE_LIMIT_SCANS_PER_MINUTE` | Backend | Optional | `10` | Scan initialization rate limit per IP. |
| `MAX_SCAN_PAGES` | Backend | Optional | `15` | Maximum number of pages to crawl per scan. |
| `SCAN_TIMEOUT_SECONDS` | Backend | Optional | `60` | Maximum timeout before terminating crawler execution. |
| `LLM_BUDGET_CAP_USD` | Backend | Optional | `0.01` | Maximum dollar cost cap per scan tracked by `BudgetGuard`. |
| `MAX_LLM_CALLS_PER_SCAN` | Backend | Optional | `35` | Maximum provider call limit per scan. |
| `DB_POOL_SIZE` | Backend | Optional | `10` | SQLAlchemy connection pool size. |
| `DB_MAX_OVERFLOW` | Backend | Optional | `20` | Max overflow connections beyond pool size. |
| `BACKEND_URL` | Frontend | Optional | `http://localhost:8000` | Internal backend address used by Next.js server-side API proxy rewrites. |
| `NEXT_PUBLIC_API_URL` | Frontend | Optional | `http://localhost:8000` | Public backend address exposed to client-side components. |

---

## Container Build Architecture

### Backend Container ([backend/Dockerfile](../../backend/Dockerfile))
The backend uses a multi-stage `python:3.11-slim` image:
1. **Builder Stage:** Compiles C-extensions and wheel dependencies into `/install`.
2. **Runner Stage:** Copies built wheels, installs system runtime libraries (including Playwright system dependencies), creates a non-root `appuser`, and runs `uvicorn` with 4 worker processes.
3. **Health Check:** Actively queries `http://localhost:8000/health` every 15 seconds.

```dockerfile
# Build Backend Container
docker build -t findable-backend ./backend

# Run Standalone Backend
docker run -d -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/findable \
  -e GROQ_API_KEY=gsk_... \
  findable-backend
```

### Frontend Container ([frontend/Dockerfile](../../frontend/Dockerfile))
The frontend uses a multi-stage `node:20-alpine` image:
1. **Deps Stage:** Installs production and build dependencies via `npm ci`.
2. **Builder Stage:** Executes Next.js standalone compilation (`npm run build`).
3. **Runner Stage:** Packages only `.next/standalone`, `.next/static`, and `public` assets, running as an unprivileged `nextjs` user.

```dockerfile
# Build Frontend Container
docker build -t findable-frontend ./frontend

# Run Standalone Frontend
docker run -d -p 3000:3000 \
  -e BACKEND_URL=http://backend:8000 \
  findable-frontend
```

---

## Target Platform Deployment Instructions

### 1. Backend on Render
1. Create a **Web Service** pointing to the repository.
2. Select **Docker** runtime (pointing to `backend/Dockerfile` as the Dockerfile path and `backend` as Docker context).
3. Set the required environment variables in the Render Dashboard (`DATABASE_URL`, `GROQ_API_KEY`, `GITHUB_TOKEN`, `CORS_ORIGINS`).
4. Set Health Check Path to `/health`.
5. Ensure plan includes at least 1 GB RAM to support headless Chromium instances during concurrent scans.

### 2. Frontend on Vercel
1. Import the repository in Vercel and set the **Root Directory** to `frontend`.
2. Framework Preset: **Next.js**.
3. Configure Environment Variables:
   - `BACKEND_URL`: `https://your-backend-service.onrender.com`
   - `NEXT_PUBLIC_API_URL`: `https://your-backend-service.onrender.com`
4. Deploy.

---

## Production Operational Gotchas

1. **Playwright Chromium Binaries:**
   - In environments where Docker is not used, Playwright requires system browser binaries. Run:
     ```bash
     python -m playwright install --with-deps chromium
     ```
   - If Playwright fails to launch, the backend crawler automatically degrades to `httpx` + `BeautifulSoup` to avoid failing scans.

2. **GitHub Personal Access Token (PAT) Scopes:**
   - Classic PAT: Requires `repo` (or `public_repo` for public open-source sites).
   - Fine-Grained PAT: Requires `Pull requests` (Read & Write), `Contents` (Read & Write), and `Metadata` (Read-only).

3. **Groq Output Tokens Per Minute (OTPM) Limits:**
   - Groq free-tier accounts enforce token rate limits. When a rate limit (`429`) is encountered, the pipeline logs the rate limit and falls back to deterministic heuristic evaluations rather than failing the scan.

4. **Database Migrations on Startup:**
   - Run Alembic migrations against the production database during deployment pipelines:
     ```bash
     cd backend
     alembic upgrade head
     ```
   - AI Website Health Brief requires heads through **`0019_summary_input_snapshot`** (`scan_summaries` + `scans.summary_input*`).

5. **AI Website Health Brief keys on the web service:**
   - Generation runs in the API process on `POST /api/v1/scans/{id}/summary`. Set `GEMINI_API_KEY_AI_SUMMARY` (and optional `…_SUMMARY1`) plus `SUMMARY_LLM_MODEL` on the **web** service (`render.yaml` already declares these). See [AI_WEBSITE_HEALTH_BRIEF.md](AI_WEBSITE_HEALTH_BRIEF.md).
