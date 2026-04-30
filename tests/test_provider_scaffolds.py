"""Tests for scaffolded providers to ensure safe not-configured behavior."""
import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ELIGIBILITY_PROVIDER", "mock")

from app.main import app  # noqa: E402

VALID_PAYLOAD = {
    "patient": {"first_name": "Jane", "last_name": "Doe", "dob": "1985-06-15", "member_id": "MBR123456"},
    "payer": {"name": "Blue Cross Blue Shield", "payer_id": "BCBS001"},
    "provider": {"npi": "1234567890", "tax_id": "12-3456789"},
    "service_type": "30",
}

PROVIDERS = ["availity", "stedi", "optum_change", "cms_hets", "state_medicaid"]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_provider_select_and_safe_not_configured(provider: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        switch = await client.post("/ui/select-connection", json={"provider": provider})
        assert switch.status_code == 200

        details = await client.get("/ui/connection-details")
        assert details.status_code == 200
        assert details.json()["configured"] is False

        response = await client.post("/ui/test-call", json=VALID_PAYLOAD)
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == provider
        assert "Not configured" in data["plan_name"]
