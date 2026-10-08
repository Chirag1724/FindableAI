import pytest

from app.engines.robots_analyzer import (
    analyze_robots_txt,
    classify_scraping_risk,
    compute_ai_visibility_index,
    extract_features,
    generate_optimized_robots_txt,
)

BALANCED_ROBOTS = """
User-agent: OAI-SearchBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Claude-SearchBot
Allow: /

User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: Bytespider
Disallow: /

User-agent: *
Allow: /
Sitemap: https://example.com/sitemap.xml
"""

BLANKET_BLOCK_ROBOTS = """
User-agent: *
Disallow: /
"""

PERMISSIVE_ROBOTS = """
User-agent: *
Allow: /
"""

CONFLICT_ROBOTS = """
User-agent: *
Allow: /pricing
Disallow: /pricing
Crawl-delay: 15
"""


def test_balanced_robots_extraction():
    features, bot_matrix = extract_features(BALANCED_ROBOTS)
    assert features.has_blanket_disallow == 0
    assert features.citation_bots_allowed_ratio == 1.0
    assert features.training_bots_blocked_ratio >= 0.6
    assert features.has_sitemap == 1
    assert features.has_ai_specific_rules == 1

    # Visibility index should be high (>= 90)
    score = compute_ai_visibility_index(features)
    assert score >= 90

    # Risk should be low
    risk = classify_scraping_risk(features, bot_matrix)
    assert risk == "low"


def test_blanket_block_penalties():
    features, bot_matrix = extract_features(BLANKET_BLOCK_ROBOTS)
    assert features.has_blanket_disallow == 1
    assert features.citation_bots_allowed_ratio == 0.0

    score = compute_ai_visibility_index(features)
    assert score <= 40

    risk = classify_scraping_risk(features, bot_matrix)
    assert risk == "critical"


def test_permissive_scraping_risk():
    features, bot_matrix = extract_features(PERMISSIVE_ROBOTS)
    risk = classify_scraping_risk(features, bot_matrix)
    # Allows all scrapers (Bytespider, CCBot) -> critical scraping risk
    assert risk == "critical"


def test_conflict_and_crawl_delay_penalties():
    features, _ = extract_features(CONFLICT_ROBOTS)
    assert features.path_conflict_count >= 1
    assert features.crawl_delay_max == 15.0

    score = compute_ai_visibility_index(features)
    assert score < 95


def test_analyze_robots_txt_helper():
    gov = analyze_robots_txt(BALANCED_ROBOTS, llms_txt_present=True)
    assert gov.ai_visibility_index >= 90
    assert gov.scraping_risk == "low"
    assert gov.llms_txt_present is True
    assert len(gov.bot_matrix) == 9

    # Verify bot entries
    bot_names = {b.bot for b in gov.bot_matrix}
    assert "GPTBot" in bot_names
    assert "PerplexityBot" in bot_names
    assert "Bytespider" in bot_names


def test_optimized_generator():
    text = generate_optimized_robots_txt("mytestdomain.com")
    assert "User-agent: OAI-SearchBot" in text
    assert "User-agent: PerplexityBot" in text
    assert "User-agent: CCBot" in text
    assert "Disallow: /" in text
    assert "Sitemap: https://mytestdomain.com/sitemap.xml" in text
