"""
UMOA Financial Intelligence — BRVM Source Connector

Discovers official market bulletins (Bulletins Officiels de la Cote - BOC),
indices, and listed company reports from the Bourse Régionale des Valeurs Mobilières (BRVM).
"""
import asyncio
from typing import ClassVar

import httpx

from app.core.logging import get_logger
from scraping.common.models import DiscoveredDocument
from scraping.connectors.base import BaseSourceConnector
from scraping.discovery.html_parser import parse_html_documents

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


class BRVMConnector(BaseSourceConnector):
    """Official connector for BRVM publications."""

    source_short_name: ClassVar[str] = "BRVM"
    source_name: ClassVar[str] = "Bourse Régionale des Valeurs Mobilières"
    base_url: ClassVar[str] = "https://www.brvm.org"
    rate_limit_delay_seconds: float = 1.0

    TARGET_SECTIONS: ClassVar[list[dict[str, str]]] = [
        {
            "path": "/fr/bulletins-officiels-de-la-cote",
            "document_type": "regulatory_report",
            "description": "Bulletins Officiels de la Cote (BOC)",
        },
        {
            "path": "/fr/rapports-societes-cotees",
            "document_type": "annual_report",
            "description": "Rapports financiers des sociétés cotées",
        },
    ]

    async def discover(
        self,
        client: httpx.AsyncClient,
        limit: int | None = None,
    ) -> list[DiscoveredDocument]:
        """
        Discover official documents across BRVM portal sections.

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

            try:
                logger.info("brvm_fetching_section", url=target_url, description=section["description"])
                resp = await client.get(
                    target_url,
                    headers=DEFAULT_HEADERS,
                    follow_redirects=True,
                    timeout=60.0,
                )
                if resp.status_code == 200:
                    docs = parse_html_documents(
                        html_content=resp.text,
                        base_page_url=str(resp.url),
                        source_short_name=self.source_short_name,
                        document_type=doc_type,
                    )
                    for doc in docs:
                        if doc.url not in seen_urls:
                            seen_urls.add(doc.url)
                            doc.metadata["section_description"] = section["description"]
                            all_discovered.append(doc)

                            if limit and len(all_discovered) >= limit:
                                logger.info(
                                    "brvm_discovery_limit_reached",
                                    count=len(all_discovered),
                                    limit=limit,
                                )
                                return all_discovered
                else:
                    logger.warning("brvm_section_returned_non_200", url=target_url, status_code=resp.status_code)

            except Exception as err:
                logger.warning("brvm_section_discovery_failed", url=target_url, error=str(err))

            await asyncio.sleep(self.rate_limit_delay_seconds)

        logger.info("brvm_discovery_completed", count=len(all_discovered))
        return all_discovered
