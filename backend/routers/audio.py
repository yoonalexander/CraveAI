from __future__ import annotations

import base64
import hmac
import math

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from openai import AsyncOpenAI

from backend.config import get_settings
from backend.services import llm
from backend.services.identity import resolve_request_usage_identities
from backend.services.entitlements import has_unlimited_usage_access, resolve_entitlements
from backend.services.product_data import has_current_policy_acceptance
from backend.services.rate_limit import burst_limiter
from backend.services.security import require_allowed_origin, sha256
from backend.services.sessions import SessionContext, optional_session
from backend.services.usage_limits import (
    DailyQuotaExceeded,
    VOICE_GLOBAL_USAGE_USER_ID,
    reserve_daily_quota,
)

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
    usage_identities = resolve_request_usage_identities(
        "voice", request, response, session.user_id if session else None
    )
    actor = usage_identities[0]
    await burst_limiter.enforce(
        f"voice:{actor}",
        limit=12 if session else 6,
        window_seconds=60,
        code="voice_rate_limited",
    )
    enforce_actor_limit = not has_unlimited_usage_access(session)
    try:
        await reserve_daily_quota(
            user_id=actor,
            token_cost=max(1, math.ceil(duration_seconds)),
            daily_limit=resolve_entitlements(bool(session))["limits"]["voice_seconds_per_day"],
            global_daily_limit=settings.GLOBAL_DAILY_VOICE_SECONDS,
            global_user_id=VOICE_GLOBAL_USAGE_USER_ID,
            namespace="voice",
            enforce_actor_limit=enforce_actor_limit,
            additional_user_ids=usage_identities[1:],
        )
    except DailyQuotaExceeded as exc:
        data = b""
        raise HTTPException(status_code=429, detail={"code": "daily_voice_quota_exceeded"}) from exc
    try:
        if llm.resolve_provider(settings) == "gemini":
            transcript = await _transcribe_with_gemini(
                settings, data, content_type
            )
        else:
            transcription = await AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY
            ).audio.transcriptions.create(
                model="whisper-1",
                file=(file.filename or "recording.webm", data, content_type),
                response_format="json",
            )
            transcript = str(transcription.text)
        return {"text": transcript.strip()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"code": "transcription_unavailable"}) from exc
    finally:
        data = b""


GEMINI_AUDIO_FORMATS = {
    "audio/webm": "webm",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
}


async def _transcribe_with_gemini(settings, data: bytes, content_type: str) -> str:
    """Gemini accepts inline audio through the OpenAI-compatible chat endpoint."""
    client = AsyncOpenAI(**llm.client_options(settings, timeout=60))
    completion = await client.chat.completions.create(
        model=llm.model_name(settings),
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Generate a verbatim transcript of the speech in this "
                        "audio. Return only the transcript text with no commentary. "
                        "If there is no speech, return an empty string."
                    ),
                },
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": base64.b64encode(data).decode("ascii"),
                        "format": GEMINI_AUDIO_FORMATS[content_type],
                    },
                },
            ],
        }],
        **llm.completion_options(
            settings, max_completion_tokens=1500, reasoning_effort="minimal"
        ),
    )
    return completion.choices[0].message.content or ""
