"""
UMOA Banking Intelligence — Financial Data Consolidation Package

Public exports for duplicate detection, conflict resolution, historical time series,
coverage metrics, and explainable data quality dimensions.
"""
from scraping.consolidation.conflict_detector import ConflictDetector
from scraping.consolidation.consolidator import FinancialDataConsolidator
from scraping.consolidation.coverage_analyzer import CoverageAnalyzer
from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.consolidation.exceptions import (
    ConflictDetectionError,
    ConsolidationError,
    DuplicateDetectionError,
    HistoricalAnalysisError,
)
from scraping.consolidation.historical_analyzer import HistoricalAnalyzer
from scraping.consolidation.models import (
    AnomalyType,
    ConflictRecord,
    ConflictType,
    DuplicateGroup,
    DuplicateType,
    HistoricalAnomaly,
    HistoricalQualityReport,
    HistoricalSeries,
    InstitutionCoverage,
    ObservationSummary,
    QualityDimensionScore,
)
from scraping.consolidation.quality_analyzer import DataQualityAnalyzer

__all__ = [
    "ConflictDetector",
    "ConflictRecord",
    "ConflictType",
    "ConsolidationError",
    "CoverageAnalyzer",
    "DataQualityAnalyzer",
    "DuplicateDetector",
    "DuplicateDetectionError",
    "DuplicateGroup",
    "DuplicateType",
    "ConflictDetectionError",
    "FinancialDataConsolidator",
    "HistoricalAnalysisError",
    "HistoricalAnalyzer",
    "HistoricalAnomaly",
    "HistoricalQualityReport",
    "HistoricalSeries",
    "InstitutionCoverage",
    "ObservationSummary",
    "QualityDimensionScore",
    "AnomalyType",
]
