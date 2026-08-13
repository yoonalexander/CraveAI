from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.config import get_settings
from backend.services.identity import resolve_request_usage_identity
from backend.services.rate_limit import burst_limiter
from backend.services.rag_pipeline import generate_recommendations
from backend.services.usage_limits import (
    DailyQuotaExceeded,
    UsageReservation,
    rate_limit_headers,
    reserve_daily_quota,
)
from backend.services.sessions import SessionContext, optional_session

router = APIRouter(prefix="/chat", tags=["chat"])
MAX_CHAT_MESSAGE_CHARS = 2000
_pipeline_semaphore = asyncio.Semaphore(20)


class ViewportBoundsPayload(BaseModel):
    """Validated Google Maps viewport rectangle."""

    model_config = ConfigDict(extra="forbid")

    north: float = Field(..., ge=-90, le=90)
    south: float = Field(..., ge=-90, le=90)
    east: float = Field(..., ge=-180, le=180)
    west: float = Field(..., ge=-180, le=180)

    @model_validator(mode="after")
    def validate_rectangle(self) -> "ViewportBoundsPayload":
        if self.north <= self.south or self.east <= self.west:
            raise ValueError("Viewport bounds must form a non-empty rectangle.")
        return self


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
    bounds: Optional[ViewportBoundsPayload] = Field(
        default=None,
        description="Confirmed visible map rectangle that strictly scopes retrieval.",
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


class RecommendationEvidence(BaseModel):
    """Attributable evidence used to support a recommendation."""

    type: str
    label: str
    source_url: Optional[str] = None


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
    match_score: Optional[float] = Field(default=None, ge=0, le=1)
    confidence: Optional[str] = None
    matching_dishes: List[str] = Field(default_factory=list)
    matched_preferences: List[str] = Field(default_factory=list)
    unmatched_preferences: List[str] = Field(default_factory=list)
    evidence: List[RecommendationEvidence] = Field(default_factory=list)


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
    intent: Optional[dict[str, Any]] = Field(
        default=None,
        description="Structured craving interpretation used by the ranking pipeline.",
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
    return ChatStatusResponse()


@router.post("", response_model=ChatResponse, response_model_exclude_defaults=True)
async def generate_chat_response(
    payload: ChatRequest,
    request: Request,
    response: Response,
    session: SessionContext | None = Depends(optional_session),
) -> ChatResponse:
    """
    Produce a chat response for the user's craving request.

    Delegates to the RAG pipeline to retrieve relevant recommendations.
    """
    settings = get_settings()
    user_text = payload.query or payload.message or ""
    usage_user_id = resolve_request_usage_identity(
        "chat", request, response, session.user_id if session else None
    )
    await burst_limiter.enforce(
        f"chat:{usage_user_id}",
        limit=20 if session else 10,
        window_seconds=60,
        code="chat_rate_limited",
    )
    configured_daily_limit = (
        settings.ACCOUNT_DAILY_CHAT_LIMIT
        if session
        else settings.GUEST_DAILY_CHAT_LIMIT
    )
    daily_limit = settings.scaled_daily_quota(configured_daily_limit)
    try:
        usage = await reserve_daily_quota(
            user_id=usage_user_id,
            token_cost=1,
            daily_limit=daily_limit,
            global_daily_limit=settings.scaled_daily_quota(
                settings.GLOBAL_DAILY_CHAT_LIMIT
            ),
            namespace="chat",
        )
    except DailyQuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "daily_chat_message_quota_exceeded",
                "message": "Daily chat quota exceeded.",
                "usage": _usage_metadata(exc.usage).model_dump(),
            },
            headers=rate_limit_headers(exc.usage, include_retry_after=True),
        ) from exc

    for header, value in rate_limit_headers(usage).items():
        response.headers[header] = value
    usage_metadata = _usage_metadata(usage)

    location_payload = payload.location.model_dump() if payload.location else {}
    try:
        async with _pipeline_semaphore:
            rag_result = await asyncio.wait_for(
                generate_recommendations(
                    user_query=user_text,
                    location=location_payload,
                    candidate_places=[item.model_dump() for item in payload.candidate_places],
                ),
                timeout=settings.CHAT_PIPELINE_TIMEOUT_SECONDS,
            )
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"code": "chat_pipeline_timeout"},
        ) from exc

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
            match_score=item.get("match_score"),
            confidence=item.get("confidence"),
            matching_dishes=item.get("matching_dishes") or [],
            matched_preferences=item.get("matched_preferences") or [],
            unmatched_preferences=item.get("unmatched_preferences") or [],
            evidence=item.get("evidence") or [],
        )
        for item in rag_result.get("recommendations", [])
    ]

    return ChatResponse(
        reply=rag_result.get("reply", ""),
        messages=[assistant_message],
        recommendations=recommendations,
        intent=rag_result.get("intent"),
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
