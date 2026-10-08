import pytest

from app.crawler.dom_chunker import ChunkData
from app.engines.lighthouse import LighthouseEngine
from app.schemas.intelligence import Contradiction, ContradictionSeverity, EntailmentStatus, IntentCategory, IntentEvaluation

SAMPLE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Acme AI Platform</title>
  <meta name="description" content="Next-generation autonomous agent orchestration for enterprise teams." />
  <meta property="og:title" content="Acme AI Platform" />
  <meta property="og:description" content="Enterprise AI Orchestration" />
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": "Acme AI",
    "url": "https://acme.ai",
    "dateModified": "2026-10-01"
  }
  </script>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [{
      "@type": "Question",
      "name": "What is Acme AI?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Acme AI provides enterprise machine discoverability."
      }
    }]
  }
  </script>
</head>
<body>
  <header><h1>Acme AI Platform</h1></header>
  <nav><a href="/privacy">Privacy Policy</a> <a href="/terms">Terms</a></nav>
  <main>
    <section id="features">
      <h2 id="features-title">Core Features</h2>
      <p>High performance deterministic engine execution.</p>
    </section>
    <section id="pricing">
      <h2 id="pricing-title">Pricing Plans</h2>
      <p>Enterprise subscription starting at $99/mo.</p>
    </section>
  </main>
</body>
</html>
"""

SAMPLE_ROBOTS = """
User-agent: *
Allow: /
"""


def test_lighthouse_scoring_complete():
    evals = [
        IntentEvaluation(
            intent_id="intent_001",
            query="Does Acme support enterprise orchestration?",
            persona="cto",
            category=IntentCategory.AVAILABILITY,
            status=EntailmentStatus.SUPPORTED,
            confidence=0.95,
            reasoning="Supported in features",
        ),
        IntentEvaluation(
            intent_id="intent_002",
            query="What is the pricing?",
            persona="procurement",
            category=IntentCategory.PRICING,
            status=EntailmentStatus.SUPPORTED,
            confidence=0.92,
            reasoning="Found pricing section",
        ),
    ]

    chunks = [
        ChunkData(url="https://acme.ai", dom_path="body > main > section#features", content="Core Features High performance", tag="section", word_count=20),
        ChunkData(url="https://acme.ai", dom_path="body > main > section#pricing", content="Pricing Plans Enterprise subscription starting at $99/mo.", tag="section", word_count=25),
    ]

    engine = LighthouseEngine(
        url="https://acme.ai",
        html_documents=[SAMPLE_HTML],
        chunks=chunks,
        evaluations=evals,
        contradictions=[],
        robots_txt=SAMPLE_ROBOTS,
        scan_id="scan_unit_test",
    )

    resp = engine.evaluate()
    assert resp.scan_id == "scan_unit_test"
    assert "chatgpt" in resp.engines
    assert "gemini" in resp.engines
    assert "perplexity" in resp.engines
    assert "claude" in resp.engines

    # ChatGPT score should be strong given Organization + FAQPage schema + supported intents
    chatgpt = resp.engines["chatgpt"]
    assert chatgpt.score >= 70
    assert "bot_access" in chatgpt.criteria
    assert "schema_coverage" in chatgpt.criteria
    assert "answerability" in chatgpt.criteria

    # Gemini score checks entity_strength & freshness
    gemini = resp.engines["gemini"]
    assert gemini.score >= 70
    assert gemini.criteria["freshness"].score >= 90

    # Perplexity checks anchor citations & chunk quality
    pplx = resp.engines["perplexity"]
    assert pplx.criteria["anchor_citations"].score >= 80

    # Claude checks consistency & policy docs
    claude = resp.engines["claude"]
    assert claude.criteria["consistency"].score == 100
    assert claude.criteria["policy_docs"].score >= 80

    # Audits
    assert len(resp.audits.passed) > 0
    passed_ids = {p.id for p in resp.audits.passed}
    assert "https-active" in passed_ids
    assert "zero-contradictions" in passed_ids


def test_lighthouse_contradiction_penalty():
    contradictions = [
        Contradiction(
            entity="pricing",
            conflict="Plans state $99/mo on home, but $199/mo in FAQ",
            values=["$99/mo", "$199/mo"],
            severity=ContradictionSeverity.HARD_CONTRADICTION,
            source_urls=["https://acme.ai", "https://acme.ai/faq"],
            dom_paths=["section#pricing", "div#faq"],
        )
    ]

    engine = LighthouseEngine(
        url="https://acme.ai",
        html_documents=[SAMPLE_HTML],
        evaluations=[],
        contradictions=contradictions,
        robots_txt=SAMPLE_ROBOTS,
        scan_id="scan_penalty_test",
    )

    resp = engine.evaluate()
    # Claude heavily weights consistency (30%)
    claude = resp.engines["claude"]
    assert claude.criteria["consistency"].score < 100

    # Audit diagnostics should report contradiction
    diag_ids = {d.id for d in resp.audits.diagnostics}
    assert "cross-page-contradiction" in diag_ids
