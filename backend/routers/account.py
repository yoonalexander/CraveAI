from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.services.sessions import (
    SessionContext,
    clear_session_cookie,
    delete_application_user,
    require_csrf,
    require_verified_session,
    revoke_user_sessions,
)
from backend.services.storage import audit_event, export_user_data
from backend.services.supabase_auth import SupabaseAuthClient, SupabaseAuthError

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/export")
async def export_account(
    session: SessionContext = Depends(require_verified_session),
) -> dict:
    return await export_user_data(session.user_id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    request: Request,
    response: Response,
    session: SessionContext = Depends(require_csrf),
) -> Response:
    authenticated_at = session.authenticated_at
    if authenticated_at.tzinfo is None:
        authenticated_at = authenticated_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - authenticated_at > timedelta(minutes=10):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "recent_authentication_required"},
        )
    try:
        await revoke_user_sessions(session.user_id)
        await SupabaseAuthClient().delete_user(session.user_id)
        # In test/local databases there is no auth.users cascade.
        await delete_application_user(session.user_id)
    except SupabaseAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code},
        ) from exc
    clear_session_cookie(response)
    await audit_event(
        "account.deleted",
        request_id=getattr(request.state, "request_id", None),
        metadata={"data_deleted": True},
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
