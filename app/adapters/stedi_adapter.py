"""Scaffold adapter for Stedi eligibility integration."""
from datetime import datetime, timezone

from app.adapters.base import BaseEligibilityAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, EligibilityResponse


class StediAdapter(BaseEligibilityAdapter):
    """Stedi eligibility candidate adapter.

    This adapter is intentionally not live yet: it records the credentials and
    endpoint family needed for a future X12 270/271 sandbox/demo call while
    returning a controlled scaffold response until Stedi endpoint mapping is
    confirmed.
    """

    def connection_details(self) -> dict:
        configured = bool(settings.stedi_api_key)
        return {
            "provider": "stedi",
            "configured": configured,
            "base_url": settings.stedi_base_url,
            "access_requirements": "STEDI_API_KEY plus Stedi account access/enrollment for eligibility APIs",
            "supported_transaction": "X12 270/271",
            "live_endpoint_implemented": False,
            "endpoint_status": "sandbox/demo endpoint mapping pending",
            "notes": "API-first eligibility candidate; live endpoint mapping pending documentation/access.",
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
                error_message="Stedi credentials are not configured",
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
            raw_response_json={
                "provider": "stedi",
                "base_url": settings.stedi_base_url,
                "endpoint_implemented": False,
                "message": "Scaffold response only; live endpoint mapping pending documentation/access.",
            },
        )
