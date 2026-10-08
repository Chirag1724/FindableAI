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

- **Status:** Accepted (Updated with Heuristic Structural Validation)
- **Code Evidence:** [backend/app/engines/framework_adapter.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/engines/framework_adapter.py), [backend/app/github/pr_engine.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/github/pr_engine.py).

#### Context
Crawled URL paths (e.g. `/about`) do not map 1:1 to filesystem paths in modern component frameworks (Next.js App Router `app/about/page.tsx`, Pages Router `pages/_app.tsx`, React Router `src/App.tsx`, Vue `src/App.vue`, Astro `src/layouts/Layout.astro`). Direct string injection into JSX/TSX layout files without structural checks risks corrupting component syntax, breaking imports, or failing target repository build pipelines.

#### Decision
Implement a three-tier safe remediation resolution strategy:
1. **Tier 1 (Static HTML Direct Injection):** If an exact or fuzzy `.html`/`.htm` file is found (e.g. `public/index.html` or `index.html`), inject the Schema.org `<script type="application/ld+json">` tag directly into the `<head>` or `<body>`.
2. **Tier 2 (Framework Component Synthesis & Layout Injection with Heuristic Validation):** For component-based repositories (Next.js, React, Vue, Astro):
   - Synthesize a framework-specific component file (`src/components/JsonLd.tsx` or framework equivalent) via `framework_adapter.py` encapsulating the Schema.org JSON-LD microdata.
   - Insert an import statement and component tag (`<JsonLd ... />`) into the identified root layout file (`layout.tsx`, `_app.tsx`, `App.tsx`, `App.vue`, `Layout.astro`).
   - Run a heuristic structural/lexical validation (`validate_framework_layout_syntax`) verifying comment/string stripping, balanced delimiters (`{}`, `()`, `[]`, `<>`), and insertion boundary validity.
   - Framing Note: This validator is a heuristic structural/lexical safety net - not a full TypeScript/JSX compiler - so it reduces risk significantly but cannot guarantee 100% semantic correctness across every possible custom layout.
3. **Tier 3 (Automatic Guidance PR Fallback):** If layout resolution fails, if heuristic syntax validation fails (e.g. unbalanced tags, malformed JSX), or if no safe layout candidate is found, automatically fall back to generating a non-breaking Markdown remediation guide at `docs/FINDABLE_AI_REMEDIATION.md`. The PR commits this comprehensive guide containing tailored Schema.org JSON-LD snippets, DOM anchor references, and copy-paste instructions without modifying application code.

#### Consequences
- Eliminates syntax corruption risks on complex React, Next.js, and Vue codebases.
- Provides native component integration where safe, with guaranteed zero-build-breakage fallback to guidance PRs.
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

---

### ADR-007: Zero-LLM Deterministic AI Lighthouse & Crawler Governance

- **Status:** Accepted (October 2026)
- **Code Evidence:** [backend/app/engines/lighthouse.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/engines/lighthouse.py), [backend/app/engines/robots_analyzer.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/engines/robots_analyzer.py), [backend/app/engines/llms_txt_generator.py](file:///c:/Users/LENOVO/Desktop/FindableAI/backend/app/engines/llms_txt_generator.py).

#### Context
Evaluating search engine readiness across 4 distinct AI search engines (ChatGPT, Gemini, Perplexity, Claude) and auditing crawler governance could introduce latency, token expense, and non-deterministic scoring if driven by prompt-based LLM queries.

#### Decision
Implement AI Lighthouse scoring as a pure deterministic heuristic engine that consumes existing DAG artifacts (DOM AST chunks, Schema.org reports, NLI entailment ratios, contradiction counts) and parses `robots.txt` via `urllib.robotparser`:
1. Use weighted linear scoring formulas specific to each engine's known indexing architecture.
2. Extract a 15-feature mathematical vector from `robots.txt` to calculate the AI Visibility Index (0-100) and Scraping Risk classification.
3. Synthesize Jeremy Howard compliant `/llms.txt` and Pareto-optimal `robots.txt` manifests deterministically.

#### Consequences
- Zero additional LLM tokens or API latency added to audit execution.
- 100% reproducible and verifiable scores across subsequent audits for the same site state.
