"""
Verified HTTP fetching for discovery (Phase 15).

HTTP 200 is not proof: bceao.int answers unknown paths with a redirect to its homepage
and a 200 status. Every fetch therefore records the final URL, status and content type, and
callers decide whether the content is what they asked for.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

USER_AGENT = "UMOA-Financial-Intelligence/1.0 (discovery engine; official sources only)"
# Transient answers retried with a growing pause (audit 22/10/2026, M4/D6): a single timeout or 503 no
# longer counts as "not found". 429 honours Retry-After.
RETRY_STATUS = (429, 500, 502, 503, 504)
RETRIES = 2
BACKOFF_SECONDS = 2.0
RETRY_AFTER_MAX = 120.0


@dataclass
class FetchResult:
    url: str
    final_url: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    content: bytes | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status_code == 200 and self.content is not None

    @property
    def text(self) -> str:
        if not self.content:
            return ""
        return self.content.decode("utf-8", errors="ignore")

    @property
    def is_pdf(self) -> bool:
        return bool(self.content and self.content[:5] == b"%PDF-")

    @property
    def redirected_to_homepage(self) -> bool:
        """True when a deep URL landed on the site root (soft 404)."""
        if not self.final_url:
            return False
        requested = urlparse(self.url)
        final = urlparse(self.final_url)
        deep_request = requested.path.strip("/") not in ("", "fr", "en")
        landed_root = final.path.strip("/") in ("", "fr", "en") and not final.query
        return deep_request and landed_root


class OfficialFetcher:
    """Polite async fetcher: a pause between two requests to the SAME host, retries with backoff on
    transient failures, a body read in chunks and refused beyond ``max_bytes`` (never a silently cut PDF),
    and robots.txt awareness."""

    def __init__(self, timeout: float = 60.0, delay_seconds: float = 0.5, max_bytes: int = 60_000_000,
                 retries: int = RETRIES, backoff_seconds: float = BACKOFF_SECONDS,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.timeout = timeout
        self.delay_seconds = delay_seconds
        self.max_bytes = max_bytes
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self._client: httpx.AsyncClient | None = None
        self._robots: dict[str, RobotFileParser | None] = {}
        self._sitemaps: dict[str, tuple[str, ...]] = {}
        self._last_request: dict[str, float] = {}
        self._transport = transport  # tests: httpx.MockTransport

    async def __aenter__(self) -> OfficialFetcher:
        self._client = httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT},
            transport=self._transport,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _pause(self, host: str) -> None:
        loop = asyncio.get_running_loop()
        last = self._last_request.get(host)
        if last is not None:
            remaining = last + self.delay_seconds - loop.time()
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last_request[host] = loop.time()

    async def get(self, url: str, *, follow_redirects: bool = True) -> FetchResult:
        assert self._client is not None, "use 'async with OfficialFetcher()'"
        host = urlparse(url).netloc
        result = FetchResult(url=url, error="not fetched")
        for attempt in range(self.retries + 1):
            await self._pause(host)
            result, retry_after = await self._once(url, follow_redirects=follow_redirects)
            transient = result.status_code in RETRY_STATUS or (result.status_code is None and result.error
                                                               and not result.error.startswith("too_large"))
            if not transient or attempt == self.retries:
                return result
            wait = retry_after if retry_after is not None else self.backoff_seconds * (2 ** attempt)
            logger.info("fetch_retry", url=url, attempt=attempt + 1, wait_seconds=wait, error=result.error)
            await asyncio.sleep(wait)
        return result

    async def _once(self, url: str, *, follow_redirects: bool = True) -> tuple[FetchResult, float | None]:
        try:
            async with self._client.stream("GET", url, follow_redirects=follow_redirects) as resp:
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        logger.warning("fetch_too_large", url=url, max_bytes=self.max_bytes)
                        return FetchResult(url=url, final_url=str(resp.url), status_code=resp.status_code,
                                           error=f"too_large: over {self.max_bytes} bytes"), None
                    chunks.append(chunk)
                retry_after = None
                if resp.status_code == 429:
                    try:
                        retry_after = min(float(resp.headers.get("retry-after", "")), RETRY_AFTER_MAX)
                    except ValueError:
                        retry_after = None
                return FetchResult(
                    url=url,
                    final_url=str(resp.url),
                    status_code=resp.status_code,
                    content_type=resp.headers.get("content-type"),
                    content=b"".join(chunks),
                    error=None if resp.status_code == 200 else f"HTTP {resp.status_code}",
                ), retry_after
        except Exception as err:  # network errors are recorded, never raised to the loop
            logger.warning("discovery_fetch_failed", url=url, error=str(err))
            return FetchResult(url=url, error=f"{type(err).__name__}: {err}"), None

    async def allowed_by_robots(self, url: str, *, follow_redirects: bool = True) -> bool:
        """robots.txt check (used for institution websites). Unknown robots → allowed."""
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self._robots:
            res = await self.get(urljoin(root, "/robots.txt"), follow_redirects=follow_redirects)
            if res.ok and res.content:
                rp = RobotFileParser()
                lines = res.text.splitlines()
                rp.parse(lines)
                self._robots[root] = rp
                self._sitemaps[root] = tuple(
                    value.strip()
                    for line in lines
                    if line.strip().lower().startswith("sitemap:")
                    if (value := line.split(":", 1)[1].strip())
                    and urlparse(value).scheme.lower() in ("http", "https")
                    and urlparse(value).netloc
                )
            else:
                self._robots[root] = None
                self._sitemaps[root] = ()
        rp = self._robots[root]
        return True if rp is None else rp.can_fetch(USER_AGENT, url)

    async def sitemap_urls(self, url: str) -> list[str]:
        """Sitemaps declared by robots.txt, with a conventional fallback."""
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        await self.allowed_by_robots(url)
        declared = list(self._sitemaps.get(root, ()))
        return declared or [urljoin(f"{root}/", "sitemap.xml")]


_HREF_RE = re.compile(r"""<a\b[^>]*?href\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """(absolute_url, anchor_text) for every http(s) link of a page."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, anchor in _HREF_RE.findall(html):
        url = urljoin(base_url, href.strip().replace("&amp;", "&"))
        if urlparse(url).scheme not in ("http", "https") or url in seen:
            continue
        seen.add(url)
        import html as html_lib

        out.append((url, " ".join(html_lib.unescape(_TAG_RE.sub(" ", anchor)).split())))
    return out


def html_to_text(html: str) -> str:
    import html as html_lib

    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    return " ".join(html_lib.unescape(_TAG_RE.sub(" ", body)).split())


def extract_sitemap_entries(content: bytes, base_url: str) -> tuple[bool, list[tuple[str, str]]]:
    """Parse a sitemap or sitemap index into (URL, title hint) entries."""
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return False, []

    is_index = root.tag.rsplit("}", 1)[-1].lower() == "sitemapindex"
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for container in root:
        location_node = next(
            (element for element in container.iter()
             if element.tag.rsplit("}", 1)[-1].lower() == "loc" and element.text),
            None,
        )
        if location_node is None or not location_node.text:
            continue
        location = urljoin(base_url, location_node.text.strip())
        parsed = urlparse(location)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc or location in seen:
            continue
        seen.add(location)
        title_hints = [
            element.text.strip()
            for element in container.iter()
            if element.tag.rsplit("}", 1)[-1].lower() in ("title", "name")
            and element.text and element.text.strip()
        ]
        entries.append((location, " ".join(title_hints)))
    return is_index, entries


def is_pdf_url(url: str) -> bool:
    """Recognize a PDF when its filename is in the path or a query parameter."""
    parsed = urlparse(url)
    return unquote(parsed.path).lower().endswith(".pdf") or ".pdf" in unquote(parsed.query).lower()
