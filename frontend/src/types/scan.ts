// Scan type definitions mirroring backend Pydantic schemas exactly

export type ScanStatus =
  | "pending"
  | "crawling"
  | "extracting_dom"
  | "synthesizing_intents"
  | "hybrid_retrieval"
  | "nli_evaluation"
  | "computing_fscore"
  | "generating_patches"
  | "completed"
  | "failed";

export interface ScanStatusEvent {
  scan_id: string;
  status: ScanStatus;
  progress_percent: number;
  current_step: string;
  message: string;
  timestamp: string;
}

export interface SubScoreMetric {
  name: string;
  weight: number;
  score: number;
  details: string;
  strengths: string[];
  gaps: string[];
}

export interface FScoreBreakdown {
  overall_score: number;
  grade: string;
  coverage: SubScoreMetric;
  entailment: SubScoreMetric;
  contradiction_penalty: SubScoreMetric;
  structural_clarity: SubScoreMetric;
}

export interface DOMSelectorAnchor {
  css_selector: string;
  tag_name: string;
  original_snippet: string;
  suggested_snippet: string;
}

export type PatchType =
  | "content_clarification"
  | "schema_microdata"
  | "heading_structure"
  | "factual_conflict_resolution";

export interface AuxiliaryFile {
  file_path: string;
  content: string;
  action: "create" | "modify" | "delete";
}

export interface PatchProposal {
  patch_id: string;
  patch_type: PatchType;
  title: string;
  rationale: string;
  impact_score_delta: number;
  dom_anchor: DOMSelectorAnchor;
  unified_diff: string;
  applied: boolean;
  target_file?: string | null;
  code_diff?: string | null;
  auxiliary_files?: AuxiliaryFile[];
  framework?: string | null;
  /** Demo/mock artifact — not evidence-backed remediation */
  is_synthetic?: boolean;
}


export interface CrawledPageDetail {
  url: string;
  status_code: number;
  chunks_count: number;
  load_time_ms?: number;
  is_spa?: boolean;
  title?: string;
}

export interface AuditSummary {
  pages_crawled: number;
  dom_chunks_extracted: number;
  intents_generated: number;
  contradictions_detected: number;
  execution_time_seconds: number;
  max_pages_requested?: number;
  crawled_pages?: CrawledPageDetail[];
  /** Evaluations from DAG before any synthetic fill */
  dag_evaluations_count?: number;
  /** Synthetically injected intent count (0 if none) */
  synthetic_intents_count?: number;
}

export type ScanOutcome = "success" | "partial" | "inconclusive" | "failed" | string;
export type ResultSource =
  | "real_pipeline"
  | "partial_real"
  | "synthetic_fallback"
  | "inconclusive"
  | string;

export interface ScanResponse {
  scan_id: string;
  target_url: string;
  status: ScanStatus;
  created_at: string;
  completed_at?: string;
  f_score?: FScoreBreakdown;
  summary?: AuditSummary;
  crawled_pages?: CrawledPageDetail[];
  patches: PatchProposal[];
  error?: string;
  /** real_llm only when DAG evals + LLM calls + no synthetic/mock intelligence */
  execution_mode?: "real_llm" | "synthetic_fallback" | "deterministic" | string;
  /** Unset until integrity is decided — do not assume live_pipeline while pending */
  data_source?: "live_pipeline" | "synthetic_fallback" | string | null;
  result_source?: ResultSource;
  outcome?: ScanOutcome;
  score_source?: "deterministic_scorer" | "mock" | "none" | string;
  patches_source?: "assembler" | "mock" | "none" | string;
  /** False for synthetic/mock scans — do not treat as evidence-backed remediation */
  remediation_eligible?: boolean;
  intelligence_warnings?: string[];
  llm_calls_made?: number;
  repo_url?: string;
  github_repo_url?: string;
}

// Intelligence layer types (mirrors backend schemas/intelligence.py)

export type IntentCategory =
  | "eligibility"
  | "policy"
  | "availability"
  | "pricing"
  | "accessibility"
  | "commercial"
  | "local"
  | "transactional"
  | "trust"
  | "edge_cases"
  | "uncategorized";

export type EntailmentStatus =
  | "SUPPORTED"
  | "PARTIALLY_SUPPORTED"
  | "CONTRADICTED"
  | "UNKNOWN";

export interface EvidenceReference {
  chunk_id: string;
  dom_path: string;
  url?: string;
  rank?: number;
  rrf_score?: number;
  excerpt?: string;
}

export interface IntentEvaluation {
  intent_id: string;
  query: string;
  category: IntentCategory;
  status: EntailmentStatus;
  reasoning: string;
  evidence: EvidenceReference[];
  confidence: number;
  difficulty?: "easy" | "medium" | "hard";
  persona?: "cto" | "developer" | "procurement" | string;
}

export type ContradictionSeverity = "HARD_CONTRADICTION" | "SOFT_INCONSISTENCY";

export interface Contradiction {
  contradiction_id: string;
  entity: string;
  conflict: string;
  values: unknown[];
  severity: ContradictionSeverity;
  source_urls: string[];
  dom_paths: string[];
}

export interface ValidationCheck {
  name: string;
  status: string;
  detail?: string;
  safety_critical?: boolean;
}

export interface PullRequestResult {
  pr_url: string;
  pr_number: number;
  branch_name: string;
  title: string;
  created_at: string;
  remediation_run_id?: string | null;
  lifecycle_state?: string | null;
  validation_checks?: ValidationCheck[] | null;
  base_sha?: string | null;
  head_sha?: string | null;
}

export interface RemediationRun {
  id: string;
  scan_id: string;
  idempotency_key: string;
  repo_full_name: string;
  base_branch: string;
  base_sha?: string | null;
  head_branch?: string | null;
  head_sha?: string | null;
  pr_number?: number | null;
  pr_url?: string | null;
  lifecycle_state: string;
  changed_files?: unknown[];
  validation_results?: unknown[];
  error?: string | null;
}

export interface VerificationRun {
  id: string;
  scan_id: string;
  remediation_run_id: string;
  evaluated_revision?: string | null;
  issue_outcome: "fixed" | "unresolved" | "inconclusive" | string;
  operational_status: string;
  detail?: string | null;
  fresh_evidence?: unknown[];
  created_at?: string | null;
}

export interface ApiError {
  status: number;
  message: string;
  detail?: string;
}
