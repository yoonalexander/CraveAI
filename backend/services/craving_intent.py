from __future__ import annotations

import logging
import re
from typing import Any

from openai import AsyncOpenAI

from backend.config import get_settings
from backend.services.recommendation_models import (
    CravingIntent,
    IntentConstraint,
    SearchQuerySpec,
)
from backend.services.venue_constraints import normalize_venue_constraint

logger = logging.getLogger(__name__)

MAX_CONSTRAINTS = 10
MAX_CANDIDATE_DISHES = 10
MAX_SEARCH_QUERIES = 4

INTENT_SYSTEM_PROMPT = """
You extract a food craving into independently scoreable constraints.

Strength rules are strict:
- required: only explicit hard language such as "must", "need", "only", "has to",
  allergies, or an unambiguous dietary requirement.
- strong: a direct request such as "I want", "I'm craving", or an unqualified food trait.
- preferred: softened language such as "maybe", "preferably", "ideally", "something like",
  or "kind of".
- weak: a tentative aside that should barely affect ranking.

Use polarity=exclude for "not", "no", "without", "except", and similar exclusions.
Separate taste, texture, temperature, cuisine, dish type, ingredients, diet, health,
price, meal context, and venue type. Use dimension=venue for an establishment category
such as pub, bar, cafe, bakery, food truck, or diner. For example, "pub food" includes a
venue=pub constraint; it is not merely a generic food-style hint. Do not turn filler words
or location words into food constraints.
Every constraint must be explicitly stated by the user or be a direct normalization of
their words. Do not add traits merely implied by a possible dish (for example, do not add
"brothy" just because the user said "soup").

Assign constraint IDs c1, c2, ... in order. Produce two to four concise Google Places
restaurant searches. Each query should combine compatible requested characteristics or
name a plausible dish, not merely a cuisine. Every constraint_ids entry must be one of
the IDs you assigned. Candidate dishes are possibilities, not facts about a restaurant.

Example: "I want something spicy, maybe like a soup" means spicy=strong and
soup=preferred, never required. Suitable searches include "spicy soup", "hot and sour
soup", and "spicy noodle soup".
""".strip()


async def extract_craving_intent(user_query: str) -> CravingIntent:
    """Use schema-constrained extraction, with a safe local fallback."""
    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        return fallback_intent(user_query)

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        max_retries=0,
        timeout=min(settings.CHAT_RANKING_TIMEOUT_SECONDS, 8),
    )
    try:
        completion = await client.chat.completions.parse(
            model=settings.MODEL_NAME,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_query},
            ],
            response_format=CravingIntent,
            max_completion_tokens=900,
            reasoning_effort="minimal",
            verbosity="low",
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("Intent extraction returned no parsed content.")
        return normalize_intent(parsed, user_query)
    except Exception as exc:
        logger.warning("intent_extraction outcome=fallback error=%r", exc)
        return fallback_intent(user_query)


