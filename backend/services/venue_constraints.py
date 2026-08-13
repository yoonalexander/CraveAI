from __future__ import annotations

import re
from typing import Any, Sequence

from backend.services.recommendation_models import CravingIntent, IntentConstraint


_VENUE_ALIASES: dict[str, tuple[str, ...]] = {
    "pub": (
        "pub",
        "gastropub",
        "irish pub",
        "public house",
        "tavern",
        "bar and grill",
        "sports bar",
    ),
    "bar": (
        "bar",
        "pub",
        "gastropub",
        "tavern",
        "sports bar",
        "wine bar",
        "cocktail bar",
        "bar and grill",
    ),
    "cafe": ("cafe", "coffee shop", "coffeehouse"),
    "bakery": ("bakery", "bake shop", "patisserie"),
    "food truck": ("food truck",),
    "diner": ("diner",),
}

_NORMALIZATION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pub", ("gastropub", "irish pub", "public house", "pub")),
    ("bar", ("sports bar", "wine bar", "cocktail bar", "bar food", "bar fare", "bar")),
    ("cafe", ("coffee shop", "coffeehouse", "cafe")),
    ("bakery", ("bake shop", "patisserie", "bakery")),
    ("food truck", ("food truck",)),
    ("diner", ("diner",)),
)


def normalize_venue_constraint(value: str) -> str | None:
    """Return a canonical venue category when text explicitly names one."""
    normalized = _normalize(value)
    for category, phrases in _NORMALIZATION_PATTERNS:
        if any(_contains_phrase(normalized, phrase) for phrase in phrases):
            return category
    return None


def candidate_matches_venue_constraints(
    intent: CravingIntent,
    candidate: dict[str, Any],
) -> bool:
    """Enforce explicit venue requests using provider types or a category-bearing name."""
    hard_includes = [
        item
        for item in intent.constraints
        if item.dimension == "venue"
        and item.polarity == "include"
        and item.strength in {"required", "strong"}
    ]
    hard_excludes = [
        item
        for item in intent.constraints
        if item.dimension == "venue"
        and item.polarity == "exclude"
        and item.strength in {"required", "strong"}
    ]
    if hard_includes and not all(
        _candidate_declares_venue(candidate, item) for item in hard_includes
    ):
        return False
    return not any(
        _candidate_declares_venue(candidate, item) for item in hard_excludes
    )


def matching_venue_constraint_ids(
    intent: CravingIntent,
    candidate: dict[str, Any],
) -> list[str]:
    """Return included venue constraints supported by explicit place metadata."""
    return [
        item.id
        for item in intent.constraints
        if item.dimension == "venue"
        and item.polarity == "include"
        and _candidate_declares_venue(candidate, item)
    ]


def venue_metadata_label(candidate: dict[str, Any]) -> str:
    tags = _clean_values(candidate.get("tags") or [])
    name = str(candidate.get("name") or "").strip()
    if name and tags:
        return f"{name} — {', '.join(tags)}"
    return name or ", ".join(tags) or "Venue metadata"


def _candidate_declares_venue(
    candidate: dict[str, Any],
    constraint: IntentConstraint,
) -> bool:
    category = normalize_venue_constraint(constraint.value)
    if not category:
        return False
    aliases = _VENUE_ALIASES[category]
    tag_text = _normalize(" ".join(_clean_values(candidate.get("tags") or [])))
    if any(_contains_phrase(tag_text, alias) for alias in aliases):
        return True

    name_text = _normalize(str(candidate.get("name") or ""))
    if category == "bar":
        # A bare leading "Bar" can be part of a brand (for example, BarBurrito),
        # so names need to use it as a category or end in it.
        return bool(
            re.search(
                r"\b(?:sports|wine|cocktail) bar\b|\bbar and grill\b|\bbar$|\bpub\b|\bgastropub\b|\btavern\b",
                name_text,
            )
        )
    return any(_contains_phrase(name_text, alias) for alias in aliases)


def _clean_values(values: Sequence[Any]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(_normalize(phrase))}(?!\w)", text))


def _normalize(value: str) -> str:
    normalized = re.sub(r"[-_]+", " ", value.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", normalized)).strip()
