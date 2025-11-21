from typing import List, Optional

from fastapi import APIRouter, Query

from backend.services.places import get_top_rated_nearby

router = APIRouter(prefix="/places", tags=["places"])


@router.get("/suggestions")
async def get_suggestions(
    lat: float = Query(..., description="Latitude of the user"),
    lng: float = Query(..., description="Longitude of the user"),
    radius: int = Query(5000, description="Search radius in meters"),
) -> List[dict]:
    """
    Get a list of high-rated restaurant suggestions near the user.
    """
    suggestions = await get_top_rated_nearby(lat, lng, radius)
    return suggestions
