from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.services.product_data import (
    ALLOWED_CONSENTS,
    clear_conversations,
    get_preferences,
    set_consent,
    update_preferences,
)
from backend.services.sessions import SessionContext, require_csrf, require_verified_session

router = APIRouter(prefix="/account", tags=["preferences"])


class LocationPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    label: str = Field(min_length=1, max_length=120)


class PreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    favorite_cuisines: list[str] | None = Field(default=None, max_length=30)
    disliked_foods: list[str] | None = Field(default=None, max_length=30)
    dietary_restrictions: list[str] | None = Field(default=None, max_length=30)
    allergies: list[str] | None = Field(default=None, max_length=30)
    default_location: LocationPreference | None = None
    default_radius_meters: int | None = Field(default=None, ge=500, le=20000)
    recommendation_preferences: dict[str, Any] | None = None
    personalization_enabled: bool | None = None
    history_enabled: bool | None = None
    reduced_motion: Literal["system", "on", "off"] | None = None
    notification_preferences: dict[str, bool] | None = None


class ConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    granted: bool = True


@router.get("/preferences")
async def read_preferences(
    session: SessionContext = Depends(require_verified_session),
) -> dict:
    return await get_preferences(session.user_id)


@router.patch("/preferences")
async def patch_preferences(
    payload: PreferencePatch,
    session: SessionContext = Depends(require_csrf),
) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    for key in ("favorite_cuisines", "disliked_foods", "dietary_restrictions", "allergies"):
        if key in changes:
            changes[key] = list(dict.fromkeys(item.strip()[:80] for item in changes[key] if item.strip()))
    if "default_location" in changes and changes["default_location"] is not None:
        changes["default_location"] = dict(changes["default_location"])
    result = await update_preferences(session.user_id, changes)
    if "history_enabled" in changes:
        await set_consent(session.user_id, "history", bool(changes["history_enabled"]))
    if "personalization_enabled" in changes:
        await set_consent(session.user_id, "personalization", bool(changes["personalization_enabled"]))
    if "notification_preferences" in changes:
        await set_consent(
            session.user_id,
            "notifications",
            any(bool(value) for value in changes["notification_preferences"].values()),
        )
    return result


@router.post("/consents/{purpose}")
async def grant_consent(
    purpose: str,
    payload: ConsentRequest,
    session: SessionContext = Depends(require_csrf),
) -> dict:
    if purpose not in ALLOWED_CONSENTS:
        raise HTTPException(status_code=404, detail={"code": "consent_purpose_not_found"})
    return await set_consent(session.user_id, purpose, payload.granted)


@router.delete("/consents/{purpose}")
async def withdraw_consent(
    purpose: str,
    session: SessionContext = Depends(require_csrf),
) -> dict:
    if purpose not in ALLOWED_CONSENTS:
        raise HTTPException(status_code=404, detail={"code": "consent_purpose_not_found"})
    return await set_consent(session.user_id, purpose, False)


@router.delete("/history")
async def clear_account_history(
    session: SessionContext = Depends(require_csrf),
) -> dict:
    return {"deleted": await clear_conversations(session.user_id)}


@router.delete("/personalization")
async def reset_personalization(
    session: SessionContext = Depends(require_csrf),
) -> dict:
    await set_consent(session.user_id, "personalization", False)
    return await update_preferences(
        session.user_id,
        {
            "favorite_cuisines": [], "disliked_foods": [],
            "dietary_restrictions": [], "allergies": [],
            "recommendation_preferences": {}, "personalization_enabled": False,
        },
    )