def normalize_intent(intent: CravingIntent, user_query: str) -> CravingIntent:
    """Bound and repair model output before it becomes executable retrieval input."""
    constraints: list[IntentConstraint] = []
    old_to_new: dict[str, str] = {}
    value_to_new: dict[str, str] = {}
    seen: set[tuple[str, str, str]] = set()

    for raw in intent.constraints[:MAX_CONSTRAINTS]:
        value = _clean_text(raw.value, 80)
        if not value:
            continue
        dimension = raw.dimension
        canonical_venue = normalize_venue_constraint(value)
        if canonical_venue:
            dimension = "venue"
            value = canonical_venue
        if raw.strength in {"preferred", "weak"} and not _constraint_grounded(
            value, user_query
        ):
            continue
        key = (dimension, value.lower(), raw.polarity)
        if key in seen:
            continue
        seen.add(key)
        constraint_id = f"c{len(constraints) + 1}"
        old_to_new[raw.id.strip().lower()] = constraint_id
        value_to_new[value.lower()] = constraint_id
        constraints.append(
            IntentConstraint(
                id=constraint_id,
                dimension=dimension,
                value=value,
                polarity=raw.polarity,
                strength=_correct_contextual_strength(raw, user_query),
            )
        )

    if not constraints:
        return fallback_intent(user_query)

    valid_ids = {item.id for item in constraints}
    queries: list[SearchQuerySpec] = []
    seen_queries: set[str] = set()
    for raw in intent.search_queries[:MAX_SEARCH_QUERIES]:
        text = _clean_text(raw.text, 100)
        normalized = text.lower()
        if not text or normalized in seen_queries:
            continue
        mapped_ids: list[str] = []
        for item in raw.constraint_ids:
            key = str(item).strip().lower()
            mapped = old_to_new.get(key) or value_to_new.get(key)
            if mapped and mapped not in mapped_ids:
                mapped_ids.append(mapped)
        if not mapped_ids:
            mapped_ids = _query_constraint_ids(text, constraints)
        if not mapped_ids:
            mapped_ids = [
                item.id
                for item in constraints
                if item.polarity == "include" and item.strength != "weak"
            ]
        mapped_ids = [item for item in mapped_ids if item in valid_ids]
        if not mapped_ids:
            continue
        seen_queries.add(normalized)
        queries.append(SearchQuerySpec(text=text, constraint_ids=mapped_ids))

    candidate_dishes = _unique_clean(intent.candidate_dishes, 100)[
        :MAX_CANDIDATE_DISHES
    ]
    if not queries:
        queries = _fallback_queries(constraints, candidate_dishes, user_query)

    return CravingIntent(
        summary=_clean_text(intent.summary, 180) or _clean_text(user_query, 180),
        constraints=constraints,
        candidate_dishes=candidate_dishes,
        search_queries=queries[:MAX_SEARCH_QUERIES],
    )


def fallback_intent(user_query: str) -> CravingIntent:
    """Conservative extraction for provider/model outages."""
    normalized = _normalize(user_query)
    constraints: list[IntentConstraint] = []

    vocab: dict[str, tuple[str, ...]] = {
        "taste": (
            "spicy",
            "sweet",
            "salty",
            "sour",
            "savory",
            "umami",
            "creamy",
            "cheesy",
        ),
        "texture": ("crispy", "crunchy", "soft", "chewy", "light"),
        "temperature": ("hot", "warm", "cold", "chilled"),
        "dish_type": (
            "soup",
            "noodles",
            "noodle",
            "stew",
            "salad",
            "sushi",
            "pizza",
            "dessert",
            "ramen",
            "pho",
        ),
        "ingredient": (
            "beef",
            "chicken",
            "pork",
            "fish",
            "seafood",
            "tofu",
            "vegetables",
        ),
        "diet": ("vegan", "vegetarian", "halal", "kosher", "gluten free", "keto"),
        "health": ("healthy", "high protein", "low carb"),
        "price": ("cheap", "affordable", "budget"),
        "venue": (
            "pub",
            "gastropub",
            "bar",
            "cafe",
            "bakery",
            "food truck",
            "diner",
        ),
    }
    soft_markers = ("maybe", "preferably", "ideally", "kind of", "something like")
    hard_markers = ("must", "need", "only", "have to", "has to")

    for dimension, values in vocab.items():
        for value in values:
            match = re.search(rf"(?<!\w){re.escape(value)}(?!\w)", normalized)
            if not match:
                continue
            prefix = normalized[max(0, match.start() - 28) : match.start()]
            polarity = (
                "exclude"
                if re.search(r"(?:\bnot\b|\bno\b|\bwithout\b|\bexcept\b)\s+\w*\s*$", prefix)
                else "include"
            )
            hard_position = _last_marker_position(prefix, hard_markers)
            soft_position = _last_marker_position(prefix, soft_markers)
            if polarity == "exclude" or dimension == "diet":
                strength = "required"
            elif hard_position > soft_position:
                strength = "required"
            elif soft_position >= 0:
                strength = "preferred"
            else:
                strength = "strong"
            constraints.append(
                IntentConstraint(
                    id=f"c{len(constraints) + 1}",
                    dimension=dimension,  # type: ignore[arg-type]
                    value=value,
                    polarity=polarity,
                    strength=strength,  # type: ignore[arg-type]
                )
            )

    if not constraints:
        constraints.append(
            IntentConstraint(
                id="c1",
                dimension="other",
                value=_clean_text(normalized, 100) or "restaurant",
                polarity="include",
                strength="strong",
            )
        )

    return CravingIntent(
        summary=_clean_text(user_query, 180),
        constraints=constraints,
        candidate_dishes=[],
        search_queries=_fallback_queries(constraints, [], user_query),
    )


