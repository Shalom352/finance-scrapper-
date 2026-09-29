"""
UMOA Banking Intelligence — Reconciliation Exceptions
"""


class ReconciliationError(Exception):
    """Base exception for institution reconciliation failures."""


class AmbiguousInstitutionError(ReconciliationError):
    """Raised when multiple institutions match with similar confidence."""


class InstitutionNotFoundError(ReconciliationError):
    """Raised when no matching institution can be found for a given name."""
