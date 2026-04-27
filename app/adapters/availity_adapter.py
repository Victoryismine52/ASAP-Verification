"""
Availity adapter stub.

Implements the OAuth2 client-credentials flow structure and a placeholder call
to Availity's /v1/coverages endpoint.  No real credentials are required yet –
the response is mocked so that the service still runs end-to-end.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.adapters.base import BaseEligibilityAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, EligibilityResponse

logger = logging.getLogger(__name__)


class AvailityAdapter(BaseEligibilityAdapter):
    """Adapter for the Availity Real-Time Eligibility API."""

    def __init__(self) -> None:
        self._access_token: Optional[str] = None  # token cache placeholder

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_access_token(self) -> str:
        """
        Obtain an OAuth2 access token using client credentials grant.

        Returns a cached token when one is available (token refresh logic
        would be added here before going to production).
        """
        if self._access_token:
            return self._access_token

        token_url = f"{settings.availity_base_url}/v1/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": settings.availity_client_id,
            "client_secret": settings.availity_client_secret,
            "scope": "hipaa",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=payload)
            response.raise_for_status()
            data = response.json()
            self._access_token = data["access_token"]
            logger.info("Availity access token obtained.")
            return self._access_token  # type: ignore[return-value]

    async def _call_coverages(
        self, token: str, request: EligibilityRequest
    ) -> dict:
        """
        Call Availity /v1/coverages and return the raw JSON payload.

        NOTE: This is currently a stub that returns mock data so the adapter
        can be wired up without live credentials.
        """
        # TODO: Replace the stub below with a real httpx call once credentials
        #       are available.
        logger.info(
            "AvailityAdapter._call_coverages – returning stub response "
            "(no live credentials configured)."
        )
        return {
            "status": "active",
            "planName": "Availity PPO Stub Plan",
            "copay": 40.0,
            "coinsurance": 0.15,
            "deductibleRemaining": 300.0,
            "outOfPocketRemaining": 1200.0,
            "authorizationRequired": True,
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResponse:
        token = await self._get_access_token()
        raw = await self._call_coverages(token, request)

        return EligibilityResponse(
            status=raw.get("status", "inactive"),
            plan_name=raw.get("planName", "Unknown"),
            copay=raw.get("copay"),
            coinsurance=raw.get("coinsurance"),
            deductible_remaining=raw.get("deductibleRemaining"),
            out_of_pocket_remaining=raw.get("outOfPocketRemaining"),
            authorization_required=raw.get("authorizationRequired", False),
            source="availity",
            checked_at=datetime.now(tz=timezone.utc),
        )
