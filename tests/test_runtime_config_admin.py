"""Tests for demo-only runtime provider config overrides."""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.availity_adapter import AvailityAdapter
from app.adapters.stedi_adapter import StediAdapter
from app.config import settings
from app.main import app
from app.models.eligibility import EligibilityRequest, Patient, Payer, Provider
from app.services.runtime_config_service import runtime_config


@pytest.fixture(autouse=True)
def reset_runtime_config():
    runtime_config.reset()
    yield
    runtime_config.reset()


@pytest.fixture
def eligibility_request() -> EligibilityRequest:
    return EligibilityRequest(
        patient=Patient(first_name="Jane", last_name="Doe", dob="1985-06-15", member_id="MBR123456"),
        payer=Payer(name="Blue Cross Blue Shield", payer_id="BCBS001"),
        provider=Provider(npi="1234567890", tax_id="12-3456789"),
        service_type="30",
    )


class CapturingAsyncClient:
    calls = []
    responses = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.__class__.calls.append({"url": url, **kwargs})
        return self.__class__.responses.pop(0)


@pytest.mark.asyncio
async def test_get_admin_config_masks_secrets(monkeypatch):
    monkeypatch.setattr(settings, "stedi_api_key", "sk_live_1234567890abcd")
    monkeypatch.setattr(settings, "availity_client_secret", "availity-secret-abcd")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/admin/runtime-config")

    assert response.status_code == 200
    data = response.json()
    assert data["stedi"]["api_key"]["value"] == "sk_live_...abcd"
    assert data["availity"]["client_secret"]["value"] == "availity...abcd"
    assert "sk_live_1234567890abcd" not in response.text
    assert "availity-secret-abcd" not in response.text


@pytest.mark.asyncio
async def test_patch_admin_config_updates_runtime_values_and_rejects_unknown_keys():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/admin/runtime-config",
            json={"stedi": {"base_url": "https://example.test", "api_key": "new-stedi-secret"}},
        )
        bad = await client.patch("/admin/runtime-config", json={"stedi": {"unknown": "nope"}})

    assert response.status_code == 200
    assert runtime_config.get_effective_value("stedi", "base_url") == "https://example.test"
    assert runtime_config.get_effective_value("stedi", "api_key") == "new-stedi-secret"
    assert "new-stedi-secret" not in response.text
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_blank_secret_patch_does_not_clear_existing_secret(monkeypatch):
    monkeypatch.setattr(settings, "stedi_api_key", "env-stedi-secret")
    runtime_config.patch({"stedi": {"api_key": "runtime-stedi-secret"}})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/admin/runtime-config", json={"stedi": {"api_key": ""}})

    assert response.status_code == 200
    assert runtime_config.get_effective_value("stedi", "api_key") == "runtime-stedi-secret"


@pytest.mark.asyncio
async def test_reset_clears_runtime_overrides_and_falls_back_to_settings(monkeypatch):
    monkeypatch.setattr(settings, "stedi_base_url", "https://env.example")
    runtime_config.patch({"stedi": {"base_url": "https://runtime.example"}})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/admin/runtime-config/reset")

    assert response.status_code == 200
    assert runtime_config.get_effective_value("stedi", "base_url") == "https://env.example"
    assert response.json()["stedi"]["base_url"]["has_override"] is False


@pytest.mark.asyncio
async def test_stedi_adapter_uses_runtime_api_key_and_org(monkeypatch, eligibility_request):
    CapturingAsyncClient.calls = []
    CapturingAsyncClient.responses = [httpx.Response(200, json={"benefitsInformation": []})]
    monkeypatch.setattr(httpx, "AsyncClient", CapturingAsyncClient)
    runtime_config.patch(
        {
            "stedi": {
                "api_key": "runtime-stedi-key",
                "base_url": "https://healthcare.us.stedi.com",
                "provider_organization_name": "Runtime Org",
            }
        }
    )

    await StediAdapter().check_eligibility(eligibility_request)

    call = CapturingAsyncClient.calls[0]
    assert call["headers"]["Authorization"] == "runtime-stedi-key"
    assert call["json"]["provider"]["organizationName"] == "Runtime Org"


@pytest.mark.asyncio
async def test_availity_adapter_uses_runtime_client_secret(monkeypatch, eligibility_request):
    CapturingAsyncClient.calls = []
    CapturingAsyncClient.responses = [
        httpx.Response(200, json={"access_token": "token-123"}),
        httpx.Response(200, json={"status": "active", "planName": "Runtime Plan"}),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", CapturingAsyncClient)
    runtime_config.patch(
        {
            "availity": {
                "client_id": "runtime-client-id",
                "client_secret": "runtime-client-secret",
                "base_url": "https://api.availity.test",
                "scope": "runtime-scope",
            }
        }
    )

    response = await AvailityAdapter().check_eligibility(eligibility_request)

    token_call = CapturingAsyncClient.calls[0]
    assert token_call["url"] == "https://api.availity.test/v1/token"
    assert token_call["data"]["client_id"] == "runtime-client-id"
    assert token_call["data"]["client_secret"] == "runtime-client-secret"
    assert token_call["data"]["scope"] == "runtime-scope"
    assert response.plan_name == "Runtime Plan"
