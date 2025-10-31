from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.rag_pipeline import generate_recommendations

router = APIRouter(prefix="/chat", tags=["chat"])


class LocationPayload(BaseModel):
    """Location information supplied by the frontend."""

    lat: float = Field(..., description="Latitude component of the user's location.")
    lng: float = Field(..., description="Longitude component of the user's location.")
    city: Optional[str] = Field(
        default=None, description="Optional human-readable location label."
    )
    radius: Optional[int] = Field(
        default=None, description="Search radius hint in meters (optional)."
    )


class ChatRequest(BaseModel):
    """Incoming chat request from the frontend."""

    query: str = Field(..., description="Natural language craving or mood description.")
    user_id: Optional[str] = Field(
        default=None, description="Optional identifier for the active user session."
    )
    location: Optional[LocationPayload] = Field(default=None, description="Structured location data.")


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


@router.post("", response_model=ChatResponse)
async def generate_chat_response(payload: ChatRequest) -> ChatResponse:
    """
    Produce a chat response for the user's craving request.

    Delegates to the RAG pipeline to retrieve relevant recommendations.
    """
    location_payload = payload.location.model_dump() if payload.location else {}
    rag_result = await generate_recommendations(
        user_query=payload.query,
        location=location_payload,
    )

    assistant_message = ChatMessage(role="assistant", content=rag_result.get("reply", ""))
    recommendations = [
        Recommendation(
            name=item.get("name", "Unknown"),
            rating=item.get("rating"),
            address=item.get("address"),
            reason=item.get("reason"),
        )
        for item in rag_result.get("recommendations", [])
    ]

    return ChatResponse(
        reply=rag_result.get("reply", ""),
        messages=[assistant_message],
        recommendations=recommendations,
    )
