from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from backend.config import get_settings
from backend.services.auth_transactions import create_transaction, consume_transaction
from backend.services.rate_limit import burst_limiter
from backend.services.security import (
    actor_ip_hash,
    require_allowed_origin,
    safe_next_path,
    sha256,
)
from backend.services.sessions import (
    SessionContext,
    clear_session_cookie,
    create_app_session,
    optional_session,
    require_csrf,
    require_verified_session,
    revoke_session,
    revoke_user_sessions,
)
from backend.services.storage import (
    audit_event,
    find_profile_by_email,
    has_account_identity,
    remove_account_identity,
    sync_account_identities,
)
from backend.services.product_data import (
    has_current_policy_acceptance,
    record_policy_acceptance,
)
from backend.services.supabase_auth import (
    ProviderSession,
    SupabaseAuthClient,
    SupabaseAuthError,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
AUTH_TRANSACTION_COOKIE = "craveai_auth_transaction"
RECOVERY_TRANSACTION_COOKIE = "craveai_recovery_transaction"


class EmailPasswordRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class RegistrationRequest(EmailPasswordRequest):
    terms_version: str = Field(min_length=1, max_length=32)
    privacy_version: str = Field(min_length=1, max_length=32)
    accept_terms: bool
    acknowledge_privacy: bool
    age_confirmed: bool


class EmailRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    user_id: str
    email: EmailStr
    email_verified: bool
    policy_required: bool = False


class AuthResponse(BaseModel):
    user: UserResponse


class StatusResponse(BaseModel):
    status: str


class CsrfResponse(BaseModel):
    csrf_token: str


class IdentityResponse(BaseModel):
    id: str
    provider: str
    email: str | None = None


class LinkResponse(BaseModel):
    authorization_url: str


@router.post("/register", response_model=StatusResponse, status_code=status.HTTP_202_ACCEPTED)
async def register(payload: RegistrationRequest, request: Request) -> StatusResponse:
    require_allowed_origin(request)
    await _auth_burst(request, "register")
    settings = get_settings()
    if (
        payload.terms_version != settings.TERMS_VERSION
        or payload.privacy_version != settings.PRIVACY_VERSION
    ):
        raise HTTPException(status_code=409, detail={"code": "policy_version_changed"})
    if not (payload.accept_terms and payload.acknowledge_privacy and payload.age_confirmed):
        raise HTTPException(status_code=422, detail={"code": "policy_acceptance_required"})
    try:
        await SupabaseAuthClient().register(
            str(payload.email).lower(),
            payload.password,
            f"{settings.PUBLIC_API_URL}/auth/confirm",
            {
                "craveai_terms_version": payload.terms_version,
                "craveai_privacy_version": payload.privacy_version,
                "craveai_age_confirmed": True,
            },
        )
    except SupabaseAuthError as exc:
        if exc.status_code >= 500:
            raise _auth_http_error(exc) from exc
        # Deliberately do not reveal whether the email is already registered.
    await audit_event("auth.registration_requested", request_id=_request_id(request))
    return StatusResponse(status="verification_email_sent")


@router.get("/confirm")
async def confirm_email(
    request: Request,
    token_hash: str = Query(min_length=20, max_length=2048),
    type: Literal["signup", "email", "email_change"] = Query(default="email"),
) -> RedirectResponse:
    settings = get_settings()
    redirect = RedirectResponse(
        f"{settings.FRONTEND_ORIGIN}/auth/result?status=verification_failed",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    try:
        provider = await SupabaseAuthClient().verify_otp(token_hash, type)
        if provider is None:
            return redirect
        redirect = RedirectResponse(
            f"{settings.FRONTEND_ORIGIN}/auth/result?status=verified",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        await create_app_session(provider, request, redirect)
        await sync_account_identities(provider.user_id, provider.identities)
        metadata = provider.user_metadata
        if metadata.get("craveai_age_confirmed") is True:
            await record_policy_acceptance(
                provider.user_id,
                str(metadata.get("craveai_terms_version") or settings.TERMS_VERSION),
                str(metadata.get("craveai_privacy_version") or settings.PRIVACY_VERSION),
                True,
            )
        await audit_event(
            "auth.email_verified", user_id=provider.user_id, request_id=_request_id(request)
        )
        return redirect
    except (SupabaseAuthError, HTTPException):
        return redirect


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: EmailPasswordRequest, request: Request, response: Response
) -> AuthResponse:
    require_allowed_origin(request)
    await _auth_burst(request, "login")
    try:
        provider = await SupabaseAuthClient().password_login(
            str(payload.email).lower(), payload.password
        )
        session = await create_app_session(provider, request, response)
        await sync_account_identities(provider.user_id, provider.identities)
    except SupabaseAuthError as exc:
        await audit_event("auth.login_failed", request_id=_request_id(request))
        if exc.status_code >= 500:
            raise _auth_http_error(exc) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials"},
        ) from exc
    await audit_event(
        "auth.login_succeeded",
        user_id=session.user_id,
        session_id=session.id,
        request_id=_request_id(request),
    )
    return AuthResponse(user=await _user_response(session))


@router.post("/logout", response_model=StatusResponse)
async def logout(
    response: Response,
    request: Request,
    session: SessionContext = Depends(require_csrf),
) -> StatusResponse:
    try:
        await SupabaseAuthClient().logout(session.access_token, scope="local")
    except SupabaseAuthError:
        # Local revocation is authoritative for the browser session and must
        # still complete during a provider outage.
        pass
    await revoke_session(session.id)
    clear_session_cookie(response)
    await audit_event(
        "auth.logout",
        user_id=session.user_id,
        session_id=session.id,
        request_id=_request_id(request),
    )
    return StatusResponse(status="signed_out")


@router.get("/me", response_model=AuthResponse)
async def me(session: SessionContext = Depends(require_verified_session)) -> AuthResponse:
    return AuthResponse(user=await _user_response(session))


@router.get("/csrf", response_model=CsrfResponse)
async def csrf(session: SessionContext = Depends(require_verified_session)) -> CsrfResponse:
    return CsrfResponse(csrf_token=session.csrf_token)


@router.post(
    "/password/forgot",
    response_model=StatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def forgot_password(payload: EmailRequest, request: Request) -> StatusResponse:
    require_allowed_origin(request)
    await _auth_burst(request, "password-forgot")
    settings = get_settings()
    try:
        await SupabaseAuthClient().send_recovery(
            str(payload.email).lower(),
            f"{settings.PUBLIC_API_URL}/auth/password/recovery",
        )
    except SupabaseAuthError as exc:
        if exc.status_code >= 500:
            raise _auth_http_error(exc) from exc
    await audit_event("auth.recovery_requested", request_id=_request_id(request))
    return StatusResponse(status="recovery_email_sent")


@router.get("/password/recovery")
async def recovery_callback(
    token_hash: str = Query(min_length=20, max_length=2048),
) -> RedirectResponse:
    settings = get_settings()
    failed = f"{settings.FRONTEND_ORIGIN}/auth/result?status=recovery_failed"
    try:
        provider = await SupabaseAuthClient().verify_otp(token_hash, "recovery")
        if provider is None:
            return RedirectResponse(failed, status_code=303)
        raw = await create_transaction(
            kind="password_recovery",
            access_token=provider.access_token,
            user_id=provider.user_id,
            next_path="/reset-password",
        )
    except SupabaseAuthError:
        return RedirectResponse(failed, status_code=303)
    response = RedirectResponse(
        f"{settings.FRONTEND_ORIGIN}/reset-password", status_code=303
    )
    _set_transaction_cookie(response, RECOVERY_TRANSACTION_COOKIE, raw)
    return response


@router.post("/password/reset", response_model=StatusResponse)
async def reset_password(
    payload: PasswordResetRequest, request: Request, response: Response
) -> StatusResponse:
    require_allowed_origin(request)
    raw = request.cookies.get(RECOVERY_TRANSACTION_COOKIE, "")
    transaction = await consume_transaction(raw, {"password_recovery"})
    if transaction is None or not transaction.access_token or not transaction.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "recovery_session_invalid"},
        )
    try:
        await SupabaseAuthClient().update_password(
            transaction.access_token, payload.password
        )
        try:
            await SupabaseAuthClient().logout(
                transaction.access_token, scope="global"
            )
        except SupabaseAuthError:
            pass
    except SupabaseAuthError as exc:
        raise _auth_http_error(exc) from exc
    await revoke_user_sessions(transaction.user_id)
    response.delete_cookie(RECOVERY_TRANSACTION_COOKIE, path="/")
    clear_session_cookie(response)
    await audit_event(
        "auth.password_reset",
        user_id=transaction.user_id,
        request_id=_request_id(request),
    )
    return StatusResponse(status="password_updated")


