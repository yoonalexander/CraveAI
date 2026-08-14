from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.config import get_settings
from backend.services.product_data import record_policy_acceptance
from backend.services.sessions import SessionContext, require_csrf

router = APIRouter(prefix="/legal", tags=["legal"])


class PolicyAcceptanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    terms_version: str
    privacy_version: str
    accept_terms: bool
    acknowledge_privacy: bool
    age_confirmed: bool


@router.get("/current")
async def current_legal_documents() -> dict:
    settings = get_settings()
    publication_issues = settings.legal_publication_issues()
    return {
        "terms": {"version": settings.TERMS_VERSION, "effective_date": settings.POLICY_EFFECTIVE_DATE, "path": "/terms"},
        "privacy": {"version": settings.PRIVACY_VERSION, "effective_date": settings.POLICY_EFFECTIVE_DATE, "path": "/privacy"},
        "minimum_age": 18,
        "operator_legal_name": settings.OPERATOR_LEGAL_NAME,
        "operator_address": settings.OPERATOR_ADDRESS,
        "governing_law": settings.GOVERNING_LAW,
        "support_email": settings.SUPPORT_EMAIL,
        "privacy_email": settings.PRIVACY_EMAIL,
        "revision_history": [
            {
                "terms_version": settings.TERMS_VERSION,
                "privacy_version": settings.PRIVACY_VERSION,
                "effective_date": settings.POLICY_EFFECTIVE_DATE,
                "summary": "Application-specific Terms and Privacy Policy finalized from the implemented CraveAI data flows.",
            },
            {
                "terms_version": "2026-08-13",
                "privacy_version": "2026-08-13",
                "effective_date": "2026-08-13",
                "summary": "Pre-publication technical draft; replaced before legal publication.",
            },
        ],
        "publication_ready": not publication_issues,
        "publication_issues": list(publication_issues),
    }


@router.post("/accept")
async def accept_legal_documents(
    payload: PolicyAcceptanceRequest,
    session: SessionContext = Depends(require_csrf),
) -> dict:
    settings = get_settings()
    if payload.terms_version != settings.TERMS_VERSION or payload.privacy_version != settings.PRIVACY_VERSION:
        raise HTTPException(status_code=409, detail={"code": "policy_version_changed"})
    if not (payload.accept_terms and payload.acknowledge_privacy and payload.age_confirmed):
        raise HTTPException(status_code=422, detail={"code": "policy_acceptance_required"})
    return await record_policy_acceptance(
        session.user_id, payload.terms_version, payload.privacy_version, True
    )
