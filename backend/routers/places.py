from typing import List
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from backend.config import get_settings
from backend.services.identity import resolve_request_usage_identities
from backend.services.entitlements import has_unlimited_usage_access, resolve_entitlements
from backend.services.rate_limit import burst_limiter
from backend.services.sessions import SessionContext, optional_session
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from backend.services.filter_enrichment import enrich_filter_places

from backend.services.places import DiscoveryCoverage, get_top_rated_nearby, resolve_place_ids, verify_dietary_place_ids
from backend.services.usage_limits import (
    DailyQuotaExceeded,
    PLACES_GLOBAL_USAGE_USER_ID,
    UsageReservation,
    rate_limit_headers,
    reserve_daily_quota,
)

router = APIRouter(prefix="/places", tags=["places"])
PlaceId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9_-]{1,256}$")]


class PlaceResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_ids: list[str] = Field(min_length=1, max_length=20)


class DietaryEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_ids: list[PlaceId] = Field(min_length=1, max_length=10)
    requirements: list[str] = Field(min_length=1, max_length=5)


class FilterEnrichmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place_ids: list[PlaceId] = Field(min_length=1, max_length=10)


@router.post("/filter-data")
async def filter_data(
    payload: FilterEnrichmentRequest, request: Request, response: Response,
    session: SessionContext | None = Depends(optional_session),
) -> dict:
    settings = get_settings()
    if not settings.GOOGLE_API_KEY:
        raise HTTPException(status_code=503, detail={"code": "places_provider_unavailable"})
    ids = list(dict.fromkeys(payload.place_ids))
    identities = resolve_request_usage_identities("places", request, response, session.user_id if session else None)
    await burst_limiter.enforce(f"places-filter:{identities[0]}", limit=5, window_seconds=60, code="places_filter_rate_limited")
    enforce_actor_limit = not has_unlimited_usage_access(session)
    try:
        # Reserve one unit for every actual Details call, before any paid work.
        usage = await reserve_daily_quota(
            user_id=identities[0], token_cost=len(ids),
            daily_limit=resolve_entitlements(bool(session))["limits"]["places_per_day"],
            global_daily_limit=settings.GLOBAL_DAILY_PLACES_LIMIT,
            global_user_id=PLACES_GLOBAL_USAGE_USER_ID, namespace="places",
            enforce_actor_limit=enforce_actor_limit, additional_user_ids=identities[1:],
        )
    except DailyQuotaExceeded as exc:
        raise HTTPException(status_code=429, detail={"code": "daily_places_request_quota_exceeded"},
                            headers=rate_limit_headers(exc.usage, include_retry_after=True)) from exc
    if enforce_actor_limit:
        for header, value in rate_limit_headers(usage).items():
            response.headers[header] = value
    response.headers["Cache-Control"] = "no-store"
    return {"places": await enrich_filter_places(ids)}


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
    Get nearby restaurant suggestions within the confirmed search area.
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
    usage_identities = resolve_request_usage_identities(
        "places", request, response, session.user_id if session else None
    )
    usage_user_id = usage_identities[0]
    await burst_limiter.enforce(
        f"places:{usage_user_id}",
        limit=20 if session else 10,
        window_seconds=60,
        code="places_rate_limited",
    )
    configured_daily_limit = resolve_entitlements(bool(session))["limits"]["places_per_day"]
    daily_limit = configured_daily_limit
    enforce_actor_limit = not has_unlimited_usage_access(session)
    try:
        usage = await reserve_daily_quota(
            user_id=usage_user_id,
            token_cost=1,
            daily_limit=daily_limit,
            global_daily_limit=settings.GLOBAL_DAILY_PLACES_LIMIT,
            global_user_id=PLACES_GLOBAL_USAGE_USER_ID,
            namespace="places",
            enforce_actor_limit=enforce_actor_limit,
            additional_user_ids=usage_identities[1:],
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

    coverage = DiscoveryCoverage()
    first_request = True

    async def before_provider_request() -> None:
        nonlocal first_request, usage
        if first_request:
            first_request = False
            return  # The initial request was reserved above.
        try:
            usage = await reserve_daily_quota(
                user_id=usage_user_id,
                token_cost=1,
                daily_limit=daily_limit,
                global_daily_limit=settings.GLOBAL_DAILY_PLACES_LIMIT,
                global_user_id=PLACES_GLOBAL_USAGE_USER_ID,
                namespace="places",
                enforce_actor_limit=enforce_actor_limit,
                additional_user_ids=usage_identities[1:],
            )
        except DailyQuotaExceeded as exc:
            # Keep already loaded pages; let the client explain why coverage is limited.
            for header, value in rate_limit_headers(exc.usage).items():
                response.headers[header] = value
            raise
        if enforce_actor_limit:
            for header, value in rate_limit_headers(usage).items():
                response.headers[header] = value

    try:
        suggestions = await get_top_rated_nearby(
            lat, lng, radius, bounds=bounds,
            before_request=before_provider_request, coverage=coverage,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"code": "places_provider_unavailable"}) from exc
    response.headers["X-Places-Coverage"] = coverage.partial_reason or "complete"
    response.headers["X-Places-Requests"] = str(coverage.provider_requests)
    response.headers["X-Places-Pages"] = str(coverage.pages_loaded)
    response.headers["Cache-Control"] = "no-store"
    return suggestions


@router.post("/resolve")
async def resolve_places(
    payload: PlaceResolveRequest,
    request: Request,
    response: Response,
    session: SessionContext | None = Depends(optional_session),
) -> dict:
    settings = get_settings()
    usage_identities = resolve_request_usage_identities(
        "places", request, response, session.user_id if session else None
    )
    usage_user_id = usage_identities[0]
    enforce_actor_limit = not has_unlimited_usage_access(session)
    try:
        usage = await reserve_daily_quota(
            user_id=usage_user_id,
            token_cost=1,
            daily_limit=resolve_entitlements(bool(session))["limits"]["places_per_day"],
            global_daily_limit=settings.GLOBAL_DAILY_PLACES_LIMIT,
            global_user_id=PLACES_GLOBAL_USAGE_USER_ID,
            namespace="places",
            enforce_actor_limit=enforce_actor_limit,
            additional_user_ids=usage_identities[1:],
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
    usage_identities = resolve_request_usage_identities(
        "places", request, response, session.user_id if session else None
    )
    usage_user_id = usage_identities[0]
    await burst_limiter.enforce(
        f"places-dietary:{usage_user_id}", limit=5, window_seconds=60,
        code="places_dietary_rate_limited",
    )
    enforce_actor_limit = not has_unlimited_usage_access(session)
    try:
        usage = await reserve_daily_quota(
            user_id=usage_user_id,
            token_cost=len(set(item.strip() for item in payload.place_ids if item.strip())),
            daily_limit=resolve_entitlements(bool(session))["limits"]["places_per_day"],
            global_daily_limit=settings.GLOBAL_DAILY_PLACES_LIMIT,
            global_user_id=PLACES_GLOBAL_USAGE_USER_ID,
            namespace="places",
            enforce_actor_limit=enforce_actor_limit,
            additional_user_ids=usage_identities[1:],
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
    response.headers["Cache-Control"] = "no-store"
    return {"matches": await verify_dietary_place_ids(payload.place_ids, payload.requirements)}
