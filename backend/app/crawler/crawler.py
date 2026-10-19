import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urldefrag, urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.core.security import SSRFSecurityException, validate_target_url

logger = logging.getLogger(__name__)

_TRACKING_QUERY_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "ref",
        "ref_src",
        "fbclid",
        "gclid",
        "msclkid",
        "_ga",
        "_gl",
    }
)

_NON_HTML_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".tgz",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
        ".ico",
        ".mp4",
        ".mp3",
        ".wav",
        ".avi",
        ".mov",
        ".exe",
        ".dmg",
        ".apk",
        ".iso",
        ".bin",
        ".docx",
        ".xlsx",
        ".pptx",
        ".csv",
    }
)


def canonicalize_url(url: str) -> str:
    """Canonicalize URL by stripping tracking parameters, normalizing trailing slashes, and removing fragments."""
    defrag_url, _ = urldefrag(url.strip())
    parsed = urlparse(defrag_url)

    # Filter out tracking query parameters
    if parsed.query:
        filtered_params = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_QUERY_PARAMS
        ]
        clean_query = urlencode(filtered_params)
    else:
        clean_query = ""

    # Normalize trailing slash: remove trailing slash if path is non-empty and not root
    path = parsed.path
    if path and path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return parsed._replace(query=clean_query, path=path).geturl()


