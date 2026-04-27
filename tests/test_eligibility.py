"""
Tests for the POST /eligibility/check endpoint using the mock adapter.
"""
import os

import pytest
from httpx import AsyncClient, ASGITransport

# Force mock adapter before importing the app so the service picks it up
os.environ.setdefault("ELIGIBILITY_PROVIDER", "mock")

from app.main import app  # noqa: E402


VALID_PAYLOAD = {
    "patient": {
        "first_name": "Jane",
        "last_name": "Doe",
        "dob": "1985-06-15",
        "member_id": "MBR123456",
    },
    "payer": {
        "name": "Blue Cross Blue Shield",
        "payer_id": "BCBS001",
    },
    "provider": {
        "npi": "1234567890",
        "tax_id": "12-3456789",
    },
    "service_type": "30",
}


@pytest.mark.asyncio
async def test_eligibility_check_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/eligibility/check", json=VALID_PAYLOAD)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_eligibility_check_response_shape():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/eligibility/check", json=VALID_PAYLOAD)
    data = response.json()
    assert data["status"] in ("active", "inactive")
    assert "plan_name" in data
    assert data["source"] == "mock"
    assert "checked_at" in data
    assert isinstance(data["authorization_required"], bool)


@pytest.mark.asyncio
async def test_eligibility_check_mock_values():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/eligibility/check", json=VALID_PAYLOAD)
    data = response.json()
    assert data["status"] == "active"
    assert data["plan_name"] == "Mock PPO Gold Plan"
    assert data["copay"] == 25.0
    assert data["coinsurance"] == 0.20
    assert data["deductible_remaining"] == 750.0
    assert data["out_of_pocket_remaining"] == 2000.0
    assert data["authorization_required"] is False


@pytest.mark.asyncio
async def test_eligibility_check_missing_field_returns_422():
    """A request body missing required fields should return HTTP 422."""
    incomplete = {
        "patient": {"first_name": "John"},  # missing required fields
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/eligibility/check", json=incomplete)
    assert response.status_code == 422
