from __future__ import annotations

import hmac
import math

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from openai import AsyncOpenAI

from backend.config import get_settings
from backend.services.identity import resolve_request_usage_identity
from backend.services.entitlements import resolve_entitlements
from backend.services.product_data import has_current_policy_acceptance
from backend.services.security import require_allowed_origin, sha256
from backend.services.sessions import SessionContext, optional_session
from backend.services.usage_limits import DailyQuotaExceeded, reserve_daily_quota

router = APIRouter(prefix="/audio", tags=["audio"])
ALLOWED_AUDIO_TYPES = {
    "audio/webm", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg",
}


@router.post("/transcriptions")
async def transcribe_audio(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    duration_seconds: float = Form(..., gt=0, le=60),
    age_confirmed: bool = Form(False),
    session: SessionContext | None = Depends(optional_session),
) -> dict:
    require_allowed_origin(request)
    settings = get_settings()
    if session:
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not hmac.compare_digest(sha256(supplied), session.csrf_token_hash):
            raise HTTPException(status_code=403, detail={"code": "csrf_validation_failed"})
        if not await has_current_policy_acceptance(
            session.user_id, settings.TERMS_VERSION, settings.PRIVACY_VERSION
        ):
            raise HTTPException(status_code=403, detail={"code": "policy_acceptance_required"})
    elif not age_confirmed:
        raise HTTPException(status_code=403, detail={"code": "guest_age_acknowledgment_required"})
    content_type = (file.content_type or "").split(";", 1)[0].lower()
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=415, detail={"code": "unsupported_audio_type"})
    data = await file.read(settings.AUDIO_MAX_BYTES + 1)
    await file.close()
    if not data or len(data) > settings.AUDIO_MAX_BYTES:
        data = b""
        raise HTTPException(status_code=413, detail={"code": "audio_too_large"})
    actor = resolve_request_usage_identity(
        "voice", request, response, session.user_id if session else None
    )
    try:
        await reserve_daily_quota(
            user_id=actor,
            token_cost=max(1, math.ceil(duration_seconds)),
            daily_limit=resolve_entitlements(bool(session))["limits"]["voice_seconds_per_day"],
            namespace="voice",
        )
    except DailyQuotaExceeded as exc:
        data = b""
        raise HTTPException(status_code=429, detail={"code": "daily_voice_quota_exceeded"}) from exc
    try:
        transcription = await AsyncOpenAI(api_key=settings.OPENAI_API_KEY).audio.transcriptions.create(
            model="whisper-1",
            file=(file.filename or "recording.webm", data, content_type),
            response_format="json",
        )
        return {"text": str(transcription.text).strip()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"code": "transcription_unavailable"}) from exc
    finally:
        data = b""
