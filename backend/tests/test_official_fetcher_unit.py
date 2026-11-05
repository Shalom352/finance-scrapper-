"""
Audit 22/10/2026 (M4/D6): the shared fetcher retries transient failures with a growing pause, honours
Retry-After, never keeps a silently truncated body, and waits per host (not before every request).
"""
from __future__ import annotations

import httpx
import pytest

from scraping.universe.http import OfficialFetcher, extract_sitemap_entries, is_pdf_url


def fetcher(handler, **kw) -> OfficialFetcher:
    return OfficialFetcher(delay_seconds=0.0, backoff_seconds=0.0, transport=httpx.MockTransport(handler), **kw)


@pytest.mark.asyncio
async def test_transient_failures_are_retried_then_succeed():
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, content=b"ok")

    async with fetcher(handler) as f:
        res = await f.get("https://example.org/a")
    assert res.ok and res.content == b"ok" and len(calls) == 3


@pytest.mark.asyncio
async def test_a_definitive_answer_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(404)

    async with fetcher(handler) as f:
        res = await f.get("https://example.org/missing")
    assert res.status_code == 404 and res.error == "HTTP 404" and len(calls) == 1


@pytest.mark.asyncio
async def test_429_honours_retry_after(monkeypatch):
    import scraping.universe.http as http_mod

    waits = []
    real_sleep = http_mod.asyncio.sleep

    async def fake_sleep(seconds):
        waits.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(http_mod.asyncio, "sleep", fake_sleep)
    answers = iter([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, content=b"x")])
    async with fetcher(lambda request: next(answers)) as f:
        assert (await f.get("https://example.org/r")).ok
    assert 7.0 in waits


@pytest.mark.asyncio
async def test_a_body_over_the_limit_is_refused_not_truncated():
    async with fetcher(lambda request: httpx.Response(200, content=b"%PDF-" + b"0" * 100), max_bytes=50) as f:
        res = await f.get("https://example.org/big.pdf")
    assert not res.ok and res.content is None and res.error.startswith("too_large")


def test_sitemap_urls_and_index_are_parsed_with_title_hints():
    xml = b'''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
      xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
      <url><loc>https://bank.example/reports/2025.pdf?download=1</loc>
      <news:name>Annual report 2025</news:name></url></urlset>'''
    is_index, entries = extract_sitemap_entries(xml, "https://bank.example/sitemap.xml")
    assert not is_index
    assert entries == [("https://bank.example/reports/2025.pdf?download=1", "Annual report 2025")]

    index = b'''<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>/sitemap-reports.xml</loc></sitemap></sitemapindex>'''
    is_index, entries = extract_sitemap_entries(index, "https://bank.example/sitemap.xml")
    assert is_index and entries == [("https://bank.example/sitemap-reports.xml", "")]


def test_malformed_sitemap_and_pdf_query_urls_are_handled():
    assert extract_sitemap_entries(b"<not xml", "https://bank.example/") == (False, [])
    assert is_pdf_url("https://bank.example/download?file=report-2025.pdf")
    assert is_pdf_url("https://bank.example/report.pdf?download=1")
    assert not is_pdf_url("https://bank.example/reports/2025")
