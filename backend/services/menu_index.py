"""Select a representative set of dishes from a restaurant's parsed menus."""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from backend.services.menu_evidence import ParsedPage
from backend.services.menu_markup import MenuPrice

MAX_DISHES_PER_RESTAURANT = 10
MAX_DISHES_PER_FAMILY = 2

# Recognize specific dishes before more general names that can appear in them.
_FAMILY_ALIASES = {
    "spring rolls": ("spring roll", "spring rolls", "cha gio", "goi cuon"),
    "vermicelli bowls": ("vermicelli bowl", "vermicelli bowls", "bun thit nuong"),
    "boat noodles": ("boat noodle", "boat noodles"),
    "pho": ("pho",),
    "banh mi": ("banh mi",),
    "fried rice": ("fried rice", "com chien"),
    "broken rice": ("broken rice", "com tam"),
    "pad thai": ("pad thai", "phad thai"),
    "dosa": ("dosa", "dosai", "dosas"),
    "ramen": ("ramen",),
    "pancakes": ("pancake", "pancakes"),
}
_MENU_CODE = re.compile(r"^(?:[a-z]{1,2}\d{1,3}[a-z]?(?:\s*[-.:)]\s*|\s+)|\d{1,3}[-.:)]\s+)")
_VARIANT = r"(?:chicken|beef|pork|shrimp|tofu|vegetable|veggie|seafood|small|medium|large)"
_LEADING_VARIANTS = re.compile(r"^(?:" + _VARIANT + r" )+")
_TRAILING_VARIANT = re.compile(r" with " + _VARIANT + r"$")


@dataclass(frozen=True)
class IndexedDish:
    name: str
    description: str
    source_url: str
    family: str
    prices: tuple[MenuPrice, ...]


def _dish_key(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char)).strip()
    return " ".join(re.findall(r"[^\W_]+", _MENU_CODE.sub("", folded)))


def _dish_family(key: str) -> str:
    main_name = key.partition(" with ")[0]
    words = f" {main_name} "
    for family, aliases in _FAMILY_ALIASES.items():
        if any(f" {alias} " in words for alias in aliases):
            return family
    base = _LEADING_VARIANTS.sub("", key)
    return _TRAILING_VARIANT.sub("", base) or key


def _evidence_quality(dish: IndexedDish) -> tuple[bool, bool]:
    return bool(dish.prices), bool(dish.description)


def select_menu_index_dishes(pages: Iterable[tuple[str, ParsedPage]]) -> list[IndexedDish]:
    """Read all provided pages for one location, then choose up to ten dishes."""
    unique: dict[str, IndexedDish] = {}
    for url, page in pages:
        for name, description in page.menu_items:
            if (name, description) in page.beverage_items:
                continue
            key = _dish_key(name)
            if not key:
                continue
            candidate = IndexedDish(
                name=name,
                description=description,
                source_url=url,
                family=_dish_family(key),
                prices=page.menu_prices.get(name.casefold(), ()),
            )
            previous = unique.get(key)
            if previous is None or _evidence_quality(candidate) > _evidence_quality(previous):
                unique[key] = candidate

    families: dict[str, list[IndexedDish]] = defaultdict(list)
    for dish in unique.values():
        families[dish.family].append(dish)
    ordered_families = sorted(families.values(), key=len, reverse=True)
    for dishes in ordered_families:
        dishes.sort(key=_evidence_quality, reverse=True)

    if len(ordered_families) > MAX_DISHES_PER_RESTAURANT:
        # Reserve a slot for the most common family, then sample across menu order.
        most_common = ordered_families[0]
        remaining = [dishes for dishes in families.values() if dishes is not most_common]
        slots = MAX_DISHES_PER_RESTAURANT - 1
        return [most_common[0]] + [
            remaining[index * (len(remaining) - 1) // (slots - 1)][0]
            for index in range(slots)
        ]

    selected: list[IndexedDish] = []
    for round_index in range(MAX_DISHES_PER_FAMILY):
        for dishes in ordered_families:
            if round_index < len(dishes):
                selected.append(dishes[round_index])
                if len(selected) == MAX_DISHES_PER_RESTAURANT:
                    return selected
    return selected
