from typing import List

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from backend.config import get_settings
from backend.services.places import get_top_rated_nearby
from backend.services.usage_limits import (
    DailyQuotaExceeded,
    rate_limit_headers,
    reserve_daily_quota,
    resolve_usage_user_id,
)

router = APIRouter(prefix="/places", tags=["places"])


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
    try:
        usage = await reserve_daily_quota(
            user_id=resolve_usage_user_id(client_host),
            token_cost=settings.PLACES_REQUEST_TOKEN_COST,
            daily_limit=settings.DAILY_TOKEN_LIMIT,
            global_daily_limit=settings.GLOBAL_DAILY_TOKEN_LIMIT,
        )
    except DailyQuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "daily_token_quota_exceeded"},
            headers=rate_limit_headers(exc.usage, include_retry_after=True),
        ) from exc
    for header, value in rate_limit_headers(usage).items():
        response.headers[header] = value

    suggestions = await get_top_rated_nearby(lat, lng, radius)
    return suggestions
