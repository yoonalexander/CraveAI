"""Cross-check unresolved municipal listings against an Overture Places extract."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from scripts.reconcile_restaurant_catalog import POSTAL_CODE, metres, street_key
from scripts.review_municipal_candidates import (
    DATA, MANUAL, TORONTO_TYPE_UNCLEAR, name_alias, normalized_unit, possible_alias, unit_key,
)

LEDGER = DATA / "gta-municipal-candidate-review.csv"
UNRESOLVED = {"needs_confirmation", "possible_catalog_match"}
LOCALITIES = {
    "Toronto": {"toronto", "old toronto", "north york", "east york", "etobicoke", "scarborough", "york"},
    "Mississauga": {"mississauga"},
}
RESTAURANT_CATEGORIES = {"restaurant", "fast_food", "fast_food_restaurant", "takeout_restaurant"}
MEAL_VENUE_TYPES = {"diner", "gastropub", "sandwich_shop", "pancake_house"}
OTHER_CATEGORIES = {"grocery_store", "supermarket", "convenience_store", "gas_station", "catering"}
SUPPORTED = {"corroborated_restaurant", "corroborated_by_inspection", "corroborated_by_operator"}
UNIT_PREFIX = re.compile(r"^(?:unit\s*|suite\s*|#\s*)?([a-z]?\d{1,3}[a-z]?)\s*-\s*(?=\d+\s+\w)", re.I)
UNIT_SUFFIX = re.compile(r"(?i)(?:[,;]\s*|\s+)(?:unit|suite|ste|apt)\.?\s+|\s*#\s*")
RELEASE_TAG = re.compile(r"(\d{4}-\d{2}-\d{2})\.\d+")
FIELDS = (
    "city", "candidate_id", "name", "address", "review_outcome", "corroboration", "reason",
    "catalog_link", "overture_release", "overture_id", "overture_name", "overture_address",
    "category", "primary_category", "operating_status", "confidence", "source_updated_on", "distance_m", "operator_url",
    "municipal_record", "municipal_source_date", "operator_checked_on", "operator_evidence",
)


@dataclass(frozen=True)
class Address:
    street: str
    unit: str


def overture_address(value: str) -> Address:
    value = POSTAL_CODE.sub("", value.strip())
    if (prefix := UNIT_PREFIX.match(value)) and (
        not prefix[1].isdigit() or int(prefix[1]) <= 100 or value.startswith(("#", "Unit", "Suite"))
    ):
        return Address(street_key(value[prefix.end():]), normalized_unit(prefix[1]))
    if suffix := UNIT_SUFFIX.search(value):
        unit = value[suffix.end():].split(",", 1)[0]
        return Address(street_key(value[:suffix.start()]), normalized_unit(unit))
    return Address(street_key(value), "")


def choose_operator_url(urls: list[str]) -> str:
    for url in urls:
        if not isinstance(url, str):
            continue
        if url.startswith(("https://", "http://")) and not re.search(
            r"(?:google\.|facebook\.|instagram\.|yelp\.|ubereats\.|doordash\.|skipthedishes\.)", url, re.I,
        ):
            return url
    return ""


@dataclass(frozen=True)
class Match:
    place: dict
    address: str
    distance: float
    address_status: str


def find_matches(row: dict, places: list[dict]) -> list[Match]:
    expected = Address(street_key(row["address"]), unit_key(row["address"]))
    if not expected.street:
        return []
    expected_name = name_alias(row["name"])
    expected_alias = possible_alias(row["name"])
    result = []
    for place in places:
        distance = metres((float(row["latitude"]), float(row["longitude"])),
                          (float(place["latitude"]), float(place["longitude"])))
        # A cuisine suffix is weaker evidence than the full trading name.
        same_name = expected_name == name_alias(place["name"])
        same_alias = len(expected_alias) >= 7 and expected_alias == possible_alias(place["name"])
        if not (same_name or same_alias) or distance > (125 if same_name else 50):
            continue
        for entry in place["addresses"]:
            if (entry.get("country") != "CA" or entry.get("region") not in (None, "", "CA-ON", "ON")
                    or (entry.get("locality") or "").strip().casefold() not in LOCALITIES[row["city"]]):
                continue
            address = entry.get("freeform") or ""
            got = overture_address(address)
            if got.street != expected.street:
                continue
            status = "exact"
            if expected.unit and expected.unit != got.unit:
                status = "unit_conflict" if got.unit else "unit_missing"
            result.append(Match(place, address, distance, status))
    quality = {"exact": 0, "unit_missing": 1, "unit_conflict": 2}
    result.sort(key=lambda match: (quality[match.address_status], -match.place["confidence"], match.distance, match.place["id"]))
    best_by_place = {}
    for match in result:
        best_by_place.setdefault(match.place["id"], match)
    return list(best_by_place.values())


def last_update(place: dict) -> str:
    valid = []
    for row in place.get("sources") or []:
        value = row.get("update_time")
        if (isinstance(value, str) and row.get("property") in (None, "")
                and (row.get("dataset") or "").casefold() != "overture"):
            try:
                valid.append(date.fromisoformat(value[:10]))
            except ValueError:
                pass
    return max(valid).isoformat() if valid else ""


def food_category(place: dict) -> bool:
    category = place.get("basic_category") or ""
    primary = place.get("primary_category") or ""
    path = set(place.get("category_path") or [])
    return category not in OTHER_CATEGORIES and (
        category in RESTAURANT_CATEGORIES or "restaurant" in path or category.endswith("_restaurant")
        or primary in MEAL_VENUE_TYPES
    )


def decide(row: dict, matches: list[Match], cutoff: str, checked_on: str, overrides: dict) -> tuple[str, str, Match | None]:
    if row["outcome"] == "possible_catalog_match":
        return "hold_catalog_match", "Resolve the linked catalog branch before adding a listing.", matches[0] if matches else None
    if overrides.get(row["candidate_id"], {}).get("outcome") == "needs_confirmation":
        return "hold_source_conflict", row["reason"], matches[0] if matches else None
    if not matches:
        return "no_exact_match", "No matching Overture name and street address within 125 metres.", None
    exact = [match for match in matches if match.address_status == "exact"]
    if not exact:
        return "hold_unit", "The outside record gives a different or missing unit for this candidate.", matches[0]
    if len(exact) > 1:
        return "hold_multiple_matches", "More than one Overture place has this name and branch address.", exact[0]
    match = exact[0]
    place = match.place
    status = place.get("operating_status")
    if status in {"closed", "temporarily_closed", "permanently_closed"}:
        return "hold_operating_status", "Overture marks the matched location as closed.", match
    if not food_category(place):
        return "hold_business_type", "The exact outside match does not have a restaurant or takeout classification.", match
    updated = last_update(place)
    fresh_source = cutoff <= updated <= checked_on and place["confidence"] >= 0.8
    recent_inspection = (row["city"] == "Toronto" and row["reason"] == TORONTO_TYPE_UNCLEAR
                         and cutoff <= row["source_date"] <= checked_on)
    if fresh_source and status in (None, "") and recent_inspection:
        return "corroborated_by_inspection", "A recent passing DineSafe inspection and uncancelled licence support activity. The outside branch match supports restaurant type.", match
    if status != "open" or not fresh_source:
        return "hold_freshness", "The restaurant type is corroborated. Open status, confidence, or source date needs another check.", match
    if row["city"] == "Toronto" and not recent_inspection:
        return "hold_municipal_freshness", "The municipality's matching inspection needs a fresh branch check.", match
    return "corroborated_restaurant", "Recent open restaurant record agrees with the municipal name, street, and any listed unit.", match


def operator_confirmation(row: dict, evidence: dict, cutoff: str, checked_on: str) -> bool:
    url = urlsplit(evidence["url"])
    return (
        url.scheme == "https" and bool(url.hostname) and not url.username and not url.password
        and evidence["signal"] in {"hours", "ordering", "reservations"}
        and cutoff <= date.fromisoformat(evidence["checked_on"]).isoformat() <= checked_on
        and evidence["city"] == row["city"]
        and name_alias(evidence["name"]) == name_alias(row["name"])
        and bool(street_key(row["address"])) and street_key(evidence["address"]) == street_key(row["address"])
        and (not unit_key(row["address"]) or unit_key(evidence["address"]) == unit_key(row["address"]))
    )


def candidate_name_keys(name: str) -> set[str]:
    return {key for key in (name_alias(name), possible_alias(name)) if len(key) >= 4}


def corroborate(ledger: Path, places_file: Path, release: str, checked_on: date, overrides: dict,
                operator_evidence: dict | None = None) -> list[dict]:
    with ledger.open(encoding="utf-8-sig", newline="") as source:
        pending = [row for row in csv.DictReader(source) if row["outcome"] in UNRESOLVED]
    ids = {row["candidate_id"] for row in pending}
    if len(ids) != len(pending) or not pending:
        raise ValueError("Expected unresolved municipal records with unique IDs.")
    evidence_by_id = operator_evidence or {}
    if evidence_by_id.keys() - ids:
        raise ValueError("Operator evidence references a candidate outside the unresolved queue.")
    names = {key for row in pending for key in candidate_name_keys(row["name"])}
    indexed = defaultdict(list)
    read_count = 0
    with places_file.open(encoding="utf-8") as source:
        for line in source:
            place = json.loads(line)
            read_count += 1
            if place.get("addresses"):
                for key in candidate_name_keys(place.get("name") or "") & names:
                    indexed[key].append(place)
    if not read_count:
        raise ValueError("The Overture extract is empty.")

    cutoff = (checked_on - timedelta(days=365)).isoformat()
    output = []
    for row in pending:
        place_by_id = {p["id"]: p for key in candidate_name_keys(row["name"]) for p in indexed[key]}
        matches = find_matches(row, list(place_by_id.values()))
        status, reason, match = decide(row, matches, cutoff, checked_on.isoformat(), overrides)
        result = {
            "city": row["city"], "candidate_id": row["candidate_id"], "name": row["name"],
            "address": row["address"], "review_outcome": row["outcome"], "corroboration": status,
            "reason": reason, "catalog_link": row["related_id"], "overture_release": release,
            "municipal_record": row["official_record"], "municipal_source_date": row["source_date"],
        }
        if match:
            place = match.place
            result.update(overture_id=place["id"], overture_name=place["name"], overture_address=match.address,
                          category=place.get("basic_category"), primary_category=place.get("primary_category"),
                          operating_status=place.get("operating_status"),
                          confidence=place["confidence"], source_updated_on=last_update(place),
                          distance_m=round(match.distance, 1), operator_url=choose_operator_url(place.get("websites") or []))
        if evidence := evidence_by_id.get(row["candidate_id"]):
            if not operator_confirmation(row, evidence, cutoff, checked_on.isoformat()):
                raise ValueError(f"Invalid operator evidence for {row['candidate_id']}.")
            result.update(operator_url=evidence["url"], operator_checked_on=evidence["checked_on"],
                          operator_evidence=evidence["signal"])
            if status in {"hold_freshness", "hold_municipal_freshness", "hold_business_type", "no_exact_match"}:
                result.update(corroboration="corroborated_by_operator",
                              reason="The operator publishes service information for the matching branch.")
        output.append(result)
    claims = Counter(row["overture_id"] for row in output if row["corroboration"] in SUPPORTED and row.get("overture_id"))
    for row in output:
        if row["corroboration"] in SUPPORTED and claims[row.get("overture_id")] > 1:
            row.update(corroboration="hold_multiple_candidates", reason="Several municipal candidates match this outside place.")
    return output


def excel_safe(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--places", type=Path, required=True)
    parser.add_argument("--release", required=True, help="Overture release tag, such as 2026-11-18.0")
    parser.add_argument("--checked-on", type=date.fromisoformat, required=True)
    parser.add_argument("--operator-evidence", type=Path, help="Reviewed branch pages keyed by municipal candidate ID")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    release = RELEASE_TAG.fullmatch(args.release)
    if not release:
        parser.error("Release must be an Overture release tag such as 2026-11-18.0.")
    if date.fromisoformat(release[1]) > args.checked_on:
        parser.error("Release date must be on or before the check date.")
    overrides = json.loads(MANUAL.read_text(encoding="utf-8"))
    operator_evidence = json.loads(args.operator_evidence.read_text(encoding="utf-8")) if args.operator_evidence else None
    rows = corroborate(args.ledger, args.places, args.release, args.checked_on, overrides, operator_evidence)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: excel_safe(value) for key, value in row.items()} for row in rows)
    for city in LOCALITIES:
        print(city, dict(sorted(Counter(row["corroboration"] for row in rows if row["city"] == city).items())))


if __name__ == "__main__":
    main()
