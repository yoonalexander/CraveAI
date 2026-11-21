"""Verify explicit CAD budgets against a published price for one dish."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from backend.services.menu_index import _dish_key
from backend.services.recommendation_models import PublishedMenuPrice

BUDGET_CONSTRAINT_ID = "verified_dish_budget"
_AMOUNT = r"(?P<currency>CA\$|CAD\b|US\$|USD\b|EUR\b|[$€£])?\s*(?P<amount>\d{1,4}(?:\.\d{1,2})?)(?!\d|[.,]\d)"
_BEFORE = re.compile(
    r"\b(?P<limit>under|less than|below|at most|no more than|up to|within|max(?:imum)?(?: of)?|budget(?: of| is|:)?|not over)\s+"
    + _AMOUNT + r"(?!\s*(?:min(?:ute)?s?|hours?|km|metres?|meters?|people|years?|%|inch(?:es)?|pieces?)\b)", re.I,
)
_AFTER = re.compile(_AMOUNT + r"\s*(?P<limit>or less|or under|at most|max(?:imum)?|budget)\b", re.I)
_FOREIGN = re.compile(r"US\$|€|£|\b(?:euros?|pounds?|USD|EUR|GBP)\b", re.I)
_PORTION = re.compile(
    r"\b(?:\d{1,2}[\s-]*(?:inch(?:es)?|pieces?|pcs)\b|\d{1,2}\s*[\x22″]"
    r"|(?:extra[ -]large|small|medium|large|regular|personal|family[ -]size|party[ -]size|party|xl)\b)", re.I,
)
_PREPARATION = re.compile(r"\b(?:deep[ -]fried|fried|grilled|steamed|vegetarian|veggie|vegetable|vegan)\b", re.I)
_CHANNEL = re.compile(r"\b(?:take[ -]?out|pick[ -]?up|delivery|dine[ -]?in)\b", re.I)
_NUMBER_WORDS = dict(zip(
    ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
     "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen"),
    range(1, 19),
))
_SPELLED_PORTION = re.compile(
    rf"\b({'|'.join(_NUMBER_WORDS)})(?=[\s-]+(?:inch(?:es)?|pieces?|pcs)\b)", re.I,
)


@dataclass(frozen=True)
class DishBudget:
    cents: int
    inclusive: bool
    portion: tuple[str, ...]
    channel: str | None
    supported_currency: bool

    def accepts(self, price: PublishedMenuPrice, dish: str, channel: str | None) -> bool:
        if not self.supported_currency or (self.channel and self.channel != channel):
            return False
        if price.amount_cents > self.cents or (not self.inclusive and price.amount_cents == self.cents):
            return False
        text = f" {normalize_portion_text(f'{dish} {price.option or ''}')} "
        if "large" in self.portion and " extra large " in text:
            return False
        return all(f" {part} " in text for part in self.portion)


def normalize_portion_text(value: str) -> str:
    value = _SPELLED_PORTION.sub(lambda match: str(_NUMBER_WORDS[match[1].lower()]), value)
    value = re.sub(r"(\d)\s*[\x22″]", r"\1 inch", value)
    value = re.sub(r"(\d)(?=inch|pc|piece)", r"\1 ", value, flags=re.I)
    normalized = _dish_key(value)
    normalized = re.sub(r"\b(?:pieces?|pcs)\b", "piece", normalized)
    normalized = re.sub(r"\binches\b", "inch", normalized)
    normalized = re.sub(r"\b(?:veggie|vegetarian)\b", "vegetable", normalized)
    normalized = re.sub(r"\bxl\b", "extra large", normalized)
    return normalized


def parse_dish_budget(request: str) -> DishBudget | None:
    match = _BEFORE.search(request) or _AFTER.search(request)
    if match is None:
        return None
    amount = int(Decimal(match["amount"]) * 100)
    remaining = request[:match.start()] + " " + request[match.end():]
    remaining = _SPELLED_PORTION.sub(lambda word: str(_NUMBER_WORDS[word[1].lower()]), remaining)
    portions = [normalize_portion_text(part.group()) for part in _PORTION.finditer(remaining)]
    portions.extend(normalize_portion_text(part.group()) for part in _PREPARATION.finditer(remaining))
    channel_match = _CHANNEL.search(remaining)
    channel = _dish_key(channel_match.group()).replace(" ", "") if channel_match else None
    channel = {"takeout": "pickup", "dinein": "dine_in"}.get(channel, channel)
    return DishBudget(
        cents=amount,
        inclusive=match["limit"].lower() not in {"under", "less than", "below", "or under"},
        portion=tuple(dict.fromkeys(portions)),
        channel=channel,
        supported_currency=_FOREIGN.search(request) is None,
    )
