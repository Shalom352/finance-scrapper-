"""
UMOA Banking Intelligence — Base Source Connector

Abstract contract for official institution connectors.
"""
from abc import ABC, abstractmethod
from typing import ClassVar

import httpx

from app.core.logging import get_logger
from scraping.common.models import DiscoveredDocument
from scraping.discovery.html_parser import parse_html_documents

logger = get_logger(__name__)


class BaseSourceConnector(ABC):
    """Abstract base connector for an official data source."""

    source_short_name: ClassVar[str]
    source_name: ClassVar[str]
    base_url: ClassVar[str]
    rate_limit_delay_seconds: float = 1.0

    @abstractmethod
    async def discover(
        self,
        client: httpx.AsyncClient,
        limit: int | None = None,
    ) -> list[DiscoveredDocument]:
        """
        Discover official documents published by this source.

        Args:
            client: Async HTTP client.
            limit: Maximum number of documents to return.

        Returns:
            List of DiscoveredDocument instances.
        """

    async def fetch_and_parse_page(
        self,
        client: httpx.AsyncClient,
        page_url: str,
        document_type: str = "annual_report",
    ) -> list[DiscoveredDocument]:
        """Fetch an HTML page and extract document links using the standard parser."""
        logger.info("connector_fetching_page", connector=self.source_short_name, url=page_url)
        resp = await client.get(page_url, follow_redirects=True)
        resp.raise_for_status()

        return parse_html_documents(
            html_content=resp.text,
            base_page_url=str(resp.url),
            source_short_name=self.source_short_name,
            document_type=document_type,
        )
