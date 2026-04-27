"""
EligibilityService – selects the correct adapter based on configuration,
delegates the check, and handles errors uniformly.
"""
import logging

from app.adapters.base import BaseEligibilityAdapter
from app.adapters.mock_adapter import MockAdapter
from app.adapters.availity_adapter import AvailityAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, EligibilityResponse

logger = logging.getLogger(__name__)


def _build_adapter() -> BaseEligibilityAdapter:
    """Factory: return the adapter that matches ELIGIBILITY_PROVIDER."""
    provider = settings.eligibility_provider.lower()
    if provider == "availity":
        logger.info("Using AvailityAdapter.")
        return AvailityAdapter()
    logger.info("Using MockAdapter (default).")
    return MockAdapter()


class EligibilityService:
    """Orchestrates eligibility checks through the configured adapter."""

    def __init__(self) -> None:
        self._adapter: BaseEligibilityAdapter = _build_adapter()

    async def check(self, request: EligibilityRequest) -> EligibilityResponse:
        """
        Perform an eligibility check.

        Args:
            request: Validated input payload.

        Returns:
            Normalised EligibilityResponse.

        Raises:
            RuntimeError: If the adapter raises an unexpected exception.
        """
        logger.info(
            "EligibilityService.check – patient=%s %s payer=%s",
            request.patient.first_name,
            request.patient.last_name,
            request.payer.payer_id,
        )
        try:
            response = await self._adapter.check_eligibility(request)
            logger.info("EligibilityService.check – completed, status=%s", response.status)
            return response
        except Exception as exc:
            logger.exception("EligibilityService.check – adapter error: %s", exc)
            raise RuntimeError(f"Eligibility check failed: {exc}") from exc
