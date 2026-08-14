from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from backend.config import get_settings
from backend.services.identity import resolve_request_usage_identity
from backend.services.entitlements import resolve_entitlements
from backend.services.rate_limit import burst_limiter
from backend.services.sessions import SessionContext, optional_session
from pydantic import BaseModel, ConfigDict, Field

from backend.services.places import get_top_rated_nearby, resolve_place_ids, verify_dietary_place_ids
from backend.services.usage_limits import (
    DailyQuotaExceeded,
    PLACES_GLOBAL_USAGE_USER_ID,
    UsageReservation,
    rate_limit_headers,
    reserve_daily_quota,
)

router = APIRouter(prefix="/places", tags=["places"])


class PlaceResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_ids: list[str] = Field(min_length=1, max_length=20)


class DietaryEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_ids: list[str] = Field(min_length=1, max_length=20)
    requirements: list[str] = Field(min_length=1, max_length=5)


@router.get("/suggestions")
async def get_suggestions(
    request: Request,
    response: Response,
    lat: float = Query(..., description="Latitude of the user"),
    lng: float = Query(..., description="Longitude of the user"),
    radius: int = Query(5000, ge=100, le=20000, description="Search radius in meters"),
    north: float | None = Query(default=None, ge=-90, le=90),
    south: float | None = Query(default=None, ge=-90, le=90),
    east: float | None = Query(default=None, ge=-180, le=180),
    west: float | None = Query(default=None, ge=-180, le=180),
    session: SessionContext | None = Depends(optional_session),
) -> List[dict]:
    """
    Get a list of high-rated restaurant suggestions near the user.
    """
    supplied_bounds = [north, south, east, west]
    if any(value is not None for value in supplied_bounds) and not all(
        value is not None for value in supplied_bounds
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "incomplete_viewport_bounds"},
        )
    bounds = None
    if all(value is not None for value in supplied_bounds):
        assert north is not None and south is not None
        assert east is not None and west is not None
        if north <= south or east <= west:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_viewport_bounds"},
            )
        bounds = {"north": north, "south": south, "east": east, "west": west}

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
    configured_daily_limit = resolve_entitlements(bool(session))["limits"]["places_per_day"]
    daily_limit = settings.scaled_daily_quota(configured_daily_limit)
    enforce_actor_limit = session is not None or settings.GUEST_USAGE_LIMITS_ENABLED
    try:
        usage = await reserve_daily_quota(
            user_id=usage_user_id,
            token_cost=1,
            daily_limit=daily_limit,
            global_daily_limit=settings.scaled_daily_quota(
                settings.GLOBAL_DAILY_PLACES_LIMIT
            ),
            global_user_id=PLACES_GLOBAL_USAGE_USER_ID,
            namespace="places",
            enforce_actor_limit=enforce_actor_limit,
        )
    except DailyQuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "daily_places_request_quota_exceeded"},
            headers=rate_limit_headers(exc.usage, include_retry_after=True),
        ) from exc
    if enforce_actor_limit:
        for header, value in rate_limit_headers(usage).items():
            response.headers[header] = value

    suggestions = await get_top_rated_nearby(lat, lng, radius, bounds=bounds)
    return suggestions


@router.post("/resolve")
async def resolve_places(
    payload: PlaceResolveRequest,
    request: Request,
    response: Response,
    session: SessionContext | None = Depends(optional_session),
) -> dict:
    settings = get_settings()
    usage_user_id = resolve_request_usage_identity(
        "places", request, response, session.user_id if session else None
    )
    enforce_actor_limit = session is not None or settings.GUEST_USAGE_LIMITS_ENABLED
    try:
        usage = await reserve_daily_quota(
            user_id=usage_user_id,
            token_cost=1,
            daily_limit=settings.scaled_daily_quota(
                resolve_entitlements(bool(session))["limits"]["places_per_day"]
            ),
            global_daily_limit=settings.scaled_daily_quota(settings.GLOBAL_DAILY_PLACES_LIMIT),
            global_user_id=PLACES_GLOBAL_USAGE_USER_ID,
            namespace="places",
            enforce_actor_limit=enforce_actor_limit,
        )
    except DailyQuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "daily_places_request_quota_exceeded"},
            headers=rate_limit_headers(exc.usage, include_retry_after=True),
        ) from exc
    if enforce_actor_limit:
        for header, value in rate_limit_headers(usage).items():
            response.headers[header] = value
    return {"places": await resolve_place_ids(payload.place_ids)}


@router.post("/dietary-evidence")
async def verify_dietary_evidence(
    payload: DietaryEvidenceRequest,
    request: Request,
    response: Response,
    session: SessionContext | None = Depends(optional_session),
) -> dict:
    """Run one user-initiated, bounded official-menu evidence pass."""
    settings = get_settings()
    usage_user_id = resolve_request_usage_identity(
        "places", request, response, session.user_id if session else None
    )
    await burst_limiter.enforce(
        f"places-dietary:{usage_user_id}", limit=5, window_seconds=60,
        code="places_dietary_rate_limited",
    )
    enforce_actor_limit = session is not None or settings.GUEST_USAGE_LIMITS_ENABLED
    try:
        usage = await reserve_daily_quota(
            user_id=usage_user_id,
            token_cost=1,
            daily_limit=settings.scaled_daily_quota(
                resolve_entitlements(bool(session))["limits"]["places_per_day"]
            ),
            global_daily_limit=settings.scaled_daily_quota(settings.GLOBAL_DAILY_PLACES_LIMIT),
            global_user_id=PLACES_GLOBAL_USAGE_USER_ID,
            namespace="places",
            enforce_actor_limit=enforce_actor_limit,
        )
    except DailyQuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "daily_places_request_quota_exceeded"},
            headers=rate_limit_headers(exc.usage, include_retry_after=True),
        ) from exc
    if enforce_actor_limit:
        for header, value in rate_limit_headers(usage).items():
            response.headers[header] = value
    return {"matches": await verify_dietary_place_ids(payload.place_ids, payload.requirements)}
