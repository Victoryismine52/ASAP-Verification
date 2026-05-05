import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ELIGIBILITY_PROVIDER", "mock")
os.environ["DATABASE_URL"] = "sqlite:///./test_asap.db"

from app.main import app  # noqa: E402
from app.db import Base, engine, SessionLocal  # noqa: E402
from app.models.persistence import VerificationWorkItem  # noqa: E402


CSV_HEADER = "first_name,last_name,dob,member_id,payer_name,payer_id,npi,tax_id,service_type\n"


@pytest.mark.asyncio
async def test_csv_new_row_inserts_pending_work_item():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    csv_text = CSV_HEADER + "Jane,Doe,1985-06-15,MBR123456,Blue Cross,BCBS001,1234567890,12-3456789,30\n"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/work-items/import.csv", files={"file": ("patients.csv", csv_text, "text/csv")})
        assert res.status_code == 200
        assert res.json()["inserted"] == 1

        pending = await client.get("/work-items", params={"status": "pending_validation"})
        assert pending.status_code == 200
        assert len(pending.json()["items"]) == 1


@pytest.mark.asyncio
async def test_duplicate_row_updates_existing_item_and_no_duplicate_created():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    csv_text = CSV_HEADER + "Jane,Doe,1985-06-15,MBR123456,Blue Cross,BCBS001,1234567890,12-3456789,30\n"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/work-items/import.csv", files={"file": ("patients.csv", csv_text, "text/csv")})
        res = await client.post("/work-items/import.csv", files={"file": ("patients.csv", csv_text, "text/csv")})
        assert res.status_code == 200
        assert res.json()["updated"] == 1

    db = SessionLocal()
    try:
        assert db.query(VerificationWorkItem).count() == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_reupload_marks_existing_item_needs_revalidation():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    csv_text = CSV_HEADER + "Jane,Doe,1985-06-15,MBR123456,Blue Cross,BCBS001,1234567890,12-3456789,30\n"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/work-items/import.csv", files={"file": ("patients.csv", csv_text, "text/csv")})
        await client.post("/work-items/import.csv", files={"file": ("patients.csv", csv_text, "text/csv")})
    db = SessionLocal()
    try:
        row = db.query(VerificationWorkItem).first()
        assert row is not None
        assert row.validation_status == "needs_revalidation"
        assert row.needs_validation is True
    finally:
        db.close()


@pytest.mark.asyncio
async def test_validate_endpoint_updates_status_to_validated():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    csv_text = CSV_HEADER + "Jane,Doe,1985-06-15,MBR123456,Blue Cross,BCBS001,1234567890,12-3456789,30\n"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/work-items/import.csv", files={"file": ("patients.csv", csv_text, "text/csv")})
        items = await client.get("/work-items", params={"status": "pending_validation"})
        item_id = items.json()["items"][0]["id"]
        validated = await client.post(f"/work-items/{item_id}/validate")
        assert validated.status_code == 200
    db = SessionLocal()
    try:
        row = db.query(VerificationWorkItem).first()
        assert row is not None
        assert row.validation_status == "validated"
        assert row.needs_validation is False
        assert row.last_request_id is not None
    finally:
        db.close()


@pytest.mark.asyncio
async def test_patch_work_item_marks_needs_revalidation_and_validate_still_works():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    csv_text = CSV_HEADER + "Jane,Doe,1985-06-15,MBR123456,Blue Cross,BCBS001,1234567890,12-3456789,30\n"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/work-items/import.csv", files={"file": ("patients.csv", csv_text, "text/csv")})
        items = await client.get("/work-items")
        item_id = items.json()["items"][0]["id"]
        patch = await client.patch(f"/work-items/{item_id}", json={"first_name": "Janet", "notes": "edited"})
        assert patch.status_code == 200
        assert patch.json()["validation_status"] == "needs_revalidation"
        assert patch.json()["needs_validation"] is True
        validated = await client.post(f"/work-items/{item_id}/validate")
        assert validated.status_code == 200


@pytest.mark.asyncio
async def test_work_item_export_csv_and_outbox_status_update():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    csv_text = CSV_HEADER + "Jane,Doe,1985-06-15,MBR123456,Blue Cross,BCBS001,1234567890,12-3456789,30\n"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/work-items/import.csv", files={"file": ("patients.csv", csv_text, "text/csv")})
        items = await client.get("/work-items")
        item_id = items.json()["items"][0]["id"]
        await client.post(f"/work-items/{item_id}/validate")
        exp = await client.get("/work-items/export.csv")
        assert exp.status_code == 200
        assert "first_name,last_name" in exp.text
        factory_exp = await client.get("/exports/factory/results.csv", params={"include_demo": "true"})
        assert factory_exp.status_code == 200
        assert "work_item_id,patient_name,dob,member_id" in factory_exp.text
        assert "request_payload_json" in factory_exp.text
        assert "response_payload_json" in factory_exp.text
        assert "Jane Doe" in factory_exp.text
        outbox = await client.get("/outbox")
        assert outbox.status_code == 200
        assert len(outbox.json()["items"]) >= 1
        outbox_id = outbox.json()["items"][0]["id"]
        upd = await client.patch(f"/outbox/{outbox_id}", json={"status": "exported"})
        assert upd.status_code == 200
        assert upd.json()["status"] == "exported"


@pytest.mark.asyncio
async def test_validate_selected_validates_selected_ids():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    csv_text = CSV_HEADER + (
        "Jane,Doe,1985-06-15,MBR123456,Blue Cross,BCBS001,1234567890,12-3456789,30\n"
        "John,Doe,1980-02-15,MBR999999,Aetna,AET001,1234567890,12-3456789,30\n"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/work-items/import.csv", files={"file": ("patients.csv", csv_text, "text/csv")})
        items = (await client.get("/work-items")).json()["items"]
        ids = [i["id"] for i in items]
        res = await client.post("/work-items/validate-selected", json={"ids": ids, "provider": "mock"})
        assert res.status_code == 200
        data = res.json()
        assert data["requested_count"] == 2
        assert data["validated_count"] == 2
        assert data["failed_count"] == 0
        assert len(data["results"]) == 2
        assert all(item.get("request_id") for item in data["results"])


@pytest.mark.asyncio
async def test_validate_selected_returns_per_item_failures_without_stopping_batch():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    csv_text = CSV_HEADER + "Jane,Doe,1985-06-15,MBR123456,Blue Cross,BCBS001,1234567890,12-3456789,30\n"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/work-items/import.csv", files={"file": ("patients.csv", csv_text, "text/csv")})
        item_id = (await client.get("/work-items")).json()["items"][0]["id"]
        res = await client.post("/work-items/validate-selected", json={"ids": [item_id, 999999], "provider": "mock"})
        assert res.status_code == 200
        data = res.json()
        assert data["requested_count"] == 2
        assert data["validated_count"] == 1
        assert data["failed_count"] == 1
        by_id = {r["id"]: r for r in data["results"]}
        assert by_id[item_id]["status"] == "validated"
        assert by_id[999999]["status"] == "failed"
