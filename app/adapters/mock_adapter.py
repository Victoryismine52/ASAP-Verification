"""
Mock adapter – returns static / deterministic test data without hitting any
external service.  Used when ELIGIBILITY_PROVIDER=mock (the default).
"""
from datetime import datetime, timezone

from app.adapters.base import BaseEligibilityAdapter
from app.models.eligibility import EligibilityRequest, EligibilityResponse


class MockAdapter(BaseEligibilityAdapter):
    """Returns hard-coded eligibility data suitable for local development and CI."""

    def connection_details(self) -> dict:
        return {
            "provider": "mock",
            "configured": True,
            "base_url": None,
            "access_requirements": "None",
            "supported_transaction": "X12 270/271 (simulated)",
            "notes": "Always available with deterministic test data.",
        }

    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResponse:
        member_id = (request.patient.member_id or "").strip().upper()
        if member_id == "D003":
            raise RuntimeError("Demo payer returned member not found")
        if member_id == "D002":
            return EligibilityResponse(
                status="active",
                plan_name="Mock Auth Required Plan",
                copay=45.0,
                coinsurance=0.25,
                deductible_remaining=850.0,
                out_of_pocket_remaining=2600.0,
                authorization_required=True,
                source="mock",
                checked_at=datetime.now(tz=timezone.utc),
            )
        if member_id == "D004":
            return EligibilityResponse(
                status="active",
                plan_name="Mock HDHP Plan",
                copay=0.0,
                coinsurance=0.1,
                deductible_remaining=3200.0,
                out_of_pocket_remaining=6000.0,
                authorization_required=False,
                source="mock",
                checked_at=datetime.now(tz=timezone.utc),
            )
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
