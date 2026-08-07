from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from backend.services.sessions import SessionContext, require_csrf, require_verified_session
from backend.services.storage import (
    add_favorite as store_favorite,
    delete_favorite as remove_favorite,
    get_favorites as fetch_favorites,
    serialize_favorites,
)

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    restaurant: str
    note: str | None = None
    created_at: str


class FavoritesResponse(BaseModel):
    favorites: list[FavoriteEntry] = Field(default_factory=list)


class FavoriteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    restaurant: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


@router.get("", response_model=FavoritesResponse)
async def list_favorites(
    session: SessionContext = Depends(require_verified_session),
) -> FavoritesResponse:
    records = await fetch_favorites(session.user_id)
    return FavoritesResponse(
        favorites=[FavoriteEntry(**item) for item in serialize_favorites(records)]
    )


@router.post("", response_model=FavoriteEntry, status_code=status.HTTP_201_CREATED)
async def add_favorite(
    payload: FavoriteCreateRequest,
    session: SessionContext = Depends(require_csrf),
) -> FavoriteEntry:
    record = await store_favorite(
        session.user_id, payload.restaurant.strip(), payload.note
    )
    return FavoriteEntry(**serialize_favorites([record])[0])


@router.delete("/{favorite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_favorite(
    favorite_id: str,
    session: SessionContext = Depends(require_csrf),
) -> None:
    if not await remove_favorite(session.user_id, favorite_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "favorite_not_found"},
        )
