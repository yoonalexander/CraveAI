from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from backend.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()
GOOGLE_PLACES_API_KEY = settings.GOOGLE_API_KEY
DEFAULT_SEARCH_RADIUS_METERS = int(os.getenv("GOOGLE_SEARCH_RADIUS", "5000"))
MAX_PLACES_PER_CUISINE = 5


async def search_nearby_places(
    cuisines: List[str],
    lat: float,
    lng: float,
    radius: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Query the Google Places API for multiple cuisines and merge results.
    """
    if not cuisines:
        return []

    if not GOOGLE_PLACES_API_KEY:
        logger.info("Google Places API key not configured; returning placeholder venues.")
        return _placeholder_places(cuisines, lat, lng)

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        tasks = [
            _query_places_api(client, cuisine, lat=lat, lng=lng, radius=radius)
            for cuisine in cuisines
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    merged: Dict[str, Dict[str, Any]] = {}
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Error during Places API lookup: %s", result)
            continue
        for place in result:
            place_id = place.get("place_id") or f"{place['name']}::{place.get('address')}"
            if place_id not in merged:
                merged[place_id] = place
    return list(merged.values())


async def get_top_rated_nearby(
    lat: float,
    lng: float,
    radius: int = 5000,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Fetch high-rated restaurants near the given location.
    """
    print(f"DEBUG: get_top_rated_nearby called with lat={lat}, lng={lng}")
    if not GOOGLE_PLACES_API_KEY:
        return _placeholder_places(["Local Favorite", "Trending"], lat, lng)[:limit]

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        try:
            candidates = await _fetch_and_filter(
                client,
                lat=lat,
                lng=lng,
                radius=radius,
                min_rating=4.0,
            )
            if not candidates:
                # Retry with a wider net and slightly lower rating threshold.
                wider_radius = min(int(radius * 2), 20000)
                print(
                    f"DEBUG: No candidates in first pass. Retrying with radius={wider_radius} and min_rating=3.5"
                )
                candidates = await _fetch_and_filter(
                    client,
                    lat=lat,
                    lng=lng,
                    radius=wider_radius,
                    min_rating=3.5,
                )

            if not candidates:
                return _placeholder_places(
                    ["Local Favorite", "Trending", "Chef's Pick"], lat, lng
                )[:limit]

            candidates.sort(key=lambda x: x.get("rating", 0), reverse=True)
            return candidates[:limit]

        except Exception as e:
            print(f"DEBUG: Failed to fetch top rated places: {e}")
            return _placeholder_places(["Local Favorite", "Trending"], lat, lng)[:limit]


async def _fetch_and_filter(
    client: httpx.AsyncClient,
    *,
    lat: float,
    lng: float,
    radius: int,
    min_rating: float,
) -> List[Dict[str, Any]]:
    """Fetch nearby restaurants and apply rating filter."""
    params = {
        "key": GOOGLE_PLACES_API_KEY,
        "location": f"{lat},{lng}",
        "radius": radius,
        "type": "restaurant",
    }
    response = await client.get(
        "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
        params=params,
    )
    response.raise_for_status()
    payload = response.json()
    status = payload.get("status")
    results = payload.get("results", [])
    print(
        f"DEBUG: Places status={status}, results={len(results)}, radius={radius}, min_rating={min_rating}"
    )

    if status not in ("OK", "ZERO_RESULTS"):
        print(f"DEBUG: Places error: {status} - {payload.get('error_message')}")
        return []

    candidates: List[Dict[str, Any]] = []
    for item in results:
        rating = item.get("rating")
        if rating and rating >= min_rating:
            candidates.append(_parse_place_item(item, "High rated nearby"))
    return candidates


async def _query_places_api(
    client: httpx.AsyncClient,
    cuisine: str,
    *,
    lat: float,
    lng: float,
    radius: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch nearby restaurants for a single cuisine keyword."""
    params = {
        "key": GOOGLE_PLACES_API_KEY,
        "location": f"{lat},{lng}",
        "radius": radius or DEFAULT_SEARCH_RADIUS_METERS,
        "type": "restaurant",
        "keyword": cuisine,
    }
    response = await client.get(
        "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
        params=params,
    )
    response.raise_for_status()
    payload = response.json()
    candidates: List[Dict[str, Any]] = []
    for item in payload.get("results", [])[:MAX_PLACES_PER_CUISINE]:
        candidates.append(_parse_place_item(item, f"Matches cuisine query '{cuisine}'"))
    return candidates


def _parse_place_item(item: Dict[str, Any], reason: str) -> Dict[str, Any]:
    geometry = item.get("geometry") or {}
    coordinates = geometry.get("location") if isinstance(geometry, dict) else {}
    return {
        "name": item.get("name"),
        "rating": item.get("rating"),
        "address": item.get("vicinity"),
        "reason": reason,
        "place_id": item.get("place_id"),
        "lat": coordinates.get("lat") if isinstance(coordinates, dict) else None,
        "lng": coordinates.get("lng") if isinstance(coordinates, dict) else None,
        "tags": item.get("types", [])[:3], # Extract some tags
        "user_ratings_total": item.get("user_ratings_total"),
    }


def _placeholder_places(cuisines: List[str], lat: Optional[float], lng: Optional[float]) -> List[Dict[str, Any]]:
    """Fallback data used when the external API is not reachable."""
    placeholders: List[Dict[str, Any]] = []
    for i, cuisine in enumerate(cuisines):
        placeholders.append(
            {
                "name": f"Placeholder {cuisine.title()} Spot",
                "rating": 4.5 + (i % 5) * 0.1,
                "address": f"{cuisine.title()} District, Sample City",
                "reason": f"Sample recommendation for {cuisine}",
                "lat": lat or 43.2557,
                "lng": lng or -79.8711,
                "tags": [cuisine, "Local"],
                "user_ratings_total": 100 + i * 10,
            }
        )
    return placeholders
