# Troubleshooting Runbook

This runbook documents verified solutions for real issues encountered during the development, testing, and deployment of FindableAI.

---

## Index of Issues

1. [Playwright Headless Browser Binaries Missing](#1-playwright-headless-browser-binaries-missing)
2. [GitHub PR Creation Rejected with Fork Collision](#2-github-pr-creation-rejected-with-fork-collision)
3. [File Not Found Error When Patching Framework Codebases](#3-file-not-found-error-when-patching-framework-codebases)
4. [GitHub PR Creation Failed with Projections Required Error](#4-github-pr-creation-failed-with-projections-required-error)
5. [Groq Output Tokens Per Minute (OTPM) Rate Limit](#5-groq-output-tokens-per-minute-otpm-rate-limit)
6. [Alembic Module Resolution Error on Headless Execution](#6-alembic-module-resolution-error-on-headless-execution)
7. [F-Score Delta Floating-Point Validation Error](#7-f-score-delta-floating-point-validation-error)
8. [Scan Completes in Fallback Mode with Synthetic or Empty Intents](#8-scan-completes-in-fallback-mode-with-synthetic-or-empty-intents)

---

### 1. Playwright Headless Browser Binaries Missing

- **Symptom:**
  `playwright._impl._errors.Error: Executable doesn't exist at C:\Users\...\AppData\Local\ms-playwright\chromium-1117\chrome-win\chrome.exe`
- **Root Cause:**
  The `playwright` Python library was installed via `pip install -r requirements.txt`, but browser binaries were not downloaded to the host cache.
- **Fix:**
  Run the Playwright installer with system dependencies:
  ```bash
  python -m playwright install --with-deps chromium
  ```
- **Code Safeguard:**
  [backend/app/crawler/crawler.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/crawler/crawler.py) catches browser launch failures and automatically degrades to `httpx` + `BeautifulSoup` extraction to prevent scan termination.

---

### 2. GitHub PR Creation Rejected with Fork Collision

- **Symptom:**
  `GitHub PR creation failed: 422 Unprocessable Entity - Cannot fork repository into same account`
- **Root Cause:**
  When a user scanned a repository belonging to their own GitHub account, the PR engine attempted to fork the repository into the authenticated account. GitHub's API explicitly forbids forking a repository into the namespace that already owns it.
- **Fix:**
  The engine now checks push permissions via `has_push_access()` in [backend/app/github/pr_engine.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/github/pr_engine.py):
  1. If the token owner has write access or owns the target repository, it bypasses forking and pushes the branch directly to the source repository.
  2. PR creation calls use the clean branch name (`head=branch_name`) rather than `owner:branch`.

---

### 3. File Not Found Error When Patching Framework Codebases

- **Symptom:**
  `GitHub PR creation failed: file not found: about.html` or syntax errors in modified JSX layout files.
- **Root Cause:**
  The legacy patch generator assumed static HTML files (e.g. `/about` -> `about.html`). Modern component frameworks (Next.js App Router `app/about/page.tsx`, React Router `src/App.tsx`, Vue, Astro) do not use static HTML files. Furthermore, naive string injection into layout files risks breaking JSX syntax or failing builds.
- **Fix:**
  `framework_adapter.py` and `resolve_target_file()` implement a three-tier remediation resolution:
  1. If static HTML files are found, it injects Schema.org JSON-LD scripts directly.
  2. If a framework repository is detected, it synthesizes a standalone component (`src/components/JsonLd.tsx`), mounts it into the root layout, and runs a heuristic structural/lexical syntax check (`validate_framework_layout_syntax()`) verifying balanced tags and delimiters.
  3. If layout resolution fails or heuristic syntax validation detects unbalanced delimiters, it automatically falls back to generating a non-breaking Markdown remediation guide at `docs/FINDABLE_AI_REMEDIATION.md`.

---

### 4. GitHub PR Creation Failed with Projections Required Error

- **Symptom:**
  `GitHub PR creation failed: projections required for PR report` (HTTP 400 returned on `/api/v1/scans/{scan_id}/patches/apply`).
- **Root Cause:**
  `build_report_data()` in `pr_engine.py` contained a hard check `raise PREngineError("projections required for PR report")` if `request.projections` was an empty list. When scans were initiated through the REST API, `PREngineRequest` omitted the internal `projections` list.
- **Fix:**
  - `build_report_data()` in [backend/app/github/pr_engine.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/github/pr_engine.py#L183-L200) was updated to handle missing projections gracefully by deriving scores from `request.current_score`, `request.projected_score`, or patch deltas.
  - [backend/app/api/v1/patches.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/api/v1/patches.py) was consolidated to delegate directly to `apply_scan_patch()` in `scans.py`.

---

### 5. Groq Output Tokens Per Minute (OTPM) Rate Limit

- **Symptom:**
  `litellm.RateLimitError: RateLimitError: GroqException - Rate limit reached for model qwen/qwen3.8-27b on output tokens per minute (OTPM)`
- **Root Cause:**
  High-frequency multi-persona query synthesis exceeded Groq free-tier token burst quotas.
- **Fix:**
  - [backend/app/api/v1/scans.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/api/v1/scans.py#L420-L460) catches rate limit exceptions and activates the deterministic fallback engine (`execution_mode = "deterministic_fallback"`), ensuring audits finish with 30 validated queries and accurate F-Scores.
  - For production environments, upgrade Groq account tiers or configure fallback provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`).

---

### 6. Alembic Module Resolution Error on Headless Execution

- **Symptom:**
  `ModuleNotFoundError: No module named 'app'` when executing `alembic upgrade head` from the backend directory.
- **Root Cause:**
  Alembic runs standalone and does not automatically include the current working directory in Python's `sys.path`.
- **Fix:**
  [backend/alembic/env.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/alembic/env.py) explicitly adds the backend directory to `sys.path`:
  ```python
  import sys
  from os.path import abspath, dirname
  sys.path.insert(0, dirname(dirname(abspath(__file__))))
  ```

---

### 7. F-Score Delta Floating-Point Validation Error

- **Symptom:**
  `pydantic_core._pydantic_core.ValidationError: Value error, delta must equal projected_score - current_score; got 3.33, expected 3.3333333333333357`
- **Root Cause:**
  `delta` was prematurely rounded with `round(..., 2)` in `build_report_data()`, causing Pydantic's strict model validator (`abs(delta - expected) > 1e-9`) to reject the report object.
- **Fix:**
  `build_report_data()` computes `delta = projected - current` without premature rounding, matching the internal float representation of `PRReportData`.

---

### 8. Scan Completes in Fallback Mode with Synthetic or Empty Intents

- **Symptom:**
  UI shows **Fallback Mode**, crawled pages/chunks look real, but intents are synthetic or zero, and the sticky button may say **No fixes required**.
- **Root Cause:**
  Crawl/chunk succeed without an LLM. `execution_mode` is `real_llm` only when evaluations exist **and** `llm_calls_made > 0`. Missing/`GROQ` auth/rate-limit/budget failures leave the scan on a non-real path; `_generate_fallback_evaluations` / mock score/patches may still populate a **completed** response. Frontend treats empty patches as “no fixes” without requiring real evaluations.
- **What to check:**
  1. `GROQ_API_KEY` set and valid; inspect backend logs for LLM / `BudgetGuard` errors.
  2. `GET /api/v1/scans/{id}` → `execution_mode`, `llm_calls_made`, `data_source`.
  3. `GET /api/v1/scans/{id}/intents` vs summary `intents_generated` (multi-worker / restart hydrate can diverge).
- **Product note:** Synthetic or empty intelligence is **not** a successful real-LLM audit. This is a known honesty gap — see [LIMITATIONS_AND_READINESS.md](LIMITATIONS_AND_READINESS.md). Do not “fix” it by documenting it as success.
