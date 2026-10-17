import pytest

from app.core.security import SSRFSecurityException
from app.crawler.crawler import AsyncCrawler

SAMPLE_INDEX_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Shop</title></head>
<body>
  <nav>
    <a href="/about">About Us</a>
    <a href="https://testshop.com/pricing">Pricing</a>
    <a href="https://external-domain.com/blog">External Blog</a>
    <a href="mailto:info@testshop.com">Contact Email</a>
    <a href="#section-contact">Anchor</a>
  </nav>
  <main>
    <h1>Welcome to Test Shop</h1>
  </main>
</body>
</html>
"""

SPA_HTML = """
<!DOCTYPE html>
<html>
<head><title>React App</title></head>
<body>
  <div id="root"></div>
  <script src="/bundle.js"></script>
</body>
</html>
"""


def test_extract_internal_links():
    crawler = AsyncCrawler()
    html_with_extras = """
    <nav>
        <a href="/about">About Us</a>
        <a href="/about/">About Us duplicate with slash</a>
        <a href="/pricing?utm_source=twitter&ref=blog&valid_param=1">Pricing</a>
        <a href="/docs/guide.pdf">PDF Manual</a>
        <a href="/images/logo.png">Logo PNG</a>
        <a href="https://testshop.com/pricing">Pricing Absolute</a>
        <a href="https://external-domain.com/blog">External Blog</a>
        <a href="mailto:info@testshop.com">Contact Email</a>
        <a href="#section-contact">Anchor</a>
    </nav>
    """
    links = crawler.extract_internal_links(html_with_extras, "https://testshop.com/index.html")

    # Should discover internal links on testshop.com normalized without tracking params
    assert "https://testshop.com/about" in links
    assert "https://testshop.com/about/" not in links  # Trailing slash normalized
    assert "https://testshop.com/pricing?valid_param=1" in links
    assert "utm_source" not in " ".join(links)
    assert "ref=blog" not in " ".join(links)

    # Should ignore binary assets (.pdf, .png)
    assert not any(link.endswith(".pdf") for link in links)
    assert not any(link.endswith(".png") for link in links)

    # Should ignore external domains, mailto, and fragment anchors
    assert "https://external-domain.com/blog" not in links
    assert "mailto:info@testshop.com" not in links
    assert "#section-contact" not in links


def test_spa_detection():
    crawler = AsyncCrawler()
    assert crawler.detect_spa(SPA_HTML) is True
    assert crawler.detect_spa(SAMPLE_INDEX_HTML) is False


@pytest.mark.asyncio
async def test_crawler_blocks_ssrf_start_url():
    crawler = AsyncCrawler(allow_private=False)
    with pytest.raises(SSRFSecurityException):
        await crawler.crawl("http://127.0.0.1:8000")

    with pytest.raises(SSRFSecurityException):
        await crawler.crawl("http://169.254.169.254/latest/meta-data/")
