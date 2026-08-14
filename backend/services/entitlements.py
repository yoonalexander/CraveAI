from __future__ import annotations

from typing import Any

from backend.config import get_settings


def resolve_entitlements(authenticated: bool) -> dict[str, Any]:
    """Single source of truth for current Guest and Free feature access."""
    settings = get_settings()
    if authenticated:
        return {
            "plan": "free",
            "limits": {
                "chats_per_day": settings.ACCOUNT_DAILY_CHAT_LIMIT,
                "places_per_day": settings.ACCOUNT_DAILY_PLACES_LIMIT,
                "voice_seconds_per_day": settings.ACCOUNT_DAILY_VOICE_SECONDS,
            },
            "features": {
                "temporary_chat": True, "map_search": True, "discovery": True,
                "server_saves": True, "collections": True, "preferences": True,
                "history_opt_in": True, "feedback": True, "voice": True,
                "billing": False,
            },
        }
    return {
        "plan": "guest",
        "limits": {
            "chats_per_day": settings.GUEST_DAILY_CHAT_LIMIT,
            "places_per_day": settings.GUEST_DAILY_PLACES_LIMIT,
            "voice_seconds_per_day": settings.GUEST_DAILY_VOICE_SECONDS,
        },
        "features": {
            "temporary_chat": True, "map_search": True, "discovery": True,
            "server_saves": False, "collections": False, "preferences": False,
            "history_opt_in": False, "feedback": False, "voice": True,
            "billing": False,
        },
    }
