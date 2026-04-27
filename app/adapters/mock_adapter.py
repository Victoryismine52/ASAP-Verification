"""
Mock adapter – returns static / deterministic test data without hitting any
external service.  Used when ELIGIBILITY_PROVIDER=mock (the default).
"""
from datetime import datetime, timezone

from app.adapters.base import BaseEligibilityAdapter
from app.models.eligibility import EligibilityRequest, EligibilityResponse


class MockAdapter(BaseEligibilityAdapter):
    """Returns hard-coded eligibility data suitable for local development and CI."""

    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResponse:
        return EligibilityResponse(
            status="active",
            plan_name="Mock PPO Gold Plan",
            copay=25.0,
            coinsurance=0.20,
            deductible_remaining=750.0,
            out_of_pocket_remaining=2000.0,
            authorization_required=False,
            source="mock",
            checked_at=datetime.now(tz=timezone.utc),
        )
