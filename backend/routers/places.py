from typing import List

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from backend.config import get_settings
from backend.services.identity import resolve_anonymous_usage_identity
from backend.services.places import get_top_rated_nearby
from backend.services.usage_limits import (
    DailyQuotaExceeded,
    PLACES_GLOBAL_USAGE_USER_ID,
    UsageReservation,
    rate_limit_headers,
    reserve_daily_quota,
)

router = APIRouter(prefix="/places", tags=["places"])
ANONYMOUS_TOKEN_HEADER = "X-CraveAI-Anonymous-Token"


@router.get("/suggestions")
async def get_suggestions(
    request: Request,
    response: Response,
    lat: float = Query(..., description="Latitude of the user"),
    lng: float = Query(..., description="Longitude of the user"),
    radius: int = Query(5000, ge=100, le=20000, description="Search radius in meters"),
) -> List[dict]:
    """
    Get a list of high-rated restaurant suggestions near the user.
    """
    settings = get_settings()
    client_host = request.client.host if request.client else None
    usage_user_id, anonymous_token = resolve_anonymous_usage_identity(
        "places",
        request.headers.get(ANONYMOUS_TOKEN_HEADER),
        client_host,
        settings.IDENTITY_SIGNING_SECRET,
    )
    try:
        usage = await reserve_daily_quota(
            user_id=usage_user_id,
            token_cost=1,
            daily_limit=settings.DAILY_PLACES_REQUEST_LIMIT,
            global_daily_limit=settings.GLOBAL_DAILY_PLACES_REQUEST_LIMIT,
            global_user_id=PLACES_GLOBAL_USAGE_USER_ID,
        )
    except DailyQuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "daily_places_request_quota_exceeded"},
            headers=_places_response_headers(
                exc.usage,
                anonymous_token=anonymous_token,
                include_retry_after=True,
            ),
        ) from exc
    for header, value in _places_response_headers(
        usage,
        anonymous_token=anonymous_token,
    ).items():
        response.headers[header] = value

    suggestions = await get_top_rated_nearby(lat, lng, radius)
    return suggestions


def _places_response_headers(
    usage: UsageReservation,
    *,
    anonymous_token: str | None,
    include_retry_after: bool = False,
) -> dict[str, str]:
    headers = rate_limit_headers(usage, include_retry_after=include_retry_after)
    if anonymous_token:
        headers[ANONYMOUS_TOKEN_HEADER] = anonymous_token
    return headers
