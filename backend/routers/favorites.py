from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from backend.services.sessions import SessionContext, require_csrf, require_verified_session
from backend.services.storage import (
    add_favorite as store_favorite,
    delete_favorite as remove_favorite,
    get_favorites as fetch_favorites,
    serialize_favorites,
)
from backend.services.product_data import (
    create_collection,
    list_collections,
    list_saved_places_page,
    remove_collection,
    save_place,
    update_collection_item,
)

router = APIRouter(prefix="/favorites", tags=["favorites"])


class FavoriteEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    restaurant: str | None = None
    place_id: str | None = None
    note: str | None = None
    created_at: str


class FavoritesResponse(BaseModel):
    favorites: list[FavoriteEntry] = Field(default_factory=list)


class FavoriteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    restaurant: str | None = Field(default=None, min_length=1, max_length=200)
    place_id: str | None = Field(default=None, min_length=1, max_length=500)
    collection_id: str | None = None
    note: str | None = Field(default=None, max_length=1000)


class CollectionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)


class CollectionNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=1000)


@router.get("", response_model=FavoritesResponse)
async def list_favorites(
    session: SessionContext = Depends(require_verified_session),
) -> FavoritesResponse:
    records = await fetch_favorites(session.user_id)
    return FavoritesResponse(
        favorites=[FavoriteEntry(**item) for item in serialize_favorites(records)]
    )


@router.get("/saved")
async def list_saved(
    collection_id: str | None = None,
    limit: int = 30,
    cursor: str | None = None,
    session: SessionContext = Depends(require_verified_session),
) -> dict:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail={"code": "invalid_page_limit"})
    return await list_saved_places_page(session.user_id, collection_id, limit, cursor)


@router.get("/collections")
async def collections(
    session: SessionContext = Depends(require_verified_session),
) -> dict:
    return {"collections": await list_collections(session.user_id)}


@router.post("/collections", status_code=status.HTTP_201_CREATED)
async def add_collection(
    payload: CollectionCreateRequest,
    session: SessionContext = Depends(require_csrf),
) -> dict:
    try:
        return await create_collection(session.user_id, payload.name.strip())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "collection_exists"}) from exc


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: str,
    session: SessionContext = Depends(require_csrf),
) -> None:
    if not await remove_collection(session.user_id, collection_id):
        raise HTTPException(status_code=404, detail={"code": "collection_not_found_or_default"})


@router.patch("/{favorite_id}/collections/{collection_id}")
async def edit_collection_note(
    favorite_id: str,
    collection_id: str,
    payload: CollectionNoteRequest,
    session: SessionContext = Depends(require_csrf),
) -> dict:
    if not await update_collection_item(session.user_id, favorite_id, collection_id, payload.note):
        raise HTTPException(status_code=404, detail={"code": "saved_item_not_found"})
    return {"status": "updated"}


@router.post("", response_model=FavoriteEntry, status_code=status.HTTP_201_CREATED)
async def add_favorite(
    payload: FavoriteCreateRequest,
    session: SessionContext = Depends(require_csrf),
) -> FavoriteEntry:
    if payload.place_id:
        item = await save_place(
            session.user_id, payload.place_id.strip(), payload.collection_id, payload.note
        )
        return FavoriteEntry(
            id=item["id"], restaurant=None, place_id=item["place_id"],
            note=item["note"], created_at=item["created_at"],
        )
    if not payload.restaurant:
        raise HTTPException(status_code=422, detail={"code": "place_id_required"})
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