@router.get("/google/start")
async def google_start(
    request: Request,
    next: str = Query(default="/"),
) -> RedirectResponse:
    await _auth_burst(request, "google-start")
    return await _begin_google(
        request=request,
        kind="google_login",
        next_path=safe_next_path(next),
    )


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str = Query(min_length=8, max_length=4096),
    state: str = Query(min_length=16, max_length=512),
    session: SessionContext | None = Depends(optional_session),
) -> RedirectResponse:
    settings = get_settings()
    raw = request.cookies.get(AUTH_TRANSACTION_COOKIE, "")
    transaction = await consume_transaction(raw, {"google_login", "google_link"})
    failed = f"{settings.FRONTEND_ORIGIN}/auth/result?status=google_failed"
    if (
        transaction is None
        or not transaction.code_verifier
        or not transaction.state_hash
        or not transaction.nonce_hash
        or not secrets.compare_digest(transaction.state_hash, sha256(state))
    ):
        return RedirectResponse(failed, status_code=303)
    try:
        provider = await SupabaseAuthClient().exchange_pkce(
            code, transaction.code_verifier
        )
        if transaction.kind == "google_link":
            if session is None or transaction.user_id != session.user_id:
                return RedirectResponse(failed, status_code=303)
            if provider.user_id != session.user_id:
                return RedirectResponse(
                    f"{settings.FRONTEND_ORIGIN}/auth/result?status=link_mismatch",
                    status_code=303,
                )
            await revoke_user_sessions(session.user_id)
        else:
            existing = await find_profile_by_email(provider.email)
            google_known = (
                await has_account_identity(provider.user_id, "google")
                if existing and existing["user_id"] == provider.user_id
                else False
            )
            if existing and (
                existing["user_id"] != provider.user_id or not google_known
            ):
                google_identity = next(
                    (
                        item
                        for item in provider.identities
                        if item.get("provider") == "google"
                    ),
                    None,
                )
                if google_identity and google_identity.get("id"):
                    await SupabaseAuthClient().unlink_identity(
                        provider.access_token, str(google_identity["id"])
                    )
                return RedirectResponse(
                    f"{settings.FRONTEND_ORIGIN}/auth/result?status=link_required",
                    status_code=303,
                )
        redirect = RedirectResponse(
            f"{settings.FRONTEND_ORIGIN}{transaction.next_path}", status_code=303
        )
        await create_app_session(provider, request, redirect)
        await sync_account_identities(provider.user_id, provider.identities)
        redirect.delete_cookie(AUTH_TRANSACTION_COOKIE, path="/")
        await audit_event(
            "auth.google_linked"
            if transaction.kind == "google_link"
            else "auth.google_login",
            user_id=provider.user_id,
            request_id=_request_id(request),
        )
        return redirect
    except (SupabaseAuthError, HTTPException):
        return RedirectResponse(failed, status_code=303)


