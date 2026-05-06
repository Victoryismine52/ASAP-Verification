"""Tests for the Stedi eligibility adapter."""

import pytest
import httpx

from app.adapters.stedi_adapter import StediAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, Patient, Payer, Provider
from app.services.eligibility_service import EligibilityService, PROVIDER_ADAPTER_MATRIX


@pytest.fixture
def eligibility_request() -> EligibilityRequest:
    return EligibilityRequest(
        patient=Patient(first_name="Jane", last_name="Doe", dob="1985-06-15", member_id="MBR123456"),
        payer=Payer(name="Blue Cross Blue Shield", payer_id="BCBS001"),
        provider=Provider(npi="1234567890", tax_id="12-3456789"),
        service_type="30",
    )


def stedi_response(*, errors=None, status="complete"):
    return {
        "status": status,
        "benefitsInformation": [
            {"code": "1", "serviceTypeCodes": ["30"], "planCoverage": "PPO Gold"},
            {"code": "B", "serviceTypeCodes": ["30"], "benefitAmount": "25"},
            {"code": "A", "serviceTypeCodes": ["30"], "benefitPercent": "0.2"},
            {"code": "C", "serviceTypeCodes": ["30"], "benefitAmount": "900", "timeQualifierCode": "23"},
            {"code": "C", "serviceTypeCodes": ["30"], "benefitAmount": "300", "timeQualifierCode": "29"},
            {"code": "G", "serviceTypeCodes": ["30"], "benefitAmount": "1200", "timeQualifierCode": "29"},
            {"code": "B", "serviceTypeCodes": ["98"], "additionalInformation": "prior authorization required"},
        ],
        "errors": errors or [],
    }


class CapturingAsyncClient:
    calls = []
    response = httpx.Response(200, json=stedi_response())

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.__class__.calls.append({"url": url, **kwargs})
        return self.__class__.response


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://healthcare.us.stedi.com/2024-04-01", "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/eligibility/v3"),
        ("https://healthcare.us.stedi.com", "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/eligibility/v3"),
        ("https://core.us.stedi.com", "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/eligibility/v3"),
        ("https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/eligibility/v3", "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/eligibility/v3"),
    ],
)
def test_stedi_url_normalization(monkeypatch, base_url, expected):
    monkeypatch.setattr(settings, "stedi_base_url", base_url)
    assert StediAdapter._eligibility_url() == expected


def test_stedi_request_body_uses_external_patient_id_when_provided(eligibility_request):
    request = eligibility_request.model_copy(update={"external_patient_id": "UAA111222333"})

    body = StediAdapter._request_body(request)

    assert body["externalPatientId"] == "UAA111222333"


def test_stedi_request_body_falls_back_to_member_id_when_external_patient_id_missing(eligibility_request):
    body = StediAdapter._request_body(eligibility_request)

    assert body["externalPatientId"] == "MBR123456"


@pytest.mark.asyncio
async def test_stedi_missing_api_key_returns_controlled_not_configured_response(monkeypatch, eligibility_request):
    monkeypatch.setattr(settings, "stedi_api_key", "")

    response = await StediAdapter().check_eligibility(eligibility_request)

    assert response.status == "inactive"
    assert response.plan_name == "Not configured: missing STEDI_API_KEY"
    assert response.source == "stedi"
    assert response.raw_response_json["error"] == "missing_api_key"
    assert response.error_message == "Stedi API key is not configured"


