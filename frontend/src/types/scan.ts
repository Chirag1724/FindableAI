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
}
