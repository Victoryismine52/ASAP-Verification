"""Stedi eligibility adapter implementation."""
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.adapters.base import BaseEligibilityAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, EligibilityResponse


class StediAdapter(BaseEligibilityAdapter):
    """Adapter for Stedi's real-time eligibility JSON API."""

    _API_VERSION = "2024-04-01"
    _ELIGIBILITY_PATH = "change/medicalnetwork/eligibility/v3"

    def connection_details(self) -> dict:
        configured = bool(settings.stedi_api_key)
        return {
            "provider": "stedi",
            "configured": configured,
            "base_url": settings.stedi_base_url,
            "normalized_base_url": self._normalized_base_url(),
            "access_requirements": "Stedi API key; test keys require approved mock requests",
            "supported_transaction": "X12 270/271 via Stedi eligibility JSON API",
            "live_endpoint_implemented": True,
            "endpoint_status": "api key configured" if configured else "missing STEDI_API_KEY",
            "notes": "Uses the configured Stedi API key directly in the Authorization header; no live eligibility call is made for connection status.",
        }

    @classmethod
    def _normalized_base_url(cls) -> str:
        base_url = (settings.stedi_base_url or "https://healthcare.us.stedi.com/2024-04-01").strip().rstrip("/")
        parts = urlsplit(base_url)
        scheme = parts.scheme or "https"
        netloc = parts.netloc or parts.path.split("/")[0]
        path = parts.path if parts.netloc else "/".join(parts.path.split("/")[1:])
        if netloc == "core.us.stedi.com":
            netloc = "healthcare.us.stedi.com"
            path = ""
        segments = [seg for seg in path.split("/") if seg]
        endpoint_segments = cls._ELIGIBILITY_PATH.split("/")
        while len(segments) >= len(endpoint_segments) and segments[-len(endpoint_segments):] == endpoint_segments:
            segments = segments[:-len(endpoint_segments)]
        if cls._API_VERSION not in segments:
            segments.append(cls._API_VERSION)
        version_index = segments.index(cls._API_VERSION)
        segments = segments[: version_index + 1]
        return urlunsplit((scheme, netloc, "/" + "/".join(segments), "", ""))

    @classmethod
    def _eligibility_url(cls) -> str:
        return f"{cls._normalized_base_url()}/{cls._ELIGIBILITY_PATH}"

    @staticmethod
    def _body_snippet(response: httpx.Response) -> str:
        try:
            return response.text[:500]
        except Exception:  # pragma: no cover - defensive for unusual response objects
            return "<unavailable>"

    @staticmethod
    def _request_body(request: EligibilityRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "tradingPartnerServiceId": request.payer.payer_id,
            "provider": {
                "organizationName": settings.stedi_provider_organization_name,
                "npi": request.provider.npi,
            },
            "subscriber": {
                "firstName": request.patient.first_name,
                "lastName": request.patient.last_name,
                "memberId": request.patient.member_id,
                "dateOfBirth": request.patient.dob.strftime("%Y%m%d"),
            },
            "encounter": {"serviceTypeCodes": [request.service_type or "30"]},
        }
        if len(request.patient.member_id) <= 36:
            body["externalPatientId"] = request.patient.member_id
        return body

    @staticmethod
    def _benefits(raw: Any) -> list[dict[str, Any]]:
        benefits = raw.get("benefitsInformation", []) if isinstance(raw, dict) else []
        return [b for b in benefits if isinstance(b, dict)]

    @staticmethod
    def _errors(raw: Any) -> list[dict[str, Any]]:
        errors = raw.get("errors", []) if isinstance(raw, dict) else []
        return [e for e in errors if isinstance(e, dict)]

    @staticmethod
    def _codes(value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, list):
            return {str(v) for v in value if v is not None}
        return {str(value)}

    @classmethod
    def _matches_service(cls, benefit: dict[str, Any], service_type: str) -> bool:
        codes = set()
        for key in ("serviceTypeCodes", "serviceTypeCode"):
            codes.update(cls._codes(benefit.get(key)))
        return not codes or service_type in codes

    @staticmethod
    def _benefit_code(benefit: dict[str, Any]) -> str:
        return str(benefit.get("code") or benefit.get("benefitInformationCode") or "")

    @staticmethod
    def _amount(benefit: dict[str, Any], key: str) -> float | None:
        value = benefit.get(key)
        if isinstance(value, dict):
            value = value.get("amount") or value.get("value")
        try:
            return None if value is None or value == "" else float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _percent(benefit: dict[str, Any]) -> float | None:
        value = benefit.get("benefitPercent")
        try:
            return None if value is None or value == "" else float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_remaining(benefit: dict[str, Any]) -> bool:
        return str(benefit.get("timeQualifierCode") or "") == "29" or "remaining" in str(benefit.get("timeQualifier") or "").lower()

    @classmethod
    def _first_amount(cls, benefits: list[dict[str, Any]], code: str, key: str, prefer_remaining: bool = False) -> float | None:
        candidates = [b for b in benefits if cls._benefit_code(b) == code]
        if prefer_remaining:
            candidates = sorted(candidates, key=lambda b: 0 if cls._is_remaining(b) else 1)
        for benefit in candidates:
            amount = cls._amount(benefit, key)
            if amount is not None:
                return amount
        return None

    @staticmethod
    def _plan_name_from(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for key in ("description", "name", "planName"):
                if value.get(key):
                    return str(value[key])
        return None

    @classmethod
    def _plan_name(cls, benefits: list[dict[str, Any]], service_type: str) -> str:
        plan_benefits = [b for b in benefits if b.get("planCoverage")]
        groups = [
            [b for b in plan_benefits if cls._matches_service(b, service_type)],
            [b for b in plan_benefits if cls._matches_service(b, "30")],
            plan_benefits,
        ]
        for group in groups:
            for benefit in group:
                plan_name = cls._plan_name_from(benefit.get("planCoverage")) or cls._plan_name_from(benefit.get("planCoverageDescription"))
                if plan_name:
                    return plan_name
        return "Unknown"

    @classmethod
    def _authorization_required(cls, benefits: list[dict[str, Any]]) -> bool:
        for benefit in benefits:
            if str(benefit.get("authOrCertIndicator") or "").upper() == "Y":
                return True
            if "prior authorization" in str(benefit.get("additionalInformation") or "").lower():
                return True
        return False

    @staticmethod
    def _error_message(errors: list[dict[str, Any]]) -> str | None:
        if not errors:
            return None
        first = errors[0]
        parts = [first.get("code"), first.get("description"), first.get("followupAction")]
        return " - ".join(str(p) for p in parts if p)

    @classmethod
    def _normalize_response(cls, raw: Any, request: EligibilityRequest) -> dict[str, Any]:
        benefits = cls._benefits(raw)
        errors = cls._errors(raw)
        service_type = request.service_type or "30"
        active = any(cls._benefit_code(b) == "1" and cls._matches_service(b, service_type) for b in benefits)
        return {
            "status": "inactive" if errors or not active else "active",
            "plan_name": cls._plan_name(benefits, service_type),
            "copay": cls._first_amount(benefits, "B", "benefitAmount"),
            "coinsurance": cls._percent(next((b for b in benefits if cls._benefit_code(b) == "A"), {})),
            "deductible_remaining": cls._first_amount(benefits, "C", "benefitAmount", prefer_remaining=True),
            "out_of_pocket_remaining": cls._first_amount(benefits, "G", "benefitAmount", prefer_remaining=True),
            "authorization_required": cls._authorization_required(benefits),
            "error_message": cls._error_message(errors),
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
                raw_response_json={"provider": "stedi", "error": "missing_api_key", "message": "Missing STEDI_API_KEY"},
                error_message="Stedi API key is not configured",
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self._eligibility_url(),
                headers={
                    "Authorization": settings.stedi_api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=self._request_body(request),
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Stedi eligibility request failed (status={response.status_code}, body={self._body_snippet(response)})")
        try:
            raw = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Stedi eligibility response was not valid JSON (body={self._body_snippet(response)})") from exc
        normalized = self._normalize_response(raw, request)
        return EligibilityResponse(
            status=normalized["status"],
            plan_name=normalized["plan_name"],
            copay=normalized["copay"],
            coinsurance=normalized["coinsurance"],
            deductible_remaining=normalized["deductible_remaining"],
            out_of_pocket_remaining=normalized["out_of_pocket_remaining"],
            authorization_required=normalized["authorization_required"],
            source="stedi",
            checked_at=datetime.now(tz=timezone.utc),
            raw_response_json=raw,
            error_message=normalized["error_message"],
        )
