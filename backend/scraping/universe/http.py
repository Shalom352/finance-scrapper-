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
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

USER_AGENT = "UMOA-Financial-Intelligence/1.0 (discovery engine; official sources only)"


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
    """Polite async fetcher with a per-host delay and robots.txt awareness."""

    def __init__(self, timeout: float = 60.0, delay_seconds: float = 0.5, max_bytes: int = 60_000_000) -> None:
        self.timeout = timeout
        self.delay_seconds = delay_seconds
        self.max_bytes = max_bytes
        self._client: httpx.AsyncClient | None = None
        self._robots: dict[str, RobotFileParser | None] = {}

    async def __aenter__(self) -> OfficialFetcher:
        self._client = httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, url: str) -> FetchResult:
        assert self._client is not None, "use 'async with OfficialFetcher()'"
        await asyncio.sleep(self.delay_seconds)
        try:
            resp = await self._client.get(url)
        except Exception as err:  # network errors are recorded, never raised to the loop
            logger.warning("discovery_fetch_failed", url=url, error=str(err))
            return FetchResult(url=url, error=f"{type(err).__name__}: {err}")
        content = resp.content[: self.max_bytes]
        return FetchResult(
            url=url,
            final_url=str(resp.url),
            status_code=resp.status_code,
            content_type=resp.headers.get("content-type"),
            content=content,
            error=None if resp.status_code == 200 else f"HTTP {resp.status_code}",
        )

    async def allowed_by_robots(self, url: str) -> bool:
        """robots.txt check (used for institution websites). Unknown robots → allowed."""
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self._robots:
            res = await self.get(urljoin(root, "/robots.txt"))
            if res.ok and res.content:
                rp = RobotFileParser()
                rp.parse(res.text.splitlines())
                self._robots[root] = rp
            else:
                self._robots[root] = None
        rp = self._robots[root]
        return True if rp is None else rp.can_fetch(USER_AGENT, url)


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
