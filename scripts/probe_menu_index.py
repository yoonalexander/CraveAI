"""Measure menu extraction coverage from a sample of the catalog without storing dishes."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import date
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
from time import perf_counter
from typing import Awaitable, Callable
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx

from backend.services.menu_evidence import (
    FETCH_TIMEOUT_SECONDS, _parse_html, _safe_fetch_menu_document, is_menu_pdf_asset,
)
from backend.services.menu_index import select_menu_index_dishes
from backend.services.menu_pdf import parse_menu_pdf

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "gta-restaurants.json"
PDF_LIMIT = 6_000_000
_MENU = re.compile(r"\b(?:menus?|food|dinner|lunch|brunch|breakfast|dine.in|order)\b", re.I)
_OTHER_MENU = re.compile(r"\b(?:drinks?|beverages?|wines?|cocktails?|catering|gift|events?|new.year)\b", re.I)


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def menu_links(page_url: str, links: list[tuple[str, str]], host: str) -> list[str]:
    result: dict[str, tuple[bool, bool]] = {}
    for href, label in links:
        try:
            url = urldefrag(urljoin(page_url, href)).url
            parts = urlsplit(url)
            if (parts.scheme not in {"http", "https"}
                    or (_host(url) != host and not is_menu_pdf_asset(url))):
                continue
        except ValueError:
            continue
        path = parts.path.replace("_", "-")
        if url == page_url or _OTHER_MENU.search(f"{label} {path}"):
            continue
        if _MENU.search(label) or _MENU.search(path):
            result.setdefault(url, (not bool(_MENU.search(label)), "order" in label.lower()))
    return sorted(result, key=result.__getitem__)


def sample_restaurants(rows: list[dict], count: int, seed: int) -> list[dict]:
    rows = [row for row in rows if row.get("website")]
    random.Random(seed).shuffle(rows)
    chosen = {}
    for row in rows:
        chosen.setdefault(_host(row["website"]), row)
        if len(chosen) == count:
            break
    return list(chosen.values())


async def probe(
    client: httpx.AsyncClient, row: dict, pdf_tool: str | None, *,
    before_fetch: Callable[[str], Awaitable[None]] | None = None,
) -> dict:
    pages = []
    issues: list[str] = []
    sources = Counter()
    pending = [row["website"]]
    seen: set[str] = set()
    host = _host(row["website"])
    try:
        async with asyncio.timeout(25):
            while pending and len(seen) < 6:
                url = pending.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                try:
                    final, kind, data, encoding = await _safe_fetch_menu_document(
                        client, url, pdf_limit=PDF_LIMIT if pdf_tool else 0, host=host, before_fetch=before_fetch,
                    )
                    if kind == "application/pdf" and pdf_tool:
                        page = await asyncio.to_thread(parse_menu_pdf, data, pdf_tool)
                    else:
                        page = _parse_html(data.decode(encoding, errors="replace"), menu_context=True)
                    pending.extend(menu_links(final, page.links, host))
                    if page.menu_items:
                        pages.append((final, page))
                        sources[kind] += 1
                except httpx.HTTPStatusError as error:
                    issues.append(f"HTTP {error.response.status_code}")
                except (httpx.RequestError, OSError, ValueError, subprocess.SubprocessError) as error:
                    issues.append(str(error).split(":", 1)[0] if isinstance(error, ValueError) else type(error).__name__)
    except TimeoutError:
        issues.append("site deadline")
    selected = select_menu_index_dishes(pages)
    return {
        "restaurant": row["name"],
        "candidates": len(selected),
        "priced": sum(bool(dish.prices) for dish in selected),
        "documents": dict(sources),
        "examples": [{"name": dish.name, "source": dish.source_url,
                      "prices_in_cents": [price.amount_cents for price in dish.prices]} for dish in selected[:2]],
        "issues": dict(Counter(issues)),
    }


async def run(rows: list[dict], pdf_tool: str | None) -> dict:
    gate = asyncio.Semaphore(5)
    started = perf_counter()
    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False,
        headers={"User-Agent": "CraveAI/1.0 (menu parser pilot)"},
    ) as client:
        async def bounded(row: dict) -> dict:
            async with gate:
                return await probe(client, row, pdf_tool)

        results = await asyncio.gather(*(bounded(row) for row in rows))
    return {
        "checked_on": date.today().isoformat(),
        "seconds": round(perf_counter() - started, 2),
        "pdf_enabled": bool(pdf_tool),
        "restaurants": len(results),
        "with_one_dish": sum(row["candidates"] >= 1 for row in results),
        "with_two_dishes": sum(row["candidates"] >= 2 for row in results),
        "priced_dishes": sum(row["priced"] for row in results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20, choices=range(1, 51), metavar="1-50")
    parser.add_argument("--seed", type=int, default=20261120)
    parser.add_argument("--without-pdf", action="store_true")
    args = parser.parse_args()
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = sample_restaurants(snapshot["restaurants"], args.count, args.seed)
    pdf_tool = None if args.without_pdf else shutil.which("pdftotext")
    print(json.dumps(asyncio.run(run(rows, pdf_tool)), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
