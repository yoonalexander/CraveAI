"""Verify municipal Tim Hortons branches using current official branch pages."""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from scripts.corroborate_municipal_candidates import LOCALITIES, overture_address
from scripts.reconcile_restaurant_catalog import csv_rows, metres, street_key
from scripts.review_municipal_candidates import DATA, unit_key
from scripts.stage_municipal_admissions import INITIAL, record_position

HOST = "https://locations.timhortons.ca"
BRANCH_PATH = re.compile(r"/en/on/([a-z-]+)/[a-z0-9-]+/?\Z")
BRAND = re.compile(r"Tim Horton'?s(?:\s*(?:#|NO\.?\s*)?\d+)?\Z", re.I)
CLOSED = re.compile(r"\b(?:permanently|temporarily) closed\b", re.I)
JSON_LD = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


class Directory(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.branch = ""
        self.entries: list[tuple[str, str]] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href") or ""
        if tag == "a" and BRANCH_PATH.fullmatch(href):
            self.branch = href
            self.parts = []

    def handle_data(self, text: str) -> None:
        if self.branch:
            self.parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag == "li" and self.branch:
            value = " ".join(" ".join(self.parts).split())
            if value.startswith("Tim Hortons - "):
                self.entries.append((self.branch, value.removeprefix("Tim Hortons - ")))
            self.branch = ""


def page_evidence(html: str, row: dict) -> str:
    if CLOSED.search(html):
        return ""
    for match in JSON_LD.finditer(html):
        try:
            place = json.loads(match[1])
            if not isinstance(place, dict) or place.get("name") != "Tim Hortons":
                continue
            address = place["address"]
            locality = address["addressLocality"].casefold()
            if address["addressRegion"] != "ON" or locality not in LOCALITIES[row["city"]]:
                continue
            text = address["streetAddress"]
            found = overture_address(text)
            if found.street != street_key(row["address"]) or found.unit != unit_key(row["address"]):
                continue
            position = place["geo"]
            coordinates = float(position["latitude"]), float(position["longitude"])
            if metres(record_position(row), coordinates) > 100:
                continue
            if any(entry.get("opens") and entry.get("closes") and entry["opens"] != entry["closes"]
                   for entry in place.get("openingHoursSpecification", [])):
                return row["address"]
        except (KeyError, ValueError, TypeError):
            continue
    return ""


def fetch(path: str) -> str:
    try:
        with urlopen(Request(HOST + path, headers={"User-Agent": "CraveAI-Catalog/1.0"}), timeout=12) as response:
            if not response.url.startswith(HOST + "/en/on/"):
                return ""
            return response.read(500_000).decode("utf-8", errors="replace")
    except (URLError, TimeoutError):
        return ""


def review(ledger: Path, pages: list[Path], checked_on: date) -> dict:
    pending = {r["candidate_id"] for r in csv_rows(ledger)
               if r["disposition"] == "pending" and r["initial_outcome"] != "possible_catalog_match"
               and r["corroboration"] != "hold_source_conflict"}
    by_address = defaultdict(set)
    for page in pages:
        directory = Directory()
        directory.feed(page.read_text(encoding="utf-8"))
        for path, address in directory.entries:
            locality = BRANCH_PATH.fullmatch(path)[1].replace("-", " ")
            city = "Mississauga" if locality == "mississauga" else "Toronto"
            by_address[city, street_key(address)].add(path)
    shortlist = [(row, by_address[row["city"], street_key(row["address"])]) for row in csv_rows(INITIAL)
                 if row["candidate_id"] in pending and BRAND.fullmatch(row["name"])]
    paths = sorted({path for _, options in shortlist for path in options})
    with ThreadPoolExecutor(max_workers=4) as executor:
        html = dict(zip(paths, executor.map(fetch, paths)))
    results = {}
    for row, options in shortlist:
        matches = [path for path in options if page_evidence(html[path], row)]
        if len(matches) == 1:
            results[row["candidate_id"]] = {"city": row["city"], "name": row["name"], "address": row["address"],
                                           "url": HOST + matches[0], "signal": "hours", "checked_on": checked_on.isoformat()}
    print(f"Matched {len(results)} exact branches with current published hours from {len(paths)} pages.")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DATA / "gta-municipal-dispositions.csv")
    parser.add_argument("--directory", type=Path, action="append", required=True)
    parser.add_argument("--checked-on", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review(args.ledger, args.directory, args.checked_on)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
