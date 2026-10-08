import pytest

from app.crawler.dom_chunker import ChunkData
from app.engines.llms_txt_generator import generate_llms_full_txt, generate_llms_txt


def test_generate_llms_txt_categorization():
    urls = [
        "https://acme.ai/docs/getting-started",
        "https://acme.ai/api/v1/reference",
        "https://acme.ai/pricing",
        "https://acme.ai/features",
        "https://acme.ai/privacy",
        "https://acme.ai/terms",
    ]
    facts = {
        "phone": "+1-800-555-0199",
        "email": "support@acme.ai",
        "address": "San Francisco, CA",
    }

    manifest = generate_llms_txt(
        domain="acme.ai",
        title="Acme AI | Enterprise Platform",
        description="Autonomous machine discoverability platform.",
        crawled_urls=urls,
        business_facts=facts,
    )

    assert "# Acme AI" in manifest
    assert "> Autonomous machine discoverability platform." in manifest
    assert "## Organization Information" in manifest
    assert "+1-800-555-0199" in manifest
    assert "## Docs" in manifest
    assert "## Product" in manifest
    assert "## Legal" in manifest
    assert "[Getting Started](https://acme.ai/docs/getting-started)" in manifest
    assert "[Pricing](https://acme.ai/pricing)" in manifest
    assert "[Privacy](https://acme.ai/privacy)" in manifest


def test_generate_llms_full_txt():
    chunks = [
        ChunkData(
            url="https://acme.ai/features",
            dom_path="section#features",
            content="Feature 1: Real-time static AST analysis for microdata.",
            tag="section",
            word_count=8,
        ),
        ChunkData(
            url="https://acme.ai/pricing",
            dom_path="section#pricing",
            content="Pricing Tier: Professional edition is $499 billed annually.",
            tag="section",
            word_count=8,
        ),
    ]

    full_manifest = generate_llms_full_txt(
        domain="acme.ai",
        title="Acme AI",
        description="Full text corpus for AI extraction.",
        chunks=chunks,
    )

    assert "# Acme AI — Full Knowledge Corpus" in full_manifest
    assert "Feature 1: Real-time static AST analysis" in full_manifest
    assert "Pricing Tier: Professional edition" in full_manifest
