"""Scaffold adapter for Optum / Change Healthcare integration."""
from datetime import datetime, timezone

from app.adapters.base import BaseEligibilityAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, EligibilityResponse


class OptumChangeAdapter(BaseEligibilityAdapter):
    def connection_details(self) -> dict:
        configured = bool(settings.optum_client_id and settings.optum_client_secret)
        return {
            "provider": "optum_change",
            "configured": configured,
            "base_url": settings.optum_base_url,
            "access_requirements": "Client credentials + trading partner setup",
            "supported_transaction": "X12 270/271",
            "notes": "Scaffold only; endpoint contract and payer onboarding pending.",
        }

    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResponse:
        if not (settings.optum_client_id and settings.optum_client_secret):
            return EligibilityResponse(
                status="inactive",
                plan_name="Not configured: missing OPTUM_CLIENT_ID/OPTUM_CLIENT_SECRET",
                copay=None,
                coinsurance=None,
                deductible_remaining=None,
                out_of_pocket_remaining=None,
                authorization_required=True,
                source="optum_change",
                checked_at=datetime.now(tz=timezone.utc),
            )
        _ = request
        return EligibilityResponse(
            status="inactive",
            plan_name="Optum/Change adapter scaffolded - live mapping not implemented",
            copay=None,
            coinsurance=None,
            deductible_remaining=None,
            out_of_pocket_remaining=None,
            authorization_required=True,
            source="optum_change",
            checked_at=datetime.now(tz=timezone.utc),
        )
