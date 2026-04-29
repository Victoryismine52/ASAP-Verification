"""Tests for landing page and provider switching UI endpoints."""
import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ELIGIBILITY_PROVIDER", "mock")

from app.main import app  # noqa: E402


@pytest.mark.asyncio
async def test_landing_page_served():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "Current Connection" in response.text
    assert "/docs" in response.text


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
async def test_switch_unknown_provider_returns_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/ui/select-connection", json={"provider": "unknown"})
    assert response.status_code == 400
