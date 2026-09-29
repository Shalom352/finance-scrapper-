"""
UMOA Banking Intelligence — Base Parsing Interface

Defines the abstract contract for document parsers (native PDF, scanned PDF, OCR, etc.).
"""
from abc import ABC, abstractmethod
from typing import Any

from scraping.parsing.models import ParsedDocument


class BaseParser(ABC):
    """Abstract contract for document parsers."""

    @abstractmethod
    async def parse(
        self,
        file_path: str,
        document_id: str | None = None,
        **kwargs: Any,
    ) -> ParsedDocument:
        """
        Parse a document file into structured pages with metadata.

        Args:
            file_path: Absolute or relative path to the file.
            document_id: Optional UUID of the document record in database for provenance.
            **kwargs: Extra parser-specific parameters.

        Returns:
            ParsedDocument containing page-by-page text and metadata.
        """
