"""Tests for the Stedi eligibility adapter candidate scaffold."""

import pytest

from app.adapters.stedi_adapter import StediAdapter
from app.config import settings
from app.models.eligibility import EligibilityRequest, Patient, Payer, Provider
from app.services.eligibility_service import EligibilityService, PROVIDER_ADAPTER_MATRIX


@pytest.fixture
def eligibility_request() -> EligibilityRequest:
    return EligibilityRequest(
        patient=Patient(
            first_name="Jane",
            last_name="Doe",
            dob="1985-06-15",
            member_id="MBR123456",
        ),
        payer=Payer(name="Blue Cross Blue Shield", payer_id="BCBS001"),
        provider=Provider(npi="1234567890", tax_id="12-3456789"),
        service_type="30",
    )


@pytest.mark.asyncio
async def test_stedi_missing_api_key_returns_controlled_not_configured_response(monkeypatch, eligibility_request):
    monkeypatch.setattr(settings, "stedi_api_key", "")
    monkeypatch.setattr(settings, "stedi_base_url", "https://core.us.stedi.com")

    response = await StediAdapter().check_eligibility(eligibility_request)

    assert response.status == "inactive"
    assert response.plan_name == "Not configured: missing STEDI_API_KEY"
    assert response.source == "stedi"
    assert response.authorization_required is True
    assert response.copay is None
    assert response.coinsurance is None
    assert response.deductible_remaining is None
    assert response.out_of_pocket_remaining is None
    assert response.error_message == "Stedi credentials are not configured"


@pytest.mark.asyncio
async def test_stedi_configured_adapter_returns_scaffold_until_endpoint_is_implemented(monkeypatch, eligibility_request):
    monkeypatch.setattr(settings, "stedi_api_key", "test-stedi-key")
    monkeypatch.setattr(settings, "stedi_base_url", "https://stedi.example.test")

    response = await StediAdapter().check_eligibility(eligibility_request)

    assert response.status == "inactive"
    assert response.plan_name == "Stedi adapter scaffolded - live mapping not implemented"
    assert response.source == "stedi"
    assert response.authorization_required is True
    assert response.raw_response_json == {
        "provider": "stedi",
        "base_url": "https://stedi.example.test",
        "endpoint_implemented": False,
        "message": "Scaffold response only; live endpoint mapping pending documentation/access.",
    }


@pytest.mark.asyncio
async def test_stedi_connection_details_are_candidate_metadata_not_live_claims(monkeypatch):
    monkeypatch.setattr(settings, "stedi_api_key", "test-stedi-key")
    monkeypatch.setattr(settings, "stedi_base_url", "https://stedi.example.test")

    details = StediAdapter().connection_details()

    assert details == {
        "provider": "stedi",
        "configured": True,
        "base_url": "https://stedi.example.test",
        "access_requirements": "STEDI_API_KEY plus Stedi account access/enrollment for eligibility APIs",
        "supported_transaction": "X12 270/271",
        "live_endpoint_implemented": False,
        "endpoint_status": "sandbox/demo endpoint mapping pending",
        "notes": "API-first eligibility candidate; live endpoint mapping pending documentation/access.",
    }

    service = EligibilityService()
    service.set_provider("stedi")
    status = await service.connection_status()
    assert status == {
        "provider": "stedi",
        "connected": False,
        "detail": "sandbox/demo endpoint mapping pending",
    }

    matrix_entry = next(p for p in PROVIDER_ADAPTER_MATRIX if p["provider"] == "stedi")
    assert matrix_entry["real_time_support"] == "Candidate; endpoint mapping pending"
