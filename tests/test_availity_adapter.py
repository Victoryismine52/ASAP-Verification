"""Tests for Availity adapter token and coverages handling."""

import pytest

from app.adapters.availity_adapter import AvailityAdapter
from app.models.eligibility import EligibilityRequest


class _FakeResponse:
    def __init__(self, payload=None, status_code=200, text=None, json_error=False):
        self._payload = payload
        self.status_code = status_code
        self.text = text if text is not None else str(payload)
        self._json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


class _FakeClient:
    def __init__(self, response, calls=None):
        self._response = response
        self.calls = calls if calls is not None else []
        self.post_args = None
        self.post_kwargs = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        self.post_args = args
        self.post_kwargs = kwargs
        self.calls.append({"args": args, "kwargs": kwargs})
        return self._response


@pytest.fixture
def eligibility_request():
    return EligibilityRequest(
        patient={
            "first_name": "Jane",
            "last_name": "Doe",
            "dob": "1985-06-15",
            "member_id": "MBR123456",
        },
        payer={"name": "Aetna", "payer_id": "AET001"},
        provider={"npi": "1234567890", "tax_id": "12-3456789"},
        service_type="30",
    )


def test_v1_url_does_not_duplicate_version(monkeypatch):
    monkeypatch.setattr("app.adapters.availity_adapter.settings.availity_base_url", "https://api.availity.com/v1")
    assert AvailityAdapter._v1_url("token") == "https://api.availity.com/v1/token"
    assert AvailityAdapter._v1_url("/coverages") == "https://api.availity.com/v1/coverages"

    monkeypatch.setattr("app.adapters.availity_adapter.settings.availity_base_url", "https://api.availity.com")
    assert AvailityAdapter._v1_url("token") == "https://api.availity.com/v1/token"
    assert AvailityAdapter._v1_url("/coverages") == "https://api.availity.com/v1/coverages"


@pytest.mark.asyncio
async def test_get_access_token_accepts_access_token(monkeypatch):
    monkeypatch.setattr("app.adapters.availity_adapter.settings.availity_base_url", "https://api.availity.com/v1")
    response = _FakeResponse({"access_token": "abc123", "token_type": "Bearer"})
    fake_client = _FakeClient(response)
    monkeypatch.setattr(
        "app.adapters.availity_adapter.httpx.AsyncClient",
        lambda *args, **kwargs: fake_client,
    )

    adapter = AvailityAdapter()
    token = await adapter._get_access_token()

    assert token == "abc123"
    assert fake_client.post_args[0] == "https://api.availity.com/v1/token"
    assert fake_client.post_kwargs["data"] == {
        "grant_type": "client_credentials",
        "scope": "healthcare-hipaa-transactions-demo",
        "client_id": "",
        "client_secret": "",
    }
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
async def test_call_coverages_posts_form_data_not_json(monkeypatch, eligibility_request):
    monkeypatch.setattr("app.adapters.availity_adapter.settings.availity_base_url", "https://api.availity.com/v1")
    response_payload = {"status": "active", "plans": [{"planName": "Demo Gold"}]}
    fake_client = _FakeClient(_FakeResponse(response_payload))
    monkeypatch.setattr(
        "app.adapters.availity_adapter.httpx.AsyncClient",
        lambda *args, **kwargs: fake_client,
    )

    raw = await AvailityAdapter()._call_coverages("token-123", eligibility_request)

    assert raw == response_payload
    assert fake_client.post_args[0] == "https://api.availity.com/v1/coverages"
    assert fake_client.post_kwargs["headers"] == {
        "Authorization": "Bearer token-123",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    assert "json" not in fake_client.post_kwargs
    assert fake_client.post_kwargs["data"]["payerId"] == "AET001"
    assert fake_client.post_kwargs["data"]["providerNpi"] == "1234567890"
    assert fake_client.post_kwargs["data"]["providerTaxId"] == "12-3456789"
    assert fake_client.post_kwargs["data"]["serviceType"] == "30"
    assert fake_client.post_kwargs["data"]["memberId"] == "MBR123456"
    assert fake_client.post_kwargs["data"]["patientFirstName"] == "Jane"
    assert fake_client.post_kwargs["data"]["patientLastName"] == "Doe"
    assert fake_client.post_kwargs["data"]["patientBirthDate"] == "1985-06-15"
    assert "asOfDate" in fake_client.post_kwargs["data"]


@pytest.mark.asyncio
async def test_check_eligibility_preserves_raw_response_json(monkeypatch, eligibility_request):
    raw_payload = {
        "status": "active",
        "plans": [
            {
                "planName": "Availity Demo Plan",
                "benefits": [{"authorizationRequired": True}],
            }
        ],
    }
    adapter = AvailityAdapter()
    monkeypatch.setattr("app.adapters.availity_adapter.settings.availity_client_id", "client")
    monkeypatch.setattr("app.adapters.availity_adapter.settings.availity_client_secret", "secret")
    monkeypatch.setattr(adapter, "_get_access_token", lambda: _async_value("token"))
    monkeypatch.setattr(adapter, "_call_coverages", lambda token, request: _async_value(raw_payload))

    result = await adapter.check_eligibility(eligibility_request)

    assert result.status == "active"
    assert result.plan_name == "Availity Demo Plan"
    assert result.authorization_required is True
    assert result.raw_response_json == raw_payload
    assert result.plan_name != "Availity PPO Stub Plan"


@pytest.mark.asyncio
async def test_call_coverages_preserves_non_json_text(monkeypatch, eligibility_request):
    fake_client = _FakeClient(_FakeResponse(status_code=202, text="accepted", json_error=True))
    monkeypatch.setattr(
        "app.adapters.availity_adapter.httpx.AsyncClient",
        lambda *args, **kwargs: fake_client,
    )

    raw = await AvailityAdapter()._call_coverages("token-123", eligibility_request)

    assert raw == {"non_json_response_text": "accepted"}


@pytest.mark.asyncio
async def test_call_coverages_400_raises_runtime_error_with_status_and_body(monkeypatch, eligibility_request):
    fake_client = _FakeClient(
        _FakeResponse({"error": "bad request"}, status_code=400, text='{"error":"bad request"}')
    )
    monkeypatch.setattr(
        "app.adapters.availity_adapter.httpx.AsyncClient",
        lambda *args, **kwargs: fake_client,
    )

    with pytest.raises(RuntimeError, match="status=400.*bad request"):
        await AvailityAdapter()._call_coverages("token-123", eligibility_request)


@pytest.mark.asyncio
async def test_availity_check_preserves_raw_payload_when_unconfigured(monkeypatch, eligibility_request):
    monkeypatch.setattr("app.adapters.availity_adapter.settings.availity_client_id", "")
    monkeypatch.setattr("app.adapters.availity_adapter.settings.availity_client_secret", "")
    adapter = AvailityAdapter()
    result = await adapter.check_eligibility(eligibility_request)
    assert result.source == "availity"
    assert result.raw_response_json is not None


async def _async_value(value):
    return value
