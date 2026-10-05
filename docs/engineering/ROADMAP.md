# Engineering Roadmap & Production Readiness

This document tracks the delivery status of production milestones and outlines the forward-looking engineering roadmap for FindableAI.

---

## 1. Verified Delivery Status (Phases 5-7)

Based on direct codebase verification, the following core production capabilities have been fully delivered:

| Milestone ID | Feature / Component | Delivery Evidence in Codebase |
| :--- | :--- | :--- |
| **PROD-5.1** | DAG Pipeline Integration | `FindableAIDAG` orchestrates real intent generation, entailment checks, contradiction detection, and patch generation in [backend/app/api/v1/scans.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/api/v1/scans.py). |
| **PROD-5.2** | Canonical F-Score Specification | Unified at `0.40 / 0.30 / 0.20 / 0.10` across [backend/app/schemas/scoring.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/schemas/scoring.py), [backend/app/schemas/fscore.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/schemas/fscore.py), frontend types, and README. |
| **PROD-5.4** | API Intelligence Contract Alignment | `ScanResponse` exposes typed score breakdowns, 30 buyer intents, cross-page contradictions, and ranked patches. |
| **PROD-5.5** | Failure Isolation | Failures during GitHub PR creation or upstream LLM rate limits never wipe already-computed scan intelligence. |
| **PROD-5.6** | Interactive Frontend Dashboard | Next.js 14 dashboard implements `ScoreGauge`, `IntentMatrix`, `ContradictionCard`, `PatchModal`, `EvidenceViewer`, and SSE progress bars. |
| **PROD-6.1** | SSRF & Crawler Protection | [backend/app/core/security.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/core/security.py) enforces private IP blocking, cloud metadata blocking, and scheme validation. |
| **PROD-6.2** | API Abuse Controls & Security Headers | Sliding-window rate limiting in [backend/app/core/rate_limiter.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/core/rate_limiter.py), `X-API-Key` auth in [backend/app/core/auth.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/core/auth.py), and security headers in [backend/app/main.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/main.py). |
| **PROD-6.4** | Secrets & Log Sanitization | Automated PR engine tests verify that GitHub tokens and auth headers are stripped from log outputs. |
| **PROD-7.1** | Production Containers | Multi-stage Dockerfiles in [backend/Dockerfile](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/Dockerfile) and [frontend/Dockerfile](file:///c:/Users/LENOVO/Desktop/FindableAI/frontend/Dockerfile), orchestrated via `docker-compose.yml`. |
| **PROD-7.2** | Continuous Integration CI | Automated GitHub Actions in [.github/workflows/backend-ci.yml](file:///c:/Users/LENOVO/Desktop/FindableAI/.github/workflows/backend-ci.yml) and [.github/workflows/frontend-ci.yml](file:///c:/Users/LENOVO/Desktop/FindableAI/.github/workflows/frontend-ci.yml) running linting, type checks, unit tests, and production builds. |

---

## 2. Near-Term Engineering Priorities

The following items represent the immediate operational and hardening roadmap:

### PROD-7.3: Database Migration Automation on Deployment
- **Goal:** Ensure automated execution of Alembic migrations (`alembic upgrade head`) on container startup before Uvicorn workers bind to the port.
- **Implementation:** Add an entrypoint wrapper script in `backend/Dockerfile` that runs database migrations with exponential backoff if the PostgreSQL instance is initializing.

### PROD-7.4: Structured Scan Latency & Token Observability
- **Goal:** Provide detailed per-stage timing breakdown (crawl duration, NLI inference time, patch generation latency) and token count histograms in the audit summary response.
- **Implementation:** Extend `AuditSummary` in [backend/app/schemas/scan.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/schemas/scan.py) with structured telemetry metadata.

### PROD-8.1: Continuous E2E Regression Gate
- **Goal:** Automated end-to-end smoke test executing a live crawl against the bundled `demo-site/` corpus during release tagging.

---

## 3. Medium-to-Longer-Term Strategic Enhancements

### Distributed Asynchronous Worker Pool (Celery / ARQ)
- **Context:** The backend currently executes background scans via FastAPI's in-process `BackgroundTasks`. While sufficient for low-to-medium concurrency, high-concurrency multi-tenant workloads can exhaust process CPU and memory.
- **Plan:** Introduce a Celery or ARQ worker pool backed by the existing Redis service (`redis://localhost:6379/0`), allowing crawler and NLI workers to scale independently from the FastAPI REST layer.

### Dynamic Multi-Provider LLM Failover
- **Context:** When primary Groq LPUs reach Output Tokens Per Minute (OTPM) rate limits, the system currently activates the deterministic heuristic engine.
- **Plan:** Implement seamless dynamic failover:
  1. Primary: Groq LPUs (`qwen/qwen3.8-27b`).
  2. Secondary: OpenAI (`gpt-4o-mini`) or Anthropic (`claude-3-haiku`).
  3. Tertiary: Google Gemini (`gemini-1.5-flash`).
  4. Quaternary: Deterministic heuristic engine.

### Webhook Notification Dispatcher
- **Context:** Enterprise users and CI/CD pipelines need automated notifications when audits complete.
- **Plan:** Add an optional `webhook_url` field to `ScanRequest` that posts the finalized `ScanResponse` JSON payload upon scan completion.

---

## 4. Explicit Non-Goals & Architecture Anti-Patterns

To maintain senior engineering focus and minimize operational complexity, the following architectural choices remain explicitly out of scope:
- **No Kubernetes / Service Mesh:** Docker Compose and single-container deployments (Render / Vercel) provide sufficient scalability without orchestration overhead.
- **No Heavy Vector Database:** PostgreSQL with `pgvector` fully satisfies semantic search requirements; standalone vector databases (Pinecone, Weaviate) are unnecessary.
- **No Proprietary Third-Party APM Platforms:** Native structured logging with `X-Request-ID` and standard Prometheus metrics endpoints are preferred over heavy vendor agents.
