"""
Eligibility router – exposes POST /eligibility/check.
"""
import logging

from fastapi import APIRouter, HTTPException, status

from app.models.eligibility import EligibilityRequest, EligibilityResponse
from app.services.eligibility_service import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eligibility", tags=["eligibility"])

@router.post(
    "/check",
    response_model=EligibilityResponse,
    summary="Check insurance eligibility",
    description=(
        "Submit a patient / payer / provider combination and receive a "
        "normalised eligibility response.  The underlying provider is "
        "controlled by the ELIGIBILITY_PROVIDER environment variable."
    ),
)
async def check_eligibility(request: EligibilityRequest) -> EligibilityResponse:
    """
    Run an eligibility check against the configured provider.

    Returns a normalised **EligibilityResponse** with coverage details.
    """
    logger.info("POST /eligibility/check – received request")
    try:
        return await service.check(request)
    except RuntimeError as exc:
        logger.error("Eligibility check error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
