"""Tests for Availity adapter token handling."""

import pytest

from app.adapters.availity_adapter import AvailityAdapter
from app.models.eligibility import EligibilityRequest


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.post_kwargs = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        self.post_kwargs = kwargs
        return self._response


@pytest.mark.asyncio
async def test_get_access_token_accepts_access_token(monkeypatch):
    response = _FakeResponse({"access_token": "abc123", "token_type": "Bearer"})
    fake_client = _FakeClient(response)
    monkeypatch.setattr(
        "app.adapters.availity_adapter.httpx.AsyncClient",
        lambda *args, **kwargs: fake_client,
    )

    adapter = AvailityAdapter()
    token = await adapter._get_access_token()

    assert token == "abc123"
    assert fake_client.post_kwargs["data"]["scope"] == "healthcare-hipaa-transactions-demo"
    assert "auth" not in fake_client.post_kwargs


@pytest.mark.asyncio
async def test_get_access_token_accepts_token_fallback(monkeypatch):
    response = _FakeResponse({"token": "fallback-token"})
    monkeypatch.setattr(
        "app.adapters.availity_adapter.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeClient(response),
    )

    adapter = AvailityAdapter()
    token = await adapter._get_access_token()

    assert token == "fallback-token"


@pytest.mark.asyncio
async def test_get_access_token_missing_token_field_raises(monkeypatch):
    response = _FakeResponse({"error": "invalid_client"})
    monkeypatch.setattr(
        "app.adapters.availity_adapter.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeClient(response),
    )

    adapter = AvailityAdapter()

    with pytest.raises(RuntimeError, match="missing token field"):
        await adapter._get_access_token()


@pytest.mark.asyncio
async def test_get_access_token_http_error_includes_oauth_context(monkeypatch):
    response = _FakeResponse(
        {
            "error": "unauthorized_client",
            "error_description": "Client is not authorized for grant type.",
        },
        status_code=401,
    )
    monkeypatch.setattr(
        "app.adapters.availity_adapter.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeClient(response),
    )

    adapter = AvailityAdapter()

    with pytest.raises(RuntimeError, match="grant_type=client_credentials"):
        await adapter._get_access_token()


@pytest.mark.asyncio
async def test_availity_check_preserves_raw_payload_when_unconfigured():
    adapter = AvailityAdapter()
    req = EligibilityRequest(
        patient={"first_name": "Jane", "last_name": "Doe", "dob": "1985-06-15", "member_id": "X"},
        payer={"name": "Aetna", "payer_id": "AET001"},
        provider={"npi": "1234567890", "tax_id": "12-3456789"},
        service_type="30",
    )
    result = await adapter.check_eligibility(req)
    assert result.source == "availity"
    assert result.raw_response_json is not None
