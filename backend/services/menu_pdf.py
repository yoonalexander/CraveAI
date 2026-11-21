"""Read clearly priced dish rows from a text-based restaurant menu PDF."""
from __future__ import annotations

import re
import subprocess

from backend.services.menu_evidence import ParsedPage
from backend.services.menu_markup import MenuPrice, _AMOUNT, _price

_ROW = re.compile(r"(?P<name>.+?)(?:\s*/\s*|\s*\.{2,}\s*|\s+(?=(?:CA\$|\$)))"
                  + _AMOUNT + r"(?:\s*\([VG]{1,2}\))?", re.IGNORECASE)
_SKIP_ROW = re.compile(
    r"^(?:add(?:\s|$)|extra\s|substitute\s|upgrade\s|choice of\s|stuff it$|includes\s|tax\s)"
    r"|(?:\bper person\b|\b(?:wine|cocktails?|beer)\b)$",
    re.IGNORECASE,
)


def parse_menu_pdf_text(source: str) -> ParsedPage:
    prices: dict[str, MenuPrice | None] = {}
    items: dict[str, tuple[str, str]] = {}
    for line in source.splitlines():
        for cell in re.split(r" {4,}", line.strip()):
            match = _ROW.fullmatch(cell.strip())
            if not match:
                continue
            name = match["name"].strip()
            # A photo caption, price column, or another priced row must not become a dish.
            if (not 2 <= len(name) <= 80 or not name[0].isalpha() or "$" in name
                    or re.search(r"[/|]|\.\d{2}\b", name) or _SKIP_ROW.search(name)):
                continue
            key = name.casefold()
            items.setdefault(key, (name, ""))
            price = _price(match)
            if prices.setdefault(key, price) != price:
                prices[key] = None
    return ParsedPage(
        menu_items=list(items.values()),
        menu_prices={name: (price,) for name, price in prices.items() if price is not None},
    )


def parse_menu_pdf(content: bytes, executable: str) -> ParsedPage:
    if not content.startswith(b"%PDF-"):
        raise ValueError("Menu response did not contain a PDF.")
    completed = subprocess.run(
        [executable, "-layout", "-f", "1", "-l", "8", "-enc", "UTF-8", "-", "-"],
        input=content, capture_output=True, timeout=12, check=True,
    )
    return parse_menu_pdf_text(completed.stdout.decode("utf-8", errors="replace"))
