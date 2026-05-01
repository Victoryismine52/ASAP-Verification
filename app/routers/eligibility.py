"""
Eligibility router – exposes POST /eligibility/check.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.eligibility import EligibilityRequest, EligibilityResponse
from app.services.eligibility_service import service
from app.services.persistence_service import complete_request_error, complete_request_success, create_request_record

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eligibility", tags=["eligibility"])


@router.post("/check", response_model=EligibilityResponse, summary="Check insurance eligibility")
async def check_eligibility(request: EligibilityRequest, db: Session = Depends(get_db)) -> EligibilityResponse:
    logger.info("POST /eligibility/check – received request")
    started = datetime.now(timezone.utc)
    req_rec = create_request_record(db, request, "/eligibility/check", service.get_provider())
    try:
        response = await service.check(request)
        complete_request_success(db, req_rec, response, started)
        return response
    except RuntimeError as exc:
        complete_request_error(db, req_rec, str(exc), started)
        logger.error("Eligibility check error: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
