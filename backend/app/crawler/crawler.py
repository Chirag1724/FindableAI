import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.core.security import SSRFSecurityException, validate_target_url

logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    url: str
    html: str
    status_code: int
    internal_links: list[str] = field(default_factory=list)
    is_spa: bool = False


class AsyncCrawler:
    """
    Asynchronous Breadth-First-Search (BFS) web crawler with built-in SSRF protection,
    concurrency limits, and SPA detection.
    """

    def __init__(
        self,
        max_pages: int = settings.MAX_SCAN_PAGES,
        concurrency: int = 5,
        timeout_seconds: float = 15.0,
        allow_private: bool = False,
    ):
        self.max_pages = max_pages
        self.semaphore = asyncio.Semaphore(concurrency)
        self.timeout = httpx.Timeout(timeout_seconds, connect=10.0)
        self.allow_private = allow_private
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        }

    async def fetch_page_playwright(self, url: str) -> CrawlResult | None:
        """Safe browser-based rendering fallback for SPAs or client challenges."""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
                context = await browser.new_context(
                    user_agent=self.headers["User-Agent"],
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()
                try:
                    resp = await page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=12000,
                    )
                    html = await page.content()
                    status_code = resp.status if resp else 200
                    internal_links = self.extract_internal_links(html, url)
                    return CrawlResult(
                        url=page.url,
                        html=html,
                        status_code=status_code,
                        internal_links=internal_links,
                        is_spa=False,
                    )
                finally:
                    await browser.close()
        except Exception as pw_err:
            logger.info("Playwright browser rendering fallback bypassed for '%s': %s", url, pw_err)
            return None

    async def fetch_page(self, client: httpx.AsyncClient, url: str) -> CrawlResult | None:
        """Fetch a single page with SSRF validation, browser headers, and SPA fallback."""
        try:
            # Validate URL against SSRF rules before attempting connection
            validate_target_url(url, allow_private=self.allow_private)
        except SSRFSecurityException as e:
            logger.warning("SSRF check rejected URL '%s': %s", url, e)
            return None

        async with self.semaphore:
            try:
                response = await client.get(url, headers=self.headers, follow_redirects=True)
                content_type = response.headers.get("content-type", "").lower()

                # Only process HTML content
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    logger.debug("Skipping non-HTML URL '%s' (content-type: %s)", url, content_type)
                    return None

                html = response.text
                internal_links = self.extract_internal_links(html, str(response.url))
                is_spa = self.detect_spa(html)

                # If SPA shell or challenge checkpoint detected, attempt Playwright rendering
                if is_spa or (
                    response.status_code in (403, 429)
                    and any(kw in html.lower() for kw in ("checkpoint", "verifying", "challenge"))
                ):
                    pw_result = await self.fetch_page_playwright(url)
                    if pw_result:
                        return pw_result

                return CrawlResult(
                    url=str(response.url),
                    html=html,
                    status_code=response.status_code,
                    internal_links=internal_links,
                    is_spa=is_spa,
                )
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.warning("Failed to fetch '%s': %s", url, e)
                return None

    def extract_internal_links(self, html: str, base_url: str) -> list[str]:
        """Extract and normalize all internal links sharing the same hostname."""
        soup = BeautifulSoup(html, "lxml")
        base_parsed = urlparse(base_url)
        internal_links: set[str] = set()

        for a_tag in soup.find_all("a", href=True):
            raw_href = a_tag.get("href")
            if not isinstance(raw_href, str):
                continue
            raw_href = raw_href.strip()
            if not raw_href or raw_href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue

            full_url = urljoin(base_url, raw_href)
            defrag_url, _ = urldefrag(full_url)
            parsed = urlparse(defrag_url)

            # Restrict strictly to the same hostname & scheme
            if parsed.scheme in ("http", "https") and parsed.netloc == base_parsed.netloc:
                internal_links.add(defrag_url)

        return sorted(internal_links)

    def detect_spa(self, html: str) -> bool:
        """
        Detect if page is an empty client-side single page application (SPA)
        such as React/Vue/Angular waiting for JavaScript hydration.
        """
        soup = BeautifulSoup(html, "lxml")
        root = soup.find(id="root") or soup.find(id="app")
        if root and hasattr(root, "get_text"):
            text = root.get_text(strip=True)
            return len(text.split()) < 3
        return False

    async def crawl(self, start_url: str) -> list[CrawlResult]:
        """
        Execute an async BFS crawl starting at start_url, up to self.max_pages.
        """
        validate_target_url(start_url, allow_private=self.allow_private)

        visited: set[str] = set()
        queue: list[str] = [start_url]
        results: list[CrawlResult] = []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while queue and len(results) < self.max_pages:
                current_url = queue.pop(0)
                if current_url in visited:
                    continue

                visited.add(current_url)
                result = await self.fetch_page(client, current_url)
                if not result:
                    continue

                results.append(result)

                # Enqueue newly discovered internal links
                for link in result.internal_links:
                    if link not in visited and link not in queue:
                        queue.append(link)

        return results
