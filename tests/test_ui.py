"""Tests for landing page and provider switching UI endpoints."""
import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ELIGIBILITY_PROVIDER", "mock")

from app.main import app  # noqa: E402
from app.db import Base, engine  # noqa: E402


@pytest.mark.asyncio
async def test_landing_page_served():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "API Factory Demo" in response.text
    assert "Load Unknown Demo Patients" in response.text
    assert "Preview Request JSON" not in response.text
    assert "API Response Payload" in response.text
    assert "Send Selected" not in response.text
    assert "Send All Pending" in response.text
    assert "Load patients" in response.text
    assert "Make JSON" in response.text
    assert "Send to API" in response.text
    assert "Get answer" in response.text
    assert "Run Full Demo" not in response.text
    assert "Activity Log" in response.text
    assert "ASAP Verification Console" in response.text
    assert "Standalone verification workbench" in response.text
    assert "Active Verification Source" in response.text
    assert "Work Queue" in response.text
    assert "Request History" in response.text
    assert "Outbox" in response.text
    assert "Demo Data" in response.text
    assert "Load Demo Data" in response.text
    assert "Delete Demo Data" in response.text
    assert "Prototype / Mock Mode" in response.text
    assert "Import CSV to Work Queue" in response.text
    assert "Provider Adapter Matrix" in response.text
    assert "Verification Source" in response.text
    assert "Preferred Source" in response.text
    assert "Preview JSON" in response.text
    assert "Edit" in response.text
    assert "Send" in response.text
    assert "View Response" in response.text
    assert "Verification Source Status" in response.text
    assert "Export Results CSV" in response.text
    assert "Check Type" in response.text
    assert "Form View" in response.text
    assert "Raw JSON" in response.text
    assert "Sync Form to JSON" in response.text
    assert "Sync JSON to Form" in response.text


@pytest.mark.asyncio
async def test_connections_metadata_and_switch_mock():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        meta = await client.get("/ui/connections")
        assert meta.status_code == 200
        data = meta.json()
        assert "mock" in data["providers"]

        switch = await client.post("/ui/select-connection", json={"provider": "mock"})
        assert switch.status_code == 200
        switched = switch.json()
        assert switched["provider"] == "mock"


@pytest.mark.asyncio
async def test_connection_details_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ui/connection-details")
    assert response.status_code == 200
    data = response.json()
    assert "provider" in data
    assert "adapter" in data


@pytest.mark.asyncio
async def test_ui_test_call_returns_eligibility_payload():
    Base.metadata.create_all(bind=engine)
    payload = {
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/ui/test-call", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "source" in data


@pytest.mark.asyncio
async def test_example_csv_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/example_patients.csv")
    assert response.status_code == 200
    assert "first_name,last_name,dob,member_id" in response.text


@pytest.mark.asyncio
async def test_switch_unknown_provider_returns_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/ui/select-connection", json={"provider": "unknown"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_provider_matrix_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ui/provider-matrix")
    assert response.status_code == 200
    providers = response.json()["providers"]
    assert any(p["provider"] == "stedi" for p in providers)


@pytest.mark.asyncio
async def test_stedi_is_selectable_provider():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ui/connections")
    assert response.status_code == 200
    assert "stedi" in response.json()["providers"]
