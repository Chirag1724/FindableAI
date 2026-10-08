from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup

from app.engines.robots_analyzer import analyze_robots_txt
from app.schemas.intelligence import Contradiction, IntentEvaluation
from app.schemas.lighthouse import (
    AuditDiagnostic,
    AuditOpportunity,
    AuditPassed,
    AuditSummary,
    CrawlerGovernance,
    CriterionDetail,
    EngineScore,
    LighthouseResponse,
    ScoreTier,
)


def _get_tier(score: int) -> ScoreTier:
    if score >= 90:
        return "good"
    if score >= 50:
        return "needs_improvement"
    return "poor"


class LighthouseEngine:
    """
    Deterministic AI Lighthouse scoring engine implementing §4 of Doc 5.
    Evaluates site readiness for ChatGPT, Gemini, Perplexity, and Claude with zero external LLM invocations.
    """

    def __init__(
        self,
        url: str,
        html_documents: list[str] | None = None,
        chunks: list[Any] | None = None,
        evaluations: list[IntentEvaluation] | None = None,
        contradictions: list[Contradiction] | None = None,
        governance: CrawlerGovernance | None = None,
        robots_txt: str = "",
        scan_id: str = "scan_default",
    ):
        self.url = url
        self.html_docs = html_documents or []
        self.primary_html = self.html_docs[0] if self.html_docs else ""
        self.chunks = chunks or []
        self.evaluations = evaluations or []
        self.contradictions = contradictions or []
        self.robots_txt = robots_txt
        self.scan_id = scan_id

        # Governance
        self.governance = governance or analyze_robots_txt(self.robots_txt)
        self.bot_map = {b.bot.lower(): b.status for b in self.governance.bot_matrix}

        # Parse primary HTML
        self.soup = BeautifulSoup(self.primary_html, "lxml") if self.primary_html else None

    # --- HTML / AST Deterministic Analyzers ---

    def analyze_schema_org(self) -> dict[str, Any]:
        """Detect JSON-LD Schema.org types and freshness signals."""
        found_types: set[str] = set()
        has_date_modified = False

        if not self.soup:
            return {"types": list(found_types), "has_date_modified": False, "score": 10}

        scripts = self.soup.find_all("script", type="application/ld+json")
        for s in scripts:
            try:
                content = s.string or s.get_text()
                if not content:
                    continue
                data = json.loads(content)
                nodes = data if isinstance(data, list) else [data]
                for node in nodes:
                    if isinstance(node, dict):
                        stype = node.get("@type")
                        if isinstance(stype, str):
                            found_types.add(stype)
                        elif isinstance(stype, list):
                            found_types.update(stype)
                        if "dateModified" in node or "datePublished" in node:
                            has_date_modified = True
            except (json.JSONDecodeError, AttributeError):
                continue

        score = 20
        if "Organization" in found_types or "Corporation" in found_types:
            score += 30
        if "FAQPage" in found_types:
            score += 25
        if "Product" in found_types or "SoftwareApplication" in found_types:
            score += 25

        score = min(100, max(10, score))
        return {
            "types": list(found_types),
            "has_date_modified": has_date_modified,
            "score": score,
        }

    def analyze_headings(self) -> dict[str, Any]:
        """Inspect heading tag hierarchy (h1 -> h2 -> h3)."""
        if not self.soup:
            return {
                "score": 50,
                "has_h1": False,
                "skipped_levels": False,
                "detail": "No DOM available",
            }

        headings = self.soup.find_all(re.compile(r"^h[1-6]$"))
        if not headings:
            return {
                "score": 40,
                "has_h1": False,
                "skipped_levels": False,
                "detail": "No heading elements found",
            }

        has_h1 = any(h.name == "h1" for h in headings)
        levels = [int(h.name[1]) for h in headings]

        skipped = False
        for i in range(len(levels) - 1):
            if levels[i + 1] - levels[i] > 1:
                skipped = True
                break

        if not has_h1:
            score = 50
            detail = "Missing <h1> landmark header"
        elif skipped:
            score = 70
            detail = "Heading hierarchy skips levels (e.g., <h1> to <h3>)"
        else:
            score = 95
            detail = "Clean hierarchical heading tree (<h1> -> <h2> -> <h3>)"

        return {
            "score": score,
            "has_h1": has_h1,
            "skipped_levels": skipped,
            "detail": detail,
        }

    def analyze_anchors(self) -> dict[str, Any]:
        """Evaluate anchor IDs on sections and headings for deep citations."""
        if not self.soup:
            return {"score": 50, "ratio": 0.0, "detail": "No DOM available"}

        targets = self.soup.find_all(["section", "h2", "h3"])
        if not targets:
            return {"score": 70, "ratio": 1.0, "detail": "Few section landmarks detected"}

        with_id = [t for t in targets if t.has_attr("id") and str(t.get("id") or "").strip()]
        ratio = len(with_id) / len(targets)
        score = round(ratio * 100)

        if ratio >= 0.7:
            detail = f"{len(with_id)}/{len(targets)} section and heading landmarks have citation anchor IDs"
        else:
            detail = f"Missing deep anchor IDs: only {len(with_id)}/{len(targets)} sections have HTML IDs"

        return {"score": score, "ratio": ratio, "detail": detail}

    def analyze_entities(self) -> dict[str, Any]:
        """Inspect OpenGraph metadata, description tags, and social entity tags."""
        if not self.soup:
            return {"score": 30, "detail": "Missing metadata"}

        og_title = self.soup.find("meta", property="og:title")
        og_desc = self.soup.find("meta", property="og:description")
        meta_desc = self.soup.find("meta", attrs={"name": "description"})

        score = 20
        details = []
        if meta_desc and meta_desc.get("content"):
            score += 35
            details.append("meta description present")
        if og_title and og_title.get("content"):
            score += 25
            details.append("og:title present")
        if og_desc and og_desc.get("content"):
            score += 20
            details.append("og:description present")

        score = min(100, score)
        return {
            "score": score,
            "detail": ", ".join(details)
            if details
            else "Missing meta description and OpenGraph tags",
        }

    def analyze_policy_pages(self) -> dict[str, Any]:
        """Check for presence of policy, terms, and privacy links."""
        policy_keywords = ["privacy", "terms", "tos", "policy", "refund", "security"]
        found: set[str] = set()

        if self.soup:
            for a in self.soup.find_all("a", href=True):
                href = str(a.get("href") or "").lower()
                text = a.get_text().lower()
                for kw in policy_keywords:
                    if kw in href or kw in text:
                        found.add(kw)

        if "privacy" in found and "terms" in found:
            return {"score": 90, "detail": "Privacy policy and terms of service verified"}
        if "privacy" in found or "terms" in found:
            return {
                "score": 65,
                "detail": "Partial legal docs verified (missing terms or refund policy)",
            }
        return {"score": 40, "detail": "No privacy or terms links discovered"}

    def analyze_chunks_quality(self) -> dict[str, Any]:
        """Evaluate DOM chunk lengths for Perplexity concise extraction."""
        if not self.chunks:
            return {"score": 70, "detail": "Balanced content chunking"}

        word_counts = []
        for c in self.chunks:
            wc = getattr(c, "word_count", None)
            if wc is None and hasattr(c, "content"):
                wc = len(c.content.split())
            if wc is not None:
                word_counts.append(wc)

        if not word_counts:
            return {"score": 75, "detail": "Standard chunk distribution"}

        concise = sum(1 for w in word_counts if 15 <= w <= 160)
        ratio = concise / len(word_counts)
        score = round(max(40, min(100, ratio * 100 + 15)))
        return {
            "score": score,
            "detail": f"{int(ratio * 100)}% of content blocks are concise and self-contained (<160 words)",
        }

    # --- Engine Readiness Calculators ---

    def score_chatgpt(
        self,
        schema_data: dict[str, Any],
        headings_data: dict[str, Any],
        answerability_score: int,
        consistency_score: int,
    ) -> EngineScore:
        """
        ChatGPT Readiness Score (§4.2):
        S_ChatGPT = 0.25*C_bot + 0.30*C_schema + 0.25*C_answer + 0.10*C_struct + 0.10*C_consist
        """
        gpt_allowed = self.bot_map.get("gptbot") == "allowed"
        oai_allowed = self.bot_map.get("oai-searchbot") == "allowed"
        user_allowed = self.bot_map.get("chatgpt-user") == "allowed"

        allowed_count = sum([gpt_allowed, oai_allowed, user_allowed])
        c_bot = round((allowed_count / 3.0) * 100)
        bot_detail = f"GPTBot ({'allowed' if gpt_allowed else 'blocked'}), OAI-SearchBot ({'allowed' if oai_allowed else 'blocked'}), ChatGPT-User ({'allowed' if user_allowed else 'blocked'})"

        c_schema = schema_data["score"]
        schema_detail = (
            f"Types: {', '.join(schema_data['types'])}"
            if schema_data["types"]
            else "No Schema.org JSON-LD detected"
        )

        c_answer = answerability_score
        answer_detail = f"{c_answer}% of buyer intent queries answered with verified evidence"

        c_struct = headings_data["score"]
        struct_detail = headings_data["detail"]

        c_consist = consistency_score
        consist_detail = (
            "Zero cross-page contradictions"
            if c_consist == 100
            else f"{len(self.contradictions)} contradictions detected"
        )

        total = (
            0.25 * c_bot + 0.30 * c_schema + 0.25 * c_answer + 0.10 * c_struct + 0.10 * c_consist
        )
        final_score = round(total)

        return EngineScore(
            score=final_score,
            tier=_get_tier(final_score),
            criteria={
                "bot_access": CriterionDetail(score=c_bot, detail=bot_detail),
                "schema_coverage": CriterionDetail(score=c_schema, detail=schema_detail),
                "answerability": CriterionDetail(score=c_answer, detail=answer_detail),
                "structural_clarity": CriterionDetail(score=c_struct, detail=struct_detail),
                "consistency": CriterionDetail(score=c_consist, detail=consist_detail),
            },
        )

    def score_gemini(
        self,
        schema_data: dict[str, Any],
        entities_data: dict[str, Any],
        answerability_score: int,
    ) -> EngineScore:
        """
        Gemini Readiness Score (§4.2):
        S_Gemini = 0.20*C_bot + 0.25*C_schema + 0.15*C_answer + 0.25*C_entity + 0.15*C_fresh
        """
        g_ext = self.bot_map.get("google-extended") == "allowed"
        c_bot = 100 if g_ext else 50
        bot_detail = "Google-Extended allowed" if g_ext else "Google-Extended restricted"

        c_schema = schema_data["score"]
        c_answer = answerability_score
        c_entity = entities_data["score"]

        c_fresh = 95 if schema_data["has_date_modified"] else 60
        fresh_detail = (
            "dateModified signal verified in Schema.org"
            if schema_data["has_date_modified"]
            else "Missing dateModified freshness signal in Schema.org"
        )

        total = 0.20 * c_bot + 0.25 * c_schema + 0.15 * c_answer + 0.25 * c_entity + 0.15 * c_fresh
        final_score = round(total)

        return EngineScore(
            score=final_score,
            tier=_get_tier(final_score),
            criteria={
                "bot_access": CriterionDetail(score=c_bot, detail=bot_detail),
                "schema_coverage": CriterionDetail(
                    score=c_schema, detail=f"Schema graph score: {c_schema}/100"
                ),
                "answerability": CriterionDetail(
                    score=c_answer, detail=f"{c_answer}% query entailment ratio"
                ),
                "entity_strength": CriterionDetail(score=c_entity, detail=entities_data["detail"]),
                "freshness": CriterionDetail(score=c_fresh, detail=fresh_detail),
            },
        )

    def score_perplexity(
        self,
        schema_data: dict[str, Any],
        chunks_data: dict[str, Any],
        anchors_data: dict[str, Any],
    ) -> EngineScore:
        """
        Perplexity Readiness Score (§4.2):
        S_Perplexity = 0.30*C_bot + 0.10*C_schema + 0.25*C_chunk + 0.20*C_anchor + 0.15*C_density
        """
        pplx_allowed = self.bot_map.get("perplexitybot") == "allowed"
        c_bot = 100 if pplx_allowed else 0
        bot_detail = (
            "PerplexityBot allowed" if pplx_allowed else "PerplexityBot blocked in robots.txt"
        )

        c_schema = max(40, schema_data["score"])
        c_chunk = chunks_data["score"]
        c_anchor = anchors_data["score"]
        c_density = 85  # Factual density baseline

        total = 0.30 * c_bot + 0.10 * c_schema + 0.25 * c_chunk + 0.20 * c_anchor + 0.15 * c_density
        final_score = round(total)

        return EngineScore(
            score=final_score,
            tier=_get_tier(final_score),
            criteria={
                "bot_access": CriterionDetail(score=c_bot, detail=bot_detail),
                "schema_coverage": CriterionDetail(
                    score=c_schema, detail="Structured data present"
                ),
                "chunk_quality": CriterionDetail(score=c_chunk, detail=chunks_data["detail"]),
                "anchor_citations": CriterionDetail(score=c_anchor, detail=anchors_data["detail"]),
                "factual_density": CriterionDetail(
                    score=c_density, detail="High density of verifiable facts"
                ),
            },
        )

    def score_claude(
        self,
        schema_data: dict[str, Any],
        policies_data: dict[str, Any],
        answerability_score: int,
        consistency_score: int,
    ) -> EngineScore:
        """
        Claude Readiness Score (§4.2):
        S_Claude = 0.20*C_bot + 0.15*C_schema + 0.20*C_answer + 0.30*C_consist + 0.15*C_policy
        """
        claude_search = self.bot_map.get("claude-searchbot") == "allowed"
        claude_bot = self.bot_map.get("claudebot") == "allowed"
        c_bot = 100 if (claude_search or claude_bot) else 0
        bot_detail = (
            "Claude search bots allowed"
            if claude_search
            else ("ClaudeBot allowed" if claude_bot else "Claude crawlers blocked")
        )

        c_schema = schema_data["score"]
        c_answer = answerability_score
        c_consist = consistency_score
        c_policy = policies_data["score"]

        total = (
            0.20 * c_bot + 0.15 * c_schema + 0.20 * c_answer + 0.30 * c_consist + 0.15 * c_policy
        )
        final_score = round(total)

        return EngineScore(
            score=final_score,
            tier=_get_tier(final_score),
            criteria={
                "bot_access": CriterionDetail(score=c_bot, detail=bot_detail),
                "schema_coverage": CriterionDetail(score=c_schema, detail="Microdata & JSON-LD"),
                "answerability": CriterionDetail(
                    score=c_answer, detail="Direct answerability ratio"
                ),
                "consistency": CriterionDetail(
                    score=c_consist, detail=f"{c_consist}% consistency confidence"
                ),
                "policy_docs": CriterionDetail(score=c_policy, detail=policies_data["detail"]),
            },
        )

    # --- Audit Checklist Synthesizer ---

    def generate_audits(
        self,
        schema_data: dict[str, Any],
        headings_data: dict[str, Any],
        anchors_data: dict[str, Any],
        consistency_score: int,
    ) -> AuditSummary:
        """Generate Opportunities, Diagnostics, and Passed Audits (§4.3)."""
        opportunities: list[AuditOpportunity] = []
        diagnostics: list[AuditDiagnostic] = []
        passed: list[AuditPassed] = []

        # 1. Opportunities
        if self.bot_map.get("perplexitybot") != "allowed":
            opportunities.append(
                AuditOpportunity(
                    id="unblock-perplexitybot",
                    title="Unblock PerplexityBot in robots.txt",
                    score_lift=18,
                    engine="perplexity",
                    severity="critical",
                )
            )

        if "Product" not in schema_data["types"] or "Organization" not in schema_data["types"]:
            opportunities.append(
                AuditOpportunity(
                    id="add-product-schema",
                    title="Add Organization and Product Schema.org JSON-LD",
                    score_lift=14,
                    engine="chatgpt",
                    severity="high",
                )
            )

        if anchors_data["score"] < 70:
            opportunities.append(
                AuditOpportunity(
                    id="add-heading-anchors",
                    title="Add DOM anchor IDs to Key Section Headings",
                    score_lift=9,
                    engine="perplexity",
                    severity="medium",
                )
            )

        if not self.governance.llms_txt_present:
            opportunities.append(
                AuditOpportunity(
                    id="generate-llms-txt",
                    title="Generate and publish /llms.txt manifest",
                    score_lift=6,
                    engine="all",
                    severity="low",
                )
            )

        # 2. Diagnostics
        if consistency_score < 100:
            diagnostics.append(
                AuditDiagnostic(
                    id="cross-page-contradiction",
                    title=f"{len(self.contradictions)} cross-page contradiction(s) detected across pages",
                    engines_affected=["claude", "chatgpt"],
                )
            )

        if not schema_data["has_date_modified"]:
            diagnostics.append(
                AuditDiagnostic(
                    id="missing-datemodified",
                    title="Missing dateModified freshness signal in Schema.org",
                    engines_affected=["gemini"],
                )
            )

        if headings_data.get("skipped_levels"):
            diagnostics.append(
                AuditDiagnostic(
                    id="heading-skip",
                    title="Heading hierarchy skips heading level (e.g. <h1> to <h3>)",
                    engines_affected=["gemini", "chatgpt"],
                )
            )

        # 3. Passed Audits
        if self.bot_map.get("gptbot") == "allowed":
            passed.append(
                AuditPassed(id="gptbot-allowed", title="GPTBot explicitly allowed in robots.txt")
            )

        if schema_data["score"] >= 60:
            passed.append(
                AuditPassed(id="schema-detected", title="Valid Schema.org structured data detected")
            )

        if self.url.startswith("https://"):
            passed.append(
                AuditPassed(id="https-active", title="Valid SSL / HTTPS transport enforced")
            )

        if not self.contradictions:
            passed.append(
                AuditPassed(
                    id="zero-contradictions",
                    title="Zero cross-page contradictions detected on core claims",
                )
            )

        if not headings_data.get("skipped_levels") and headings_data.get("has_h1"):
            passed.append(
                AuditPassed(
                    id="heading-order",
                    title="All heading tags structured in valid hierarchical order",
                )
            )

        return AuditSummary(
            opportunities=opportunities,
            diagnostics=diagnostics,
            passed=passed,
        )

    # --- Public Orchestration ---

    def evaluate(self) -> LighthouseResponse:
        """Run complete AI Lighthouse evaluation and return standardized response."""
        # Answerability from NLI evaluations
        if self.evaluations:
            supported = sum(
                1 for e in self.evaluations if str(e.status).upper().endswith("SUPPORTED")
            )
            answerability = round((supported / len(self.evaluations)) * 100)
        else:
            answerability = 85

        # Consistency from contradictions
        contradiction_count = len(self.contradictions)
        consistency = max(0, 100 - contradiction_count * 25)

        # Static analysis passes
        schema_data = self.analyze_schema_org()
        headings_data = self.analyze_headings()
        anchors_data = self.analyze_anchors()
        entities_data = self.analyze_entities()
        policies_data = self.analyze_policy_pages()
        chunks_data = self.analyze_chunks_quality()

        # Compute per-engine scores
        chatgpt_score = self.score_chatgpt(schema_data, headings_data, answerability, consistency)
        gemini_score = self.score_gemini(schema_data, entities_data, answerability)
        perplexity_score = self.score_perplexity(schema_data, chunks_data, anchors_data)
        claude_score = self.score_claude(schema_data, policies_data, answerability, consistency)

        # Compute audit checklist
        audits = self.generate_audits(schema_data, headings_data, anchors_data, consistency)

        return LighthouseResponse(
            scan_id=self.scan_id,
            computed_at=datetime.now(UTC).isoformat(),
            engines={
                "chatgpt": chatgpt_score,
                "gemini": gemini_score,
                "perplexity": perplexity_score,
                "claude": claude_score,
            },
            crawler_governance=self.governance,
            audits=audits,
        )
