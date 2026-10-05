# Architecture Decision Records (ADRs)

This document records the foundational architectural decisions made in FindableAI, detailing the context, decision rationale, and engineering consequences for each choice.

---

## Index of Decisions

- [ADR-001: Canonical F-Score Weight Formulation](#adr-001-canonical-f-score-weight-formulation)
- [ADR-002: Direct-Push-First with Fork Fallback for GitHub PRs](#adr-002-direct-push-first-with-fork-fallback-for-github-prs)
- [ADR-003: Framework Route Detection & Safe Guidance PRs](#adr-003-framework-route-detection--safe-guidance-prs)
- [ADR-004: DAG State Machine Pipeline Orchestration](#adr-004-dag-state-machine-pipeline-orchestration)
- [ADR-005: BudgetGuard & Deterministic Heuristic Fallback](#adr-005-budgetguard--deterministic-heuristic-fallback)
- [ADR-006: Consolidation of Patch PR Endpoints](#adr-006-consolidation-of-patch-pr-endpoints)

---

### ADR-001: Canonical F-Score Weight Formulation

- **Status:** Accepted (Unified in October 2026)
- **Code Evidence:** [backend/app/schemas/scoring.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/schemas/scoring.py#L28-L32), [backend/app/engines/scorer.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/engines/scorer.py), [backend/app/schemas/fscore.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/schemas/fscore.py).

#### Context
Prior iterations had conflicting documentation and code regarding the mathematical weights assigned to the four sub-scores:
- Query Intent Answerability ($S_{ans}$)
- Cross-Page Factual Consistency ($S_{con}$)
- DOM & Schema.org Structural Clarity ($S_{str}$)
- Machine Accessibility & Extractability ($S_{acc}$)

#### Decision
Standardize on the canonical formula:
$$\text{F-Score} = 0.40 \times S_{ans} + 0.30 \times S_{con} + 0.20 \times S_{str} + 0.10 \times S_{acc}$$

- $S_{ans}$ (40%): The primary metric for machine discoverability is whether an AI agent can find an explicit answer to synthetic commercial buyer queries.
- $S_{con}$ (30%): Factual contradictions across pages directly induce hallucinated answers in LLMs; penalizing conflicts heavily prevents inaccurate indexing.
- $S_{str}$ (20%): Machine-readable Schema.org microdata and clean heading hierarchies provide unambiguous semantic grounding.
- $S_{acc}$ (10%): Raw extractability and accessibility of core business metadata (hours, address, contact).

#### Consequences
- Eliminates discrepancy between API schemas, mock generators, and documentation.
- All internal scoring engines and public API DTOs enforce `w_ans=0.40, w_con=0.30, w_str=0.20, w_acc=0.10`.

---

### ADR-002: Direct-Push-First with Fork Fallback for GitHub PRs

- **Status:** Accepted
- **Code Evidence:** [backend/app/github/pr_engine.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/github/pr_engine.py#L380-L425), [backend/app/github/client.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/github/client.py#L180-L205).

#### Context
Initial implementations assumed all automated PRs must fork the target repository. When users audited repositories they owned or had push access to, GitHub's API rejected attempts to fork a repository into the same account that already owns it (`422 Unprocessable Entity`). Furthermore, organizations frequently disable repository forking on private repositories.

#### Decision
Implement a permission-aware strategy in `GitHubPRService.create_remediation_pr()`:
1. Inspect the repository's `permissions` block (`push: true`) or verify same-owner login.
2. If push access is confirmed, create the feature branch directly on the target repository and open a same-repo PR using the bare branch name.
3. If push access is false or absent, fallback to creating or reusing a personal fork (`login:branch`).
4. If forking is disabled on the upstream repository and the user lacks write access, return a clear `forking_disabled` error rather than a generic crash.

#### Consequences
- Enables seamless PR creation on personal, internal, and private repositories without requiring fork permissions.
- Preserves fork fallback for open-source contributions.

---

### ADR-003: Framework Route Detection & Safe Guidance PRs

- **Status:** Accepted
- **Code Evidence:** [backend/app/github/pr_engine.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/github/pr_engine.py#L250-L310), [backend/app/github/pr_engine.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/github/pr_engine.py#L508-L530).

#### Context
Crawled URL paths (e.g. `/about`) do not map 1:1 to filesystem paths in modern component frameworks (Next.js App Router `app/about/page.tsx`, React Router `src/views/About.jsx`, Vue, Astro). Attempting to inject raw HTML or unified diffs directly into JSX/TSX components causes build syntax errors and TypeScript compiler breaks.

#### Decision
Implement two-tier file resolution in `resolve_target_file()`:
1. **Tier 1 (Static HTML):** If an exact or fuzzy `.html`/`.htm` file is found (e.g. `public/index.html` or `index.html`), inject the Schema.org `<script type="application/ld+json">` tag directly into the file.
2. **Tier 2 (Framework Route Match):** If a matching framework component (`.tsx`, `.jsx`, `.vue`, `.astro`, `.svelte`) is detected or no safe static HTML file exists, generate a clean Markdown remediation guide at `docs/FINDABLE_AI_REMEDIATION.md`. The PR commits this guide containing tailored Schema.org JSON-LD snippets, DOM anchor references, and copy-paste instructions.

#### Consequences
- Completely eliminates syntax corruption on React/Next.js/Vue codebases.
- Keeps PR creation safe and actionable across any frontend architecture.

---

### ADR-004: DAG State Machine Pipeline Orchestration

- **Status:** Accepted
- **Code Evidence:** [backend/app/orchestration/dag.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/orchestration/dag.py), [backend/app/orchestration/state.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/orchestration/state.py).

#### Context
A linear procedural script for crawling, query synthesis, NLI evaluation, contradiction detection, and patch generation is difficult to test, resume, or debug when intermediate stages encounter network timeouts or provider failures.

#### Decision
Encapsulate the intelligence workflow in a Directed Acyclic Graph (`FindableAIDAG`) with explicit state transitions (`PLAN`, `OBSERVE`, `ORIENT`, `DECIDE`, `ACT`, `REFLECT`, `STOP`):
1. Each stage receives an immutable `OrchestrationState` context and emits structured artifacts.
2. Failure at an intelligence stage (e.g. LLM budget exceeded) degrades gracefully to heuristic evaluation without aborting the scan.
3. PR creation failures in the `REFLECT` stage never delete or invalidate already-computed score breakdowns and contradiction findings.

#### Consequences
- Enables strict stage-by-stage unit testing with in-memory fixtures.
- Guarantees isolation between intelligence generation and GitHub API mutations.

---

### ADR-005: BudgetGuard & Deterministic Heuristic Fallback

- **Status:** Accepted
- **Code Evidence:** [backend/app/core/budget.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/core/budget.py), [backend/app/core/llm.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/core/llm.py), [backend/app/api/v1/scans.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/api/v1/scans.py#L87-L145).

#### Context
LLM API calls can become expensive or encounter provider rate limits (e.g. Groq Output Tokens Per Minute limits). Unbounded LLM calls create operational reliability risks during high-concurrency audits.

#### Decision
1. Wrap all LLM provider requests in `BudgetGuard`, enforcing a monetary budget cap (`LLM_BUDGET_CAP_USD = 0.01`) and hard call ceiling (`MAX_LLM_CALLS_PER_SCAN = 35`).
2. Implement deterministic fallback generators in `scans.py` that synthesize 30 buyer queries across 10 commercial categories, detect contradictions via regex patterns, and compute valid Schema.org microdata when LLMs are unavailable.

#### Consequences
- Zero scan crashes when upstream AI providers experience outages or rate limits.
- Guaranteed predictable operating costs per audit.

---

### ADR-006: Consolidation of Patch PR Endpoints

- **Status:** Accepted (Unified in October 2026)
- **Code Evidence:** [backend/app/api/v1/patches.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/api/v1/patches.py), [backend/app/api/v1/scans.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/api/v1/scans.py#L1103-L1258).

#### Context
`patches.py` (`POST /api/v1/patches/apply-pr`) and `scans.py` (`POST /api/v1/scans/{scan_id}/patches/apply`) maintained separate, drifting implementations of the PR creation workflow, leading to duplicated bugs around missing projection data and hardcoded fallback placeholders.

#### Decision
Consolidate `patches.py` to delegate 100% directly to `scans.py`'s `apply_scan_patch()`:
- `apply_patch_as_pr` resolves the scan record in `SCANS_DB`, binds the target repo URL override, and invokes the canonical `apply_scan_patch` function.
- All GitHub client initialization, score derivations, and PR engine executions exist in a single location.

#### Consequences
- Eliminates duplicate PR request assembly and error translation logic.
- Prevents future divergence between scan-level and patch-level PR operations.
