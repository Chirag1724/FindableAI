# AI Website Health Brief (AI Summary)

Canonical engineering reference for the on-demand **AI Website Health Brief** feature (UI label: **AI Summary**). Derived from `backend/app/orchestration/scan_summary.py`, `backend/app/schemas/summary.py`, `backend/app/api/v1/scans.py`, Alembic `0018`/`0019`, `.env.example`, and `render.yaml`.

**Not the same as** scan pipeline `AuditSummary` / `summary` stats on `GET /api/v1/scans/{id}` (pages crawled, intents generated, etc.). Those are deterministic crawl metrics. This feature is a separate Gemini-backed narrative brief.

---

## 1. End-to-end architecture

```text
Completed scan (worker/API pipeline)
        │
        ▼
prepare_summary_input()  ──►  scans.summary_input (+ hash, prepared_at)
        │                      (no LLM; grounded snapshot JSON)
        ▼
User opens AI Summary tab / clicks generate
        │
   GET  /api/v1/scans/{id}/summary   ← cache lookup only (no LLM)
   POST /api/v1/scans/{id}/summary   ← generate or return cache
        │
        ├─ eligibility (completed + eligible outcome)
        ├─ load_or_build_snapshot (prefer prepared summary_input)
        ├─ cache hit on scan_summaries? → 200 ready (cached=true)
        ├─ single-flight insert status=generating
        ├─ Gemini structured generation (SUMMARY_* keys/model)
        ├─ validate / soft-drop / schema repair / truncation repair
        ├─ key failover (SUMMARY → SUMMARY1 → GEMINI → GROQ)
        └─ persist scan_summaries status=ready → 200 (cached=false)
        │
        ▼
Frontend AiHealthBrief renders brief; polls GET if POST returned 202
```

| Stage | What runs | LLM? |
| :--- | :--- | :--- |
| Scan complete | `prepare_summary_input` after successful pipeline persistence | No |
| GET summary | Lookup `scan_summaries` by `(scan_id, input_hash, prompt_version, model)` | No |
| POST summary (cache hit) | Same lookup; return ready payload | No |
| POST summary (miss) | Gemini via LiteLLM/Instructor; validate; persist | Yes |
| UI refresh | GET (and optional poll while `generating`) | No |

**Versions (hard-coded in orchestration):**

| Constant | Value | Role |
| :--- | :--- | :--- |
| `PROMPT_VERSION` | `v2` | Prompt / cache key dimension |
| `CONTEXT_SCHEMA_VERSION` | `ctx_v2` | Snapshot schema; mismatch forces rebuild |

---

## 2. API

### Paths

| Method | Primary | Alias (Contract 2) |
| :--- | :--- | :--- |
| `GET` | `/api/v1/scans/{scan_id}/summary` | `/api/scans/{scan_id}/summary` |
| `POST` | `/api/v1/scans/{scan_id}/summary` | `/api/scans/{scan_id}/summary` |

- **Query parameter:** `scope` (optional, default `intelligence`):
  - `intelligence`: Search query claim evaluation, gaps, and grounded findability analysis.
  - `lighthouse`: AI crawler governance, bot access policies, and per-engine readiness.
- **Request body:** none (both methods).
- **Response model:** `SummaryResponse` ([backend/app/schemas/summary.py](../../backend/app/schemas/summary.py)).
- **Handlers:** `get_scan_summary` / `post_scan_summary` in [backend/app/api/v1/scans.py](../../backend/app/api/v1/scans.py).

### Authentication & tenancy

The scans router uses `dependencies=[Depends(verify_api_key)]`.

| Situation | Behavior |
| :--- | :--- |
| `API_KEY` empty, non-production, no key sent | Allowed (system-admin `TenantContext`) |
| `API_KEY` set or org API key | Require `X-API-Key` or `Authorization: Bearer <key>` |
| Production with empty `API_KEY` | `503` (fail-closed) |
| Missing/invalid key when required | `401` |
| Authenticated but lacks `read_scans` | `403` via `assert_permission(..., OrgAction.READ_SCANS)` |
| Scan missing / wrong org | `404` |

Summary routes are **read-like** (GET and POST both require `READ_SCANS`). Generation does **not** increment `scan.llm_calls_made` / scan `MAX_LLM_CALLS_PER_SCAN` budget.

### Status codes (POST)

