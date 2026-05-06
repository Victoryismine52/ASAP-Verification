from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class VerificationRequest(Base):
    __tablename__ = "verification_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    endpoint: Mapped[str] = mapped_column(String(64), default="/eligibility/check")
    provider_source: Mapped[str] = mapped_column(String(64))

    patient_first_name: Mapped[str] = mapped_column(String(120))
    patient_last_name: Mapped[str] = mapped_column(String(120))
    patient_dob: Mapped[date] = mapped_column(Date)
    patient_member_id: Mapped[str] = mapped_column(String(120))
    external_patient_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    payer_name: Mapped[str] = mapped_column(String(200))
    payer_id: Mapped[str] = mapped_column(String(80))

    provider_npi: Mapped[str] = mapped_column(String(40))
    provider_tax_id: Mapped[str] = mapped_column(String(40))
    service_type: Mapped[str] = mapped_column(String(20))

    raw_request_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="received")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    result: Mapped["VerificationResult"] = relationship(back_populates="request", uselist=False)


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), ForeignKey("verification_requests.request_id"), index=True)

    eligibility_status: Mapped[str] = mapped_column(String(32))
    plan_name: Mapped[str] = mapped_column(String(200))
    copay: Mapped[float | None] = mapped_column(Float, nullable=True)
    coinsurance: Mapped[float | None] = mapped_column(Float, nullable=True)
    deductible_remaining: Mapped[float | None] = mapped_column(Float, nullable=True)
    out_of_pocket_remaining: Mapped[float | None] = mapped_column(Float, nullable=True)
    authorization_required: Mapped[bool] = mapped_column()
    source: Mapped[str] = mapped_column(String(64))
    checked_at: Mapped[datetime] = mapped_column(DateTime)
    raw_response_json: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    request: Mapped[VerificationRequest] = relationship(back_populates="result")


class IntegrationOutbox(Base):
    __tablename__ = "integration_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    target_system: Mapped[str] = mapped_column(String(64))
    target_record_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class VerificationWorkItem(Base):
    __tablename__ = "verification_work_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)

    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120))
    dob: Mapped[date] = mapped_column(Date)
    member_id: Mapped[str] = mapped_column(String(120))
    payer_name: Mapped[str] = mapped_column(String(200))
    payer_id: Mapped[str] = mapped_column(String(80))
    npi: Mapped[str] = mapped_column(String(40))
    tax_id: Mapped[str] = mapped_column(String(40))
    service_type: Mapped[str] = mapped_column(String(20), default="30")
    external_patient_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    preferred_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)

    needs_validation: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_status: Mapped[str] = mapped_column(String(64), default="pending_validation")
    source_method: Mapped[str] = mapped_column(String(64), default="csv_upload")
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
