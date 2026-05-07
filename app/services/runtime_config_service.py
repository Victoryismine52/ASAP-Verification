"""Runtime-only provider connection settings overrides.

Overrides live only in this Python process and are never written to disk.
"""
from __future__ import annotations

from typing import Any

from app.config import settings

SECRET_FIELDS = {
    ("stedi", "api_key"),
    ("availity", "client_secret"),
}

KNOWN_FIELDS = {
    "stedi": {"api_key", "base_url", "provider_organization_name"},
    "availity": {
        "client_id",
        "client_secret",
        "base_url",
        "scope",
        "submitter_id",
        "provider_npi",
        "provider_tax_id",
    },
    "global": {"eligibility_provider"},
}

SETTINGS_ATTRS = {
    ("stedi", "api_key"): "stedi_api_key",
    ("stedi", "base_url"): "stedi_base_url",
    ("stedi", "provider_organization_name"): "stedi_provider_organization_name",
    ("availity", "client_id"): "availity_client_id",
    ("availity", "client_secret"): "availity_client_secret",
    ("availity", "base_url"): "availity_base_url",
    ("availity", "scope"): "availity_scope",
    ("availity", "submitter_id"): "availity_submitter_id",
    ("availity", "provider_npi"): "availity_provider_npi",
    ("availity", "provider_tax_id"): "availity_provider_tax_id",
    ("global", "eligibility_provider"): "eligibility_provider",
}


def mask_secret(value: str | None) -> str:
    """Return a display-safe secret value without exposing the full secret."""
    if not value:
        return ""
    value = str(value)
    if len(value) <= 4:
        return "****"
    if len(value) <= 12:
        return f"********{value[-4:]}"
    return f"{value[:8]}...{value[-4:]}"


class RuntimeConfigService:
    """In-memory store for process-local provider config overrides."""

    def __init__(self) -> None:
        self._overrides: dict[str, dict[str, str]] = {section: {} for section in KNOWN_FIELDS}

    def reset(self) -> None:
        self._overrides = {section: {} for section in KNOWN_FIELDS}

    def get_effective_value(self, section: str, field: str) -> str:
        if section not in KNOWN_FIELDS or field not in KNOWN_FIELDS[section]:
            raise KeyError(f"Unknown runtime config key: {section}.{field}")
        if field in self._overrides.get(section, {}):
            return self._overrides[section][field]
        attr = SETTINGS_ATTRS[(section, field)]
        return str(getattr(settings, attr, "") or "")

    def patch(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Runtime config payload must be an object")
        for section, values in payload.items():
            if section not in KNOWN_FIELDS:
                raise ValueError(f"Unknown runtime config section: {section}")
            if not isinstance(values, dict):
                raise ValueError(f"Runtime config section must be an object: {section}")
            for field, value in values.items():
                if field not in KNOWN_FIELDS[section]:
                    raise ValueError(f"Unknown runtime config key: {section}.{field}")
                if (section, field) in SECRET_FIELDS and (value is None or str(value).strip() == ""):
                    continue
                self._overrides[section][field] = "" if value is None else str(value)

    def response(self) -> dict[str, Any]:
        data: dict[str, Any] = {"overrides_active": {section: sorted(values.keys()) for section, values in self._overrides.items()}}
        for section, fields in KNOWN_FIELDS.items():
            data[section] = {}
            for field in sorted(fields):
                effective = self.get_effective_value(section, field)
                item: dict[str, Any] = {
                    "value": mask_secret(effective) if (section, field) in SECRET_FIELDS else effective,
                    "is_secret": (section, field) in SECRET_FIELDS,
                    "has_override": field in self._overrides.get(section, {}),
                }
                if (section, field) in SECRET_FIELDS:
                    item["configured"] = bool(effective)
                data[section][field] = item
        data["global"]["database_url"] = {
            "value": settings.database_url,
            "is_secret": False,
            "has_override": False,
            "view_only": True,
        }
        return data


runtime_config = RuntimeConfigService()