@dataclass
class CrawlResult:
    url: str
    html: str
    status_code: int
    internal_links: list[str] = field(default_factory=list)
    is_spa: bool = False
    robots_txt: str = ""


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
        self.concurrency = concurrency
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

    def _fetch_playwright_sync(self, url: str) -> CrawlResult | None:
        """Synchronous browser runner isolated in a worker thread to bypass Windows asyncio subprocess limitations."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
                )
                try:
                    context = browser.new_context(
                        user_agent=self.headers["User-Agent"],
                        viewport={"width": 1280, "height": 800},
                    )
                    page = context.new_page()
                    resp = page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=15000,
                    )
                    html = page.content()
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
                    browser.close()
        except Exception as pw_err:
            logger.info("Playwright sync fallback bypassed for '%s': %s", url, pw_err)
            return None

    async def fetch_page_playwright(self, url: str) -> CrawlResult | None:
        """Safe browser-based rendering fallback for SPAs or client challenges."""
        try:
            import sys

            # On Windows, SelectorEventLoop (used by uvicorn reload) does not support subprocesses.
            # Using asyncio.to_thread with sync_playwright completely circumvents NotImplementedError.
            if sys.platform == "win32":
                return await asyncio.to_thread(self._fetch_playwright_sync, url)

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
        """Fetch a single page with SSRF validation, browser headers, retry backoff, and SPA fallback."""
        try:
            # Validate URL against SSRF rules before attempting connection
            validate_target_url(url, allow_private=self.allow_private)
        except SSRFSecurityException as e:
            logger.warning("SSRF check rejected URL '%s': %s", url, e)
            return None

        async with self.semaphore:
            response = None
            last_err = None
            # Retry up to 3 times for transient connection or DNS resolution glitches (e.g. getaddrinfo timeouts)
            for attempt in range(3):
                try:
                    response = await client.get(url, headers=self.headers, follow_redirects=True)
                    break
                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    last_err = e
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue

            if response is None:
                logger.info(
                    "Direct HTTP fetch failed for '%s': %s; attempting Playwright browser fallback",
                    url,
                    last_err,
                )
                pw_result = await self.fetch_page_playwright(url)
                if pw_result:
                    return pw_result
                logger.warning("Failed to fetch '%s': %s", url, last_err)
                return None

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
                # Playwright unavailable / failed: keep HTTP HTML but promote
                # ``<noscript>`` SEO mirrors so DOMChunker is not left with an
                # empty #root shell (otherwise pages_crawled>0 and chunks=0).
                if is_spa:
                    html = self.promote_noscript_html(html)

            return CrawlResult(
                url=str(response.url),
                html=html,
                status_code=response.status_code,
                internal_links=internal_links,
                is_spa=is_spa,
            )

    def extract_internal_links(self, html: str, base_url: str) -> list[str]:
        """Extract and normalize all internal links sharing the same hostname, stripping tracking params and binary assets."""
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
            canonical = canonicalize_url(full_url)
            parsed = urlparse(canonical)

            # Restrict strictly to the same hostname & scheme
            if parsed.scheme in ("http", "https") and parsed.netloc == base_parsed.netloc:
                # Pre-filter static binary assets (PDFs, images, archives)
                path_lower = parsed.path.lower()
                if any(path_lower.endswith(ext) for ext in _NON_HTML_EXTENSIONS):
                    continue
                internal_links.add(canonical)

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

    @staticmethod
    def promote_noscript_html(html: str) -> str:
        """Unwrap ``<noscript>`` bodies into the document when the SPA shell is empty.

        Used when Playwright cannot render the hydrated DOM so chunking still
        sees crawler-visible SEO content instead of an empty ``#root``.
        """
        if not html or "<noscript" not in html.lower():
            return html
        soup = BeautifulSoup(html, "lxml")
        root = soup.find(id="root") or soup.find(id="app")
        root_words = 0
        if root is not None and hasattr(root, "get_text"):
            root_words = len(root.get_text(" ", strip=True).split())
        if root_words >= 3:
            return html
        from bs4 import Tag

        promoted = 0
        for el in list(soup.find_all("noscript")):
            if isinstance(el, Tag):
                el.unwrap()
                promoted += 1
        if not promoted:
            return html
        return str(soup)

    async def fetch_robots_txt(self, client: httpx.AsyncClient, base_url: str) -> str:
        """Fetch robots.txt for the given base domain with SSRF validation."""
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        for attempt in range(2):
            try:
                validate_target_url(robots_url, allow_private=self.allow_private)
                resp = await client.get(robots_url, headers=self.headers, follow_redirects=True)
                if resp.status_code == 200:
                    return resp.text
                break
            except Exception as e:
                logger.debug(
                    "Attempt %d failed to fetch robots.txt from '%s': %s",
                    attempt + 1,
                    robots_url,
                    e,
                )
                if attempt == 0:
                    await asyncio.sleep(0.5)
        return ""

    async def crawl(self, start_url: str) -> list[CrawlResult]:
        """
        Execute an async BFS crawl starting at start_url, up to self.max_pages,
        using concurrent batch dispatch bounded by self.concurrency.
        """
        canonical_start = canonicalize_url(start_url)
        validate_target_url(canonical_start, allow_private=self.allow_private)

        visited: set[str] = set()
        queue: list[str] = [canonical_start]
        results: list[CrawlResult] = []

        concurrency_limit = max(1, getattr(self, "concurrency", 5))

        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=50,
            keepalive_expiry=30.0,
        )
        async with httpx.AsyncClient(timeout=self.timeout, limits=limits) as client:
            robots_txt = await self.fetch_robots_txt(client, canonical_start)

            while queue and len(results) < self.max_pages:
                remaining_slots = self.max_pages - len(results)
                batch_size = min(concurrency_limit, remaining_slots, len(queue))

                # Collect next wave of unvisited URLs
                batch_urls: list[str] = []
                while queue and len(batch_urls) < batch_size:
                    candidate = queue.pop(0)
                    if candidate not in visited:
                        visited.add(candidate)
                        batch_urls.append(candidate)

                if not batch_urls:
                    continue

                # Fetch batch in parallel
                batch_results = await asyncio.gather(
                    *[self.fetch_page(client, u) for u in batch_urls],
                    return_exceptions=True,
                )

                for res in batch_results:
                    if not isinstance(res, CrawlResult):
                        continue

                    res.robots_txt = robots_txt
                    results.append(res)
                    if len(results) >= self.max_pages:
                        break

                    # Enqueue newly discovered internal links
                    for link in res.internal_links:
                        if link not in visited and link not in queue:
                            queue.append(link)

        return results
