"""Nearby lookup for the OpenStreetMap Toronto and Mississauga pilot."""
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


async def find_catalog_restaurants(
    lat: float, lng: float, radius: int, bounds: dict[str, float] | None,
) -> list[dict]:
    south, west, north, east = PILOT_BOUNDS
    if not (south <= lat <= north and west <= lng <= east):
        return []

    # Local equirectangular distance is appropriate for these short distances
    # near Toronto. Viewport queries use the supplied rectangle directly.
    lng_scale = 111_195 * cos(radians(lat))
    lat_delta = radius / 111_195
    lng_delta = radius / lng_scale
    area = bounds or {"south": lat - lat_delta, "north": lat + lat_delta,
                      "west": lng - lng_delta, "east": lng + lng_delta}
    lat_offset = (CatalogRestaurant.lat - lat) * 111_195
    lng_offset = (CatalogRestaurant.lng - lng) * lng_scale
    distance_squared = lat_offset * lat_offset + lng_offset * lng_offset
    query = select(CatalogRestaurant).where(
        CatalogRestaurant.lat.between(area["south"], area["north"]),
        CatalogRestaurant.lng.between(area["west"], area["east"]),
    )
    if bounds is None:
        query = query.where(distance_squared <= radius * radius)
    query = query.order_by(distance_squared, CatalogRestaurant.id).limit(SUGGESTION_POOL_LIMIT)

    def load() -> list[dict]:
        with get_session_factory()() as db:
            return [_suggestion(place) for place in db.scalars(query)]

    try:
        return await asyncio.to_thread(load)
    except SQLAlchemyError:
        logger.warning("Restaurant catalog lookup failed; using the existing discovery provider.")
        return []


async def resolve_catalog_restaurants(ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}

    def load() -> dict[str, dict]:
        with get_session_factory()() as db:
            rows = db.scalars(select(CatalogRestaurant).where(CatalogRestaurant.id.in_(ids)))
            return {place.id: _suggestion(place) for place in rows}

    return await asyncio.to_thread(load)


def _suggestion(place: CatalogRestaurant) -> dict:
    cuisines = list(dict.fromkeys(
        CUISINE_NAMES.get(cuisine, cuisine.replace("_", " ").title())
        for item in place.cuisine.split(";") if (cuisine := item.strip().lower())
    ))
    return {
        "place_id": place.id, "name": place.name, "lat": place.lat, "lng": place.lng,
        "address": place.address, "rating": None, "reason": "OpenStreetMap listing",
        "source": "openstreetmap", "tags": cuisines, "website": place.website or None,
        "cuisine_labels": [{"value": cuisine, "source": "openstreetmap", "evidence": []}
                           for cuisine in cuisines],
    }
