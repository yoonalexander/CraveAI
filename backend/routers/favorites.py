from __future__ import annotations

from typing import List

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

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
    """
    Retrieve the saved favorites for a given user.

    Currently serves static data until persistence is implemented.
    """
    placeholder_favorites = [
        FavoriteEntry(restaurant="Sample Sushi Bar", note="Saved during initial testing.")
    ]
    return FavoritesResponse(user_id=user_id, favorites=placeholder_favorites)


@router.post("", response_model=FavoriteEntry, status_code=status.HTTP_201_CREATED)
async def add_favorite(payload: FavoriteCreateRequest) -> FavoriteEntry:
    """
    Store a new favorite restaurant for a user.

    The data store integration will be added in a future milestone.
    """
    return FavoriteEntry(restaurant=payload.restaurant, note=payload.note)

