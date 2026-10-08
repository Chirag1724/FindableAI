from typing import Literal

from pydantic import BaseModel, Field

EngineKey = Literal["chatgpt", "gemini", "perplexity", "claude"]
ScoreTier = Literal["good", "needs_improvement", "poor"]
ScrapingRisk = Literal["low", "moderate", "critical"]
BotCategory = Literal["training", "search", "scraper"]
BotAccessStatus = Literal["allowed", "blocked"]


class CriterionDetail(BaseModel):
    score: int
    detail: str


class EngineScore(BaseModel):
    score: int
    tier: ScoreTier
    criteria: dict[str, CriterionDetail]


class BotStatus(BaseModel):
    bot: str
    category: BotCategory
    status: BotAccessStatus
    impact: str | None = None


class CrawlerGovernance(BaseModel):
    ai_visibility_index: int
    scraping_risk: ScrapingRisk
    bot_matrix: list[BotStatus] = Field(default_factory=list)
    llms_txt_present: bool = False


class AuditOpportunity(BaseModel):
    id: str
    title: str
    score_lift: int
    engine: str
    severity: Literal["critical", "high", "medium", "low"]


class AuditDiagnostic(BaseModel):
    id: str
    title: str
    engines_affected: list[str] = Field(default_factory=list)


class AuditPassed(BaseModel):
    id: str
    title: str


class AuditSummary(BaseModel):
    opportunities: list[AuditOpportunity] = Field(default_factory=list)
    diagnostics: list[AuditDiagnostic] = Field(default_factory=list)
    passed: list[AuditPassed] = Field(default_factory=list)


class LighthouseResponse(BaseModel):
    scan_id: str
    computed_at: str
    engines: dict[str, EngineScore]
    crawler_governance: CrawlerGovernance
    audits: AuditSummary
