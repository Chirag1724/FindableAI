# FindableAI Cloud Deployment Guide: Vercel + Render

This guide provides end-to-end instructions for deploying FindableAI into production using **Vercel** (for the Next.js frontend) and **Render** (for the FastAPI backend, background queue worker, and Redis), backed by PostgreSQL 16 with `pgvector`.

---

## Architecture Topology

```
┌─────────────────────────────────┐
│     End User Web Browser        │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│        Vercel (Frontend)        │  Next.js 14 Standalone
│    findable-ai.vercel.app       │  Reverse-proxies `/api/*` to Render
└──────────────┬──────────────────┘
               │ HTTPS Rewrites / CORS
               ▼
┌─────────────────────────────────┐
│     Render (findable-api)       │  FastAPI REST API & SSE Streaming
│    findable-api.onrender.com    │  Port 8000
└───────┬──────────────┬──────────┘
        │              │
        │ Enqueues     │ Polls & Leases
        ▼              ▼
┌─────────────────────────────────┐
│    Render (findable-worker)     │  Durable Background Scan Worker
│    Durable DAG pipeline         │  Runs `python -m app.worker`
└───────┬──────────────┬──────────┘
        │              │
        ▼              ▼
┌─────────────────────────────────┐   ┌───────────────────────────────┐
│   PostgreSQL 16 + pgvector      │   │     Render (findable-redis)   │
│   (Neon / Supabase / Render)    │   │     Internal Queue & Cache    │
└─────────────────────────────────┘   └───────────────────────────────┘
```

---

## Step 1: Provision PostgreSQL with `pgvector`

FindableAI requires PostgreSQL 16+ with the `pgvector` extension enabled for hybrid vector search.

Recommended free/serverless options:
1. **Neon** ([neon.tech](https://neon.tech)) — Native `pgvector` support out-of-the-box.
2. **Supabase** ([supabase.com](https://supabase.com)) — Free tier PostgreSQL with `pgvector`.
3. **Render PostgreSQL** — If using a paid Render plan with extension permissions.

### Database Connection String Format
Ensure your connection URL uses `postgresql+asyncpg://`:
```text
postgresql+asyncpg://<username>:<password>@<host>/<database>?ssl=require
```

---

## Step 2: Deploy Backend & Worker on Render

FindableAI includes a top-level [`render.yaml`](../render.yaml) blueprint that automatically provisions:
- `findable-api` (FastAPI Web Service)
- `findable-worker` (Background Scan Worker)
- `findable-redis` (Redis Key-Value Cache)

### Deploy via Blueprint:
1. Fork or push your FindableAI repository to GitHub.
2. Log into the [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** → **Blueprint**.
4. Connect your GitHub repository. Render will detect `render.yaml`.
5. Enter the required environment variables:
   - `DATABASE_URL`: Your `postgresql+asyncpg://...` connection string from Step 1.
   - `GROQ_API_KEY`: Your Groq API key for LPU-accelerated inference.
   - `API_KEY`: A secure master secret (Render can auto-generate this).
   - *(Optional)* `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GITHUB_TOKEN`.
6. Click **Apply**.
7. Once deployed, note your Web Service URL (e.g., `https://findable-api.onrender.com`).

Alembic migrations run automatically on startup via `backend/Dockerfile` (`python -m alembic upgrade head`).

---

## Step 3: Deploy Frontend on Vercel

The frontend is a Next.js 14 application configured with [`frontend/vercel.json`](../frontend/vercel.json) and built-in proxy rewrites in [`frontend/next.config.js`](../frontend/next.config.js).

### Deploy via Vercel Dashboard:
1. Log into [Vercel](https://vercel.com/) and click **Add New...** → **Project**.
2. Select your FindableAI repository.
3. Configure the Project Settings:
   - **Framework Preset:** `Next.js`
   - **Root Directory:** Edit and set to `frontend`.
4. Configure Environment Variables:
   - `NEXT_PUBLIC_API_URL`: `https://findable-api.onrender.com` (Your Render API URL).
   - `BACKEND_URL`: `https://findable-api.onrender.com`.
5. Click **Deploy**.

---

## Step 4: Verification & Readiness Checks

Once both services are deployed, verify the deployment health:

### 1. Backend Health Check
```bash
curl -i https://findable-api.onrender.com/health
# HTTP/1.1 200 OK
# {"status":"healthy"}
```

### 2. Full System Readiness (Database + Worker + Queue)
```bash
curl -i https://findable-api.onrender.com/api/v1/ready
# HTTP/1.1 200 OK
# {"ready":true,"database":"connected","queue_depth":0,"worker_active":true}
```

### 3. Frontend End-to-End
1. Visit your Vercel URL (e.g. `https://findable-ai.vercel.app`).
2. Run a scan against a test URL (e.g. `https://example.com`).
3. Verify that the Server-Sent Events (SSE) stream connects and displays real-time progress.
