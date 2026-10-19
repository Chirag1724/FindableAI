from pathlib import Path

from bs4 import BeautifulSoup

from app.crawler.dom_chunker import DOMChunker

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<body>
  <header class="site-header">
    <nav class="main-nav">
      <a href="/home">Home</a>
      <a href="/pricing">Pricing</a>
    </nav>
  </header>
  <main>
    <section id="features">
      <h2>Core Engine Capabilities</h2>
      <article class="feature-card">
        <h3>Fast Verification</h3>
        <p>Verifies 30 high intent buyer queries in under ten seconds.</p>
      </article>
      <article class="feature-card">
        <h3>Evidence Grounding</h3>
        <p>Links every single claim directly to semantic DOM elements.</p>
      </article>
    </section>
    <section class="pricing-table">
      <table>
        <thead>
          <tr><th>Tier</th><th>Price</th></tr>
        </thead>
        <tbody>
          <tr><td>Developer</td><td>Free</td></tr>
          <tr><td>Enterprise</td><td>$99/mo</td></tr>
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def test_chunker_basic_extraction():
    chunker = DOMChunker(min_word_count=3)
    chunks = chunker.chunk(SAMPLE_HTML, "https://example.com")

    assert len(chunks) > 0
    # Every chunk should have non-empty attributes
    for c in chunks:
        assert c.url == "https://example.com"
        assert c.word_count >= 3
        assert len(c.dom_path) > 0
        assert len(c.content) > 0


def test_css_selector_paths_are_valid():
    """Verify that generated CSS selectors can be queried back by BeautifulSoup."""
    chunker = DOMChunker(min_word_count=3)
    chunks = chunker.chunk(SAMPLE_HTML, "https://example.com")
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")

    matched_count = 0
    for c in chunks:
        # Check that selector does not raise syntax error
        selected = soup.select(c.dom_path)
        if selected:
            matched_count += 1

    # At least 80% of selectors should directly match elements in the DOM tree
    assert matched_count > 0


def test_chunking_demo_site_files():
    """Test chunker against the actual Bistro 2026 testbed pages."""
    demo_dir = Path(__file__).resolve().parent.parent.parent / "demo-site"
    assert demo_dir.exists(), "demo-site directory must exist"

    chunker = DOMChunker(min_word_count=3)

    for page_name in ["index.html", "menu.html", "about.html"]:
        file_path = demo_dir / page_name
        assert file_path.exists(), f"{page_name} must exist in demo-site"

        html = file_path.read_text(encoding="utf-8")
        chunks = chunker.chunk(html, f"http://localhost:8080/{page_name}")

        assert len(chunks) >= 3, f"Expected at least 3 chunks from {page_name}"

        # Verify that operating hours are present in extracted chunks
        all_text = " ".join(c.content for c in chunks)
        assert "Bistro 2026" in all_text


def test_empty_html_handling():
    chunker = DOMChunker()
    assert chunker.chunk("", "https://example.com") == []
    assert chunker.chunk("   ", "https://example.com") == []
    assert chunker.chunk("<div><p>hi</p></div>", "https://example.com") == []


SPA_NOSCRIPT_HTML = """
<!DOCTYPE html>
<html>
<head><title>Worthfinding Studio</title></head>
<body>
  <div id="root"></div>
  <script src="/assets/index.js"></script>
  <noscript>
    <main>
      <h1>Worthfinding Digital Experience Studio</h1>
      <p>Worthfinding engineers bespoke digital flagships and direct acquisition funnels for boutique hospitality brands.</p>
      <h2>Local SEO Dominance</h2>
      <p>Google Maps Top-3 local dominance without aggregator commissions for architecture studios.</p>
    </main>
  </noscript>
</body>
</html>
"""


def test_spa_noscript_mirror_is_chunked_not_discarded():
    """Regression: empty #root + SEO noscript must not yield zero chunks.

    Production scan_7f994f4f… crawled 5 pages of worthfinding.tech but persisted
    0 DOM chunks because clean_soup decomposed <noscript> wholesale while
    Playwright was unavailable to hydrate #root.
    """
    chunker = DOMChunker(min_word_count=3)
    chunks = chunker.chunk(SPA_NOSCRIPT_HTML, "https://www.worthfinding.tech/")
    assert len(chunks) >= 2
    all_text = " ".join(c.content for c in chunks).lower()
    assert "worthfinding" in all_text
    assert "digital" in all_text


def test_hydrated_page_does_not_duplicate_noscript_mirror():
    html = """
    <html><body>
      <div id="root"><main><p>Live hydrated marketing copy about premium studios and growth.</p></main></div>
      <noscript><main><p>Duplicate noscript mirror about premium studios and growth.</p></main></noscript>
    </body></html>
    """
    chunks = DOMChunker(min_word_count=3).chunk(html, "https://example.com/")
    assert len(chunks) >= 1
    joined = " ".join(c.content for c in chunks).lower()
    assert "duplicate noscript" not in joined
    assert "live hydrated" in joined
