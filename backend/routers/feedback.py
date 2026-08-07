from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field

from backend.config import get_settings
from backend.services.rate_limit import burst_limiter
from backend.services.sessions import SessionContext, require_csrf
from backend.services.storage import record_feedback
from backend.services.usage_limits import DailyQuotaExceeded, reserve_daily_quota

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    restaurant: str = Field(min_length=1, max_length=200)
    liked: bool
    notes: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    status: str = "received"


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_feedback(
    payload: FeedbackRequest,
    request: Request,
    session: SessionContext = Depends(require_csrf),
) -> FeedbackResponse:
    settings = get_settings()
    await burst_limiter.enforce(
        f"feedback:{session.user_id}",
        limit=5,
        window_seconds=60,
        code="feedback_rate_limited",
    )
    try:
        await reserve_daily_quota(
            user_id=f"account:{session.user_id}",
            token_cost=1,
            daily_limit=settings.FEEDBACK_DAILY_LIMIT,
            namespace="feedback",
        )
    except DailyQuotaExceeded as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "daily_feedback_quota_exceeded"},
        ) from exc
    await record_feedback(
        user_id=session.user_id,
        restaurant=payload.restaurant.strip(),
        liked=payload.liked,
        notes=payload.notes,
    )
    return FeedbackResponse()