def _correct_contextual_strength(
    constraint: IntentConstraint,
    user_query: str,
) -> str:
    """Deterministically enforce explicit hedges the model occasionally misses."""
    normalized = _normalize(user_query)
    value = _normalize(constraint.value)
    match = re.search(rf"(?<!\w){re.escape(value)}(?!\w)", normalized)
    if not match:
        return constraint.strength
    prefix = normalized[max(0, match.start() - 35) : match.start()]
    soft_markers = ("maybe", "preferably", "ideally", "kind of", "something like")
    hard_markers = ("must", "need", "only", "have to", "has to")
    soft_position = _last_marker_position(prefix, soft_markers)
    hard_position = _last_marker_position(prefix, hard_markers)
    if soft_position > hard_position:
        return "preferred"
    if hard_position >= 0:
        return "required"
    if constraint.strength == "required" and constraint.dimension != "diet":
        return "strong"
    return constraint.strength


def _fallback_queries(
    constraints: list[IntentConstraint],
    candidate_dishes: list[str],
    user_query: str,
) -> list[SearchQuerySpec]:
    included = [
        item
        for item in constraints
        if item.polarity == "include" and item.strength != "weak"
    ]
    combined = " ".join(item.value for item in included[:4]).strip()
    queries: list[SearchQuerySpec] = []
    if combined:
        queries.append(
            SearchQuerySpec(
                text=combined,
                constraint_ids=[item.id for item in included[:4]],
            )
        )
    for dish in candidate_dishes:
        ids = _query_constraint_ids(dish, constraints)
        if ids:
            queries.append(SearchQuerySpec(text=dish, constraint_ids=ids))
        if len(queries) >= MAX_SEARCH_QUERIES:
            break
    if not queries:
        queries.append(
            SearchQuerySpec(
                text=_clean_text(user_query, 100) or "restaurants",
                constraint_ids=[item.id for item in constraints],
            )
        )
    return queries[:MAX_SEARCH_QUERIES]


def _query_constraint_ids(
    text: str,
    constraints: list[IntentConstraint],
) -> list[str]:
    normalized = _normalize(text)
    ids: list[str] = []
    for item in constraints:
        tokens = [token for token in _normalize(item.value).split() if len(token) > 2]
        if tokens and all(token in normalized for token in tokens):
            ids.append(item.id)
    return ids


def _unique_clean(values: list[Any], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_text(str(value), limit)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _constraint_grounded(value: str, user_query: str) -> bool:
    normalized_value = _normalize(value)
    normalized_query = _normalize(user_query)
    tokens = [token for token in normalized_value.split() if len(token) > 2]
    if tokens and all(token in normalized_query for token in tokens):
        return True
    direct_normalizations = {
        "light": ("not too heavy", "not heavy"),
        "affordable": ("cheap", "budget"),
        "low cost": ("cheap", "budget"),
        "warm": ("hot",),
        "cold": ("chilled",),
    }
    return any(
        phrase in normalized_query
        for phrase in direct_normalizations.get(normalized_value, ())
    )


def _last_marker_position(value: str, markers: tuple[str, ...]) -> int:
    return max((value.rfind(marker) for marker in markers), default=-1)


def _clean_text(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", value.lower())).strip()
