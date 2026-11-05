"""
Audit 22/10/2026 — discovery engine (D3): a group or sister-bank site is never VERIFIED as the official
website of one country's bank on a name without country.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from scraping.universe.http import FetchResult
from scraping.universe.strategies.market_and_web import verify_website


class Fetcher:
    def __init__(self, html: str) -> None:
        self.html = html

    async def allowed_by_robots(self, url: str) -> bool:
        return True

    async def get(self, url: str) -> FetchResult:
        return FetchResult(url=url, final_url=url, status_code=200, content=self.html.encode())


def ctx(html: str):
    return SimpleNamespace(fetcher=Fetcher(html), options={})


ECOBANK_CI = SimpleNamespace(canonical_name="ECOBANK - CÔTE D'IVOIRE", short_name=None)


@pytest.mark.asyncio
async def test_full_name_with_country_verifies():
    v = await verify_website(ctx("<h1>Ecobank Côte d'Ivoire</h1>"), ECOBANK_CI, "CI", "https://ecobank.ci/")
    assert v["status"] == "VERIFIED"


@pytest.mark.asyncio
async def test_group_site_naming_several_countries_stays_candidate():
    html = "<p>Ecobank est présent au Bénin, au Burkina Faso, en Côte d'Ivoire, au Mali, au Sénégal et au Togo.</p>"
    v = await verify_website(ctx(html), ECOBANK_CI, "CI", "https://ecobank.com/")
    assert v["status"] == "CANDIDATE" and "group or sister site" in v["evidence"]


@pytest.mark.asyncio
async def test_name_without_country_on_a_page_of_its_country_verifies():
    v = await verify_website(ctx("<p>Ecobank, votre banque à Abidjan, Côte d'Ivoire</p>"), ECOBANK_CI, "CI",
                             "https://ecobank.ci/")
    assert v["status"] == "VERIFIED"


@pytest.mark.asyncio
async def test_sister_bank_site_is_not_verified():
    v = await verify_website(ctx("<p>Ecobank Sénégal — Dakar</p>"), ECOBANK_CI, "CI", "https://ecobank.sn/")
    assert v["status"] == "CANDIDATE"
