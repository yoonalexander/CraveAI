"""Check candidate websites for branch evidence, without changing catalog state."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx

from backend.services.menu_evidence import _MenuHTMLParser, _safe_fetch_menu_document
from scripts.corroborate_municipal_candidates import LOCALITIES, overture_address
from scripts.reconcile_restaurant_catalog import csv_rows, street_key
from scripts.review_municipal_candidates import DATA, name_alias, unit_key
from scripts.stage_municipal_admissions import INITIAL, REVIEW

FOOD_TYPES = {"Restaurant", "FastFoodRestaurant", "FoodEstablishment"}
LINK_WORDS = re.compile(r"\b(?:locations?|contact|visit|hours|find us)\b", re.I)
CLOSURE = re.compile(r"\b(?:permanently|temporarily) closed\b", re.I)
BLOCKED_HOSTS = {"facebook.com", "instagram.com", "twitter.com", "x.com", "google.com", "yelp.ca", "yelp.com"}
PRIORITY = {"hold_freshness": 0, "hold_unit": 1, "no_exact_match": 2, "corroborated_by_dinesafe_history": 3}


def values(value):
    if isinstance(value, list):
        return value
    return [value] if value is not None else []


def business_objects(document):
    if isinstance(document, list):
        for entry in document:
            yield from business_objects(entry)
    elif isinstance(document, dict):
        yield document
        yield from business_objects(document.get("@graph"))


def has_service(place: dict, today: str) -> str:
    for entry in values(place.get("openingHoursSpecification")):
        if (isinstance(entry, dict) and isinstance(entry.get("opens"), str) and isinstance(entry.get("closes"), str)
                and entry["opens"] != entry["closes"]
                and str(entry.get("validFrom", ""))[:10] <= today <= str(entry.get("validThrough", "9999"))[:10]):
            return "hours"
    if any(isinstance(hours, str) and re.search(r"\b(?:Mo|Tu|We|Th|Fr|Sa|Su)\b.{0,24}\d\d:\d\d-\d\d:\d\d", hours)
           and not re.search(r"00:00-00:00", hours) for hours in values(place.get("openingHours"))):
        return "hours"
    return ""


def examine(parser: _MenuHTMLParser, row: dict, today: str) -> tuple[str, str]:
    if any(CLOSURE.search(block) for block in parser.visible_blocks):
        return "closure_text", ""
    expected = street_key(row["address"])
    for raw in parser._json_documents:
        try:
            document = json.loads(raw)
        except ValueError:
            continue
        for place in business_objects(document):
            category = {str(value).rsplit("/", 1)[-1] for value in values(place.get("@type"))}
            if not (category & FOOD_TYPES) or name_alias(str(place.get("name") or "")) != name_alias(row["name"]):
                continue
            for address in values(place.get("address")):
                if not isinstance(address, dict):
                    continue
                locality = str(address.get("addressLocality") or "").strip().casefold()
                region = str(address.get("addressRegion") or "").casefold()
                street = overture_address(str(address.get("streetAddress") or ""))
                if (locality in LOCALITIES[row["city"]] and region in {"on", "ontario", "ca-on"}
                        and expected and street.street == expected and street.unit == unit_key(row["address"])
                        and (signal := has_service(place, today))):
                    return "structured_branch", signal
    snippets = [" ".join(parser.visible_blocks[i:i + 3]) for i in range(len(parser.visible_blocks))]
    for snippet in snippets:
        street = street_key(snippet)
        if expected and (street == expected or street.startswith(expected + " ")):
            return "visible_address", ""
    return "no_exact_evidence", ""


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def website(value: str) -> str:
    if value and "://" not in value:
        value = "https://" + value
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
            return ""
        normalized_host = host(value)
        if any(normalized_host == item or normalized_host.endswith("." + item) for item in BLOCKED_HOSTS):
            return ""
        return urldefrag(value).url
    except ValueError:
        return ""


async def review_group(client, url: str, rows: list[dict], day: str) -> list[dict]:
    pending = [url]
    seen: set[str] = set()
    results = {r["candidate_id"]: {"candidate_id": r["candidate_id"], "name": r["name"], "address": r["address"],
                                    "city": r["city"], "source": url, "status": "unreachable", "signal": ""} for r in rows}
    ranking = {"unreachable": 0, "no_exact_evidence": 1, "visible_address": 2, "structured_branch": 3, "closure_text": 4}
    while pending and len(seen) < 3:
        next_url = pending.pop(0)
        if next_url in seen:
            continue
        seen.add(next_url)
        try:
            final, _, content, encoding = await _safe_fetch_menu_document(client, next_url, host=host(url))
        except (httpx.HTTPError, ValueError, OSError):
            continue
        parser = _MenuHTMLParser()
        parser.feed(content.decode(encoding, errors="replace"))
        for row in rows:
            status, signal = examine(parser, row, day)
            result = results[row["candidate_id"]]
            if ranking[status] > ranking[result["status"]]:
                result.update(status=status, signal=signal, source=final)
        if len(seen) == 1:
            for href, label in parser.links:
                if LINK_WORDS.search(label):
                    link = website(urljoin(final, href))
                    if link and host(link) == host(final) and link not in seen and link not in pending:
                        pending.append(link)
    return list(results.values())


async def review(args: argparse.Namespace) -> list[dict]:
    base = {r["candidate_id"]: r for r in csv_rows(INITIAL)}
    detail = {r["candidate_id"]: r for r in csv_rows(REVIEW)}
    osm = {}
    if args.osm_leads:
        for row in csv_rows(args.osm_leads):
            if row["address_evidence"] == "exact" and row["operator_url"]:
                osm.setdefault(row["candidate_id"], row["operator_url"])
    candidates = sorted((r for r in csv_rows(args.ledger) if r["disposition"] == "pending"),
                        key=lambda r: PRIORITY.get(r["corroboration"], 5))
    groups = defaultdict(list)
    for row in candidates:
        ident = row["candidate_id"]
        url = (website(detail.get(ident, {}).get("operator_url", "")) or website(base[ident]["website"])
               or website(osm.get(ident, "")))
        if url:
            groups[url].append(row)
    selected = list(groups.items())[args.offset:args.offset + args.limit]
    semaphore = asyncio.Semaphore(8)
    host_limits = defaultdict(lambda: asyncio.Semaphore(1))
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=False, headers={"User-Agent": "CraveAI Directory Review/1.0"}) as client:
        async def run(url, rows):
            async with host_limits[host(url)], semaphore:
                return await review_group(client, url, rows, args.checked_on.isoformat())

        responses = await asyncio.gather(*(run(url, rows) for url, rows in selected))
    return [r for result in responses for r in result]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checked-on", type=date.fromisoformat, required=True)
    parser.add_argument("--ledger", type=Path, default=DATA / "gta-municipal-dispositions.csv")
    parser.add_argument("--osm-leads", type=Path)
    parser.add_argument("--limit", type=int, default=90)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = asyncio.run(review(args))
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(dict(Counter(r["status"] for r in rows)))


if __name__ == "__main__":
    main()
