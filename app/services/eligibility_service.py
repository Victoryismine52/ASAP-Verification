"""Eligibility service with switchable provider adapters."""
import logging
import json
from pathlib import Path
from typing import Callable

from app.adapters.base import BaseEligibilityAdapter
from app.adapters.mock_adapter import MockAdapter
from app.adapters.availity_adapter import AvailityAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, EligibilityResponse

logger = logging.getLogger(__name__)


_ADAPTER_BUILDERS: dict[str, Callable[[], BaseEligibilityAdapter]] = {
    "mock": MockAdapter,
    "availity": AvailityAdapter,
}


def get_available_connections() -> list[str]:
    """Return providers from config file, falling back to built-ins."""
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
    """Orchestrates eligibility checks through the configured adapter."""

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
        """Return diagnostic info about the active provider wiring."""
        details = {
            "provider": self._provider,
            "adapter": self._adapter.__class__.__name__,
        }
        if self._provider == "availity":
            details.update(
                {
                    "base_url": settings.availity_base_url,
                    "token_url": f"{settings.availity_base_url}/v1/token",
                    "scope": settings.availity_scope,
                    "coverage_call_mode": "stubbed_response",
                    "notes": (
                        "OAuth token call is live, but coverage lookup currently returns "
                        "a deterministic stub response."
                    ),
                }
            )
        return details

    async def connection_status(self) -> dict:
        """Attempt provider-level connectivity and return status payload."""
        try:
            if self._provider == "availity":
                await self._adapter._get_access_token()  # type: ignore[attr-defined]
            return {"provider": self._provider, "connected": True, "detail": "ok"}
        except Exception as exc:
            return {"provider": self._provider, "connected": False, "detail": str(exc)}

    async def check(self, request: EligibilityRequest) -> EligibilityResponse:
        """
        Perform an eligibility check.

        Args:
            request: Validated input payload.

        Returns:
            Normalised EligibilityResponse.

        Raises:
            RuntimeError: If the adapter raises an unexpected exception.
        """
        logger.info(
            "EligibilityService.check – patient=%s %s payer=%s",
            request.patient.first_name,
            request.patient.last_name,
            request.payer.payer_id,
        )
        try:
            response = await self._adapter.check_eligibility(request)
            logger.info("EligibilityService.check – completed, status=%s", response.status)
            return response
        except Exception as exc:
            logger.exception("EligibilityService.check – adapter error: %s", exc)
            raise RuntimeError(f"Eligibility check failed: {exc}") from exc


service = EligibilityService()
