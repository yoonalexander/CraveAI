from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from backend.config import get_settings
from backend.services.identity import resolve_request_usage_identity
from backend.services.rate_limit import burst_limiter
from backend.services.sessions import SessionContext, optional_session
from backend.services.places import get_top_rated_nearby
from backend.services.usage_limits import (
    DailyQuotaExceeded,
    PLACES_GLOBAL_USAGE_USER_ID,
    UsageReservation,
    rate_limit_headers,
    reserve_daily_quota,
)

router = APIRouter(prefix="/places", tags=["places"])


@router.get("/suggestions")
async def get_suggestions(
    request: Request,
    response: Response,
    lat: float = Query(..., description="Latitude of the user"),
    lng: float = Query(..., description="Longitude of the user"),
    radius: int = Query(5000, ge=100, le=20000, description="Search radius in meters"),
    session: SessionContext | None = Depends(optional_session),
) -> List[dict]:
    """
    Get a list of high-rated restaurant suggestions near the user.
    """
    settings = get_settings()
    usage_user_id = resolve_request_usage_identity(
        "places", request, response, session.user_id if session else None
    )
    await burst_limiter.enforce(
        f"places:{usage_user_id}",
        limit=20 if session else 10,
        window_seconds=60,
        code="places_rate_limited",
    )
    daily_limit = (
        settings.ACCOUNT_DAILY_PLACES_LIMIT
        if session
        else settings.GUEST_DAILY_PLACES_LIMIT
    )
    try:
        usage = await reserve_daily_quota(
            user_id=usage_user_id,
            token_cost=1,
            daily_limit=daily_limit,
            global_daily_limit=settings.GLOBAL_DAILY_PLACES_LIMIT,
            global_user_id=PLACES_GLOBAL_USAGE_USER_ID,
            namespace="places",
        )
    except DailyQuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "daily_places_request_quota_exceeded"},
            headers=rate_limit_headers(exc.usage, include_retry_after=True),
        ) from exc
    for header, value in rate_limit_headers(usage).items():
        response.headers[header] = value

    suggestions = await get_top_rated_nearby(lat, lng, radius)
    return suggestions
