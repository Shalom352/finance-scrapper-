"""
UMOA Banking Intelligence — Analytics Domain Exceptions

Specific exception types for financial ratio calculation, eligibility checks,
growth analysis, and sector aggregation.
"""


class AnalyticsError(Exception):
    """Base exception for all analytics and financial ratio calculations."""


class IneligibleDataError(AnalyticsError):
    """Raised when an observation or component is not eligible for ratio calculation."""


class RatioCalculationError(AnalyticsError):
    """Base exception for ratio calculation failures."""


class ZeroDenominatorError(RatioCalculationError):
    """Raised when the ratio denominator is equal to zero."""


class NegativeDenominatorError(RatioCalculationError):
    """Raised when the ratio denominator is negative where positive values are required."""


class CurrencyMismatchError(RatioCalculationError):
    """Raised when components of a ratio or growth calculation have incompatible currencies."""


class PeriodMismatchError(RatioCalculationError):
    """Raised when synchronous components do not belong to the same period."""


class AggregationError(AnalyticsError):
    """Raised when a sector or regional aggregation encounters inconsistent or conflicting data."""
