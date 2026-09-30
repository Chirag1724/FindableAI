# Graph Report - FindableAI  (2026-09-25)

## Corpus Check
- 70 files · ~94,890 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 7 file(s) not represented in the graph (top: (none) 2, .css 2, .example 1)

## Summary
- 719 nodes · 1845 edges · 39 communities (30 shown, 9 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 215 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community_0
- Community_1
- Community_2
- Community_3
- Community_4
- Community_5
- Community_6
- Community_7
- Community_8
- Community_9
- Community_10
- Community_11
- Community_12
- Community_13
- Community_14
- Community_15
- Community_16
- Community_17
- Community_18
- Community_19
- Community_20
- Community_21
- Community_22
- Community_23
- Community_24
- Community_25
- Community_26
- Community_27
- Community_28
- Community_29
- Community_30
- Community_31
- Community_32
- Community_33
- Community_34
- Community_35

## God Nodes (most connected - your core abstractions)
1. `LLMClient` - 39 edges
2. `EntailmentStatus` - 34 edges
3. `ContradictionSeverity` - 31 edges
4. `_llm()` - 30 edges
5. `EntailmentEngine` - 29 edges
6. `analyze_schema_org()` - 29 edges
7. `FakeChunk` - 29 edges
8. `detect_contradictions()` - 24 edges
9. `ContradictionDetector` - 23 edges
10. `IntentEvaluation` - 22 edges

## Surprising Connections (you probably didn't know these)
- `apply_patch_as_pr()` --uses--> `PullRequestResult`  [INFERRED]
  backend/app/api/v1/patches.py → backend/app/schemas/patch.py
- `run_scan_pipeline()` --uses--> `ChunkData`  [INFERRED]
  backend/app/api/v1/scans.py → backend/app/crawler/dom_chunker.py
- `run_scan_pipeline()` --uses--> `Scan`  [INFERRED]
  backend/app/api/v1/scans.py → backend/app/models/database.py
- `create_scan()` --uses--> `SSRFSecurityException`  [INFERRED]
  backend/app/api/v1/scans.py → backend/app/core/security.py
- `create_scan()` --uses--> `Scan`  [INFERRED]
  backend/app/api/v1/scans.py → backend/app/models/database.py

## Import Cycles
- None detected.

## Communities (39 total, 9 thin omitted)

### Community 0 - "Community_0"
Cohesion: 0.07
Nodes (68): build_nli_user_prompt(), _chunk_id(), default_hybrid_retriever(), EntailmentEngine, EntailmentError, evaluate_intent(), evaluate_intents(), format_evidence_for_prompt() (+60 more)

### Community 1 - "Community_1"
Cohesion: 0.06
Nodes (29): BudgetExhausted, LLMClient, Any, Exception, Shared async LLM client with Instructor structured outputs and call budget., Execute a structured completion and validate into ``response_model``. Raises:…, Raised when the per-pipeline LLM call budget has been fully consumed., Single reusable async client for structured LLM calls. Engines must use this… (+21 more)

### Community 2 - "Community_2"
Cohesion: 0.07
Nodes (42): AsyncClient, is_ip_blocked(), Raised when a URL targets a prohibited or internal network resource., Return True if the given IP address falls within any blocked subnet., Validate that a given target URL is safe to crawl and cannot be used for…, SSRFSecurityException, validate_target_url(), AsyncCrawler (+34 more)

### Community 3 - "Community_3"
Cohesion: 0.12
Nodes (41): Intelligence engines package., _build_system_prompt(), _build_user_prompt(), _category_distribution(), generate_intents(), IntentGenerationError, IntentGenerator, _normalize_for_dedupe() (+33 more)

### Community 4 - "Community_4"
Cohesion: 0.15
Nodes (45): ContradictionDetector, detect_contradictions(), normalize_phone(), normalize_price(), BaseModel, Internal LLM response for ambiguous semantic pairs only., Canonical phone form for comparison. Indian mobiles are normalized to ``+91`` +…, Hybrid contradiction detector over caller-provided evidence chunks. (+37 more)

### Community 5 - "Community_5"
Cohesion: 0.09
Nodes (40): addresses_are_compatible(), _build_contradiction(), ContradictionDetectionError, dedupe_contradictions(), _email_entity_hint(), EvidenceChunk, extract_facts(), extract_facts_from_chunk() (+32 more)

### Community 6 - "Community_6"
Cohesion: 0.16
Nodes (31): _emit_event(), generate_mock_fscore(), generate_mock_patches(), get_scan(), get_scan_patches(), UUID, Autonomous scan worker pipeline: 1. BFS Crawl (httpx / Playwright fallback) 2.…, Fetches status and results of a scan. (+23 more)

### Community 7 - "Community_7"
Cohesion: 0.12
Nodes (20): Settings, get_embeddings_batch(), Generate 1536-dimensional embeddings for a batch of text strings., ChunkData, hybrid_search(), AsyncSession, UUID, Persist extracted DOM chunks into the database associated with a scan. (+12 more)

### Community 8 - "Community_8"
Cohesion: 0.18
Nodes (26): analyze_schema_org(), calculate_structure(), Parse untrusted JSON-LD from HTML documents (BeautifulSoup + json.loads).…, S_str from equal-weight coverage of structurally valid required schema types., SchemaOrgReport, _html_with_jsonld(), Unit tests for deterministic F-score calculator and Schema.org checker., test_s_str_all_six_present() (+18 more)

### Community 9 - "Community_9"
Cohesion: 0.11
Nodes (19): health_check(), HealthCheckResponse, BaseModel, get, System health check endpoint., apply_patch_as_pr(), ApplyPatchRequest, BaseModel (+11 more)

### Community 10 - "Community_10"
Cohesion: 0.18
Nodes (15): Base, Business, Contradiction, DOMChunk, Evidence, Intent, Patch, Scan (+7 more)

### Community 11 - "Community_11"
Cohesion: 0.13
Nodes (15): DOMChunker, Parse HTML and decompose it into semantic chunks with CSS selector paths., Structural DOM Chunker that splits HTML at semantic tag boundaries and…, Strip non-content elements and comments from DOM tree in-place., Derive a unique, DevTools-verifiable CSS selector path for an element by…, Verify that generated CSS selectors can be queried back by BeautifulSoup., Test chunker against the actual Bistro 2026 testbed pages., test_chunker_basic_extraction() (+7 more)

### Community 12 - "Community_12"
Cohesion: 0.13
Nodes (18): calculate_f_score(), provisional_score_weights(), Exception, Raised when scorer inputs violate contracts (not for optional JSON-LD issues)., Provisional defaults aligned with docs/01 & docs/04 (pending team confirmation)., Weighted aggregation F = Σ w_i * S_i with validated components and weights., ScorerError, validate_component_score() (+10 more)

### Community 13 - "Community_13"
Cohesion: 0.11
Nodes (18): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+10 more)

