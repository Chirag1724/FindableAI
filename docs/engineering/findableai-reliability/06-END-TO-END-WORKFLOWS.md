# 06 — End-to-End Workflows

---

## 1. Current scan sequence (Current)

```mermaid
sequenceDiagram
  autonumber
  participant UI as Frontend
  participant API as FastAPI
  participant PG as PostgreSQL
  participant W as Worker
  participant WEB as Website
  participant LLM as LLM provider
  participant GH as GitHub

  UI->>API: POST /api/v1/scans
  API->>PG: persist scan + scan_jobs
  API-->>UI: scan id
  W->>PG: claim SKIP LOCKED
  W->>WEB: crawl / extract
  W->>PG: chunks / embeddings
  W->>LLM: intents / evaluations (BudgetGuard)
  W->>PG: evidence / scores / patches
  opt Remediation
    W->>GH: create/reconcile PR
    W->>W: evaluate_verification_outcome heuristics
    W->>PG: verification run
  end
  W->>PG: job succeeded + scan final
  UI->>API: poll / SSE
  Note over UI,API: SSE only sees API process memory (F-01)
  API-->>UI: status / events
```

---

## 2. Current workflow flowchart (Current)

```mermaid
flowchart TD
  A[Submit URL] --> B{Valid + idempotent?}
  B -->|no| X[4xx]
  B -->|yes| C[Persist scan + enqueue job]
  C --> D[Worker claim]
  D --> E[Crawl + DOM]
  E --> F[Chunk + embed]
  F --> G[Buyer intents]
  G --> H[Hybrid retrieve + RRF]
  H --> I[LLM evaluate + validate]
  I --> J[Evidence + score + integrity]
  J --> K[Patches + validate]
  K --> L{Remediate?}
  L -->|no| M[Finalize scan]
  L -->|yes| N[GitHub PR reconcile]
  N --> O[Heuristic post-PR verify]
  O --> M
  E -->|error| R{Retryable?}
  F -->|error| R
  I -->|error| R
  R -->|yes attempts left| Q[Requeue full pipeline]
  R -->|no| F1[Job failed]
  Q --> D
```

---

## 3. Stage I/O summary (Current)

| Stage | Inputs | Outputs / persistence | Failure modes |
| :--- | :--- | :--- | :--- |
| 1 Submit | URL, client key | Scan + job rows | Validation, DB down |
| 2 Claim | Queued jobs | Lease + fence | Contention, DB |
| 3 Crawl | URL | Pages/DOM | Timeout, block |
| 4 Chunk/embed | DOM | Chunks, vectors | Embed provider fail |
| 5 Intents | Site context | Intent set | LLM/schema |
| 6 Retrieve | Intents + index | Ranked evidence | Empty index |
| 7 Evaluate | Evidence + prompts | Structured findings | 429, schema |
| 8 Evidence/score | Findings | Evidence rows, scores | Integrity fail |
| 9 Patches | Findings | Patch artifacts | Validation fail |
| 10 GitHub | Valid patches | PR id | API timeout |
| 11 Verify | PR content + keywords | Outcome enum | Inconclusive |
| 12 Deliver | Scan id | UI via poll/SSE | SSE empty if split |

---

## 4. Proposed Durable Scan Execution Engine (Proposed)

Full target workflow (ingestion → resume/cache → evaluate with recovery → remediate → publish). **Not current production behavior.** Same diagram lives in [04-PROPOSED-ARCHITECTURE.md](./04-PROPOSED-ARCHITECTURE.md) §3.1.

```mermaid
flowchart TD
  Start[Client submits scan] --> PersistScan[Persist Scan + ScanJob]
  PersistScan --> Queue[PostgreSQL durable job queue]
  Queue --> Claim[Worker claims job using lease + fencing token]

  Claim --> LoadCP[Load checkpoint and restore budget]
  LoadCP --> Fingerprint[Fingerprint inputs and check valid caches]
  Fingerprint --> Crawl[Crawl and extract DOM]
  Crawl --> PersistChunk[Persist page/chunk checkpoints]

  PersistChunk --> GenIntents[Generate buyer intents]
  GenIntents --> PersistGen[Persist intent generation result]
  PersistGen --> Retrieve[Retrieve evidence: dense + lexical + RRF]
  Retrieve --> Eval[Evaluate intents in bounded batches]

  Eval --> ValidCheck{Result valid?}
  ValidCheck -->|No| Classify[Classify failure]
  Classify --> RecoveryCheck{Recovery permitted?}
  Classify -.->|Restart phase when warranted| GenIntents

  RecoveryCheck -->|Yes| Retry[Retry, split batch, or compatible provider]
  Retry --> Eval
  RecoveryCheck -->|No| RecordFail[Record partial or terminal failure]

  ValidCheck -->|Yes| ValidPersist[Validate and persist result]

  ValidPersist --> UpdateProg[Update durable progress]
  RecordFail --> UpdateProg

  UpdateProg --> WorkDoneCheck{Required work complete?}
  WorkDoneCheck -->|No| LoadCP

  WorkDoneCheck -->|Yes| CalcScore[Calculate score from valid results]
  CalcScore --> ValPatches[Validate evidence-grounded patches]
  ValPatches --> RemGate[Apply remediation eligibility gate]
  RemGate --> GitHubPR[Create/reconcile GitHub PR]
  GitHubPR --> PRLifecycle[Persist PR lifecycle]
  PRLifecycle --> PostVerify[Run fresh post-PR verification]
  PostVerify --> PersistOutcome[Persist verification outcome]
  PersistOutcome --> FinalResult[Publish final scan result]
```

