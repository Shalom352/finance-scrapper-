"""Optional web search adapter used only to produce candidate official-site leads."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from scraping.universe.strategies.base import SearchProvider


class BraveSearchProvider(SearchProvider):
    """Brave Web Search API adapter. Callers must verify every result independently."""

    name = "brave"
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str, *, timeout_seconds: float = 15.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str, *, country_code: str | None = None, limit: int = 10) -> list[str]:
        await asyncio.sleep(1.0)
        params = {"q": query, "count": max(1, min(limit, 10))}
        if country_code:
            params["country"] = country_code.upper()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                self.endpoint, params=params,
                headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        results = payload.get("web", {}).get("results", [])
        urls: list[str] = []
        for item in results:
            url = item.get("url") if isinstance(item, dict) else None
            if isinstance(url, str) and await _public_http_url(url) and url not in urls:
                urls.append(url)
        return urls


async def _public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() not in ("http", "https") or not host or parsed.username or parsed.password:
        return False
    if host in ("localhost", "localhost.localdomain") or host.endswith((".local", ".internal", ".localhost")):
        return False
    if "." not in host:
        return False
    try:
        if parsed.port not in (None, 80, 443):
            return False
    except ValueError:
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    try:
        answers = await asyncio.get_running_loop().getaddrinfo(
            host, parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
            type=socket.SOCK_STREAM,
        )
        addresses = {answer[4][0] for answer in answers}
        return bool(addresses) and all(ipaddress.ip_address(address.split("%", 1)[0]).is_global
                                       for address in addresses)
    except (OSError, ValueError):
        return False
