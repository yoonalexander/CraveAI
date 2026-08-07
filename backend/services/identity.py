from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid

from fastapi import Header, HTTPException, Request, Response, status

from backend.config import get_settings
from backend.services.security import actor_ip_hash

MAX_USER_ID_LENGTH = 128
ANONYMOUS_USER_PREFIX = "anon:"
ANONYMOUS_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 180


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


def issue_anonymous_identity_token(
    secret: str,
    *,
    now: int | None = None,
) -> tuple[str, str]:
    """Issue a long-lived signed token for an anonymous browser identity."""
    subject = f"{ANONYMOUS_USER_PREFIX}{uuid.uuid4()}"
    token = issue_identity_token(
        subject,
        secret,
        ttl_seconds=ANONYMOUS_TOKEN_TTL_SECONDS,
        now=now,
    )
    return subject, token


def verify_anonymous_identity_token(
    token: str,
    secret: str,
    *,
    now: int | None = None,
) -> str:
    """Verify an anonymous browser identity token and return its subject."""
    subject = verify_identity_token(token, secret, now=now)
    if not subject.startswith(ANONYMOUS_USER_PREFIX):
        raise ValueError("Identity token is not anonymous.")
    return subject


def resolve_anonymous_usage_identity(
    namespace: str,
    anonymous_token: str | None,
    client_host: str | None,
    signing_secret: str,
) -> tuple[str, str | None]:
    """Resolve a stable signed browser identity for an isolated quota namespace."""
    if not signing_secret:
        return f"{namespace}:ip:{client_host or 'unknown'}", None

    if anonymous_token:
        try:
            anonymous_subject = verify_anonymous_identity_token(
                anonymous_token.strip(),
                signing_secret,
            )
            return f"{namespace}:{anonymous_subject}", anonymous_token.strip()
        except ValueError:
            pass

    anonymous_subject, issued_token = issue_anonymous_identity_token(signing_secret)
    ip_actor = hashlib.sha256((client_host or "unknown").encode()).hexdigest()
    return f"{namespace}:guest-ip:{ip_actor}", issued_token


def resolve_request_usage_identity(
    namespace: str,
    request: Request,
    response: Response,
    user_id: str | None,
) -> str:
    """Resolve quotas to an account or a server-derived network actor.

    The guest cookie improves continuity but is deliberately not the daily quota
    authority, so deleting browser storage cannot reset the allowance.
    """
    if user_id:
        return f"account:{user_id}"
    settings = get_settings()
    raw = request.cookies.get(settings.guest_cookie_name)
    valid = False
    if raw and settings.IDENTITY_SIGNING_SECRET:
        try:
            verify_anonymous_identity_token(raw, settings.IDENTITY_SIGNING_SECRET)
            valid = True
        except ValueError:
            pass
    if not valid and settings.IDENTITY_SIGNING_SECRET:
        _, raw = issue_anonymous_identity_token(settings.IDENTITY_SIGNING_SECRET)
        response.set_cookie(
            settings.guest_cookie_name,
            raw,
            max_age=ANONYMOUS_TOKEN_TTL_SECONDS,
            secure=settings.is_production,
            httponly=True,
            samesite="lax",
            path="/",
        )
    if raw:
        # Compatibility only; the frontend no longer stores this value and the
        # durable quota key is server-derived from the network prefix.
        response.headers["X-CraveAI-Anonymous-Token"] = raw
    return f"guest-ip:{actor_ip_hash(request)}"


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
