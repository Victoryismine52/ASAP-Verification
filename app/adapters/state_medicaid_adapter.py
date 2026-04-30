"""Scaffold adapter for State Medicaid eligibility integration."""
from datetime import datetime, timezone

from app.adapters.base import BaseEligibilityAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, EligibilityResponse


class StateMedicaidAdapter(BaseEligibilityAdapter):
    def connection_details(self) -> dict:
        configured = bool(settings.state_medicaid_endpoint and settings.state_medicaid_api_key)
        return {
            "provider": "state_medicaid",
            "configured": configured,
            "base_url": settings.state_medicaid_endpoint or None,
            "access_requirements": "State-specific enrollment + credentials (varies by state)",
            "supported_transaction": "Usually X12 270/271",
            "notes": "Scaffold only; implement per-state routing and schema differences.",
        }

    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResponse:
        if not (settings.state_medicaid_endpoint and settings.state_medicaid_api_key):
            return EligibilityResponse(
                status="inactive",
                plan_name="Not configured: missing STATE_MEDICAID_ENDPOINT/STATE_MEDICAID_API_KEY",
                copay=None,
                coinsurance=None,
                deductible_remaining=None,
                out_of_pocket_remaining=None,
                authorization_required=True,
                source="state_medicaid",
                checked_at=datetime.now(tz=timezone.utc),
            )
        _ = request
        return EligibilityResponse(
            status="inactive",
            plan_name="State Medicaid adapter scaffolded - live mapping not implemented",
            copay=None,
            coinsurance=None,
            deductible_remaining=None,
            out_of_pocket_remaining=None,
            authorization_required=True,
            source="state_medicaid",
            checked_at=datetime.now(tz=timezone.utc),
        )
