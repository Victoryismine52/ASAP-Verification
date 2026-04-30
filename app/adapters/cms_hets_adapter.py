"""Scaffold adapter for CMS HETS eligibility integration."""
from datetime import datetime, timezone

from app.adapters.base import BaseEligibilityAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, EligibilityResponse


class CmsHetsAdapter(BaseEligibilityAdapter):
    def connection_details(self) -> dict:
        configured = bool(settings.cms_hets_submitter_id and settings.cms_hets_password)
        return {
            "provider": "cms_hets",
            "configured": configured,
            "base_url": None,
            "access_requirements": "CMS HETS submitter ID/password + IP allowlist",
            "supported_transaction": "X12 270/271",
            "notes": "Scaffold only; requires EDI certificate and approved HETS access.",
        }

    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResponse:
        if not (settings.cms_hets_submitter_id and settings.cms_hets_password):
            return EligibilityResponse(
                status="inactive",
                plan_name="Not configured: missing CMS_HETS_SUBMITTER_ID/CMS_HETS_PASSWORD",
                copay=None,
                coinsurance=None,
                deductible_remaining=None,
                out_of_pocket_remaining=None,
                authorization_required=True,
                source="cms_hets",
                checked_at=datetime.now(tz=timezone.utc),
            )
        _ = request
        return EligibilityResponse(
            status="inactive",
            plan_name="CMS HETS adapter scaffolded - live mapping not implemented",
            copay=None,
            coinsurance=None,
            deductible_remaining=None,
            out_of_pocket_remaining=None,
            authorization_required=True,
            source="cms_hets",
            checked_at=datetime.now(tz=timezone.utc),
        )
