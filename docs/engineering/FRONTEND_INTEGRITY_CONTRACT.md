# Frontend integration contract — scan integrity (P0)

For **Frontend Team (Chirag / Himanshu / Shiv)**. Backend now emits additive fields on `ScanResponse`. Minimal UI wiring is in `frontend/src/app/scans/[id]/page.tsx` and `frontend/src/types/scan.ts`; further polish can follow this contract.

## Fields to read

| Field | Use |
| :--- | :--- |
| `execution_mode` | `real_llm` only for genuine LLM intelligence (not “any provider call”). |
| `outcome` | `success` \| `partial` \| `inconclusive` \| `failed` |
| `result_source` | Provenance of intents |
| `remediation_eligible` | **Required** gate before “No fixes required” / PR CTA |
| `intelligence_warnings[]` | Show first warning under the sticky CTA |
| `summary.dag_evaluations_count` | Real DAG eval count (before synthetic fill) |
| `summary.synthetic_intents_count` | How many synthetic intents were injected |
| `score_source` / `patches_source` | Do not present mock artifacts as audit-grade |
| `patches[].is_synthetic` | Hide or badge mock patches |

## Example responses (shape)

### Real success
```json
{
  "status": "completed",
  "execution_mode": "real_llm",
  "result_source": "real_pipeline",
  "outcome": "success",
  "score_source": "deterministic_scorer",
  "patches_source": "assembler",
  "remediation_eligible": true,
  "llm_calls_made": 31,
  "intelligence_warnings": [],
  "summary": { "intents_generated": 30, "dag_evaluations_count": 30, "synthetic_intents_count": 0 }
}
```

### Missing key / synthetic demo (non-prod)
```json
{
  "status": "completed",
  "execution_mode": "synthetic_fallback",
  "result_source": "synthetic_fallback",
  "outcome": "inconclusive",
  "score_source": "mock",
  "patches_source": "mock",
  "remediation_eligible": false,
  "llm_calls_made": 0,
  "intelligence_warnings": ["Intent evaluations were synthetically generated; not a real-LLM NLI audit."],
  "summary": { "intents_generated": 30, "dag_evaluations_count": 0, "synthetic_intents_count": 30 }
}
```

### Production LLM failure, zero evals
```json
{
  "status": "failed",
  "execution_mode": "deterministic",
  "result_source": "inconclusive",
  "outcome": "failed",
  "remediation_eligible": false,
  "llm_calls_made": 0,
  "error": "…",
  "summary": { "intents_generated": 0, "dag_evaluations_count": 0, "synthetic_intents_count": 0 }
}
```

### Partial real (budget exhausted mid-ACT)
```json
{
  "status": "completed",
  "execution_mode": "real_llm",
  "result_source": "partial_real",
  "outcome": "partial",
  "remediation_eligible": false,
  "llm_calls_made": 35
}
```

## UI rules (must)

1. Never show **“No fixes required”** unless `remediation_eligible === true` and non-synthetic `patches.length === 0`.
2. If `remediation_eligible` is not **exactly** `true` (including `false` / missing), show incomplete/synthetic copy; disable PR apply.
3. Disable the remediation CTA while patches are still loading — never enable temporarily during load.
4. Do not default intent counts to `30` when data is missing — use `0` / `dag_evaluations_count`.
5. Treat `outcome !== "success"` as non-clean even if `status === "completed"`.
6. Render ScoreGauge only for authoritative scores (`score_source=deterministic_scorer` with real/partial result provenance). Otherwise show an unavailable/incomplete state.
7. Do not render synthetic demo intent rows as real website findings.
8. Filter `is_synthetic` patches out of remediation UI.
