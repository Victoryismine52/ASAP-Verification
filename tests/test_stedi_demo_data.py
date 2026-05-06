import json
from pathlib import Path


MOCK_VALUES_PATH = Path("data/stedi_mock_values.example.json")
DEMO_SEED_PATH = Path("data/demo_seed.json")


def test_stedi_mock_values_example_has_no_placeholders():
    text = MOCK_VALUES_PATH.read_text(encoding="utf-8")
    assert "REPLACE_WITH" not in text
    assert "YYYY-MM-DD" not in text


def test_demo_seed_has_no_stedi_placeholders():
    text = DEMO_SEED_PATH.read_text(encoding="utf-8")
    for placeholder in ("StediMock", "ReplaceWithApproved", "STEDI_MOCK", "STEDI-D"):
        assert placeholder not in text


def test_demo_seed_stedi_rows_are_docs_sample_rows():
    seed = json.loads(DEMO_SEED_PATH.read_text(encoding="utf-8"))
    stedi_rows = [row for row in seed["work_items"] if row.get("preferred_provider") == "stedi"]

    assert len(stedi_rows) >= 2
    assert all(row["preferred_provider"] == "stedi" for row in stedi_rows)
    assert all(row["service_type"] == "30" for row in stedi_rows)
    assert all(row["validation_status"] == "pending_validation" for row in stedi_rows)
    assert all(row["needs_validation"] is True for row in stedi_rows)

    member_ids = {row["member_id"] for row in stedi_rows}
    assert "123456789" in member_ids
    assert "123456780" in member_ids
    assert all(row.get("external_patient_id") for row in stedi_rows)
    assert any("Correct member_id to 123456789 and resend." in (row.get("notes") or "") for row in stedi_rows)
