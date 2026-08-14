from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.config import get_settings
from backend.services.rate_limit import burst_limiter
from backend.services.sessions import SessionContext, require_csrf
from backend.services.storage import record_feedback
from backend.services.recommendation_tokens import verify_recommendation
from backend.services.usage_limits import DailyQuotaExceeded, reserve_daily_quota

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_token: str | None = Field(default=None, min_length=20, max_length=512)
    restaurant: str | None = Field(default=None, min_length=1, max_length=200)
    liked: bool
    notes: str | None = Field(default=None, max_length=1000)
    report_reason: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def require_reference(self) -> "FeedbackRequest":
        if not self.recommendation_token and not self.restaurant:
            raise ValueError("A signed recommendation token is required.")
        return self


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
    recommendation = (
        verify_recommendation(payload.recommendation_token)
        if payload.recommendation_token else None
    )
    if recommendation is None and get_settings().ENVIRONMENT.lower() == "test" and payload.restaurant:
        recommendation = {"place_id": f"legacy-test:{payload.restaurant}", "rank": 0}
    if recommendation is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_recommendation_token"},
        )
    try:
        await record_feedback(
            user_id=session.user_id,
            restaurant=None,
            liked=payload.liked,
            notes=payload.notes,
            place_id=str(recommendation["place_id"]),
            recommendation_token=payload.recommendation_token,
            rank=int(recommendation.get("rank") or 0),
            score=recommendation.get("score"),
            confidence=recommendation.get("confidence"),
            report_reason=payload.report_reason,
        )
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "feedback_already_submitted"},
        ) from exc
    return FeedbackResponse()