### Community 14 - "Community_14"
Cohesion: 0.18
Nodes (16): All data required for a deterministic score pass (no I/O inside Scorer)., Pure evaluation layer: supplied intelligence artifacts → ScoreBreakdown., score(), ScoreInputs, Scorer, Deterministic Findability score breakdown (ScanResult-compatible fields)., ScoreBreakdown, EvidenceLikeChunk (+8 more)

### Community 15 - "Community_15"
Cohesion: 0.13
Nodes (14): name, private, version, autoprefixer, clsx, eslint, eslint-config-next, postcss (+6 more)

### Community 16 - "Community_16"
Cohesion: 0.16
Nodes (13): asyncio, do_run_migrations(), Run migrations in 'offline' mode., In this scenario we need to create an Engine and associate a connection with…, Run migrations in 'online' mode., run_async_migrations(), run_migrations_offline(), run_migrations_online() (+5 more)

### Community 17 - "Community_17"
Cohesion: 0.16
Nodes (11): AuditSummary, DOMSelectorAnchor, FScoreBreakdown, PatchProposal, PatchType, ScanResponse, ScanStatus, ScanStatusEvent (+3 more)

### Community 18 - "Community_18"
Cohesion: 0.24
Nodes (12): calculate_consistency(), _contradiction_impact(), _dedupe_contradictions(), S_con = 100 * (1 - normalized_impact). normalized_impact = min(1,…, ContradictionSeverityWeights, Relative impact of contradiction severities on S_con (configurable)., _contra(), test_s_con_bounded() (+4 more)

### Community 19 - "Community_19"
Cohesion: 0.26
Nodes (11): _deterministic_fallback_embedding(), get_embedding(), Generate a deterministic, unit-normalized float vector of length `dim` derived…, Generate a 1536-dimensional embedding vector for a single text string. Uses…, asyncio, test_create_scan_and_get_details(), test_deterministic_fallback_embedding(), test_get_embedding_and_batch() (+3 more)

### Community 20 - "Community_20"
Cohesion: 0.24
Nodes (11): _as_type_list(), _FactCountResolution, _iter_jsonld_nodes(), _matches_required_type(), Any, Deterministic Findability F-score calculator + Schema.org JSON-LD checker.…, Resolve the S_con denominator. Preference order: 1. Explicit…, _resolve_fact_count() (+3 more)

### Community 21 - "Community_21"
Cohesion: 0.24
Nodes (12): calculate_accessibility(), Protocol, S_acc: machine extractability from DOM chunks (not WCAG). Signals actually…, TextChunk, FakeChunk, test_s_acc_empty(), test_s_acc_fully_extractable(), test_s_acc_heading_ratio_deterministic() (+4 more)

### Community 22 - "Community_22"
Cohesion: 0.20
Nodes (10): devDependencies, autoprefixer, eslint, eslint-config-next, postcss, tailwindcss, @types/node, @types/react (+2 more)

### Community 23 - "Community_23"
Cohesion: 0.33
Nodes (9): calculate_answerability(), S_ans: mean contribution of entailment statuses (0-100). SUPPORTED=100,…, _eval(), test_s_ans_all_contradicted(), test_s_ans_all_supported(), test_s_ans_all_unknown(), test_s_ans_empty(), test_s_ans_mixed() (+1 more)

### Community 24 - "Community_24"
Cohesion: 0.32
Nodes (8): get_scan_chunks(), get_scan_contradictions(), get_scan_intents(), Any, get, Returns all extracted DOM chunks for this scan (Task P1-2.3 & Interface…, Returns synthetic intent evaluations for this scan (Task P1-2.3)., Returns detected factual contradictions across crawled pages (Task P1-2.3).

### Community 25 - "Community_25"
Cohesion: 0.29
Nodes (6): ComponentDiagnostics, BaseModel, field_validator, Scorer / Schema.org report contracts (Phase E). Coexist with API…, Explainable per-component diagnostics (only include supported signals)., SchemaTypeResult

### Community 26 - "Community_26"
Cohesion: 0.29
Nodes (7): dependencies, clsx, lucide-react, next, react, react-dom, tailwind-merge

### Community 27 - "Community_27"
Cohesion: 0.29
Nodes (3): frontend_src_app_globals, metadata, next

### Community 28 - "Community_28"
Cohesion: 0.33
Nodes (6): apply_scan_patch(), create_scan(), post, Initiates an asynchronous machine discoverability scan. Validates URL SSRF…, Triggers autonomous GitHub PR creation for this scan's proposed patches (Task…, BackgroundTasks

### Community 29 - "Community_29"
Cohesion: 0.40
Nodes (5): scripts, build, dev, lint, start

## Knowledge Gaps
- **62 isolated node(s):** `extends`, `next/core-web-vitals`, `nextConfig`, `name`, `version` (+57 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 253 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `LLMClient` connect `Community_1` to `Community_0`, `Community_3`, `Community_4`, `Community_5`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `EntailmentStatus` connect `Community_0` to `Community_1`, `Community_3`, `Community_6`, `Community_8`, `Community_14`, `Community_20`, `Community_23`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Why does `DOMChunker` connect `Community_11` to `Community_6`, `Community_7`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `LLMClient` (e.g. with `ContradictionDetector` and `detect_contradictions()`) actually correct?**
  _`LLMClient` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `EntailmentStatus` (e.g. with `EntailmentEngine` and `validate_intent_evaluation()`) actually correct?**
  _`EntailmentStatus` has 26 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `ContradictionSeverity` (e.g. with `_build_contradiction()` and `ContradictionDetector`) actually correct?**
  _`ContradictionSeverity` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `EntailmentEngine` (e.g. with `BudgetExhausted` and `LLMClient`) actually correct?**
  _`EntailmentEngine` has 17 INFERRED edges - model-reasoned connections that need verification._