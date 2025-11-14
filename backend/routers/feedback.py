from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from backend.services.storage import record_feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    """Payload capturing thumbs-up or thumbs-down reactions."""

    user_id: str = Field(..., description="Identifier for the user submitting feedback.")
    restaurant: str = Field(
        ...,
        description="Name or canonical identifier for the restaurant being rated.",
    )
    liked: bool = Field(..., description="True for positive feedback, False otherwise.")
    notes: str | None = Field(
        default=None, description="Optional free-form feedback from the user."
    )


class FeedbackResponse(BaseModel):
    """Acknowledges that the feedback event was accepted."""

    status: str = Field(default="received")


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_feedback(payload: FeedbackRequest) -> FeedbackResponse:
    """
    Accept a feedback event for downstream learning and analytics.

    The persistence layer will be connected in a later iteration.
    """
    await record_feedback(
        user_id=payload.user_id,
        restaurant=payload.restaurant,
        liked=payload.liked,
        notes=payload.notes,
    )
    return FeedbackResponse()