**Label:** Proposed / Target State.

### 4.1 Stage resume helper (Proposed)

Compact recovery loop used inside the engine above:

```mermaid
flowchart TD
  A[Claim job] --> B[Restore budget + stage cursor]
  B --> C{Stage complete?}
  C -->|yes| D[Skip to next]
  C -->|no| E{Cache hit valid?}
  E -->|yes| F[Load cached artifact]
  E -->|no| G[Execute stage/batch]
  G --> H{Classify error}
  H -->|retry| I[Backoff bounded]
  I --> G
  H -->|fallback| J[Provider/model fallback]
  J --> G
  H -->|fatal| K[Fail job]
  G --> L[Checkpoint + budget commit]
  F --> L
  L --> D
  D --> M{More stages?}
  M -->|yes| C
  M -->|no| N[Finalize]
```

**Label:** Proposed.

---

## 5. Retry / provider fallback decision (Proposed)

```mermaid
flowchart TD
  E[Exception] --> C{Error classifier}
  C -->|timeout/429| R[Retry with backoff]
  C -->|schema invalid| S[Repair or fail batch]
  C -->|auth/config| F[Terminal fail]
  C -->|budget| F
  R --> N{Attempts < bound?}
  N -->|yes| T[Re-enter stage]
  N -->|no| FB{Fallback model configured?}
  FB -->|yes| T2[Retry once on fallback]
  FB -->|no| F
  T2 --> F2{ok?}
  F2 -->|no| F
```

**Label:** Proposed.

---

## 6. Budget reservation (Proposed)

```mermaid
sequenceDiagram
  participant S as Stage
  participant BG as BudgetGuard
  participant DB as Job row
  S->>BG: estimate calls + USD
  BG->>DB: BEGIN reserve
  alt insufficient
    DB-->>BG: abort
    BG-->>S: BudgetExhausted
  else ok
    DB-->>BG: reserved
    S->>S: provider call
    S->>DB: commit usage checkpoint
  end
```

---

## 7. Cache lookup / invalidation (Proposed — Stage 2)

```mermaid
flowchart TD
  Q[Stage needs artifact] --> K[Compute fingerprint]
  K --> L{Lookup cache}
  L -->|miss| M[Compute + store]
  L -->|hit| V{Versions compatible?}
  V -->|no| M
  V -->|yes| H[Use cached]
  M --> H
```

---

## 8. Progress + SSE replay (Proposed — Stage 3)

Durable progress path that fixes process-local `EVENT_*` gaps (F-01). Checkpoint commit happens **before** the progress event is published so reconnect/replay cannot show stages that were never persisted.

```mermaid
flowchart TD
  W[Worker performs operation] --> CP[Commit checkpoint and progress state]
  CP --> Pub[Publish durable progress event]
  Pub --> SSE[SSE delivery layer]
  SSE --> FE[Next.js frontend]
  FE --> Render[Render current stage and actual counts]
  FE --> Reconn[Reconnect with last sequence]
  Reconn --> Replay[Replay missed events or load snapshot]
  Replay --> Render
```

**Label:** Proposed / Target State.

Sequence view of the same design:

```mermaid
sequenceDiagram
  participant W as Worker
  participant DB as Progress store
  participant API as API
  participant UI as Frontend
  W->>DB: event seq++
  UI->>API: SSE Last-Event-ID
  API->>DB: events after id + snapshot
  API-->>UI: replay
  loop Live
    W->>DB: event
    API-->>UI: push / poll tail
  end
```

---

## 9. Remediation + verification (Current)

```mermaid
flowchart TD
  A[Patches validated] --> B{Eligible?}
  B -->|no| Z[Skip remediation]
  B -->|yes| C[Idempotent PR create/reconcile]
  C --> D[Fetch patched content]
  D --> E[evaluate_verification_outcome]
  E --> F[Persist verification run]
  F --> G[Expose outcome to UI]
```

**Not a full re-scan.** Keyword / validation heuristics only.

---

## 10. Current vs proposed delivery

| Concern | Current | Proposed |
| :--- | :--- | :--- |
| Job durability | Yes | Yes (extended) |
| Stage resume | No | Yes |
| Progress across processes | Broken / poll-only | Durable + SSE replay |
| Budget mid-run | Incomplete | Checkpointed |
| Cache | None | Versioned (Stage 2) |
| Verification | Heuristic | Heuristic + honest labeling |