from __future__ import annotations

import asyncio
import base64
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update

from backend.config import get_settings
from backend.database import get_session_factory
from backend.models import AppSession, Profile
from backend.services.security import (
    actor_ip_hash,
    decrypt_secret,
    encrypt_secret,
    keyed_hash,
    random_token,
    require_allowed_origin,
    sha256,
)
from backend.services.storage import upsert_profile
from backend.services.supabase_auth import (
    ProviderSession,
    SupabaseAuthClient,
    SupabaseAuthError,
)


@dataclass(frozen=True)
class SessionContext:
    id: str
    user_id: str
    email: str
    email_verified: bool
    access_token: str
    refresh_token: str
    csrf_token: str
    csrf_token_hash: str
    authenticated_at: datetime


async def create_app_session(
    provider: ProviderSession,
    request: Request,
    response: Response,
) -> SessionContext:
    if not provider.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "email_verification_required"},
        )
    await upsert_profile(provider.user_id, provider.email, True)
    now = datetime.now(timezone.utc)
    raw_token = random_token()
    settings = get_settings()
    session_id = str(uuid.uuid4())
    csrf_token = _csrf_token(session_id, now)
    record = AppSession(
        id=session_id,
        token_hash=sha256(raw_token),
        user_id=provider.user_id,
        encrypted_access_token=encrypt_secret(provider.access_token),
        encrypted_refresh_token=encrypt_secret(provider.refresh_token),
        csrf_token_hash=sha256(csrf_token),
        authenticated_at=now,
        created_at=now,
        last_seen_at=now,
        rotated_at=now,
        expires_at=now + timedelta(days=settings.SESSION_IDLE_DAYS),
        absolute_expires_at=now + timedelta(days=settings.SESSION_ABSOLUTE_DAYS),
        revoked_at=None,
        user_agent_hash=sha256(request.headers.get("user-agent", "")) or None,
        ip_prefix_hash=actor_ip_hash(request),
    )

    def _insert() -> None:
        with get_session_factory()() as db:
            db.add(record)
            db.commit()

    await asyncio.to_thread(_insert)
    _set_session_cookie(response, raw_token)
    response.headers["Cache-Control"] = "no-store"
    return SessionContext(
        id=record.id,
        user_id=record.user_id,
        email=provider.email,
        email_verified=True,
        access_token=provider.access_token,
        refresh_token=provider.refresh_token,
        csrf_token=csrf_token,
        csrf_token_hash=record.csrf_token_hash,
        authenticated_at=now,
    )


async def optional_session(request: Request, response: Response) -> SessionContext | None:
    settings = get_settings()
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        return None
    now = datetime.now(timezone.utc)

    def _load() -> tuple[AppSession, Profile] | None:
        with get_session_factory()() as db:
            row = db.scalar(
                select(AppSession).where(AppSession.token_hash == sha256(raw))
            )
            if row is None or row.revoked_at is not None:
                return None
            if _utc(row.expires_at) <= now or _utc(row.absolute_expires_at) <= now:
                row.revoked_at = now
                db.commit()
                return None
            profile = db.get(Profile, row.user_id)
            if profile is None or not profile.email_verified:
                return None
            row.last_seen_at = now
            row.expires_at = min(
                now + timedelta(days=settings.SESSION_IDLE_DAYS),
                _utc(row.absolute_expires_at),
            )
            db.commit()
            db.refresh(row)
            return row, profile

    loaded = await asyncio.to_thread(_load)
    if loaded is None:
        clear_session_cookie(response)
        return None
    row, profile = loaded
    context = _context(row, profile)
    if _access_token_needs_refresh(context.access_token):
        try:
            provider = await SupabaseAuthClient().refresh(context.refresh_token)
            if (
                provider.user_id != context.user_id
                or not provider.email_verified
                or provider.email.lower() != context.email.lower()
            ):
                raise SupabaseAuthError(401, "provider_session_mismatch")
            await _replace_provider_tokens(context.id, provider)
            await upsert_profile(provider.user_id, provider.email, True)
            context = SessionContext(
                id=context.id,
                user_id=provider.user_id,
                email=provider.email,
                email_verified=True,
                access_token=provider.access_token,
                refresh_token=provider.refresh_token,
                csrf_token=context.csrf_token,
                csrf_token_hash=context.csrf_token_hash,
                authenticated_at=context.authenticated_at,
            )
        except SupabaseAuthError:
            await revoke_session(context.id)
            clear_session_cookie(response)
            return None
    if now - _utc(row.rotated_at) >= timedelta(hours=settings.SESSION_ROTATE_HOURS):
        context = await rotate_session(context, request, response)
    return context


async def require_session(
    session: SessionContext | None = Depends(optional_session),
) -> SessionContext:
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required"},
        )
    return session


