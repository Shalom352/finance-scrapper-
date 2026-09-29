"""
UMOA Banking Intelligence — Base Validation Interface

Contract for quality control and verification workflow checks.
Implementation will be delivered in the dedicated validation phase.
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseValidator(ABC):
    """Abstract base class for financial data validators."""

    @abstractmethod
    def validate(self, financial_data_point: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Validate a financial data point against database and business invariants.

        Returns:
            Tuple of (is_valid, list of error messages).
        """
