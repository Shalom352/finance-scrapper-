"""
UMOA Financial Intelligence — UMOA-Titres Source Connector

Discovers official public debt auction results (Comptes-Rendus d'adjudications BAT/OAT),
emission calendars, and statistical bulletins from the Agence UMOA-Titres.
"""
import asyncio
import re
from typing import ClassVar
from urllib.parse import urljoin

import httpx

from app.core.logging import get_logger
from scraping.common.models import DiscoveredDocument
from scraping.connectors.base import BaseSourceConnector
from scraping.discovery.html_parser import LinkExtractor, parse_html_documents

logger = get_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Country code detection from UMOA-Titres filenames / URLs
COUNTRY_PATTERNS = {
    "CI": re.compile(r"[-_](CI|COTE[-_]D[-_]?IVOIRE)[-_.]", re.IGNORECASE),
    "SN": re.compile(r"[-_](SN|SENEGAL)[-_.]", re.IGNORECASE),
    "BJ": re.compile(r"[-_](BJ|BENIN)[-_.]", re.IGNORECASE),
    "BF": re.compile(r"[-_](BF|BURKINA|BURKINA[-_]FASO)[-_.]", re.IGNORECASE),
    "ML": re.compile(r"[-_](ML|MALI)[-_.]", re.IGNORECASE),
    "NE": re.compile(r"[-_](NE|NIGER)[-_.]", re.IGNORECASE),
    "TG": re.compile(r"[-_](TG|TOGO)[-_.]", re.IGNORECASE),
    "GW": re.compile(r"[-_](GW|GUINEE[-_]BISSAU)[-_.]", re.IGNORECASE),
}


def detect_country_code(text: str) -> str | None:
    """Detect 2-letter ISO country code from filename or URL text."""
    for code, pattern in COUNTRY_PATTERNS.items():
        if pattern.search(text):
            return code
    return None


class UMOATitresConnector(BaseSourceConnector):
    """Official connector for UMOA-Titres publications and auctions."""

    source_short_name: ClassVar[str] = "UMOA-Titres"
    source_name: ClassVar[str] = "Agence UMOA-Titres"
    base_url: ClassVar[str] = "https://www.umoatitres.org"
    rate_limit_delay_seconds: float = 0.5

    TARGET_SECTIONS: ClassVar[list[dict[str, str]]] = [
        {
            "path": "/fr/emissions/",
            "document_type": "regulatory_report",
            "description": "Annonces et résultats d'adjudications (BAT & OAT)",
            "is_emissions_index": "true",
        },
        {
            "path": "/fr/category/publications/bulletin-statistiques/",
            "document_type": "regulatory_report",
            "description": "Bulletins statistiques du Marché des Titres Publics",
            "is_emissions_index": "false",
        },
        {
            "path": "/fr/publications/",
            "document_type": "regulatory_report",
            "description": "Rapports et publications officielles UMOA-Titres",
            "is_emissions_index": "false",
        },
    ]

    async def discover(
        self,
        client: httpx.AsyncClient,
        limit: int | None = None,
    ) -> list[DiscoveredDocument]:
        """
        Discover official documents across UMOA-Titres portal sections.

        Args:
            client: Async HTTP client.
            limit: Maximum number of discovered documents to collect.

        Returns:
            List of DiscoveredDocument objects.
        """
        all_discovered: list[DiscoveredDocument] = []
        seen_urls: set[str] = set()

        for section in self.TARGET_SECTIONS:
            target_url = f"{self.base_url}{section['path']}"
            doc_type = section["document_type"]
            is_emissions = section.get("is_emissions_index") == "true"

            try:
                logger.info("umoa_titres_fetching_section", url=target_url, description=section["description"])
                resp = await client.get(
                    target_url,
                    headers=DEFAULT_HEADERS,
                    follow_redirects=True,
                    timeout=60.0,
                )
                if resp.status_code == 200:
                    # 1. Direct PDF links on the page
                    direct_docs = parse_html_documents(
                        html_content=resp.text,
                        base_page_url=str(resp.url),
                        source_short_name=self.source_short_name,
                        document_type=doc_type,
                    )
                    for doc in direct_docs:
                        if doc.url not in seen_urls:
                            seen_urls.add(doc.url)
                            doc.metadata["section_description"] = section["description"]
                            cc = detect_country_code(f"{doc.url} {doc.title}")
                            if cc:
                                doc.metadata["country_code"] = cc
                            all_discovered.append(doc)

                            if limit and len(all_discovered) >= limit:
                                return all_discovered

                    # 2. If this is the emissions index, crawl emission detail pages
                    if is_emissions:
                        extractor = LinkExtractor()
                        extractor.feed(resp.text)
                        emission_links = [
                            urljoin(str(resp.url), href)
                            for href, _ in extractor.links
                            if "/emission/" in href
                        ]

                        for em_url in emission_links:
                            if limit and len(all_discovered) >= limit:
                                break

                            await asyncio.sleep(self.rate_limit_delay_seconds)
                            try:
                                em_resp = await client.get(
                                    em_url,
                                    headers=DEFAULT_HEADERS,
                                    follow_redirects=True,
                                    timeout=20.0,
                                )
                                if em_resp.status_code == 200:
                                    em_docs = parse_html_documents(
                                        html_content=em_resp.text,
                                        base_page_url=str(em_resp.url),
                                        source_short_name=self.source_short_name,
                                        document_type="regulatory_report",
                                    )
                                    for doc in em_docs:
                                        if doc.url not in seen_urls:
                                            seen_urls.add(doc.url)
                                            doc.metadata["section_description"] = "Résultats d'adjudications"
                                            doc.metadata["emission_url"] = em_url
                                            cc = detect_country_code(f"{doc.url} {doc.title} {em_url}")
                                            if cc:
                                                doc.metadata["country_code"] = cc
                                            all_discovered.append(doc)

                                            if limit and len(all_discovered) >= limit:
                                                return all_discovered
                            except Exception as em_err:
                                logger.warning("umoa_titres_emission_detail_failed", url=em_url, error=str(em_err))

                else:
                    logger.warning("umoa_titres_section_non_200", url=target_url, status_code=resp.status_code)

            except Exception as err:
                logger.warning("umoa_titres_section_discovery_failed", url=target_url, error=str(err))

            await asyncio.sleep(self.rate_limit_delay_seconds)

        logger.info("umoa_titres_discovery_completed", count=len(all_discovered))
        return all_discovered
