from __future__ import annotations

import hmac
from datetime import datetime, time, timedelta, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.config import get_settings
from backend.services.identity import (
    issue_anonymous_identity_token,
    verify_anonymous_identity_token,
)
from backend.services.rag_pipeline import generate_recommendations
from backend.services.usage_limits import (
    DailyQuotaExceeded,
    UsageReservation,
    rate_limit_headers,
    reserve_daily_quota,
    resolve_usage_user_id,
)

router = APIRouter(prefix="/chat", tags=["chat"])
MAX_CHAT_MESSAGE_CHARS = 2000
ANONYMOUS_TOKEN_HEADER = "X-CraveAI-Anonymous-Token"
DEV_BYPASS_HEADER = "X-CraveAI-Dev-Bypass"


class LocationPayload(BaseModel):
    """Location information supplied by the frontend."""

    lat: float = Field(
        ...,
        ge=-90,
        le=90,
        description="Latitude component of the user's location.",
    )
    lng: float = Field(
        ...,
        ge=-180,
        le=180,
        description="Longitude component of the user's location.",
    )
    city: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Optional human-readable location label.",
    )
    radius: Optional[int] = Field(
        default=None,
        ge=100,
        le=20000,
        description="Search radius hint in meters (optional).",
    )


class CandidatePlacePayload(BaseModel):
    """A bounded, session-scoped restaurant candidate supplied by the UI."""

    model_config = ConfigDict(extra="forbid")

    place_id: str = Field(..., min_length=1, max_length=500)
    name: str = Field(..., min_length=1, max_length=200)
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    user_ratings_total: Optional[int] = Field(default=None, ge=0)
    address: Optional[str] = Field(default=None, max_length=500)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    tags: List[Annotated[str, Field(min_length=1, max_length=60)]] = Field(
        default_factory=list,
        max_length=3,
    )


class ChatRequest(BaseModel):
    """Incoming chat request from the frontend."""

    model_config = ConfigDict(extra="forbid")

    query: Optional[str] = Field(
        default=None,
        max_length=MAX_CHAT_MESSAGE_CHARS,
        description="Natural language craving or mood description.",
    )
    message: Optional[str] = Field(
        default=None,
        max_length=MAX_CHAT_MESSAGE_CHARS,
        description="Alternate chat message field accepted by deployed clients.",
    )
    location: Optional[LocationPayload] = Field(default=None, description="Structured location data.")
    candidate_places: List[CandidatePlacePayload] = Field(
        default_factory=list,
        max_length=20,
        description="Ephemeral restaurant candidates from the active browser session.",
    )

    @model_validator(mode="after")
    def require_chat_text(self) -> "ChatRequest":
        if not (self.query or self.message):
            raise ValueError("Either query or message is required.")
        return self


class ChatMessage(BaseModel):
    """Single chat response entry that the UI can display."""

    role: str = Field(..., description="Speaker role, e.g., assistant or system.")
    content: str = Field(..., description="Message content shown to the user.")


class Recommendation(BaseModel):
    """Recommendation payload returned by the RAG pipeline."""

    name: str
    place_id: Optional[str] = None
    rating: Optional[float] = None
    address: Optional[str] = None
    reason: Optional[str] = Field(
        default=None,
        description="Explanation for why this venue was recommended.",
    )
    lat: Optional[float] = Field(default=None, description="Latitude for the venue, if known.")
    lng: Optional[float] = Field(default=None, description="Longitude for the venue, if known.")


class UsageMetadata(BaseModel):
    """Daily demo quota metadata returned with chat responses."""

    limit: int
    used: int
    remaining: int
    reset_at: str
    unlimited: bool = False


class ChatResponse(BaseModel):
    """Structured response returned to the frontend."""

    reply: str = Field(
        default="",
        description="Primary assistant response summarizing the recommendations.",
    )
    messages: List[ChatMessage] = Field(
        default_factory=list,
        description="Ordered transcript containing the assistant reply.",
    )
    recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="Ranked restaurant suggestions that match the user's craving.",
    )
    usage: Optional[UsageMetadata] = Field(
        default=None,
        description="Daily demo chat message quota state for the resolved user.",
    )


class ChatStatusResponse(BaseModel):
    """Non-counting chat status used by the UI for mode indicators."""

    usage: Optional[UsageMetadata] = None


@router.get("/status", response_model=ChatStatusResponse, response_model_exclude_defaults=True)
async def get_chat_status(request: Request) -> ChatStatusResponse:
    settings = get_settings()
    bypass_quota = settings.CHAT_DEVELOPER_MODE or _is_dev_bypass_authorized(
        request.headers.get(DEV_BYPASS_HEADER),
        settings.CHAT_DEV_BYPASS_SECRET,
    )
    if bypass_quota:
        return ChatStatusResponse(usage=_unlimited_usage_metadata())
    return ChatStatusResponse()


