"""
UMOA Banking Intelligence — Base Discovery Interface

Abstract base class defining the contract for discovery engines.
"""
from abc import ABC, abstractmethod
from collections.abc import Sequence

import httpx

from scraping.common.models import DiscoveredDocument


class BaseDiscoveryEngine(ABC):
    """Contract for discovering official documents from source websites."""

    @abstractmethod
    async def discover_page(
        self,
        client: httpx.AsyncClient,
        page_url: str,
        source_short_name: str,
        document_type: str = "annual_report",
    ) -> Sequence[DiscoveredDocument]:
        """
        Discover downloadable documents available on a given page URL.

        Args:
            client: Async HTTP client to make requests.
            page_url: Target URL to inspect.
            source_short_name: Identifier of the source (e.g. "BCEAO", "CB-UMOA").
            document_type: Default document type classification.

        Returns:
            List of discovered documents with metadata.
        """
