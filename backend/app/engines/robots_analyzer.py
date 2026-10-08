from __future__ import annotations

import re
import urllib.robotparser
from dataclasses import dataclass
from typing import Literal

from app.schemas.lighthouse import (
    BotAccessStatus,
    BotCategory,
    BotStatus,
    CrawlerGovernance,
    ScrapingRisk,
)

# Known AI bots tracked in FindableAI
AI_BOTS_SPEC: list[dict[str, str]] = [
    {"bot": "GPTBot", "category": "training"},
    {"bot": "PerplexityBot", "category": "search"},
    {"bot": "Bytespider", "category": "scraper"},
    {"bot": "OAI-SearchBot", "category": "search"},
    {"bot": "ChatGPT-User", "category": "search"},
    {"bot": "Claude-SearchBot", "category": "search"},
    {"bot": "ClaudeBot", "category": "training"},
    {"bot": "Google-Extended", "category": "training"},
    {"bot": "CCBot", "category": "scraper"},
]

SENSITIVE_PATHS = ["/pricing", "/api", "/docs", "/features", "/about"]


@dataclass
class RobotsFeatureVector:
    citation_bots_allowed_ratio: float
    training_bots_blocked_ratio: float
    total_disallow_rules: int
    total_allow_rules: int
    allow_disallow_ratio: float
    wildcard_rule_count: int
    has_blanket_disallow: int
    crawl_delay_max: float
    has_sitemap: int
    sensitive_paths_exposed: int
    sensitive_paths_blocked: int
    unique_user_agents: int
    has_ai_specific_rules: int
    path_conflict_count: int
    file_size_bytes: int


def _is_bot_allowed(rp: urllib.robotparser.RobotFileParser, bot_name: str, path: str = "/") -> bool:
    """
    Check if a specific user-agent is permitted for the given path.
    Falls back to True if the robot parser has no entries for this bot or wildcard.
    """
    try:
        can_fetch = rp.can_fetch(bot_name, path)
        return bool(can_fetch)
    except Exception:
        return True


def extract_features(robots_txt: str) -> tuple[RobotsFeatureVector, list[BotStatus]]:
    """
    Deterministic 15-feature extraction vector from raw robots.txt (§5.3).
    """
    raw_text = robots_txt or ""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip() and not line.strip().startswith("#")]

    rp = urllib.robotparser.RobotFileParser()
    rp.parse(raw_text.splitlines() if raw_text else ["User-agent: *", "Allow: /"])

    total_disallow = 0
    total_allow = 0
    wildcard_count = 0
    has_blanket_disallow = 0
    crawl_delays: list[float] = []
    has_sitemap = 1 if re.search(r"^\s*sitemap:\s*", raw_text, re.IGNORECASE | re.MULTILINE) else 0
    user_agents: set[str] = set()
    paths_allow: set[str] = set()
    paths_disallow: set[str] = set()

    current_agents: list[str] = []
    for line in lines:
        lower_line = line.lower()
        if lower_line.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            current_agents.append(agent)
            user_agents.add(agent)
        elif lower_line.startswith("disallow:"):
            total_disallow += 1
            path = line.split(":", 1)[1].strip()
            paths_disallow.add(path)
            if "*" in path:
                wildcard_count += 1
            if path in ("/", "/*") and any(a == "*" for a in current_agents):
                has_blanket_disallow = 1
        elif lower_line.startswith("allow:"):
            total_allow += 1
            path = line.split(":", 1)[1].strip()
            paths_allow.add(path)
            if "*" in path:
                wildcard_count += 1
        elif lower_line.startswith("crawl-delay:"):
            try:
                val = float(line.split(":", 1)[1].strip())
                crawl_delays.append(val)
            except ValueError:
                pass

    total_rules = total_allow + total_disallow
    allow_ratio = (total_allow / total_rules) if total_rules > 0 else 1.0
    crawl_delay_max = max(crawl_delays) if crawl_delays else 0.0

    # Path conflicts (same path specified in allow and disallow)
    path_conflict_count = len(paths_allow.intersection(paths_disallow))

    # Evaluate bot accessibility matrix
    bot_matrix: list[BotStatus] = []
    citation_allowed_count = 0
    citation_total = 0
    training_blocked_count = 0
    training_total = 0

    known_ai_names = {b["bot"].lower() for b in AI_BOTS_SPEC}
    has_ai_specific_rules = 1 if any(a.lower() in known_ai_names for a in user_agents) else 0

    for bot_def in AI_BOTS_SPEC:
        bot_name = bot_def["bot"]
        category = bot_def["category"]
        allowed = _is_bot_allowed(rp, bot_name, "/")
        status: BotAccessStatus = "allowed" if allowed else "blocked"

        impact: str | None = None
        if category == "search":
            citation_total += 1
            if allowed:
                citation_allowed_count += 1
                impact = "positive"
            else:
                impact = "critical"
        elif category == "training":
            training_total += 1
            if not allowed:
                training_blocked_count += 1
                impact = "neutral"
            else:
                impact = "neutral"
        elif category == "scraper":
            if not allowed:
                impact = "positive"
            else:
                impact = "critical"

        bot_matrix.append(
            BotStatus(
                bot=bot_name,
                category=category,  # type: ignore[arg-type]
                status=status,
                impact=impact,
            )
        )

    citation_bots_allowed_ratio = (
        (citation_allowed_count / citation_total) if citation_total > 0 else 1.0
    )
    training_bots_blocked_ratio = (
        (training_blocked_count / training_total) if training_total > 0 else 0.0
    )

    # Sensitive path analysis
    exposed_count = 0
    blocked_count = 0
    for p in SENSITIVE_PATHS:
        if _is_bot_allowed(rp, "*", p):
            exposed_count += 1
        else:
            blocked_count += 1

    feature_vec = RobotsFeatureVector(
        citation_bots_allowed_ratio=citation_bots_allowed_ratio,
        training_bots_blocked_ratio=training_bots_blocked_ratio,
        total_disallow_rules=total_disallow,
        total_allow_rules=total_allow,
        allow_disallow_ratio=allow_ratio,
        wildcard_rule_count=wildcard_count,
        has_blanket_disallow=has_blanket_disallow,
        crawl_delay_max=crawl_delay_max,
        has_sitemap=has_sitemap,
        sensitive_paths_exposed=exposed_count,
        sensitive_paths_blocked=blocked_count,
        unique_user_agents=len(user_agents),
        has_ai_specific_rules=has_ai_specific_rules,
        path_conflict_count=path_conflict_count,
        file_size_bytes=len(raw_text.encode("utf-8")),
    )

    return feature_vec, bot_matrix


