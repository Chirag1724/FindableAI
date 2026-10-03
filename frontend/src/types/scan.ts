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

export interface PatchProposal {
  patch_id: string;
  patch_type: PatchType;
  title: string;
  rationale: string;
  impact_score_delta: number;
  dom_anchor: DOMSelectorAnchor;
  unified_diff: string;
  applied: boolean;
}

export interface AuditSummary {
  pages_crawled: number;
  dom_chunks_extracted: number;
  intents_generated: number;
  contradictions_detected: number;
  execution_time_seconds: number;
}

export interface ScanResponse {
  scan_id: string;
  target_url: string;
  status: ScanStatus;
  created_at: string;
  completed_at?: string;
  f_score?: FScoreBreakdown;
  summary?: AuditSummary;
  patches: PatchProposal[];
  error?: string;
  execution_mode?: "real_llm" | "deterministic_fallback" | string;
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

export interface PullRequestResult {
  pr_url: string;
  pr_number: number;
  branch_name: string;
  title: string;
  created_at: string;
}

export interface ApiError {
  status: number;
  message: string;
  detail?: string;
}
