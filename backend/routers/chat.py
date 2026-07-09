from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import List, Optional

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
    if settings.CHAT_DEVELOPER_MODE:
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
    )

    assistant_message = ChatMessage(role="assistant", content=rag_result.get("reply", ""))
    recommendations = [
        Recommendation(
            name=item.get("name", "Unknown"),
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
