"""Read dish records from recognizable, server-rendered menu layouts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from html.parser import HTMLParser

_VOID = set("area base br col embed hr img input link meta param source track wbr".split())
_SKIP = {"head", "script", "style", "template", "noscript", "svg", "nav", "footer"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_AMOUNT = r"(?P<currency>CA\$|US\$|CAD|USD|\$)?\s*(?P<amount>\d{1,5}(?:\.\d{2})?)"
_DECIMAL_AMOUNT = _AMOUNT.replace(r"(?:\.\d{2})?", r"\.\d{2}")
_PRICE = re.compile(_AMOUNT, re.IGNORECASE)
_PRICED_NAME = re.compile(r"^(.+?)\s*(?:\.\s*){2,}((?:CA|US)?\$\s*\d{1,5}(?:\.\d{2})?)$")
_PORTION = re.compile(r"(?P<size>S|M|L|Small|Medium|Large)\s+" + _AMOUNT, re.IGNORECASE)
_PORTION_NAMES = {"s": "Small", "m": "Medium", "l": "Large"}
_CURRENCIES = {"CA$": "CAD", "CAD": "CAD", "US$": "USD", "USD": "USD"}
_WORDPRESS_BEVERAGE_CATEGORY = re.compile(r"menus_category-(?:cocktails|on-tap|[\w-]+-(?:wine|beer))")
_SPOT_PRICE = re.compile(_AMOUNT + r"(?:\s*/\s*(?P<option>[\w \"'”.-]{1,25}))?", re.IGNORECASE)
_NUTRITION_PRICE = re.compile(
    r"(?<!\S)" + _DECIMAL_AMOUNT + r"\s+\(\s*\d{1,4}\s+cals?\.?\s*\)\s*$", re.IGNORECASE,
)
_PIPE_NAME = re.compile(r"(.+?)\s+\|\s+(" + _AMOUNT + r"|m\.?p\.?)", re.IGNORECASE)
_INLINE_NAME = re.compile(r"(.+?)\s+(" + _AMOUNT + r")")
_MENU_FIELDS = {
    "spot": {"food-item-title": "name", "food-price": "price", "food-item-description": "description"},
    "search_card": {"item-name": "name", "item-price": "price", "item-desc": "description"},
    "squarespace": {"menu-item-title": "name", "menu-item-description": "description",
                    "menu-item-price-top": "price", "menu-item-price-bottom": "price"},
}


@dataclass(frozen=True)
class MenuPrice:
    amount_cents: int
    currency: str | None = None
    option: str | None = None


def _price(match: re.Match[str], option: str | None = None) -> MenuPrice:
    currency = _CURRENCIES.get((match["currency"] or "").upper())
    return MenuPrice(int(Decimal(match["amount"]) * 100), currency, option)


@dataclass
class _Dish:
    layout: str
    values: dict[str, list[str]] = field(default_factory=dict)
    beverage: bool = False

    def prices(self) -> tuple[MenuPrice, ...]:
        values = self.values.get("price", [])
        if self.layout == "wix_grid":
            match = _PRICED_NAME.fullmatch(self.values["name"][0])
            values = [match[2]] if match else []
        if self.layout == "nutrition_list":
            values = self.values.get("description", [])
        if self.layout == "pipe":
            match = _PIPE_NAME.fullmatch(self.values["name"][0])
            values = [match[2]] if match else []
        if self.layout == "inline":
            match = _INLINE_NAME.fullmatch(self.values["name"][0])
            values = [match[2]] if match else []
        prices = []
        for value in values:
            if self.layout == "framer":
                portions = [_PORTION.fullmatch(part.strip()) for part in value.split(",")]
                if len(portions) >= 2 and all(portions):
                    prices.extend(
                        _price(part, _PORTION_NAMES.get(part["size"].lower(), part["size"].title()))
                        for part in portions if part is not None
                    )
            elif self.layout == "spot" and (match := _SPOT_PRICE.fullmatch(value)):
                label = match["option"]
                prices.append(_price(match, label.strip() if label else None))
            elif self.layout == "nutrition_list" and (match := _NUTRITION_PRICE.search(value)):
                prices.append(_price(match))
            elif match := _PRICE.fullmatch(value):
                prices.append(_price(match))
        unique = tuple(dict.fromkeys(prices))
        # Conflicting responsive copies leave the amount for that option unknown.
        return tuple(p for p in unique if sum(other.option == p.option for other in unique) == 1)

    def row(self) -> tuple[str, str] | None:
        names = list(dict.fromkeys(self.values.get("name", [])))
        if len(names) != 1 or len(names[0]) > 180:
            return None
        name = names[0]
        if self.layout == "wix_grid":
            match = _PRICED_NAME.fullmatch(name)
            if not match:
                return None
            descriptions = list(dict.fromkeys(self.values.get("description", [])))
            return match[1].strip(), descriptions[0][:320] if len(descriptions) == 1 else ""

        descriptions = self.values.get("description", [])
        if self.layout == "pipe":
            match = _PIPE_NAME.fullmatch(name)
            if not match or not descriptions:
                return None
            name = match[1]
        if self.layout == "inline":
            match = _INLINE_NAME.fullmatch(name)
            if not match or not descriptions:
                return None
            name = match[1]
        if self.layout == "plento" and re.match(r"^(?:side|add|sub)\b", name, re.I):
            return None
        if self.layout == "ordering_preview" and not descriptions:
            return None
        if self.layout in {"photo_article", "squarespace"} and not descriptions:
            return None
        if self.layout == "nutrition_list":
            if len(descriptions) != 1 or not (match := _NUTRITION_PRICE.search(descriptions[0])):
                return None
            return name, descriptions[0][:match.start()].strip()[:320]
        notes = self.values.get("notes", [])
        options = self.values.get("options", [])
        if self.layout == "framer":
            # Framer emits alternate responsive copies. Keep one description.
            descriptions = [max(descriptions, key=len)] if descriptions else []
            if not descriptions:
                return None
            notes = [note for note in notes if note.casefold() in {"spicy", "contains peanuts"}]
        detail = " · ".join(dict.fromkeys([*descriptions, *options, *notes]))
        return name, detail[:320]


@dataclass
class _Element:
    tag: str
    dish: _Dish | None
    owns_dish: bool
    section: str
    excluded: bool
    beverage_section: bool
    menu_column: bool
    capture: str = ""
    text: list[str] = field(default_factory=list)


class MenuMarkupParser(HTMLParser):
    def __init__(self, *, menu_context: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.menu_context = menu_context
        self.stack: list[_Element] = []
        self.items: list[tuple[str, str]] = []
        self.beverage_items: set[tuple[str, str]] = set()
        self.prices: dict[str, tuple[MenuPrice, ...]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        parent = self.stack[-1] if self.stack else None
        if tag in _VOID:
            if tag == "br":
                self.handle_data(" ")
            elif (tag == "img" and parent and not parent.excluded and parent.dish
                  and parent.dish.layout == "photo_article"
                  and (attributes.get("src") or "").startswith("/assets/img/food/")
                  and (name := (attributes.get("alt") or "").strip())):
                parent.dish.values.setdefault("name", []).append(name)
            return
        classes = (attributes.get("class") or "").split()
        hook = attributes.get("data-hook")
        framer = (attributes.get("data-framer-name") or "").casefold()
        dish = parent.dish if parent else None
        section = parent.section if parent else ""
        excluded = (
            tag in _SKIP or "hidden" in attributes or "menu-item__title-alt" in classes
            or attributes.get("aria-hidden") == "true" or bool(parent and parent.excluded)
        )
        capture = ""
        owns_dish = False
        beverage_section = bool(parent and parent.beverage_section) or (
            tag == "section" and "category" in classes and attributes.get("id") in {"alcoholic", "hotcold"}
        )
        menu_column = bool(parent and parent.menu_column) or bool({"menu-column-left", "menu-column-right"}.intersection(classes))

        if not excluded:
            layout = "wix" if hook == "item.root" else ""
            if "wrapper-menu-item" in classes:
                layout = "wordpress"
            elif self.menu_context and "food-item-holder" in classes:
                layout = "spot"
            elif self.menu_context and "item" in classes and "data-search" in attributes:
                layout = "search_card"
            elif self.menu_context and "menu-item" in classes and tag == "div":
                layout = "squarespace"
            elif self.menu_context and "ct-mini-menu-item" in classes:
                layout = "plento"
            elif self.menu_context and "sub-item" in classes:
                layout = "ordering_preview"
            elif framer == "text":
                layout = "framer"
            elif dish is None or dish.layout == "wix_grid":
                if attributes.get("data-testid") == "mesh-container-content":
                    layout = "wix_grid"
                elif dish is None and tag in _HEADINGS and "wixui-rich-text__text" in classes:
                    layout = "wix_grid"
                elif dish is None and tag == "li" and self.menu_context:
                    layout = "nutrition_list"
                elif dish is None and self.menu_context:
                    if tag == "p" and "p1" in classes:
                        layout = "pipe"
                    elif tag == "p" and menu_column:
                        layout = "inline"
                    elif tag == "article" and "group" in classes:
                        layout = "photo_article"
            if layout:
                dish = _Dish(layout, beverage=beverage_section)
                section = ""
                owns_dish = True
            if dish:
                if dish.layout == "wordpress" and any(_WORDPRESS_BEVERAGE_CATEGORY.fullmatch(c) for c in classes):
                    dish.beverage = True
                section, capture = self._field(dish.layout, tag, classes, hook, framer, section)
                if dish.layout == "nutrition_list":
                    if owns_dish:
                        capture = "description"
                    elif tag == "strong" and parent and parent.owns_dish:
                        capture = "name"
                if dish.layout == "inline" and owns_dish:
                    capture = "description"
        self.stack.append(_Element(tag, dish, owns_dish, section, excluded, beverage_section, menu_column, capture))

    @staticmethod
    def _field(layout: str, tag: str, classes: list[str], hook: str | None,
               framer: str, section: str) -> tuple[str, str]:
        if layout == "wix":
            return section, {"item.name": "name", "item.description": "description",
                             "item.price": "price"}.get(hook, "")
        if layout in _MENU_FIELDS:
            fields = _MENU_FIELDS[layout]
            return section, next((fields[c] for c in classes if c in fields), "")
        if layout == "nutrition_list":
            return section, ""
        if layout == "pipe":
            return section, {"b": "name", "strong": "name", "em": "description"}.get(tag, "")
        if layout == "photo_article":
            return section, "description" if tag == "p" and "leading-snug" in classes else ""
        if layout == "inline":
            return section, "name" if "menu-item" in classes else ""
        if layout == "plento":
            if "ct-mini-menu-top" in classes:
                section = "top"
            if section == "top":
                return section, "name" if tag == "h5" else "price" if "custom-primary" in classes else ""
            return section, "description" if tag == "p" else ""
        if layout == "ordering_preview":
            if tag == "h4":
                section = "title"
            if section == "title" and tag == "div" and "price" not in classes:
                return section, "name"
            return section, "description" if tag == "p" else ""
        if layout == "wordpress":
            if "menu-desc" in classes:
                section = "description"
            if "menu-item__title-main" in classes:
                return section, "name"
            if "menu-item__price" in classes:
                return section, "price"
            return section, "description" if section == "description" and tag == "p" else ""
        if layout == "framer":
            section = {"title": "name", "description": "description", "note": "notes",
                       "choice of meat": "options"}.get(framer, section)
            if (section == "name" and tag in _HEADINGS) or (section in {"description", "notes"} and tag == "p"):
                return section, section
            if section in {"", "description"} and tag in _HEADINGS:
                return section, "price"
            return section, "options" if framer == "choice of meat" else ""
        if "wixui-rich-text__text" not in classes:
            return section, ""
        return section, "name" if tag in _HEADINGS else "description" if tag == "p" else ""

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if not self.stack or self.stack[-1].excluded:
            return
        dish = self.stack[-1].dish
        if dish is None:
            return
        for element in reversed(self.stack):
            if element.dish is not dish:
                break
            if element.capture:
                element.text.append(data)
                break

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                break
        else:
            return
        closing = self.stack[index:]
        del self.stack[index:]
        for element in reversed(closing):
            dish = element.dish
            if dish is None:
                continue
            if element.capture:
                if element.capture == "options":
                    parts = [" ".join(chunk.split()).strip(" /") for chunk in element.text]
                    parts = [part for part in parts if part]
                    if len(parts) < 2 or parts[0].rstrip(":").casefold() not in {"choice of meat", "choice of noodles"}:
                        continue
                    value = parts[0].rstrip(":") + ": " + " / ".join(dict.fromkeys(parts[1:]))
                else:
                    value = " ".join("".join(element.text).split())
                if value:
                    dish.values.setdefault(element.capture, []).append(value)
            if element.owns_dish and (row := dish.row()):
                self.items.append(row)
                if dish.beverage:
                    self.beverage_items.add(row)
                prices = dish.prices()
                name = row[0].casefold()
                if self.prices.setdefault(name, prices) != prices:
                    # The name alone cannot distinguish two differently priced cards.
                    self.prices[name] = ()
