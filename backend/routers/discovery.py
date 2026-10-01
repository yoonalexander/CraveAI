import asyncio

from fastapi import APIRouter, Query, Response

from backend.services.discovery import discovery_snapshot

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("/signals")
async def signals(response: Response, lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180)) -> dict:
    # Read-only, bounded database work. Viewing news never calls a paid provider.
    response.headers["Cache-Control"] = "no-store"
    return await asyncio.to_thread(discovery_snapshot, lat, lng)
