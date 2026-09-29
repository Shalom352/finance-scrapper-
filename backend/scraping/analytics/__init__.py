"""
UMOA Banking Intelligence — Analytics Package

Public exports for financial ratios, eligibility engine, YoY growth,
sector aggregations, and comparative analytics.
"""
from scraping.analytics.aggregation import SectorAggregator
from scraping.analytics.analytics_service import AnalyticsService
from scraping.analytics.eligibility import EligibilityEngine
from scraping.analytics.exceptions import (
    AggregationError,
    AnalyticsError,
    CurrencyMismatchError,
    IneligibleDataError,
    NegativeDenominatorError,
    PeriodMismatchError,
    RatioCalculationError,
    ZeroDenominatorError,
)
from scraping.analytics.growth_calculator import CORE_GROWTH_METRICS, GrowthCalculator
from scraping.analytics.models import (
    AggregationStatus,
    ComparisonResult,
    ComparisonType,
    ComponentProvenance,
    GrowthCalculationResult,
    GrowthStatus,
    MarketShareResult,
    RatioCalculationResult,
    RatioDefinition,
    RatioStatus,
    ScopeType,
    SectorAggregationResult,
)
from scraping.analytics.ratio_calculator import RATIO_DEFINITIONS, RatioCalculator
from scraping.analytics.sector_analysis import SectorAnalyzer

__all__ = [
    "AggregationError",
    "AggregationStatus",
    "AnalyticsError",
    "AnalyticsService",
    "CORE_GROWTH_METRICS",
    "ComparisonResult",
    "ComparisonType",
    "ComponentProvenance",
    "CurrencyMismatchError",
    "EligibilityEngine",
    "GrowthCalculationResult",
    "GrowthCalculator",
    "GrowthStatus",
    "IneligibleDataError",
    "MarketShareResult",
    "NegativeDenominatorError",
    "PeriodMismatchError",
    "RATIO_DEFINITIONS",
    "RatioCalculationError",
    "RatioCalculationResult",
    "RatioCalculator",
    "RatioDefinition",
    "RatioStatus",
    "ScopeType",
    "SectorAggregationResult",
    "SectorAggregator",
    "SectorAnalyzer",
    "ZeroDenominatorError",
]