@pytest.mark.asyncio
async def test_stedi_request_body_headers_and_json_post(monkeypatch, eligibility_request):
    CapturingAsyncClient.calls = []
    CapturingAsyncClient.response = httpx.Response(200, json=stedi_response())
    monkeypatch.setattr(settings, "stedi_api_key", "raw-test-key")
    monkeypatch.setattr(settings, "stedi_base_url", "https://healthcare.us.stedi.com")
    monkeypatch.setattr(settings, "stedi_provider_organization_name", "Demo Org")
    monkeypatch.setattr(httpx, "AsyncClient", CapturingAsyncClient)

    await StediAdapter().check_eligibility(eligibility_request)

    call = CapturingAsyncClient.calls[0]
    assert call["url"] == "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/eligibility/v3"
    assert call["headers"]["Authorization"] == "raw-test-key"
    assert call["headers"]["Accept"] == "application/json"
    assert call["headers"]["Content-Type"] == "application/json"
    assert "json" in call
    assert "data" not in call
    assert call["json"] == {
        "tradingPartnerServiceId": "BCBS001",
        "provider": {"organizationName": "Demo Org", "npi": "1234567890"},
        "subscriber": {"firstName": "Jane", "lastName": "Doe", "memberId": "MBR123456", "dateOfBirth": "19850615"},
        "encounter": {"serviceTypeCodes": ["30"]},
        "externalPatientId": "MBR123456",
    }


@pytest.mark.asyncio
async def test_stedi_preserves_raw_response_and_normalizes_benefits(monkeypatch, eligibility_request):
    raw = stedi_response(status="queued")
    CapturingAsyncClient.calls = []
    CapturingAsyncClient.response = httpx.Response(200, json=raw)
    monkeypatch.setattr(settings, "stedi_api_key", "raw-test-key")
    monkeypatch.setattr(httpx, "AsyncClient", CapturingAsyncClient)

    response = await StediAdapter().check_eligibility(eligibility_request)

    assert response.raw_response_json == raw
    assert response.status == "active"
    assert response.plan_name == "PPO Gold"
    assert response.copay == 25
    assert response.coinsurance == 0.2
    assert response.deductible_remaining == 300
    assert response.out_of_pocket_remaining == 1200
    assert response.authorization_required is True


@pytest.mark.asyncio
async def test_stedi_errors_create_error_message_and_inactive_status(monkeypatch, eligibility_request):
    raw = stedi_response(errors=[{"code": "42", "description": "Subscriber not found", "followupAction": "Correct member ID"}])
    CapturingAsyncClient.response = httpx.Response(200, json=raw)
    monkeypatch.setattr(settings, "stedi_api_key", "raw-test-key")
    monkeypatch.setattr(httpx, "AsyncClient", CapturingAsyncClient)

    response = await StediAdapter().check_eligibility(eligibility_request)

    assert response.status == "inactive"
    assert response.error_message == "42 - Subscriber not found - Correct member ID"


@pytest.mark.asyncio
async def test_stedi_http_400_raises_runtime_error(monkeypatch, eligibility_request):
    CapturingAsyncClient.response = httpx.Response(400, text="bad request body")
    monkeypatch.setattr(settings, "stedi_api_key", "raw-test-key")
    monkeypatch.setattr(httpx, "AsyncClient", CapturingAsyncClient)

    with pytest.raises(RuntimeError, match="status=400"):
        await StediAdapter().check_eligibility(eligibility_request)


@pytest.mark.asyncio
async def test_stedi_invalid_json_raises_runtime_error(monkeypatch, eligibility_request):
    CapturingAsyncClient.response = httpx.Response(200, text="not json")
    monkeypatch.setattr(settings, "stedi_api_key", "raw-test-key")
    monkeypatch.setattr(httpx, "AsyncClient", CapturingAsyncClient)

    with pytest.raises(RuntimeError, match="not valid JSON"):
        await StediAdapter().check_eligibility(eligibility_request)


@pytest.mark.asyncio
async def test_stedi_connection_status_uses_api_key_without_live_call(monkeypatch):
    monkeypatch.setattr(settings, "stedi_api_key", "test-stedi-key")
    service = EligibilityService()
    service.set_provider("stedi")

    status = await service.connection_status()

    assert status == {"provider": "stedi", "connected": True, "detail": "api key configured"}
    matrix_entry = next(p for p in PROVIDER_ADAPTER_MATRIX if p["provider"] == "stedi")
    assert matrix_entry["real_time_support"] == "API key live; eligibility JSON API"
