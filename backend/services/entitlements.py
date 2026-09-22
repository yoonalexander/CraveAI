from __future__ import annotations

from typing import Any

from backend.config import get_settings

DEVELOPMENT_ADMIN_EMAILS = frozenset(
    {
        "proto95430@gmail.com",
        "alexanderyoon02@gmail.com",
    }
)


def has_development_admin_access(email: str | None, email_verified: bool) -> bool:
    """Grant development access only to an exact, verified account email."""
    if not email_verified or not email:
        return False
    return email.strip().casefold() in DEVELOPMENT_ADMIN_EMAILS


def has_unlimited_usage_access(session: Any) -> bool:
    """True only for a verified development-admin session.

    Used by every metered surface (chat, places, voice) so the admin bypass is
    consistent everywhere. Global provider-cost ceilings still apply.
    """
    if session is None:
        return False
    return has_development_admin_access(
        getattr(session, "email", None),
        bool(getattr(session, "email_verified", False)),
    )


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