| HTTP | `status` field | Typical `reason` |
| :--- | :--- | :--- |
| `200` | `ready` | Cache hit or fresh generation |
| `202` | `generating` | `summary_generating` (peer in-flight) |
| `409` | `none` | `scan_queued` / `scan_running` / `scan_failed` / `scan_cancelled` / `scan_ineligible` |
| `429` | `failed` | `summary_rate_limited` (+ `retry_after` seconds) |
| `502` | `failed` | `summary_generation_failed` / `provider_auth_error` / `provider_model_rejected` |

GET authorized success is always **`200`**. Payload may be `status: "none"` (no ready cache) or `status: "ready"`.

### Response fields (ready brief)

| Field | Notes |
| :--- | :--- |
| `status` | `none` \| `generating` \| `ready` \| `failed` |
| `verdict` | Server-computed: `scan_incomplete` \| `insufficient_evidence` \| `issues_found` \| `no_confirmed_issues` |
| `overall_assessment` | `{ text, fact_ids }` |
| `what_the_scan_found` / `why_it_matters` / `evidence_gaps` | Lists of `{ text, fact_ids }` |
| `next_steps` | `{ text, priority, fact_ids }` (`high` \| `medium` \| `low`) |
| `limitations` | Free text |
| `signals` / `coverage` / `omitted` | Snapshot metadata |
| `remediation_status` / `remediation_reason` | Live label at read time |
| `generated_at` / `model` / `cached` | Observability; UI may omit showing `cached` |
| `reason` / `message` / `retry_after` | Error / in-progress messaging |

Optional legacy fields (`headline`, `overview`, `items`) may appear for older clients; v2 clients should use the structured fields above.

### Example: check cache (no LLM)

```bash
curl -sS -H "X-API-Key: YOUR_API_KEY" \
  "http://localhost:8000/api/v1/scans/SCAN_ID/summary"
```

Redacted none response:

```json
{
  "status": "none",
  "verdict": "issues_found",
  "overall_assessment": null,
  "what_the_scan_found": [],
  "why_it_matters": [],
  "evidence_gaps": [],
  "next_steps": [],
  "limitations": "",
  "signals": {
    "all_intents_unknown": false,
    "zero_dom_chunks": false,
    "single_page_crawl": false,
    "score_pillar_mismatch": false,
    "lighthouse_available": true,
    "remediation_unavailable_reason": null,
    "weighted_pillar_sum": 72.4,
    "overall_score": 72.4
  },
  "omitted": [],
  "coverage": {
    "evaluations_completed": 10,
    "evaluations_total": 10,
    "findings_included": 3,
    "omitted_count": 0
  },
  "cached": false,
  "reason": null,
  "message": null
}
```

### Example: generate or return cache

```bash
curl -sS -X POST -H "X-API-Key: YOUR_API_KEY" \
  "http://localhost:8000/api/v1/scans/SCAN_ID/summary"
```

Redacted ready response:

```json
{
  "status": "ready",
  "verdict": "issues_found",
  "overall_assessment": {
    "text": "Hours and pricing appear inconsistent across pages.",
    "fact_ids": ["C_total", "E_contradicted_count"]
  },
  "what_the_scan_found": [
    {
      "text": "Two different hour ranges appear in crawl evidence.",
      "fact_ids": ["C_<uuid>", "F_dom_chunks"]
    }
  ],
  "why_it_matters": [
    {
      "text": "Visitors may arrive when you are closed.",
      "fact_ids": ["C_<uuid>"]
    }
  ],
  "evidence_gaps": [],
  "next_steps": [
    {
      "text": "Publish one hours block on every page that mentions hours.",
      "priority": "high",
      "fact_ids": ["C_<uuid>"]
    }
  ],
  "limitations": "Brief is grounded only in this scan’s stored evidence.",
  "coverage": {
    "evaluations_completed": 10,
    "evaluations_total": 10,
    "findings_included": 3,
    "omitted_count": 0
  },
  "remediation_status": "not_started",
  "generated_at": "2026-10-20T04:12:00.000000Z",
  "model": "gemini/gemini-3.5-flash-lite",
  "cached": false,
  "reason": null,
  "message": null
}
```

---

## 3. Configuration

