"""
Pydantic models for eligibility check requests and responses.
"""
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class Patient(BaseModel):
    first_name: str = Field(..., json_schema_extra={"example": "Jane"})
    last_name: str = Field(..., json_schema_extra={"example": "Doe"})
    dob: date = Field(..., json_schema_extra={"example": "1985-06-15"})
    member_id: str = Field(..., json_schema_extra={"example": "MBR123456"})


class Payer(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Blue Cross Blue Shield"})
    payer_id: str = Field(..., json_schema_extra={"example": "BCBS001"})


class Provider(BaseModel):
    npi: str = Field(..., json_schema_extra={"example": "1234567890"})
    tax_id: str = Field(..., json_schema_extra={"example": "12-3456789"})


class EligibilityRequest(BaseModel):
    patient: Patient
    payer: Payer
    provider: Provider
    # e.g. "30" = Health Benefit Plan Coverage
    service_type: str = Field(..., json_schema_extra={"example": "30"})


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class EligibilityResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "active"})
    plan_name: str = Field(..., json_schema_extra={"example": "PPO Gold Plan"})
    copay: Optional[float] = Field(None, json_schema_extra={"example": 30.0})
    coinsurance: Optional[float] = Field(None, json_schema_extra={"example": 0.20})
    deductible_remaining: Optional[float] = Field(None, json_schema_extra={"example": 500.0})
    out_of_pocket_remaining: Optional[float] = Field(None, json_schema_extra={"example": 1500.0})
    authorization_required: bool = Field(..., json_schema_extra={"example": False})
    source: str = Field(..., json_schema_extra={"example": "mock"})
    checked_at: datetime = Field(..., json_schema_extra={"example": "2026-01-01T12:00:00Z"})
    raw_response_json: Any | None = Field(default=None)
    error_message: Optional[str] = Field(default=None)
