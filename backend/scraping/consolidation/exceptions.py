"""
UMOA Banking Intelligence — Consolidation Exceptions

Domain-specific exceptions for duplicate detection, conflict resolution,
and historical time series analysis.
"""


class ConsolidationError(Exception):
    """Base exception for all consolidation and data quality operations."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DuplicateDetectionError(ConsolidationError):
    """Raised when duplicate evaluation encounters invalid or corrupt records."""


class ConflictDetectionError(ConsolidationError):
    """Raised when conflict evaluation or resolution processing fails."""


class HistoricalAnalysisError(ConsolidationError):
    """Raised when chronological series construction or anomaly detection fails."""