Source of truth: [backend/app/core/config.py](../../backend/app/core/config.py), mirrored in [.env.example](../../.env.example) and [render.yaml](../../render.yaml) (web + worker).

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `GEMINI_API_KEY_AI_SUMMARY` | `""` | Primary dedicated key for Health Brief |
| `GEMINI_API_KEY_AI_SUMMARY1` | `""` | Secondary dedicated key |
| `GEMINI_API_KEY` | `""` | Third fallback for summary keys |
| `GROQ_API_KEY` | `""` | Last-resort key in the summary key list |
| `SUMMARY_LLM_MODEL` | `gemini/gemini-3.5-flash-lite` | LiteLLM model id (**include** `gemini/` prefix) |
| `SUMMARY_MAX_FINDINGS` | `25` | Snapshot findings cap |
| `SUMMARY_MAX_OUTPUT_TOKENS` | `8192` | Primary completion budget |
| `SUMMARY_MAX_OUTPUT_TOKENS_REPAIR` | `12288` | Raised budget after truncation |
| `SUMMARY_LLM_TIMEOUT_SECONDS` | `60` | Per-call timeout; also drives stale `generating` reclaim (`2×`) |
| `SUMMARY_LLM_MAX_CALLS` | `4` | Max LLM attempts per generation (incl. repairs) |
| `SUMMARY_PROVIDER_BACKOFF_SECONDS` | `1.5` | Backoff between key/model retries |
| `SUMMARY_RATE_LIMIT_PER_SCAN_PER_HOUR` | `3` | Distinct generation attempts / scan / hour |
| `SUMMARY_RATE_LIMIT_PER_ORG_PER_DAY` | `30` | Distinct generation attempts / org / day |

### Key precedence (verified)

`_summary_api_keys()` builds an ordered **unique** list:

1. `GEMINI_API_KEY_AI_SUMMARY`
2. `GEMINI_API_KEY_AI_SUMMARY1`
3. `GEMINI_API_KEY`
4. `GROQ_API_KEY` (last resort)

Empty entries are skipped. If the list is empty → POST `502` with `provider_auth_error`.

The summary `LLMClient` is constructed with **`allow_provider_failover=False`**, so Gemini failures do **not** spill into the scan-pipeline multi-provider failover path inside `LLMClient`. Retry uses the next key in the list above (and repair/compact loops), not automatic Groq model switching for the same call.

### Model naming

- Prefer a current Flash-class Gemini id. New Google AI keys often **404** on older ids such as `gemini-2.5-flash`.
- Default used in code / Render: `gemini/gemini-3.5-flash-lite`.
- Separate from scan `GEMINI_MODEL` (default `gemini-2.5-flash`).

### Safe `.env` sketch (placeholders only)

```bash
# AI Website Health Brief — never commit real keys
GEMINI_API_KEY_AI_SUMMARY=your_primary_gemini_summary_key
GEMINI_API_KEY_AI_SUMMARY1=your_secondary_gemini_summary_key
SUMMARY_LLM_MODEL=gemini/gemini-3.5-flash-lite
SUMMARY_MAX_OUTPUT_TOKENS=8192
```

---

## 4. Data model, cache, and reliability

### Migrations

| Revision | Change |
| :--- | :--- |
| `0018_scan_summaries` | Creates `scan_summaries` cache table + unique `(scan_id, input_hash, prompt_version, model)` |
| `0019_summary_input_snapshot` | Adds `scans.summary_input`, `summary_input_hash`, `summary_input_prepared_at` |

Apply with:

```bash
cd backend
alembic upgrade head
```

### Snapshot (`scans.summary_input`)

Built by `build_scan_snapshot` / `prepare_summary_input` from persisted scan graph: DOM chunk counts, intents + evidence excerpts, contradictions (capped), patch titles (capped), F-Score pillars, lighthouse (if available), remediation eligibility, warnings → `facts`, `allowed_fact_ids`, `verdict`, `signals`, `coverage`, `omitted`.

- Persisted at scan completion (best-effort; failures are logged and skipped).
- `load_or_build_snapshot` reuses stored JSON when `context_schema_version` / `prompt_version` match and hash is consistent; otherwise rebuilds.

### Cache (`scan_summaries`)

| Column | Role |
| :--- | :--- |
| `input_hash` | SHA-256 over versioned facts payload |
| `prompt_version` / `model` | Cache dimensions |
| `status` | `generating` \| `ready` \| `failed` |
| `content` | JSONB brief body |
| tokens / `latency_ms` / `error_code` | Observability |

**Invalidation:** changing prompt version, context schema, model string, or grounded facts (new hash) misses the cache and requires regeneration. Remediation labels are attached at read time and do **not** force regeneration.

**Idempotency / single-flight:** `ON CONFLICT DO NOTHING` on the unique cache key; concurrent POSTs see `generating` → `202`. Stale generating/failed rows may be reclaimed after `2 * SUMMARY_LLM_TIMEOUT_SECONDS`.

**Validation & repair:**

