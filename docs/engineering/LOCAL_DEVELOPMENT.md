# Local Development Guide

This guide walks through configuring, running, and testing FindableAI locally from a clean clone.

**Also read:** [ENVIRONMENT.md](ENVIRONMENT.md) (canonical env vars) · [LIMITATIONS_AND_READINESS.md](LIMITATIONS_AND_READINESS.md) (what “working” means) · [TESTING.md](TESTING.md) (test suites & smoke runs).

**Port pitfall:** `backend/app/core/config.py` defaults `DATABASE_URL` to port **5433**, while `.env.example` / Compose typically use **5432**. Set `DATABASE_URL` explicitly after copying `.env.example`.

Commands below are taken from project scripts/config. Full-suite pass/fail counts are **not verified** in the documentation pass unless you re-run them.

---

## Prerequisites

Ensure the following tools are installed on your host system:
- **Python:** Version `3.11+` (see [backend/pyproject.toml](../../backend/pyproject.toml))
- **Node.js:** Version `20+` with `npm 10+` (see [frontend/package.json](../../frontend/package.json))
- **Docker & Docker Compose:** Required if running local PostgreSQL (pgvector) and Redis containers.
- **Git:** Standard CLI client.

---

## Step 1: Clone Repository & Configure Environment

Clone the repository and copy the environment configuration:

```bash
git clone https://github.com/Chirag1724/FindableAI.git

# Copy environment template
cp .env.example .env
cp .env.example backend/.env
```

Edit `.env` to configure your keys (e.g. `GROQ_API_KEY` for live AI generation, `GEMINI_API_KEY_AI_SUMMARY` for on-demand **AI Summary**, `GITHUB_TOKEN` for pull request testing). See [ENVIRONMENT.md](ENVIRONMENT.md) and [AI_WEBSITE_HEALTH_BRIEF.md](AI_WEBSITE_HEALTH_BRIEF.md).

---

## Step 2: Backend Setup

1. **Create and activate a Python virtual environment:**

```bash
cd backend

# On Linux / macOS
python3 -m venv venv
source venv/bin/activate

# On Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2. **Install Python dependencies:**

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

3. **Install Playwright headless browser binaries:**

```bash
python -m playwright install --with-deps chromium
```

---

## Step 3: Start Supporting Services (Database & Redis)

You can launch PostgreSQL with pgvector and Redis using Docker Compose:

```bash
# From the project root
docker compose up -d postgres redis
```

Run database migrations to initialize tables and pgvector vector extensions:

```bash
cd backend
alembic upgrade head
```

Migrations **`0018_scan_summaries`** and **`0019_summary_input_snapshot`** are required for AI Website Health Brief cache + `scans.summary_input` persistence.

*Note: FindableAI includes a process-local memory store (`SCANS_DB`). The backend can run scans if PostgreSQL is offline, but results will not survive restart / multi-worker handoff. Redis is optional and **unused by application code** today (rate limits are in-memory; durable scans use the job worker when enabled).*

---

## Step 4: Run Backend Development Server

Start the FastAPI application with live code reload:

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verify backend health at [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health) and interactive Swagger documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Step 5: Frontend Setup & Development Server

1. **Install Node dependencies:**

```bash
cd ../frontend
npm ci
```

2. **Start Next.js development server:**

```bash
npm run dev
```

The frontend dashboard will be live at [http://localhost:3000](http://localhost:3000).

---

## Step 6: Running the Full Verification Suites

### Run Backend Tests (Pytest)
```bash
cd backend
pytest tests -v
```

### Run Backend Type Checker (Mypy)
```bash
cd backend
mypy app
```

### Run Backend Linter (Ruff)
```bash
cd backend
ruff check .
```

### Run Frontend Unit & Component Tests (Vitest)
```bash
cd frontend
npm run test
```

### Run Frontend Type Check & Production Build
```bash
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```

---

## Local Development Tips

### Testing Scans Against Local Websites
When `ENVIRONMENT` is set to `development` (the default), the SSRF validator in [backend/app/core/security.py](../../backend/app/core/security.py) allows scans against `http://localhost:*` and `http://127.0.0.1:*` (e.g. testing against the bundled `demo-site/` folder).

### Serving the Bundled Demo Site
To run the included Bistro demo site locally for crawl testing:

```bash
cd demo-site
python -m http.server 8080
```
Then initiate an audit in the FindableAI dashboard targeting `http://localhost:8080/index.html`.
