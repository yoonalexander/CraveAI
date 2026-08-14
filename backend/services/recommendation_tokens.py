from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from backend.config import get_settings


def _secret() -> bytes:
    settings = get_settings()
    value = settings.IDENTITY_SIGNING_SECRET or "craveai-development-recommendation-token"
    return value.encode("utf-8")


def sign_recommendation(
    place_id: str, rank: int, score: float | None, confidence: str | None
) -> str:
    payload = {
        "place_id": place_id,
        "rank": rank,
        "score": score,
        "confidence": confidence,
        "issued_at": int(time.time()),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(_secret(), encoded, hashlib.sha256).digest()
    return (encoded + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode("ascii")


def verify_recommendation(token: str, max_age_seconds: int = 7 * 86400) -> dict[str, Any] | None:
    try:
        encoded, supplied = token.encode("ascii").split(b".", 1)
        expected = base64.urlsafe_b64encode(
            hmac.new(_secret(), encoded, hashlib.sha256).digest()
        ).rstrip(b"=")
        if not hmac.compare_digest(expected, supplied):
            return None
        padding = b"=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        if int(payload.get("issued_at", 0)) < int(time.time()) - max_age_seconds:
            return None
        if not payload.get("place_id"):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
