from __future__ import annotations

import secrets
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.services.identity import require_user_identity
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

    user_id: str = Field(..., min_length=1, max_length=128)
    restaurant: str = Field(..., min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


@router.get("/{user_id}", response_model=FavoritesResponse)
async def list_favorites(
    user_id: str,
    authenticated_user_id: str = Depends(require_user_identity),
) -> FavoritesResponse:
    """Retrieve saved favorites for a given user."""
    _require_owner(authenticated_user_id, user_id)
    stored_records = await fetch_favorites(user_id)
    favorites = [FavoriteEntry(**record_dict) for record_dict in serialize_favorites(stored_records)]
    return FavoritesResponse(user_id=user_id, favorites=favorites)


@router.post("", response_model=FavoriteEntry, status_code=status.HTTP_201_CREATED)
async def add_favorite(
    payload: FavoriteCreateRequest,
    authenticated_user_id: str = Depends(require_user_identity),
) -> FavoriteEntry:
    """Store a new favorite restaurant for a user."""
    _require_owner(authenticated_user_id, payload.user_id)
    record = await store_favorite(payload.user_id, payload.restaurant, payload.note)
    record_dict = serialize_favorites([record])[0]
    return FavoriteEntry(**record_dict)


def _require_owner(authenticated_user_id: str, requested_user_id: str) -> None:
    if not secrets.compare_digest(authenticated_user_id, requested_user_id.strip()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "favorites_owner_mismatch"},
        )
