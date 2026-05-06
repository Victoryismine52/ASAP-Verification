"""Eligibility service with switchable provider adapters."""
import json
import logging
from pathlib import Path
from typing import Callable

from app.adapters.availity_adapter import AvailityAdapter
from app.adapters.base import BaseEligibilityAdapter
from app.adapters.cms_hets_adapter import CmsHetsAdapter
from app.adapters.mock_adapter import MockAdapter
from app.adapters.optum_change_adapter import OptumChangeAdapter
from app.adapters.state_medicaid_adapter import StateMedicaidAdapter
from app.adapters.stedi_adapter import StediAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, EligibilityResponse

logger = logging.getLogger(__name__)


_ADAPTER_BUILDERS: dict[str, Callable[[], BaseEligibilityAdapter]] = {
    "mock": MockAdapter,
    "availity": AvailityAdapter,
    "stedi": StediAdapter,
    "optum_change": OptumChangeAdapter,
    "cms_hets": CmsHetsAdapter,
    "state_medicaid": StateMedicaidAdapter,
}

PROVIDER_ADAPTER_MATRIX = [
    {"provider": "mock", "coverage_type": "Simulated", "real_time_support": "Yes (mocked)", "access_needed": "None", "best_use": "Local development and CI"},
    {"provider": "availity", "coverage_type": "Commercial and payer network", "real_time_support": "OAuth live; /coverages API call", "access_needed": "Availity app credentials", "best_use": "Availity-connected workflows"},
    {"provider": "stedi", "coverage_type": "Multi-payer EDI gateway", "real_time_support": "Candidate; endpoint mapping pending", "access_needed": "Stedi API key + eligibility API access/enrollment", "best_use": "Unified API-first X12 270/271 integrations"},
    {"provider": "optum_change", "coverage_type": "Commercial + clearinghouse", "real_time_support": "Scaffolded", "access_needed": "Client credentials + trading partner", "best_use": "Enterprise clearinghouse connectivity"},
    {"provider": "cms_hets", "coverage_type": "Medicare", "real_time_support": "Scaffolded", "access_needed": "HETS submitter account", "best_use": "Medicare beneficiary checks"},
    {"provider": "state_medicaid", "coverage_type": "State Medicaid", "real_time_support": "Varies by state", "access_needed": "State portal/API credentials", "best_use": "State-specific Medicaid verification"},
]


def get_available_connections() -> list[str]:
    config_path = Path(settings.connections_config_path)
    if not config_path.exists():
        return list(_ADAPTER_BUILDERS.keys())
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Unable to parse connections config %s: %s", config_path, exc)
        return list(_ADAPTER_BUILDERS.keys())
    if isinstance(data, dict):
        providers = data.get("providers", [])
        if isinstance(providers, list):
            valid = [p for p in providers if isinstance(p, str) and p in _ADAPTER_BUILDERS]
            if valid:
                return valid
    return list(_ADAPTER_BUILDERS.keys())


class EligibilityService:
    def __init__(self) -> None:
        self._provider = settings.eligibility_provider.lower()
        self._adapter: BaseEligibilityAdapter = self._build_adapter(self._provider)

    def _build_adapter(self, provider: str) -> BaseEligibilityAdapter:
        if provider not in _ADAPTER_BUILDERS:
            raise ValueError(f"Unsupported provider: {provider}")
        logger.info("Using %s adapter.", provider)
        return _ADAPTER_BUILDERS[provider]()

    def get_provider(self) -> str:
        return self._provider

    def set_provider(self, provider: str) -> None:
        provider = provider.lower()
        self._adapter = self._build_adapter(provider)
        self._provider = provider

    def connection_details(self) -> dict:
        details = {"provider": self._provider, "adapter": self._adapter.__class__.__name__}
        details.update(self._adapter.connection_details())
        return details

    async def connection_status(self) -> dict:
        try:
            details = self._adapter.connection_details()
            if not details.get("configured", False):
                return {"provider": self._provider, "connected": False, "detail": "not configured"}
            if details.get("live_endpoint_implemented") is False:
                return {
                    "provider": self._provider,
                    "connected": False,
                    "detail": details.get("endpoint_status", "live endpoint mapping pending"),
                }
            if self._provider == "availity":
                await self._adapter._get_access_token()  # type: ignore[attr-defined]
            return {"provider": self._provider, "connected": True, "detail": "ok"}
        except Exception as exc:
            return {"provider": self._provider, "connected": False, "detail": str(exc)}

    async def check(self, request: EligibilityRequest) -> EligibilityResponse:
        try:
            return await self._adapter.check_eligibility(request)
        except Exception as exc:
            logger.exception("EligibilityService.check – adapter error: %s", exc)
            raise RuntimeError(f"Eligibility check failed: {exc}") from exc


service = EligibilityService()
