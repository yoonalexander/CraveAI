from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.config import get_settings
from backend.services.entitlements import resolve_entitlements
from backend.services.sessions import SessionContext, require_verified_session

router = APIRouter(tags=["plans"])


def _plans() -> list[dict]:
    settings = get_settings()
    guest = resolve_entitlements(False)
    free = resolve_entitlements(True)
    guest_unmetered = not settings.GUEST_USAGE_LIMITS_ENABLED
    return [
        {"id": "guest", "name": "Guest", "available": True, "price": None,
         "limits": None if guest_unmetered else guest["limits"],
         "features": ["Temporary chat", "Map search", "Discovery"] +
                     (["Unmetered during public testing"] if guest_unmetered else [])},
        {"id": "free", "name": "Free", "available": True, "price": 0,
         "limits": free["limits"],
         "features": ["Collections", "Preferences", "Opt-in History", "Feedback"]},
        {"id": "plus", "name": "Plus", "available": False, "coming_later": True, "price": None, "limits": None,
         "features": ["Limits and pricing will follow cost validation"]},
    ]


@router.get("/plans")
async def plans() -> dict:
    return {"plans": _plans()}


@router.get("/account/entitlements")
async def entitlements(
    session: SessionContext = Depends(require_verified_session),
) -> dict:
    entitlement = resolve_entitlements(True)
    return {
        "user_id": session.user_id, **entitlement,
    }