@router.get("/identities", response_model=list[IdentityResponse])
async def identities(
    session: SessionContext = Depends(require_verified_session),
) -> list[IdentityResponse]:
    try:
        user = await SupabaseAuthClient().get_user(session.access_token)
    except SupabaseAuthError as exc:
        raise _auth_http_error(exc) from exc
    return [_identity_response(item) for item in user.get("identities") or []]


@router.post("/identities/google/link", response_model=LinkResponse)
async def link_google(
    request: Request,
    response: Response,
    session: SessionContext = Depends(require_csrf),
) -> LinkResponse:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _pkce_challenge(verifier)
    settings = get_settings()
    raw = await create_transaction(
        kind="google_link",
        state=state,
        nonce=nonce,
        code_verifier=verifier,
        user_id=session.user_id,
        next_path="/account?linked=google",
    )
    _set_transaction_cookie(response, AUTH_TRANSACTION_COOKIE, raw)
    try:
        url = await SupabaseAuthClient().identity_link_url(
            access_token=session.access_token,
            redirect_to=f"{settings.PUBLIC_API_URL}/auth/google/callback",
            code_challenge=challenge,
            state=state,
        )
    except SupabaseAuthError as exc:
        raise _auth_http_error(exc) from exc
    # The endpoint response middleware transfers this value to an HttpOnly cookie.
    return LinkResponse(authorization_url=url)


