# Remediation Lifecycle (Stage 3)

Authoritative map of FindableAI’s evidence-grounded remediation path. Complements [LIMITATIONS_AND_READINESS.md](LIMITATIONS_AND_READINESS.md).

## Trust boundaries

1. Findings and LLM patches are untrusted until durable same-scan evidence and deterministic validators pass.
2. `remediation_eligible is True` is required and **recomputed server-side** from persisted integrity + evidence before GitHub mutation (client flags are not authoritative).
3. Opening a PR is **not** verification.
4. Heuristic post-PR checks never set `fully_verified=true` (enforced in `persist_verification_run`).
5. Projected F-Score deltas are heuristics only — never verification oracles.
6. A GitHub timeout does not prove the PR was not created — reconcile before retrying mutation.
7. Lifecycle transitions use DB compare-and-set (`state_revision`) so stale workers cannot overwrite newer results.
8. Apply/verify are deterministic (no LLM). Any remediation-adjacent LLM call must reserve via `BudgetGuard` first; exhaustion blocks the call and must not trigger GitHub mutation.

## Lifecycle states (`remediation_runs.lifecycle_state`)

| State | Meaning |
| :--- | :--- |
| `validating` / `ready` | Planned / patch validated locally |
| `validation_failed` | Deterministic checks rejected the candidate |
| `mutating` | GitHub write in progress |
| `pr_open` | PR created and identifiers persisted |
| `pr_persist_failed` | GitHub accepted PR; DB persist failed (recoverable) |
| `verifying` | Post-PR verification running |
| `verified` | **Heuristic** check reported `issue_outcome=fixed` (`fully_verified` still false) |
| `failed` | Verification unresolved or operation failed |
| `blocked` | Inconclusive / needs human review |
| `cancelled` | Safely terminated |

Transitions are enforced by `assert_valid_transition` and CAS updates on `(id, state_revision, lifecycle_state)`.

Idempotency key: `{scan_id}|{repo}|{branch}` — unique constraint; cross-scan/repo reuse raises `IdempotencyScopeConflict`.

## Patch safety (before GitHub)

`app/engines/patch_validator.py`:

- Repo-relative path normalization (`PurePosixPath`) — reject absolute, UNC, drive letters, traversal, control/NUL bytes.
- Forbidden paths: `.github/workflows/`, credential filenames, `.env*`, dependency lockfiles.
- Suffix allowlist aligned with PR engine.
- Size / empty / binary NUL checks.
- Secret heuristics on added patch lines (does not log secret values).
- Durable evidence grounding against same-scan chunk IDs.

## Verification

`POST /api/v1/scans/{id}/remediation/verify`:

1. Requires a remediation run with PR metadata.
2. Persists `verifying`.
3. Resolves an **immutable commit SHA** (`head_sha`); refuses branch-only evaluation when SHA cannot be resolved.
4. Fetches content at that SHA; if the branch tip moved, returns inconclusive/stale (does not claim fixed).
5. Runs deterministic content checks + keyword acceptance heuristic.
6. Persists `verification_runs` with `verification_method=heuristic_post_pr`, `fully_verified=false`.
7. Maps outcome → `verified` / `failed` / `blocked`.

## Budget

- Scan DAG LLM calls use scan-scoped `BudgetGuard` (call + optional USD ceiling).
- Apply/verify do not call LLM; `assert_github_mutation_not_tied_to_llm_budget(would_call_llm=False)` documents that invariant.
- Optional remediation LLM helpers (`reserve_remediation_llm_call`) fail closed when exhausted and block mutation if `would_call_llm=True`.

## Configuration

| Variable | Role |
| :--- | :--- |
| `API_KEY` | Production fail-closed auth |
| `GITHUB_TOKEN` | Required for apply + verify (never logged) |
| `MAX_LLM_CALLS_PER_SCAN` / `LLM_ENFORCE_USD_BUDGET` | Scan LLM ceilings |
| `FINDABLE_PG_*` | Disposable Postgres for integration tests only |

## Remaining limitations (honest)

- No full website re-scan after PR (`fully_verified` stays false for heuristic).
- Live GitHub success depends on token permissions — **not proven by mocked CI tests**.
- Framework guidance PRs may commit advisory `.txt` rather than mutating components.
- Production-equivalent CI / multi-worker load tests may still be unverified in a given environment.
