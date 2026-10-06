"""
UMOA Banking Intelligence — Commission Bancaire (CB-UMOA) Connector

Discovers official annual reports, supervisory reviews, and regulated bank registries
from the Commission Bancaire de l'UMOA.
"""
import asyncio
from typing import ClassVar

import httpx

from app.core.logging import get_logger
from scraping.common.models import DiscoveredDocument
from scraping.connectors.base import BaseSourceConnector

logger = get_logger(__name__)


class CBUMOAConnector(BaseSourceConnector):
    """Official connector for Commission Bancaire de l'UMOA publications."""

    source_short_name: ClassVar[str] = "CB-UMOA"
    source_name: ClassVar[str] = "Commission Bancaire de l'Union Monétaire Ouest Africaine"
    base_url: ClassVar[str] = "https://www.cb-umoa.org"

    TARGET_SECTIONS: ClassVar[list[dict[str, str]]] = [
        {
            "path": "/fr/rapport-annuels",
            "document_type": "annual_report",
            "description": "Rapports annuels d'activité de la Commission Bancaire",
        },
        {
            "path": "/publications",
            "document_type": "regulatory_report",
            "description": "Publications et études prudentielles",
        },
        {
            "path": "/fr/etablissements-assujettis-au-controle-de-la-commission-bancaire-de-lumoa",
            "document_type": "regulatory_report",
            "description": "Situation et registre des établissements de crédit agréés",
        },
    ]

    async def discover(
        self,
        client: httpx.AsyncClient,
        limit: int | None = None,
    ) -> list[DiscoveredDocument]:
        """
        Discover official documents across CB-UMOA publication sections.

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
                docs = await self.fetch_and_parse_page(
                    client,
                    target_url,
                    document_type=doc_type,
                )
                for doc in docs:
                    if doc.url not in seen_urls:
                        seen_urls.add(doc.url)
                        doc.metadata["section_description"] = section["description"]
                        all_discovered.append(doc)

                        if limit and len(all_discovered) >= limit:
                            logger.info(
                                "cbumoa_discovery_limit_reached",
                                count=len(all_discovered),
                                limit=limit,
                            )
                            return all_discovered

            except Exception as err:
                logger.warning(
                    "cbumoa_section_discovery_failed",
                    url=target_url,
                    error=str(err),
                )

            await asyncio.sleep(self.rate_limit_delay_seconds)

        logger.info("cbumoa_discovery_completed", count=len(all_discovered))
        return all_discovered