@router.post("", response_model=ChatResponse, response_model_exclude_defaults=True)
async def generate_chat_response(
    payload: ChatRequest,
    request: Request,
    response: Response,
) -> ChatResponse:
    """
    Produce a chat response for the user's craving request.

    Delegates to the RAG pipeline to retrieve relevant recommendations.
    """
    settings = get_settings()
    user_text = payload.query or payload.message or ""
    client_host = request.client.host if request.client else None
    usage_user_id, anonymous_token = _resolve_chat_usage_identity(
        request.headers.get(ANONYMOUS_TOKEN_HEADER),
        client_host,
        settings.IDENTITY_SIGNING_SECRET,
    )
    bypass_quota = settings.CHAT_DEVELOPER_MODE or _is_dev_bypass_authorized(
        request.headers.get(DEV_BYPASS_HEADER),
        settings.CHAT_DEV_BYPASS_SECRET,
    )
    if bypass_quota:
        usage_metadata = _unlimited_usage_metadata()
        if anonymous_token:
            response.headers[ANONYMOUS_TOKEN_HEADER] = anonymous_token
    else:
        try:
            usage = await reserve_daily_quota(
                user_id=usage_user_id,
                token_cost=1,
                daily_limit=settings.DAILY_CHAT_MESSAGE_LIMIT,
                global_daily_limit=settings.GLOBAL_DAILY_TOKEN_LIMIT,
            )
        except DailyQuotaExceeded as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "daily_chat_message_quota_exceeded",
                    "message": "Daily demo chat message quota exceeded.",
                    "usage": _usage_metadata(exc.usage).model_dump(),
                },
                headers=_chat_response_headers(
                    exc.usage,
                    anonymous_token=anonymous_token,
                    include_retry_after=True,
                ),
            ) from exc

        for header, value in _chat_response_headers(
            usage,
            anonymous_token=anonymous_token,
        ).items():
            response.headers[header] = value
        usage_metadata = _usage_metadata(usage)

    location_payload = payload.location.model_dump() if payload.location else {}
    rag_result = await generate_recommendations(
        user_query=user_text,
        location=location_payload,
        candidate_places=[item.model_dump() for item in payload.candidate_places],
    )

    assistant_message = ChatMessage(role="assistant", content=rag_result.get("reply", ""))
    recommendations = [
        Recommendation(
            name=item.get("name", "Unknown"),
            place_id=item.get("place_id"),
            rating=item.get("rating"),
            address=item.get("address"),
            reason=item.get("reason"),
            lat=item.get("lat"),
            lng=item.get("lng"),
        )
        for item in rag_result.get("recommendations", [])
    ]

    return ChatResponse(
        reply=rag_result.get("reply", ""),
        messages=[assistant_message],
        recommendations=recommendations,
        usage=usage_metadata,
    )


def _usage_metadata(usage: UsageReservation) -> UsageMetadata:
    return UsageMetadata(
        limit=usage.limit,
        used=usage.used,
        remaining=usage.remaining,
        reset_at=usage.reset_at,
    )


def _unlimited_usage_metadata() -> UsageMetadata:
    now = datetime.now(timezone.utc)
    reset_at = datetime.combine(
        now.date() + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    ).isoformat().replace("+00:00", "Z")
    return UsageMetadata(
        limit=0,
        used=0,
        remaining=0,
        reset_at=reset_at,
        unlimited=True,
    )


def _resolve_chat_usage_identity(
    anonymous_token: str | None,
    client_host: str | None,
    signing_secret: str,
) -> tuple[str, str | None]:
    if not signing_secret:
        return f"chat:{resolve_usage_user_id(client_host)}", None

    if anonymous_token:
        try:
            anonymous_subject = verify_anonymous_identity_token(
                anonymous_token.strip(),
                signing_secret,
            )
            return f"chat:{anonymous_subject}", anonymous_token.strip()
        except ValueError:
            pass

    anonymous_subject, issued_token = issue_anonymous_identity_token(signing_secret)
    return f"chat:{anonymous_subject}", issued_token


def _is_dev_bypass_authorized(
    provided_secret: str | None,
    configured_secret: str,
) -> bool:
    if not provided_secret or not configured_secret:
        return False
    return hmac.compare_digest(provided_secret.strip(), configured_secret)


def _chat_response_headers(
    usage: UsageReservation,
    *,
    anonymous_token: str | None,
    include_retry_after: bool = False,
) -> dict[str, str]:
    headers = rate_limit_headers(usage, include_retry_after=include_retry_after)
    if anonymous_token:
        headers[ANONYMOUS_TOKEN_HEADER] = anonymous_token
    return headers