async def require_verified_session(
    session: SessionContext = Depends(require_session),
) -> SessionContext:
    if not session.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "email_verification_required"},
        )
    return session


async def require_csrf(
    request: Request,
    session: SessionContext = Depends(require_verified_session),
) -> SessionContext:
    require_allowed_origin(request)
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied or not hmac.compare_digest(sha256(supplied), session.csrf_token_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "csrf_validation_failed"},
        )
    return session


async def rotate_session(
    context: SessionContext,
    request: Request,
    response: Response,
) -> SessionContext:
    raw_token = random_token()
    now = datetime.now(timezone.utc)
    settings = get_settings()
    csrf_token = _csrf_token(context.id, now)

    def _rotate() -> AppSession:
        with get_session_factory()() as db:
            row = db.get(AppSession, context.id)
            if row is None or row.revoked_at is not None:
                raise HTTPException(status_code=401, detail={"code": "session_expired"})
            row.token_hash = sha256(raw_token)
            row.csrf_token_hash = sha256(csrf_token)
            row.rotated_at = now
            row.last_seen_at = now
            row.expires_at = min(
                now + timedelta(days=settings.SESSION_IDLE_DAYS),
                _utc(row.absolute_expires_at),
            )
            row.user_agent_hash = sha256(request.headers.get("user-agent", ""))
            row.ip_prefix_hash = actor_ip_hash(request)
            db.commit()
            db.refresh(row)
            return row

    row = await asyncio.to_thread(_rotate)
    _set_session_cookie(response, raw_token)
    profile = Profile(
        user_id=context.user_id,
        email=context.email,
        email_verified=context.email_verified,
        created_at=now,
        updated_at=now,
    )
    return _context(row, profile)


async def revoke_session(session_id: str) -> None:
    now = datetime.now(timezone.utc)

    def _revoke() -> None:
        with get_session_factory()() as db:
            db.execute(
                update(AppSession)
                .where(AppSession.id == session_id, AppSession.revoked_at.is_(None))
                .values(
                    revoked_at=now,
                    encrypted_access_token=encrypt_secret(""),
                    encrypted_refresh_token=encrypt_secret(""),
                )
            )
            db.commit()

    await asyncio.to_thread(_revoke)


async def revoke_user_sessions(user_id: str) -> None:
    now = datetime.now(timezone.utc)

    def _revoke() -> None:
        with get_session_factory()() as db:
            db.execute(
                update(AppSession)
                .where(AppSession.user_id == user_id, AppSession.revoked_at.is_(None))
                .values(
                    revoked_at=now,
                    encrypted_access_token=encrypt_secret(""),
                    encrypted_refresh_token=encrypt_secret(""),
                )
            )
            db.commit()

    await asyncio.to_thread(_revoke)


async def delete_application_user(user_id: str) -> None:
    def _delete() -> None:
        with get_session_factory()() as db:
            db.execute(delete(Profile).where(Profile.user_id == user_id))
            db.commit()

    await asyncio.to_thread(_delete)


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        get_settings().session_cookie_name,
        path="/",
        secure=get_settings().is_production,
        httponly=True,
        samesite="lax",
    )


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.SESSION_ABSOLUTE_DAYS * 86400,
        path="/",
        secure=settings.is_production,
        httponly=True,
        samesite="lax",
    )


def _context(row: AppSession, profile: Profile) -> SessionContext:
    return SessionContext(
        id=row.id,
        user_id=row.user_id,
        email=profile.email,
        email_verified=profile.email_verified,
        access_token=decrypt_secret(row.encrypted_access_token),
        refresh_token=decrypt_secret(row.encrypted_refresh_token),
        csrf_token=_csrf_token(row.id, _utc(row.rotated_at)),
        csrf_token_hash=row.csrf_token_hash,
        authenticated_at=_utc(row.authenticated_at),
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _csrf_token(session_id: str, rotated_at: datetime) -> str:
    return keyed_hash(f"csrf:{session_id}:{_utc(rotated_at).isoformat()}")


async def _replace_provider_tokens(
    session_id: str, provider: ProviderSession
) -> None:
    def _update() -> None:
        with get_session_factory()() as db:
            db.execute(
                update(AppSession)
                .where(AppSession.id == session_id, AppSession.revoked_at.is_(None))
                .values(
                    encrypted_access_token=encrypt_secret(provider.access_token),
                    encrypted_refresh_token=encrypt_secret(provider.refresh_token),
                )
            )
            db.commit()

    await asyncio.to_thread(_update)


def _access_token_needs_refresh(access_token: str) -> bool:
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode()))
        return int(claims["exp"]) <= int(datetime.now(timezone.utc).timestamp()) + 60
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        # Opaque or malformed provider access tokens are refreshed before use.
        return True
