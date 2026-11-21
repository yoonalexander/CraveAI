"""Add branch-scoped catalog evidence to the chat retrieval pilot."""
from __future__ import annotations

import asyncio
import logging
from math import cos, radians
import re

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from backend.database import get_session_factory
from backend.models import CatalogDish, CatalogRestaurant
from backend.services.dish_budget import DishBudget, normalize_portion_text
from backend.services.menu_index import _dish_key
from backend.services.recommendation_models import CravingIntent, EvidenceItem, IntentConstraint
from backend.services.restaurant_catalog import _suggestion, catalog_area_query
from backend.services.restaurant_retrieval import _assign_evidence_ids
from backend.services.venue_constraints import (
    candidate_matches_venue_constraints, matching_venue_constraint_ids,
)

logger = logging.getLogger(__name__)
MAX_PILOT_RADIUS = 5_000
MAX_LOCAL_MENU_PLACES = 4
MAX_LOCAL_LISTINGS = 2
MAX_LOCAL_EVIDENCE = 4
_REVIEWABLE_TRAITS = {"dish_type", "ingredient", "taste", "texture", "temperature", "meal"}
_MENU_TERMS = {
    "noodle soup": {"pho", "ramen", "boat noodles", "clear broth"},
    "dumplings": {"gyoza", "wontons"},
    "fritters": {"medu vada", "bonda"},
}


def _tokens_match(value: str, text: str) -> bool:
    key = normalize_portion_text(value)
    if not key:
        return False
    targets = set(key.split())
    words = set(text.split())
    singular = lambda word: word[:-1] if len(word) > 3 and word.endswith("s") else word
    return {singular(word) for word in targets} <= {singular(word) for word in words} or any(
        f" {alias} " in f" {text} " for alias in _MENU_TERMS.get(key, ())
    )


def _is_hard(item: IntentConstraint) -> bool:
    return item.strength in {"required", "strong"}


def _catalog_tags(intent: CravingIntent, place: dict) -> list[str]:
    return matching_venue_constraint_ids(intent, place) + [
        item.id for item in intent.constraints
        if item.dimension == "cuisine" and item.polarity == "include"
        and any(_dish_key(item.value.lower().removesuffix(" cuisine").removesuffix(" food")) == _dish_key(tag)
                for tag in place["tags"])
    ]


def _tag_evidence(place: dict, matched: list[str]) -> dict:
    return EvidenceItem(
        id="pending", kind="restaurant_tag", label=", ".join(place["tags"]) or place["name"],
        detail="Explicit venue or cuisine metadata from the Toronto and Mississauga catalog.",
        quality=0.82, declared_constraint_ids=matched,
    ).model_dump()


