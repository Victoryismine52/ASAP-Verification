import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ELIGIBILITY_PROVIDER", "mock")
os.environ["DATABASE_URL"] = "sqlite:///./test_asap.db"

from app.main import app  # noqa: E402
from app.db import Base, engine, SessionLocal  # noqa: E402
from app.models.persistence import IntegrationOutbox, VerificationRequest  # noqa: E402

PAYLOAD = {
    "patient": {"first_name": "Jane", "last_name": "Doe", "dob": "1985-06-15", "member_id": "MBR123456"},
    "payer": {"name": "Blue Cross Blue Shield", "payer_id": "BCBS001"},
    "provider": {"npi": "1234567890", "tax_id": "12-3456789"},
    "service_type": "30",
}


@pytest.mark.asyncio
async def test_eligibility_is_persisted_and_history_and_exports():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/eligibility/check", json=PAYLOAD)
        assert res.status_code == 200

        history = await client.get("/history")
        assert history.status_code == 200
        assert len(history.json()["items"]) >= 1
        request_id = history.json()["items"][0]["request_id"]
        history_detail = await client.get(f"/history/{request_id}")
        assert history_detail.status_code == 200
        assert history_detail.json()["result"]["raw_response_json"] is not None

        csv_resp = await client.get("/exports/nextgen/eligibility-results.csv")
        assert csv_resp.status_code == 200
        assert "patient_first_name,patient_last_name" in csv_resp.text

    db = SessionLocal()
    try:
        assert db.query(VerificationRequest).count() >= 1
        assert db.query(IntegrationOutbox).count() >= 1
    finally:
        db.close()
