import csv
import io
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.eligibility import EligibilityRequest, EligibilityResponse
from app.models.persistence import IntegrationOutbox, VerificationRequest, VerificationResult


def create_request_record(db: Session, request: EligibilityRequest, endpoint: str, provider_source: str) -> VerificationRequest:
    rid = uuid.uuid4().hex
    rec = VerificationRequest(
        request_id=rid,
        endpoint=endpoint,
        provider_source=provider_source,
        patient_first_name=request.patient.first_name,
        patient_last_name=request.patient.last_name,
        patient_dob=request.patient.dob,
        patient_member_id=request.patient.member_id,
        payer_name=request.payer.name,
        payer_id=request.payer.payer_id,
        provider_npi=request.provider.npi,
        provider_tax_id=request.provider.tax_id,
        service_type=request.service_type,
        raw_request_json=json.dumps(request.model_dump(mode="json")),
        status="received",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def complete_request_success(db: Session, request_rec: VerificationRequest, response: EligibilityResponse, started: datetime) -> None:
    ended = datetime.now(timezone.utc)
    request_rec.status = "completed"
    request_rec.completed_at = ended.replace(tzinfo=None)
    request_rec.duration_ms = int((ended - started).total_seconds() * 1000)
    vr = VerificationResult(
        request_id=request_rec.request_id,
        eligibility_status=response.status,
        plan_name=response.plan_name,
        copay=response.copay,
        coinsurance=response.coinsurance,
        deductible_remaining=response.deductible_remaining,
        out_of_pocket_remaining=response.out_of_pocket_remaining,
        authorization_required=response.authorization_required,
        source=response.source,
        checked_at=response.checked_at,
        raw_response_json=json.dumps(response.model_dump(mode="json")),
    )
    db.add(vr)
    outbox = IntegrationOutbox(
        request_id=request_rec.request_id,
        target_system="nextgen",
        target_record_type="eligibility_result",
        status="ready_for_review",
        payload_json=vr.raw_response_json,
    )
    db.add(outbox)
    db.commit()


def complete_request_error(db: Session, request_rec: VerificationRequest, error_message: str, started: datetime) -> None:
    ended = datetime.now(timezone.utc)
    request_rec.status = "error"
    request_rec.error_message = error_message
    request_rec.completed_at = ended.replace(tzinfo=None)
    request_rec.duration_ms = int((ended - started).total_seconds() * 1000)
    db.commit()


def outbox_status_counts(db: Session) -> dict[str, int]:
    rows = db.query(IntegrationOutbox.status, func.count(IntegrationOutbox.id)).group_by(IntegrationOutbox.status).all()
    return {status: count for status, count in rows}


def nextgen_csv(db: Session) -> str:
    rows = db.query(VerificationRequest, VerificationResult).join(VerificationResult, VerificationRequest.request_id == VerificationResult.request_id).order_by(VerificationRequest.created_at.desc()).all()
    out = io.StringIO()
    fields = ["patient_first_name","patient_last_name","dob","member_id","payer_name","payer_id","service_type","eligibility_status","plan_name","copay","coinsurance","deductible_remaining","out_of_pocket_remaining","authorization_required","checked_at","source","notes"]
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    for req, res in rows:
        w.writerow({"patient_first_name": req.patient_first_name, "patient_last_name": req.patient_last_name, "dob": req.patient_dob, "member_id": req.patient_member_id, "payer_name": req.payer_name, "payer_id": req.payer_id, "service_type": req.service_type, "eligibility_status": res.eligibility_status, "plan_name": res.plan_name, "copay": res.copay, "coinsurance": res.coinsurance, "deductible_remaining": res.deductible_remaining, "out_of_pocket_remaining": res.out_of_pocket_remaining, "authorization_required": res.authorization_required, "checked_at": res.checked_at.isoformat(), "source": res.source, "notes": res.notes or ""})
    return out.getvalue()