def _load_candidates(intent: CravingIntent, area, budget: DishBudget | None) -> list[dict]:
    constraints = [item for item in intent.constraints if item.polarity == "include"]
    food = [item for item in constraints if item.dimension in _REVIEWABLE_TRAITS]
    metadata_only = bool(constraints) and all(item.dimension in {"cuisine", "venue"} for item in constraints)
    hard_exclusion = any(item.polarity == "exclude" and _is_hard(item) and item.dimension != "venue"
                         for item in intent.constraints)
    # Dish names alone cannot establish the absence of an ingredient or allergen.
    if hard_exclusion or (not food and not metadata_only):
        return []

    candidates = {}
    strengths = {}
    with get_session_factory()() as db:
        if food:
            query = area.add_columns(CatalogDish).join(CatalogDish, CatalogRestaurant.id == CatalogDish.restaurant_id)
            for restaurant, dish in db.execute(query.order_by(CatalogDish.slot).limit(300)):
                place = candidates.get(restaurant.id) or _suggestion(restaurant)
                if not candidate_matches_venue_constraints(intent, place):
                    continue
                label = normalize_portion_text(dish.name)
                evidence = EvidenceItem(
                    id="pending", kind="official_menu", label=dish.name, source_url=dish.source_url,
                    quality=1, prices=dish.prices, price_channel=dish.channel,
                )
                hard_food = [item for item in constraints if _is_hard(item)
                             and item.dimension not in {"price", "cuisine", "venue"}]
                def matches_food(text: str) -> bool:
                    return all(
                        item.dimension in _REVIEWABLE_TRAITS | {"other"} and _tokens_match(item.value, text)
                        for item in hard_food
                    ) and any(_tokens_match(item.value, text) for item in food)

                evidence_labels = [label] if matches_food(label) else []
                if budget:
                    evidence.prices = [
                        price for price in evidence.prices
                        if budget.accepts(price, dish.name, dish.channel)
                        and matches_food(normalize_portion_text(f"{dish.name} {price.option or ''}"))
                    ]
                    evidence_labels = [
                        normalize_portion_text(f"{dish.name} {price.option or ''}") for price in evidence.prices
                    ]
                matched = next((
                    [item.id for item in constraints if item.dimension in _REVIEWABLE_TRAITS | {"other"}
                     and _tokens_match(item.value, text)]
                    for text in evidence_labels
                ), [])
                if not matched:
                    continue
                evidence.declared_constraint_ids = matched
                items = place.setdefault("evidence", [])
                if len(items) < MAX_LOCAL_EVIDENCE:
                    items.append(evidence.model_dump())
                    candidates[restaurant.id] = place
                    strengths[restaurant.id] = max(strengths.get(restaurant.id, 0), len(matched))
            for place in candidates.values():
                matched = _catalog_tags(intent, place)
                if matched:
                    place["evidence"].append(_tag_evidence(place, matched))
            return sorted(candidates.values(), key=lambda place: strengths[place["place_id"]], reverse=True)

        if budget:
            return []
        cuisines = [item for item in constraints if item.dimension == "cuisine"]
        # Use explicit catalog tags only, with exact comparison after the SQL prefilter.
        query = area
        if cuisines:
            query = query.where(or_(*(
                CatalogRestaurant.cuisine.icontains(item.value.split()[0], autoescape=True)
                for item in cuisines if item.value.split()
            )))
        for restaurant in db.scalars(query.limit(100)):
            place = _suggestion(restaurant)
            if not candidate_matches_venue_constraints(intent, place):
                continue
            matched = _catalog_tags(intent, place)
            if not matched or any(_is_hard(item) and item.id not in matched for item in constraints):
                continue
            place["evidence"] = [_tag_evidence(place, matched)]
            candidates[restaurant.id] = place
            if len(candidates) == MAX_LOCAL_LISTINGS:
                break
    return list(candidates.values())


async def find_chat_catalog_candidates(
    intent: CravingIntent, lat: float, lng: float, radius: int, bounds: dict | None,
    budget: DishBudget | None,
) -> list[dict]:
    if radius > MAX_PILOT_RADIUS:
        return []
    if bounds and (
        bounds["north"] - bounds["south"] > 0.13 or bounds["east"] - bounds["west"] > 0.18
    ):
        return []
    query = catalog_area_query(lat, lng, radius, bounds)
    if query is None:
        return []
    try:
        return await asyncio.wait_for(asyncio.to_thread(_load_candidates, intent, query, budget), 2)
    except (SQLAlchemyError, TimeoutError):
        logger.warning("chat_catalog outcome=unavailable")
        return []


def _matches_branch(local: dict, provider: dict) -> bool:
    if local["place_id"] == provider.get("place_id"):
        return True
    name = _dish_key(local["name"])
    if name != _dish_key(str(provider.get("name") or "")):
        return False
    numbers = [re.match(r"\s*(\d+)\b", item.get("address") or "") for item in (local, provider)]
    if all(numbers) and numbers[0][1] != numbers[1][1]:
        return False
    lat, lng = provider.get("lat"), provider.get("lng")
    if not isinstance(lat, (float, int)) or not isinstance(lng, (float, int)):
        return False
    return (
        ((local["lat"] - lat) * 111_195) ** 2
        + ((local["lng"] - lng) * 111_195 * cos(radians(lat))) ** 2
        <= 35 ** 2
    )


def merge_catalog_candidates(provider: list[dict], catalog: list[dict]) -> list[dict]:
    combined = [dict(place) for place in provider]
    local_extra = []
    for local in catalog:
        matches = [place for place in combined + local_extra if _matches_branch(local, place)]
        if len(matches) == 1:
            place = matches[0]
            place["evidence"] = [
                *local.get("evidence", ()), *place.get("evidence", ()),
            ]
            _assign_evidence_ids(place)
        elif not matches and len(local_extra) < MAX_LOCAL_MENU_PLACES:
            _assign_evidence_ids(local)
            local_extra.append(local)
    return combined + local_extra
