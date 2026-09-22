from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.services.entitlements import (
    has_development_admin_access,
    resolve_entitlements,
)
from backend.services.sessions import SessionContext, require_verified_session

router = APIRouter(tags=["plans"])


def _plans() -> list[dict]:
    guest = resolve_entitlements(False)
    free = resolve_entitlements(True)
    return [
        {"id": "guest", "name": "Guest", "available": True, "price": None,
         "limits": guest["limits"],
         "features": ["Temporary chat", "Map search", "Discovery"]},
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
    is_admin = has_development_admin_access(session.email, session.email_verified)
    if is_admin:
        entitlement = {
            **entitlement,
            "plan": "development_admin",
            "limits": {
                "chats_per_day": None,
                "places_per_day": None,
                "voice_seconds_per_day": None,
            },
        }
    return {
        "user_id": session.user_id,
        "role": "development_admin" if is_admin else "user",
        **entitlement,
    }
