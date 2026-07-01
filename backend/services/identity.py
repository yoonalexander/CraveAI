from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import Header, HTTPException, status

from backend.config import get_settings

MAX_USER_ID_LENGTH = 128


def issue_identity_token(
    user_id: str,
    secret: str,
    *,
    ttl_seconds: int = 3600,
    now: int | None = None,
) -> str:
    """Create a compact signed subject token for a trusted auth issuer."""
    normalized = _normalize_user_id(user_id)
    if not secret:
        raise ValueError("Identity signing secret is required.")
    if ttl_seconds <= 0:
        raise ValueError("Identity token lifetime must be positive.")
    expires_at = (now if now is not None else int(time.time())) + ttl_seconds
    payload = f"{normalized}\n{expires_at}"
    encoded_payload = (
        base64.urlsafe_b64encode(payload.encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    signature = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded_payload}.{signature}"


def verify_identity_token(token: str, secret: str, *, now: int | None = None) -> str:
    """Verify a signed subject token and return its normalized user id."""
    if not secret:
        raise ValueError("Identity signing secret is required.")
    try:
        encoded_payload, supplied_signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed identity token.") from exc

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise ValueError("Invalid identity token signature.")

    padding = "=" * (-len(encoded_payload) % 4)
    try:
        decoded = base64.b64decode(
            encoded_payload + padding,
            altchars=b"-_",
            validate=True,
        ).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Malformed identity token subject.") from exc
    try:
        user_id, expires_at_raw = decoded.rsplit("\n", 1)
        expires_at = int(expires_at_raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("Malformed identity token payload.") from exc
    if expires_at <= (now if now is not None else int(time.time())):
        raise ValueError("Identity token has expired.")
    return _normalize_user_id(user_id)


async def require_user_identity(authorization: str | None = Header(default=None)) -> str:
    """Require a trusted issuer's signed bearer token."""
    secret = get_settings().IDENTITY_SIGNING_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "identity_auth_unconfigured"},
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "identity_token_required"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return verify_identity_token(authorization.removeprefix("Bearer ").strip(), secret)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_identity_token"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _normalize_user_id(user_id: str) -> str:
    normalized = user_id.strip()
    if not normalized or len(normalized) > MAX_USER_ID_LENGTH:
        raise ValueError("User id must contain 1 to 128 characters.")
    return normalized