def compute_ai_visibility_index(features: RobotsFeatureVector) -> int:
    """
    Deterministic AI Visibility Index (0-100) per §5.4.
    """
    score = 100.0

    # Critical penalties
    if features.has_blanket_disallow:
        score -= 60.0

    # Citation bot accessibility (most important)
    score -= (1.0 - features.citation_bots_allowed_ratio) * 30.0

    # Reward training bot blocking (protecting IP)
    score += features.training_bots_blocked_ratio * 5.0

    # Path conflict penalties
    score -= features.path_conflict_count * 3.0

    # Crawl delay penalty
    if features.crawl_delay_max > 10:
        score -= 10.0
    elif features.crawl_delay_max > 5:
        score -= 5.0

    # Sensitive path exposure bonus (pricing, docs, features allowed)
    if features.sensitive_paths_exposed >= 3:
        score += 5.0

    # llms.txt / Sitemap bonus
    if features.has_sitemap:
        score += 3.0

    clamped = max(0.0, min(100.0, score))
    return int(round(clamped))


def classify_scraping_risk(features: RobotsFeatureVector, bot_matrix: list[BotStatus]) -> ScrapingRisk:
    """
    Scraping Risk Classification per §5.4:
    - Low: Training bots blocked AND citation bots allowed
    - Moderate: Mixed
    - Critical: All bots allowed (including scrapers) OR blanket disallow
    """
    if features.has_blanket_disallow:
        return "critical"

    scraper_statuses = [b.status for b in bot_matrix if b.category == "scraper"]
    if all(s == "allowed" for s in scraper_statuses) and scraper_statuses:
        return "critical"

    if features.training_bots_blocked_ratio >= 0.6 and features.citation_bots_allowed_ratio >= 0.75:
        return "low"

    if features.citation_bots_allowed_ratio < 0.5:
        return "critical"

    return "moderate"


def analyze_robots_txt(robots_txt: str, llms_txt_present: bool = False) -> CrawlerGovernance:
    """
    Complete analysis pipeline synthesizing governance outputs.
    """
    features, bot_matrix = extract_features(robots_txt)
    visibility_index = compute_ai_visibility_index(features)
    risk = classify_scraping_risk(features, bot_matrix)

    return CrawlerGovernance(
        ai_visibility_index=visibility_index,
        scraping_risk=risk,
        bot_matrix=bot_matrix,
        llms_txt_present=llms_txt_present,
    )


def generate_optimized_robots_txt(
    domain: str = "example.com",
    sitemap_url: str | None = None,
) -> str:
    """
    Pareto-optimal robots.txt generator per §5.5 balancing citation access vs scraping protection.
    """
    sitemap_directive = (
        f"Sitemap: {sitemap_url}" if sitemap_url else f"Sitemap: https://{domain}/sitemap.xml"
    )

    return f"""# === FindableAI Optimized robots.txt ===
# Strategy: Maximize AI search citations, block training scrapers

# --- AI Search & Citation Bots (ALLOW) ---
User-agent: OAI-SearchBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Claude-SearchBot
Allow: /

# --- AI Training Bots (BLOCK to protect data) ---
User-agent: GPTBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: Bytespider
Disallow: /

# --- Default: Allow traditional search engines ---
User-agent: *
Allow: /

{sitemap_directive}
"""
