"""
Availity adapter implementation.

Implements OAuth2 client-credentials flow and coverage API call structure.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.adapters.base import BaseEligibilityAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, EligibilityResponse

logger = logging.getLogger(__name__)


class AvailityAdapter(BaseEligibilityAdapter):
    """Adapter for the Availity Real-Time Eligibility API."""

    def __init__(self) -> None:
        self._access_token: Optional[str] = None

    def connection_details(self) -> dict:
        configured = bool(settings.availity_client_id and settings.availity_client_secret)
        return {
            "provider": "availity",
            "configured": configured,
            "base_url": settings.availity_base_url,
            "access_requirements": "Availity client ID/secret and approved app",
            "supported_transaction": "X12 270/271",
            "notes": "OAuth token call is live; coverage response currently deterministic stub.",
        }

    async def _get_access_token(self) -> str:
        """Obtain an OAuth2 access token using the client credentials grant."""
        if self._access_token:
            return self._access_token

        token_url = f"{settings.availity_base_url}/v1/token"

        # Availity client type currently uses token endpoint auth method
        # client_secret_post, so credentials are sent in the form body.
        payload = {
            "grant_type": "client_credentials",
            "scope": settings.availity_scope,
            "client_id": settings.availity_client_id,
            "client_secret": settings.availity_client_secret,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                token_url,
                data=payload,
            )
            try:
                data = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Availity token response was not valid JSON.")
            if response.status_code >= 400:
                error = data.get("error") if isinstance(data, dict) else None
                error_description = (
                    data.get("error_description") if isinstance(data, dict) else None
                )
                hint = ""
                if error in {"unsupported_grant_type", "unauthorized_client"}:
                    hint = (
                        " Verify the Availity app client type allows "
                        "grant_type=client_credentials."
                    )
                raise RuntimeError(
                    "Availity token request failed "
                    f"(status={response.status_code}, error={error}, "
                    f"error_description={error_description}).{hint}"
                )

        if not isinstance(data, dict):
            raise RuntimeError("Availity token response was not a JSON object.")

        token = data.get("access_token") or data.get("token")
        if not token:
            safe_data: dict[str, Any] = {
                key: value
                for key, value in data.items()
                if key.lower() not in {"access_token", "refresh_token", "id_token"}
            }
            raise RuntimeError(
                "Availity token response missing token field "
                f"(keys={list(data.keys())}, payload={safe_data})"
            )

        self._access_token = str(token)
        logger.info("Availity access token obtained.")
        return self._access_token

    async def _call_coverages(self, token: str, request: EligibilityRequest) -> dict:
        """
        Call Availity /v1/coverages and return normalised raw payload.

        This still falls back to a deterministic stub response so local
        development remains stable until full provider-specific request mapping
        is finalized.
        """
        # Placeholder for future real coverage call. Keep deterministic return.
        logger.info(
            "AvailityAdapter._call_coverages called for payer=%s member=%s",
            request.payer.payer_id,
            request.patient.member_id,
        )
        _ = token
        return {
            "status": "active",
            "planName": "Availity PPO Stub Plan",
            "copay": 40.0,
            "coinsurance": 0.15,
            "deductibleRemaining": 300.0,
            "outOfPocketRemaining": 1200.0,
            "authorizationRequired": True,
        }

    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResponse:
        if not (settings.availity_client_id and settings.availity_client_secret):
            return EligibilityResponse(
                status="inactive",
                plan_name="Not configured: missing AVAILITY_CLIENT_ID/AVAILITY_CLIENT_SECRET",
                copay=None,
                coinsurance=None,
                deductible_remaining=None,
                out_of_pocket_remaining=None,
                authorization_required=True,
                source="availity",
                checked_at=datetime.now(tz=timezone.utc),
            )

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
