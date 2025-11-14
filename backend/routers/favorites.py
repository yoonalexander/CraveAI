from __future__ import annotations

from typing import List

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from backend.services.storage import (
    add_favorite as store_favorite,
    get_favorites as fetch_favorites,
    serialize_favorites,
)

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteEntry(BaseModel):
    """Represents a single saved restaurant for a user."""

    restaurant: str = Field(..., description="Display name for the restaurant.")
    note: str | None = Field(
        default=None,
        description="Optional user-provided context about why it was saved.",
    )


class FavoritesResponse(BaseModel):
    """Collection of a user's saved places."""

    user_id: str
    favorites: List[FavoriteEntry] = Field(default_factory=list)


class FavoriteCreateRequest(BaseModel):
    """Payload for adding a new favorite restaurant."""

    user_id: str
    restaurant: str
    note: str | None = None


@router.get("/{user_id}", response_model=FavoritesResponse)
async def list_favorites(user_id: str) -> FavoritesResponse:
    """Retrieve saved favorites for a given user."""
    stored_records = await fetch_favorites(user_id)
    favorites = [FavoriteEntry(**record_dict) for record_dict in serialize_favorites(stored_records)]
    return FavoritesResponse(user_id=user_id, favorites=favorites)


@router.post("", response_model=FavoriteEntry, status_code=status.HTTP_201_CREATED)
async def add_favorite(payload: FavoriteCreateRequest) -> FavoriteEntry:
    """Store a new favorite restaurant for a user."""
    record = await store_favorite(payload.user_id, payload.restaurant, payload.note)
    record_dict = serialize_favorites([record])[0]
    return FavoriteEntry(**record_dict)
