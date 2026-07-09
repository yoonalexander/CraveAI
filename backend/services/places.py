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

FOOD_PLACE_TYPES = {
    "restaurant",
    "meal_takeaway",
    "meal_delivery",
    "cafe",
    "bakery",
    "bar",
}

NON_RESTAURANT_PLACE_TYPES = {
    "amusement_center",
    "amusement_park",
    "aquarium",
    "art_gallery",
    "bowling_alley",
    "casino",
    "clothing_store",
    "convenience_store",
    "department_store",
    "electronics_store",
    "gym",
    "lodging",
    "movie_theater",
    "museum",
    "night_club",
    "park",
    "shopping_mall",
    "spa",
    "stadium",
    "store",
    "tourist_attraction",
}

FOOD_NAME_HINTS = {
    "bagel",
    "bakery",
    "barbecue",
    "bbq",
    "bistro",
    "burger",
    "burrito",
    "cafe",
    "coffee",
    "deli",
    "grill",
    "izakaya",
    "kebab",
    "noodle",
    "pasta",
    "pizza",
    "ramen",
    "restaurant",
    "ristorante",
    "shawarma",
    "steak",
    "sushi",
    "taco",
    "taqueria",
    "trattoria",
}


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
        if rating and rating >= min_rating and _is_restaurant_candidate(item):
            candidates.append(_parse_place_item(item))
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
        if _is_restaurant_candidate(item):
            candidates.append(_parse_place_item(item, f"Matches cuisine query '{cuisine}'"))
    return candidates


def _is_restaurant_candidate(item: Dict[str, Any]) -> bool:
    """Reject venues where food is incidental to another business category."""
    raw_types = set(item.get("types", []) or [])
    if raw_types & NON_RESTAURANT_PLACE_TYPES:
        return False
    if raw_types & FOOD_PLACE_TYPES:
        return True

    name_lower = (item.get("name") or "").lower()
    return any(hint in name_lower for hint in FOOD_NAME_HINTS)


def _parse_place_item(item: Dict[str, Any], reason_hint: Optional[str] = None) -> Dict[str, Any]:
    geometry = item.get("geometry") or {}
    coordinates = geometry.get("location") if isinstance(geometry, dict) else {}
    rating = item.get("rating")
    total_reviews = item.get("user_ratings_total")
    vicinity = item.get("vicinity")

    reason_parts: List[str] = []
    if reason_hint:
        reason_parts.append(reason_hint)
    if rating:
        reason_parts.append(f"{rating}★")
    if total_reviews:
        reason_parts.append(f"{total_reviews} reviews")
    if vicinity:
        reason_parts.append(vicinity)
    reason = " · ".join(reason_parts) if reason_parts else "Highly rated nearby"

    tags = _clean_tags(item.get("types", []) or [], item.get("name", ""))

    return {
        "name": item.get("name"),
        "rating": rating,
        "address": vicinity,
        "reason": reason,
        "place_id": item.get("place_id"),
        "lat": coordinates.get("lat") if isinstance(coordinates, dict) else None,
        "lng": coordinates.get("lng") if isinstance(coordinates, dict) else None,
        "tags": tags,
        "user_ratings_total": total_reviews,
    }


# Refined override: prefer explicit cuisine types, avoid mislabeling ("Cantina" etc.),
# and only use name-based hints when Google types lack a cuisine.
def _clean_tags(raw_types: List[str], name_str: str) -> List[str]:
    blacklist = {
        "point_of_interest",
        "establishment",
        "food",
        "restaurant",
        *NON_RESTAURANT_PLACE_TYPES,
    }

    cuisine_map = {
        "italian": "Italian",
        "mexican": "Mexican",
        "chinese": "Chinese",
        "japanese": "Japanese",
        "korean": "Korean",
        "thai": "Thai",
        "vietnamese": "Vietnamese",
        "indian": "Indian",
        "greek": "Greek",
        "mediterranean": "Mediterranean",
        "middle_eastern": "Middle Eastern",
        "pizza": "Pizza",
        "sushi": "Sushi",
        "seafood": "Seafood",
        "steakhouse": "Steakhouse",
        "barbecue": "BBQ",
        "bbq": "BBQ",
        "burger": "Burgers",
        "sandwich": "Sandwiches",
        "cafe": "Cafe",
        "bakery": "Bakery",
        "dessert": "Dessert",
        "ice_cream": "Ice Cream",
        "vegan": "Vegan",
        "vegetarian": "Vegetarian",
        "tapas": "Tapas",
        "spanish": "Spanish",
        "french": "French",
        "latin": "Latin",
        "caribbean": "Caribbean",
        "halal": "Halal",
        "kosher": "Kosher",
    }

    general_map = {
        "bar": "Bar",
        "meal_takeaway": "Takeout",
        "meal_delivery": "Delivery",
        "night_club": "Nightlife",
        "brewery": "Brewery",
        "pub": "Pub",
    }

    name_hints = {
        "pizza": "Pizza",
        "pizzeria": "Pizza",
        "trattoria": "Italian",
        "ristorante": "Italian",
        "osteria": "Italian",
        "taqueria": "Mexican",
        "taco": "Mexican",
        "sushi": "Sushi",
        "ramen": "Japanese",
        "izakaya": "Japanese",
        "noodle": "Noodles",
        "kebab": "Middle Eastern",
        "shawarma": "Middle Eastern",
        "bbq": "BBQ",
        "barbecue": "BBQ",
        "steak": "Steakhouse",
        "burger": "Burgers",
        "burrito": "Mexican",
        "deli": "Deli",
        "bagel": "Bakery",
        "bakery": "Bakery",
        "cafe": "Cafe",
        "coffee": "Cafe",
        "brew": "Brewery",
        "tapas": "Tapas",
    }

    tags: List[str] = []
    name_lower = (name_str or "").lower()

    def add_tag(label: str) -> None:
        if label not in tags and len(tags) < 3:
            tags.append(label)

    cuisine_added = False
    for t in raw_types:
        if t in blacklist:
            continue
        if t in cuisine_map:
            add_tag(cuisine_map[t])
            cuisine_added = True

    for t in raw_types:
        if t in blacklist or len(tags) >= 3:
            continue
        if t in general_map:
            add_tag(general_map[t])
        else:
            add_tag(t.replace("_", " ").title())

    if len(tags) < 3 and not cuisine_added and name_lower:
        for needle, label in name_hints.items():
            if needle in name_lower:
                add_tag(label)
                if len(tags) >= 3:
                    break

    return tags


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
