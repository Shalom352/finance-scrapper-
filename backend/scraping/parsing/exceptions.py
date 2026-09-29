"""
UMOA Banking Intelligence — PDF Parsing Exceptions

Specialized exceptions for PDF opening, parsing, and structural analysis.
"""
from scraping.common.exceptions import ScrapingError


class PDFParsingError(ScrapingError):
    """Base exception for all PDF parsing errors."""

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        page_number: int | None = None,
    ) -> None:
        super().__init__(message)
        self.file_path = file_path
        self.page_number = page_number


class InvalidPDFError(PDFParsingError):
    """Raised when a file is not a valid PDF or header is corrupted."""


class PDFReadError(PDFParsingError):
    """Raised when an error occurs while reading bytes or pages from a PDF."""


class UnsupportedPDFError(PDFParsingError):
    """Raised when a PDF feature (e.g. strong encryption) is unsupported."""


class EmptyPDFError(PDFParsingError):
    """Raised when a PDF contains 0 pages or is completely unpopulated."""
