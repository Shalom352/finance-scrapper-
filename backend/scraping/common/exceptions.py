"""
UMOA Banking Intelligence — Scraping Exceptions

Domain-specific exceptions for scraping, downloading, storage, and validation.
"""


class ScrapingError(Exception):
    """Base exception for all scraping errors."""


class DiscoveryError(ScrapingError):
    """Raised when document discovery fails on a source page."""


class DownloadError(ScrapingError):
    """Raised when downloading a document fails."""

    def __init__(self, message: str, url: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class StorageError(ScrapingError):
    """Raised when persisting a file or calculating hashes fails."""


class SecurityError(ScrapingError):
    """Raised when a security constraint (SSRF, path traversal, file size) is violated."""
