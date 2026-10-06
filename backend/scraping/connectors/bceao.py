"""
UMOA Banking Intelligence — BCEAO Connector

Discovers official financial reports and publications from the Banque Centrale
des États de l'Afrique de l'Ouest (BCEAO).
"""
import asyncio
from typing import ClassVar

import httpx

from app.core.logging import get_logger
from scraping.common.models import DiscoveredDocument
from scraping.connectors.base import BaseSourceConnector

logger = get_logger(__name__)


class BCEAOConnector(BaseSourceConnector):
    """Official connector for BCEAO publications."""

    source_short_name: ClassVar[str] = "BCEAO"
    source_name: ClassVar[str] = "Banque Centrale des États de l'Afrique de l'Ouest"
    base_url: ClassVar[str] = "https://www.bceao.int"

    # Targeted publication sections on the BCEAO portal
    TARGET_SECTIONS: ClassVar[list[dict[str, str]]] = [
        {
            "path": "/fr/publications/rapport-annuel-de-la-commission-bancaire-de-lumoa-2025",
            "document_type": "annual_report",
            "description": "Rapport annuel 2025 de la Commission Bancaire",
        },
        {
            "path": "/fr/publications/rapport-annuel-de-la-bceao-2025",
            "document_type": "annual_report",
            "description": "Rapport annuel 2025 de la BCEAO",
        },
        {
            "path": "/fr/publications/etats-financiers-de-la-bceao-au-titre-de-lexercice-2025",
            "document_type": "financial_statement",
            "description": "États financiers 2025 de la BCEAO",
        },
        {
            "path": "/fr/publications/bilans-et-comptes-de-resultats-des-etablissements-de-credit-de-lumoa",
            "document_type": "financial_statement",
            "description": "Bilans et comptes de résultats des banques et établissements financiers de l'UMOA",
        },
        {
            "path": "/fr/publications/rapports",
            "document_type": "annual_report",
            "description": "Rapports annuels et de politique monétaire de la BCEAO",
        },
        {
            "path": "/fr/documents/conditions-de-banque",
            "document_type": "financial_statement",
            "description": "Conditions de banque et bilans semestriels",
        },
        {
            "path": "/fr/publications/annuaires",
            "document_type": "financial_statement",
            "description": "Annuaires des banques et statistiques de l'UMOA",
        },
        {
            "path": "/fr/publications/bulletins",
            "document_type": "regulatory_report",
            "description": "Bulletins statistiques monétaires et financiers",
        },
        {
            "path": "/fr/publications/perspectives-economiques",
            "document_type": "regulatory_report",
            "description": "Perspectives économiques des États de l'UEMOA",
        },
        {
            "path": "/fr/publications/notes",
            "document_type": "regulatory_report",
            "description": "Notes d'information et de conjoncture",
        },
    ]

    async def discover(
        self,
        client: httpx.AsyncClient,
        limit: int | None = None,
    ) -> list[DiscoveredDocument]:
        """
        Discover official documents across BCEAO publication sections.

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
                                "bceao_discovery_limit_reached",
                                count=len(all_discovered),
                                limit=limit,
                            )
                            return all_discovered

            except Exception as err:
                logger.warning(
                    "bceao_section_discovery_failed",
                    url=target_url,
                    error=str(err),
                )

            # Polite delay between section requests
            await asyncio.sleep(self.rate_limit_delay_seconds)

        logger.info("bceao_discovery_completed", count=len(all_discovered))
        return all_discovered
