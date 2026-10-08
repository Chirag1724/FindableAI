// Lighthouse type definitions mirroring backend spec 4.4 exactly

export type EngineKey = "chatgpt" | "gemini" | "perplexity" | "claude";

export type ScoreTier = "good" | "needs_improvement" | "poor";

export type ScrapingRisk = "low" | "moderate" | "critical";

export type BotCategory = "training" | "search" | "scraper";

export type BotAccessStatus = "allowed" | "blocked";

export interface CriterionDetail {
  score: number;
  detail: string;
}

export interface EngineScore {
  score: number;
  tier: ScoreTier;
  criteria: Record<string, CriterionDetail>;
}

export interface BotStatus {
  bot: string;
  category: BotCategory;
  status: BotAccessStatus;
  impact?: string;
}

export interface CrawlerGovernance {
  ai_visibility_index: number;
  scraping_risk: ScrapingRisk;
  bot_matrix: BotStatus[];
  llms_txt_present: boolean;
}

export interface AuditOpportunity {
  id: string;
  title: string;
  score_lift: number;
  engine: EngineKey | string;
  severity: "critical" | "high" | "medium" | "low";
}

export interface AuditDiagnostic {
  id: string;
  title: string;
  engines_affected: (EngineKey | string)[];
}

export interface AuditPassed {
  id: string;
  title: string;
}

export interface AuditSummary {
  opportunities: AuditOpportunity[];
  diagnostics: AuditDiagnostic[];
  passed: AuditPassed[];
}

export interface LighthouseResponse {
  scan_id: string;
  computed_at: string;
  engines: Record<EngineKey, EngineScore>;
  crawler_governance: CrawlerGovernance;
  audits: AuditSummary;
}
