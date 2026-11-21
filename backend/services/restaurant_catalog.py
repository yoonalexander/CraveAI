"""Geographic and named lookup for the Toronto and Mississauga catalog."""
import asyncio
import logging
from math import cos, radians

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.database import get_session_factory
from backend.models import CatalogRestaurant
from backend.services.places import SUGGESTION_POOL_LIMIT

logger = logging.getLogger(__name__)

# Coarse bounds only skip queries far from the pilot. Records are imported from
# the municipal boundaries and every result is filtered to the requested area.
PILOT_BOUNDS = (43.45, -79.85, 43.87, -79.10)
CUISINE_NAMES = {"bbq": "BBQ", "barbecue": "BBQ", "burger": "American",
                 "pizza": "Italian", "sushi": "Japanese"}
CATALOG_SOURCES = {
    "osm:": ("openstreetmap", "OpenStreetMap listing"),
    "toronto-licence:": ("toronto", "Verified Toronto licence listing"),
    "mississauga-directory-2025:": ("mississauga", "Verified Mississauga directory listing"),
}


def is_catalog_place_id(place_id: str) -> bool:
    return place_id.startswith(tuple(CATALOG_SOURCES))


async def find_catalog_restaurants(
    lat: float, lng: float, radius: int, bounds: dict[str, float] | None,
    name: str = "",
) -> list[dict]:
    area_query = catalog_area_query(lat, lng, radius, bounds)
    if area_query is None:
        return []
    query = area_query
    if name:
        query = query.where(CatalogRestaurant.name.icontains(name, autoescape=True))
    query = query.limit(SUGGESTION_POOL_LIMIT)

    def load() -> list[dict]:
        with get_session_factory()() as db:
            return [_suggestion(place) for place in db.scalars(query)]

    try:
        return await asyncio.to_thread(load)
    except SQLAlchemyError:
        logger.warning("Restaurant catalog lookup failed; using the existing discovery provider.")
        return []


def catalog_area_query(lat: float, lng: float, radius: int, bounds: dict[str, float] | None):
    south, west, north, east = PILOT_BOUNDS

    # Local equirectangular distance is appropriate for these short distances
    # near Toronto. Viewport queries use the supplied rectangle directly.
    lng_scale = 111_195 * max(cos(radians(lat)), 0.001)
    lat_delta = radius / 111_195
    lng_delta = radius / lng_scale
    area = bounds or {"south": lat - lat_delta, "north": lat + lat_delta,
                      "west": lng - lng_delta, "east": lng + lng_delta}
    if area["north"] < south or area["south"] > north or area["east"] < west or area["west"] > east:
        return None
    lat_offset = (CatalogRestaurant.lat - lat) * 111_195
    lng_offset = (CatalogRestaurant.lng - lng) * lng_scale
    distance_squared = lat_offset * lat_offset + lng_offset * lng_offset
    query = select(CatalogRestaurant).where(
        CatalogRestaurant.listed.is_(True),
        CatalogRestaurant.lat.between(area["south"], area["north"]),
        CatalogRestaurant.lng.between(area["west"], area["east"]),
    )
    if bounds is None:
        query = query.where(distance_squared <= radius * radius)
    return query.order_by(distance_squared, CatalogRestaurant.id)


async def resolve_catalog_restaurants(ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}

    def load() -> dict[str, dict]:
        with get_session_factory()() as db:
            rows = db.scalars(select(CatalogRestaurant).where(CatalogRestaurant.id.in_(ids)))
            return {place.id: _suggestion(place) for place in rows}

    return await asyncio.to_thread(load)


def _suggestion(place: CatalogRestaurant) -> dict:
    source, reason = next(
        (info for prefix, info in CATALOG_SOURCES.items() if place.id.startswith(prefix)),
        ("openstreetmap", "OpenStreetMap listing"),
    )
    cuisines = list(dict.fromkeys(
        CUISINE_NAMES.get(cuisine, cuisine.replace("_", " ").title())
        for item in place.cuisine.split(";") if (cuisine := item.strip().lower())
    ))
    return {
        "place_id": place.id, "name": place.name, "lat": place.lat, "lng": place.lng,
        "address": place.address, "rating": None, "reason": reason,
        "source": source, "tags": cuisines, "website": place.website or None,
        "checked_on": place.checked_on, "phone": place.phone, "hours": place.hours,
        "cuisine_labels": [{"value": cuisine, "source": source, "evidence": []}
                           for cuisine in cuisines],
    }
