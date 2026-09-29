"""
UMOA Banking Intelligence — Base Normalization Interface

Contract for normalizing extracted raw values into standardized units and currencies.
Implementation will be delivered in the dedicated normalization phase.
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseNormalizer(ABC):
    """Abstract base class for financial value normalizers."""

    @abstractmethod
    def normalize(
        self,
        value_original: str,
        unit_original: str | None,
        currency_original: str | None,
        value_type: str,
    ) -> dict[str, Any]:
        """Normalize extracted value according to V1 financial specification."""
