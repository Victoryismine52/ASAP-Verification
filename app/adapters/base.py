"""
Abstract base adapter that all eligibility adapters must implement.
"""
from abc import ABC, abstractmethod

from app.models.eligibility import EligibilityRequest, EligibilityResponse


class BaseEligibilityAdapter(ABC):
    """Interface contract for eligibility provider adapters."""

    @abstractmethod
    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResponse:
        """
        Check eligibility for the given request.

        Args:
            request: Validated EligibilityRequest payload.

        Returns:
            Normalised EligibilityResponse.
        """
        ...

    @abstractmethod
    def connection_details(self) -> dict:
        """Return adapter-level connection metadata and configuration status."""
        ...