@router.delete("/identities/google", response_model=StatusResponse)
async def unlink_google(
    request: Request,
    identity_id: str = Query(min_length=1, max_length=128),
    session: SessionContext = Depends(require_csrf),
) -> StatusResponse:
    client = SupabaseAuthClient()
    try:
        user = await client.get_user(session.access_token)
        identities = user.get("identities") or []
        target = next(
            (
                item
                for item in identities
                if str(item.get("id")) == identity_id and item.get("provider") == "google"
            ),
            None,
        )
        if target is None:
            raise HTTPException(status_code=404, detail={"code": "identity_not_found"})
        if len(identities) <= 1:
            raise HTTPException(
                status_code=409, detail={"code": "last_identity_cannot_be_removed"}
            )
        await client.unlink_identity(session.access_token, identity_id)
        await remove_account_identity(session.user_id, "google")
    except SupabaseAuthError as exc:
        raise _auth_http_error(exc) from exc
    await audit_event(
        "auth.google_unlinked",
        user_id=session.user_id,
        session_id=session.id,
        request_id=_request_id(request),
    )
    return StatusResponse(status="identity_unlinked")


async def _begin_google(
    *, request: Request, kind: str, next_path: str
) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    raw = await create_transaction(
        kind=kind,
        state=state,
        nonce=nonce,
        code_verifier=verifier,
        next_path=next_path,
    )
    settings = get_settings()
    url = SupabaseAuthClient().oauth_url(
        redirect_to=f"{settings.PUBLIC_API_URL}/auth/google/callback",
        code_challenge=_pkce_challenge(verifier),
        state=state,
    )
    response = RedirectResponse(url, status_code=303)
    _set_transaction_cookie(response, AUTH_TRANSACTION_COOKIE, raw)
    return response


async def _auth_burst(request: Request, operation: str) -> None:
    settings = get_settings()
    await burst_limiter.enforce(
        f"auth:{operation}:{actor_ip_hash(request)}",
        limit=settings.AUTH_BURST_LIMIT,
        window_seconds=300,
        code="authentication_rate_limited",
    )


def _set_transaction_cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(
        name,
        value,
        max_age=600,
        secure=get_settings().is_production,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _pkce_challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )


def _identity_response(item: dict[str, Any]) -> IdentityResponse:
    data = item.get("identity_data") or {}
    return IdentityResponse(
        id=str(item.get("id") or ""),
        provider=str(item.get("provider") or ""),
        email=data.get("email"),
    )


async def _user_response(session: SessionContext) -> UserResponse:
    settings = get_settings()
    accepted = await has_current_policy_acceptance(
        session.user_id, settings.TERMS_VERSION, settings.PRIVACY_VERSION
    )
    return UserResponse(
        user_id=session.user_id,
        email=session.email,
        email_verified=session.email_verified,
        policy_required=not accepted,
    )


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _auth_http_error(exc: SupabaseAuthError) -> HTTPException:
    code = exc.code if exc.status_code >= 500 else "authentication_failed"
    return HTTPException(
        status_code=503 if exc.status_code >= 500 else 400,
        detail={"code": code},
    )
