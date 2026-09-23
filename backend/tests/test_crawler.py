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
    links = crawler.extract_internal_links(SAMPLE_INDEX_HTML, "https://testshop.com/index.html")

    # Should discover internal links on testshop.com
    assert "https://testshop.com/about" in links
    assert "https://testshop.com/pricing" in links

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
