from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Sequence

import httpx

from backend.config import get_settings
from backend.services.places import is_coordinate_in_bounds, search_nearby_places
from backend.services.recommendation_models import CravingIntent, EvidenceItem
from backend.services.venue_constraints import (
    candidate_matches_venue_constraints,
    matching_venue_constraint_ids,
    venue_metadata_label,
)

logger = logging.getLogger(__name__)

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.types",
        "places.priceLevel",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.businessStatus",
    )
)
MAX_RESULTS_PER_QUERY = 10
MAX_RETRIEVAL_CANDIDATES = 12


async def retrieve_candidate_restaurants(
    intent: CravingIntent,
    location: dict[str, Any],
    session_pool: Sequence[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Retrieve restaurants for dish-oriented queries and attach retrieval evidence."""
    settings = get_settings()
    lat = _number_or_none(location.get("lat"))
    lng = _number_or_none(location.get("lng"))
    if lat is None or lng is None:
        return []

    radius = max(100, min(int(location.get("radius") or 5000), 20000))
    bounds = _validated_bounds(location.get("bounds"))
    queries = intent.search_queries
    live_results: list[list[dict[str, Any]]] = []

    if settings.GOOGLE_API_KEY and queries:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            tasks = [
                _search_text(
                    client,
                    query.text,
                    lat=lat,
                    lng=lng,
                    radius=radius,
                    api_key=settings.GOOGLE_API_KEY,
                    bounds=bounds,
                )
                for query in queries
            ]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        for _query, raw in zip(queries, raw_results):
            if isinstance(raw, Exception):
                logger.warning(
                    "restaurant_retrieval outcome=error error_type=%s",
                    type(raw).__name__,
                )
                live_results.append([])
                continue
            parsed: list[dict[str, Any]] = []
            for rank, place in enumerate(raw, start=1):
                candidate = _parse_text_search_place(place)
                if not candidate:
                    continue
                candidate["evidence"] = [
                    EvidenceItem(
                        id="pending",
                        kind="provider_query",
                        label=query.text,
                        detail=(
                            "Returned by Google Places Text Search for this dish-oriented query."
                        ),
                        source_url=candidate.get("google_maps_uri"),
                        quality=0.55,
                        declared_constraint_ids=query.constraint_ids,
                        retrieval_rank=rank,
                    ).model_dump()
                ]
                candidate["retrieval_score"] = _rank_score(rank)
                parsed.append(candidate)
            live_results.append(parsed)

    merged = _merge_query_results(live_results)
    if not merged:
        merged = await _legacy_provider_fallback(intent, location)

    _merge_relevant_session_pool(merged, session_pool, intent)
    if bounds:
        merged = {
            place_id: candidate
            for place_id, candidate in merged.items()
            if is_coordinate_in_bounds(
                candidate.get("lat"), candidate.get("lng"), bounds
            )
        }
    candidates = [
        candidate
        for candidate in merged.values()
        if candidate_matches_venue_constraints(intent, candidate)
    ]
    candidates.sort(
        key=lambda place: (
            _number(place.get("retrieval_score")),
            _number(place.get("rating")),
            _number(place.get("user_ratings_total")),
        ),
        reverse=True,
    )
    candidates = candidates[:MAX_RETRIEVAL_CANDIDATES]
    for candidate in candidates:
        _attach_venue_metadata_evidence(candidate, intent)
        _assign_evidence_ids(candidate)
    return candidates


async def _search_text(
    client: httpx.AsyncClient,
    query: str,
    *,
    lat: float,
    lng: float,
    radius: int,
    api_key: str,
    bounds: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    if bounds:
        low_lat = bounds["south"]
        low_lng = bounds["west"]
        high_lat = bounds["north"]
        high_lng = bounds["east"]
    else:
        low_lat, low_lng, high_lat, high_lng = _bounding_box(lat, lng, radius)
    payload = {
        "textQuery": query,
        "includedType": "restaurant",
        "strictTypeFiltering": True,
        "maxResultCount": MAX_RESULTS_PER_QUERY,
        "locationRestriction": {
            "rectangle": {
                "low": {"latitude": low_lat, "longitude": low_lng},
                "high": {"latitude": high_lat, "longitude": high_lng},
            }
        },
    }
    response = await client.post(
        PLACES_TEXT_SEARCH_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": PLACES_FIELD_MASK,
        },
        json=payload,
    )
    response.raise_for_status()
    return response.json().get("places", [])


def _validated_bounds(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        bounds = {
            "north": float(value["north"]),
            "south": float(value["south"]),
            "east": float(value["east"]),
            "west": float(value["west"]),
        }
    except (KeyError, TypeError, ValueError):
        return None
    if bounds["north"] <= bounds["south"] or bounds["east"] <= bounds["west"]:
        return None
    return bounds


def _parse_text_search_place(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("businessStatus") in {"CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"}:
        return None
    place_id = str(item.get("id") or "").strip()
    name = str((item.get("displayName") or {}).get("text") or "").strip()
    location = item.get("location") or {}
    lat = _number_or_none(location.get("latitude"))
    lng = _number_or_none(location.get("longitude"))
    if not place_id or not name or lat is None or lng is None:
        return None
    return {
        "place_id": place_id,
        "name": name,
        "rating": item.get("rating"),
        "user_ratings_total": item.get("userRatingCount"),
        "address": item.get("formattedAddress"),
        "lat": lat,
        "lng": lng,
        "tags": _clean_provider_types(item.get("types") or []),
        "price_level": item.get("priceLevel"),
        "website": item.get("websiteUri"),
        "google_maps_uri": item.get("googleMapsUri"),
    }


def _merge_query_results(
    result_sets: Sequence[Sequence[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for result_set in result_sets:
        for candidate in result_set:
            place_id = candidate["place_id"]
            if place_id not in merged:
                merged[place_id] = dict(candidate)
                merged[place_id]["evidence"] = list(candidate.get("evidence", []))
                continue
            current = merged[place_id]
            current["retrieval_score"] = _number(current.get("retrieval_score")) + _number(
                candidate.get("retrieval_score")
            )
            current["evidence"].extend(candidate.get("evidence", []))
            if not current.get("website") and candidate.get("website"):
                current["website"] = candidate["website"]
    return merged


async def _legacy_provider_fallback(
    intent: CravingIntent,
    location: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Keep availability during a Places New rollout without claiming menu evidence."""
    lat = _number_or_none(location.get("lat"))
    lng = _number_or_none(location.get("lng"))
    if lat is None or lng is None:
        return {}
    terms = [item.text for item in intent.search_queries[:3]]
    try:
        places = await search_nearby_places(
            terms,
            lat=lat,
            lng=lng,
            radius=location.get("radius"),
        )
    except Exception as exc:
        logger.warning(
            "restaurant_retrieval legacy_fallback outcome=error error_type=%s",
            type(exc).__name__,
        )
        return {}

    merged: dict[str, dict[str, Any]] = {}
    for place in places:
        place_id = str(place.get("place_id") or "").strip()
        if not place_id or place_id.startswith("placeholder-"):
            continue
        candidate = dict(place)
        candidate["retrieval_score"] = 0.25
        candidate["evidence"] = []
        merged[place_id] = candidate
    return merged


def _merge_relevant_session_pool(
    merged: dict[str, dict[str, Any]],
    session_pool: Sequence[dict[str, Any]],
    intent: CravingIntent,
) -> None:
    """Use the browser pool only when its explicit name/tags support a constraint."""
    constraints = {item.id: item for item in intent.constraints}
    for place in session_pool:
        place_id = str(place.get("place_id") or "").strip()
        if not place_id or place_id in merged:
            continue
        text = " ".join(
            [str(place.get("name") or ""), *map(str, place.get("tags") or [])]
        ).lower()
        matched = [
            item.id
            for item in constraints.values()
            if item.dimension in {"cuisine", "dish_type", "diet", "venue"}
            and item.polarity == "include"
            and all(token in text for token in item.value.lower().split())
        ]
        if not matched:
            continue
        candidate = dict(place)
        candidate["retrieval_score"] = 0.2
        candidate["evidence"] = [
            EvidenceItem(
                id="pending",
                kind="restaurant_tag",
                label=", ".join(map(str, place.get("tags") or [])) or place.get("name"),
                detail="Explicit restaurant name/type metadata from the nearby session pool.",
                quality=0.35,
                declared_constraint_ids=matched,
            ).model_dump()
        ]
        merged[place_id] = candidate


def _assign_evidence_ids(candidate: dict[str, Any]) -> None:
    place_id = candidate.get("place_id") or "place"
    for index, evidence in enumerate(candidate.get("evidence") or [], start=1):
        evidence["id"] = f"{place_id}:e{index}"


def _attach_venue_metadata_evidence(
    candidate: dict[str, Any],
    intent: CravingIntent,
) -> None:
    constraint_ids = matching_venue_constraint_ids(intent, candidate)
    if not constraint_ids:
        return
    candidate.setdefault("evidence", []).append(
        EvidenceItem(
            id="pending",
            kind="restaurant_tag",
            label=venue_metadata_label(candidate),
            detail="Explicit venue category from Google Places type or name metadata.",
            quality=0.75,
            declared_constraint_ids=constraint_ids,
        ).model_dump()
    )


def _bounding_box(
    lat: float,
    lng: float,
    radius_meters: int,
) -> tuple[float, float, float, float]:
    lat_delta = radius_meters / 111_320
    longitude_scale = max(math.cos(math.radians(lat)), 0.1)
    lng_delta = radius_meters / (111_320 * longitude_scale)
    return (
        max(-90, lat - lat_delta),
        max(-180, lng - lng_delta),
        min(90, lat + lat_delta),
        min(180, lng + lng_delta),
    )


def _clean_provider_types(values: Sequence[Any]) -> list[str]:
    ignored = {"restaurant", "food", "point_of_interest", "establishment"}
    result: list[str] = []
    for value in values:
        normalized = str(value).strip().lower()
        if not normalized or normalized in ignored:
            continue
        label = normalized.replace("_", " ").title()
        if label not in result:
            result.append(label)
        if len(result) >= 3:
            break
    return result


def _rank_score(rank: int) -> float:
    return 1 / (1 + 0.18 * max(rank - 1, 0))


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _number_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