- Fact ids, numbers, and URLs must be grounded in the snapshot.
- Soft-drop bad bullets; hard-fail on overall assessment / forbidden “healthy” language for incomplete/insufficient verdicts / empty required lists.
- `_ensure_evidence_gaps` can fill gaps server-side for `insufficient_evidence`.
- Truncation → compact prompt + `SUMMARY_MAX_OUTPUT_TOKENS_REPAIR`.
- Schema coercion: lite models often return a single object instead of a one-item array (`LlmSummaryPayload` validators).

---

## 5. Frontend

| Piece | Role |
| :--- | :--- |
| `frontend/src/lib/api.ts` | `getScanSummary` (GET), `generateScanSummary` (POST; treats 2xx including 202 as success) |
| `frontend/src/components/AiHealthBrief.tsx` | Tab control + brief UI |
| `frontend/src/lib/scanReportTabs.ts` | `?tab=summary` routing |
| `frontend/src/app/scans/[id]/page.tsx` | Hosts AI Summary tab beside Overview / Lighthouse |

UI flow: mount GET → if not ready, user/tab triggers POST → if `generating`, poll GET every ~2s (timeout ~60s). Collapsed panel keeps mount so state survives tab switches.

---

## 6. Operations

### Requirements

1. PostgreSQL with migrations through **`0019_summary_input_snapshot`** (and `0018`).
2. Completed eligible scan (`status=completed`, outcome in `{success, partial, ""}`).
3. At least one usable key in the summary key chain (ideally dedicated Gemini summary keys).
4. **`SUMMARY_LLM_MODEL`** reachable for those keys.
5. Summary generation runs **inside the API process** on POST (not a separate summary worker). Durable **scan** workers still prepare `summary_input` at scan complete — configure summary keys on the **web** service for generate; worker benefits from DB reachability for prepare.

### Local smoke

```bash
# After scan completes:
curl -sS -X POST -H "X-API-Key: YOUR_API_KEY" \
  "http://localhost:8000/api/v1/scans/SCAN_ID/summary"
```

Or open the scan report → **AI Summary** tab in the UI (`NEXT_PUBLIC_API_URL` pointing at the backend).

### Troubleshooting (summary-specific)

| Symptom | Likely cause | What to check |
| :--- | :--- | :--- |
| `502` + `provider_auth_error` | No usable keys | `GEMINI_API_KEY_AI_SUMMARY*` / `GEMINI_API_KEY` |
| `502` + `provider_model_rejected` | Model 404 / not allowed for key | Set `SUMMARY_LLM_MODEL=gemini/gemini-3.5-flash-lite` (or another allowed Flash-class id) |
| `502` + `summary_generation_failed` | Validation failure, truncation, or provider error | Raise `SUMMARY_MAX_OUTPUT_TOKENS`; inspect backend logs `scan_summary_*` |
| `429` + `summary_rate_limited` | Per-scan/hour or per-org/day caps | Wait `retry_after`; tune `SUMMARY_RATE_LIMIT_*` |
| `409` | Scan not eligible | Finish scan; outcome must be success/partial |
| `202` then stuck | Peer generate hung | Wait `2× SUMMARY_LLM_TIMEOUT_SECONDS` for reclaim; retry POST |
| UI shows none forever | Snapshot/hash mismatch or failed prepare | Confirm migrations; check `summary_input` on scan row |

Broader ops: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### Tests

```bash
# Backend unit (no PostgreSQL)
cd backend
pytest tests/test_scan_summary.py -q

# Backend PG integration (requires FINDABLE_PG_INTEGRATION=1 + disposable Postgres)
# See TESTING.md and CI workflow backend-pg-integration
pytest tests/test_scan_summary_pg.py -q

# Frontend
cd frontend
npx vitest run src/components/AiHealthBrief.test.tsx src/lib/api.test.ts src/lib/scanReportTabs.test.ts
```

Do not treat historical suite totals as a live pass certificate unless re-run.

---

## 7. Source map

| Area | Path |
| :--- | :--- |
| Orchestration | `backend/app/orchestration/scan_summary.py` |
| Schemas | `backend/app/schemas/summary.py` |
| Routes | `backend/app/api/v1/scans.py` (`get_scan_summary`, `post_scan_summary`) |
| Models | `backend/app/models/database.py` (`ScanSummary`, `Scan.summary_input*`) |
| Migrations | `backend/alembic/versions/0018_scan_summaries.py`, `0019_summary_input_snapshot.py` |
| Config | `backend/app/core/config.py`, `.env.example`, `render.yaml` |
| Frontend | `frontend/src/components/AiHealthBrief.tsx`, `frontend/src/lib/api.ts` |
| Unit tests | `backend/tests/test_scan_summary.py` |
| PG tests | `backend/tests/test_scan_summary_pg.py` |
