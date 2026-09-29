"""
UMOA Banking Intelligence — Institutional Reconciliation

Provides tools for resolving raw extracted bank names to registered UMOA institutions:
  - InstitutionNameNormalizer: cleans names while preserving distinguishing tokens
  - InstitutionMatcher: candidate matching using exact, aliases, and token overlap
  - ConfidenceScorer: confidence scoring and ambiguity detection
  - InstitutionResolver: high-level coordinator
  - Models: MatchCandidate, ResolutionResult, InstitutionEntity
  - Exceptions: ReconciliationError, AmbiguousInstitutionError, InstitutionNotFoundError
"""
from scraping.reconciliation.confidence import ConfidenceScorer
from scraping.reconciliation.exceptions import (
    AmbiguousInstitutionError,
    InstitutionNotFoundError,
    ReconciliationError,
)
from scraping.reconciliation.matcher import InstitutionMatcher
from scraping.reconciliation.models import (
    InstitutionEntity,
    MatchCandidate,
    ResolutionResult,
)
from scraping.reconciliation.normalizer import InstitutionNameNormalizer
from scraping.reconciliation.resolver import InstitutionResolver

__all__ = [
    "InstitutionNameNormalizer",
    "InstitutionMatcher",
    "ConfidenceScorer",
    "InstitutionResolver",
    "MatchCandidate",
    "ResolutionResult",
    "InstitutionEntity",
    "ReconciliationError",
    "AmbiguousInstitutionError",
    "InstitutionNotFoundError",
]
