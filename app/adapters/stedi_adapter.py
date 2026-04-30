"""Scaffold adapter for Stedi eligibility integration."""
from datetime import datetime, timezone

from app.adapters.base import BaseEligibilityAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, EligibilityResponse


class StediAdapter(BaseEligibilityAdapter):
    def connection_details(self) -> dict:
        configured = bool(settings.stedi_api_key)
        return {
            "provider": "stedi",
            "configured": configured,
            "base_url": settings.stedi_base_url,
            "access_requirements": "Stedi API key + partner enrollment",
            "supported_transaction": "X12 270/271",
            "notes": "Scaffold only; wire payer-specific mappings before production use.",
        }

    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResponse:
        if not settings.stedi_api_key:
            return EligibilityResponse(
                status="inactive",
                plan_name="Not configured: missing STEDI_API_KEY",
                copay=None,
                coinsurance=None,
                deductible_remaining=None,
                out_of_pocket_remaining=None,
                authorization_required=True,
                source="stedi",
                checked_at=datetime.now(tz=timezone.utc),
            )
        _ = request
        return EligibilityResponse(
            status="inactive",
            plan_name="Stedi adapter scaffolded - live mapping not implemented",
            copay=None,
            coinsurance=None,
            deductible_remaining=None,
            out_of_pocket_remaining=None,
            authorization_required=True,
            source="stedi",
            checked_at=datetime.now(tz=timezone.utc),
        )
