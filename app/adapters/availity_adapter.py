"""
Availity adapter implementation.

Implements OAuth2 client-credentials flow and Availity coverages API calls.
"""
import logging
from datetime import date, datetime, timezone
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
            "notes": "OAuth token call is live; coverage API calls Availity /coverages demo endpoint.",
        }

    @staticmethod
    def _v1_url(path: str) -> str:
        """Build an Availity v1 URL without duplicating the /v1 path segment."""
        base_url = settings.availity_base_url.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[: -len("/v1")]
        normalized_path = path.lstrip("/")
        if normalized_path.startswith("v1/"):
            normalized_path = normalized_path[len("v1/") :]
        return f"{base_url}/v1/{normalized_path}"

    async def _get_access_token(self) -> str:
        """Obtain an OAuth2 access token using the client credentials grant."""
        if self._access_token:
            return self._access_token

        token_url = self._v1_url("token")

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

    @staticmethod
    def _non_empty_form_data(payload: dict[str, Any]) -> dict[str, str]:
        return {
            key: str(value)
            for key, value in payload.items()
            if value is not None and str(value).strip() != ""
        }

    @staticmethod
    def _response_body(response: httpx.Response) -> str:
        try:
            return response.text
        except Exception:  # pragma: no cover - defensive for unusual response objects
            return "<unavailable>"

    async def _call_coverages(self, token: str, request: EligibilityRequest) -> dict:
        """POST an eligibility request to Availity /v1/coverages."""
        coverages_url = self._v1_url("coverages")
        form_data = self._non_empty_form_data(
            {
                "payerId": request.payer.payer_id,
                "providerNpi": request.provider.npi,
                "providerTaxId": request.provider.tax_id,
                "serviceType": request.service_type or "30",
                "memberId": request.patient.member_id,
                "patientFirstName": request.patient.first_name,
                "patientLastName": request.patient.last_name,
                "patientBirthDate": request.patient.dob.isoformat(),
                "asOfDate": date.today().isoformat(),
            }
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        logger.info(
            "Calling Availity /coverages for payer=%s member=%s",
            request.payer.payer_id,
            request.patient.member_id,
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                coverages_url,
                headers=headers,
                data=form_data,
            )

        body = self._response_body(response)
        if response.status_code >= 400:
            raise RuntimeError(
                "Availity coverages request failed "
                f"(status={response.status_code}, body={body[:500]})"
            )

        try:
            parsed = response.json()
        except ValueError:
            return {"non_json_response_text": body}

        return parsed

    @staticmethod
    def _iter_nested(value: Any):
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from AvailityAdapter._iter_nested(nested)
        elif isinstance(value, list):
            for item in value:
                yield from AvailityAdapter._iter_nested(item)

    @staticmethod
    def _find_first_value(raw: Any, keys: tuple[str, ...]) -> Any:
        for obj in AvailityAdapter._iter_nested(raw):
            for key in keys:
                value = obj.get(key)
                if value is not None and str(value).strip() != "":
                    return value
        return None

    @staticmethod
    def _authorization_required(raw: Any) -> bool:
        for obj in AvailityAdapter._iter_nested(raw):
            if obj.get("authorizationRequired") is True:
                return True
        return False

    @staticmethod
    def _normalize_response(raw: Any) -> dict[str, Any]:
        status = AvailityAdapter._find_first_value(raw, ("status",)) or "unknown"
        plan_name = AvailityAdapter._find_first_value(
            raw,
            ("planName", "description", "groupName", "insuranceType"),
        ) or "Unknown"
        return {
            "status": str(status),
            "plan_name": str(plan_name),
            "copay": None,
            "coinsurance": None,
            "deductible_remaining": None,
            "out_of_pocket_remaining": None,
            "authorization_required": AvailityAdapter._authorization_required(raw),
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
                raw_response_json={
                    "provider": "availity",
                    "error": "missing_credentials",
                    "message": "Missing AVAILITY_CLIENT_ID or AVAILITY_CLIENT_SECRET",
                },
                error_message="Availity credentials are not configured",
            )

        token = await self._get_access_token()
        raw = await self._call_coverages(token, request)
        normalized = self._normalize_response(raw)

        return EligibilityResponse(
            status=normalized["status"],
            plan_name=normalized["plan_name"],
            copay=normalized["copay"],
            coinsurance=normalized["coinsurance"],
            deductible_remaining=normalized["deductible_remaining"],
            out_of_pocket_remaining=normalized["out_of_pocket_remaining"],
            authorization_required=normalized["authorization_required"],
            source="availity",
            checked_at=datetime.now(tz=timezone.utc),
            raw_response_json=raw,
        )
