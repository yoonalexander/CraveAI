"""Review every remaining Stage 2 municipal candidate without changing the catalog."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from scripts.import_restaurant_catalog import SNAPSHOT, read_catalog_rows
from scripts.reconcile_restaurant_catalog import (
    EATING, TAKEOUT, UNIT, conflicting_units, csv_rows, metres, similar_name, street_key, text_key,
)

DATA = SNAPSHOT.parent
LICENCE_URL = "https://open.toronto.ca/dataset/municipal-licensing-and-standards-business-licences-and-permits/"
INSPECTION_URL = "https://open.toronto.ca/dataset/dinesafe/"
DIRECTORY_URL = "https://www.arcgis.com/home/item.html?id=073787e3977e4e2e9c68ff13093b6d9e"
MANUAL = DATA / "gta-municipal-branch-evidence.json"
TORONTO_TYPE_UNCLEAR = "Two city records match the location, but the operating name or endorsements do not clearly establish an eligible public restaurant."
TRADE_SUFFIX = re.compile(r"\b(?:limited|ltd|incorporated|inc|corporation|corp|llc)\.?\s*$", re.I)
STORE_NUMBER = re.compile(r"\s+(?:store\s+|#\s*)\d+\s*$", re.I)
RESTAURANT_NAME = re.compile(
    r"\b(?:restaurants?|resto|bistro|diner|pizzeria|pizza|burgers?|shawarma|souvlaki|ramen|"
    r"pho|sushi|tacos?|noodles?|sandwich(?:es)?|fish (?:and|&) chips|"
    r"bar (?:and|&) grill|bbq|barbecue|take[ -]?out|pub|"
    r"kabobs?|kebabs?|biryani|dosa|dumplings?|taqueria|rotisserie|"
    r"tim hortons|mcdonald'?s|subway|popeyes|wendy'?s|kfc|a&w|harvey'?s|"
    r"chick-fil-a|chipotle|swiss chalet|osmow'?s|five guys|taco bell)\b", re.I,
)
NON_RESTAURANT = re.compile(
    r"\b(?:pharmac(?:y|ies)|medical clinic|dental clinic|convenience store|gas station|"
    r"supermarket|grocery|7[ -]?eleven|circle k|gas bar|oil change|self.storage|"
    r"packaging supplies|auto repair|freight forwarding|dollarama|"
    r"elementary school|secondary school|child care centre|daycare|"
    r"summerhill market|no frills|loblaws)\b", re.I,
)
MIXED_VENUE = re.compile(
    r"\b(?:catering|banquet|commissary|wholesale|manufacturing|distribution|hotel|"
    r"conference centre|private club|corporate|retirement|hospital|"
    r"food court|test kitchen|bakery|bakehouse|concession|coffee|cafe|cafeteria|"
    r"butcher|superstore|food mart|food market|meat market|fish market|"
    r"farmers? market|convenience|fuel|gift shop|cinema|theatre|dance club)\b", re.I,
)
GENERIC_TRAILING = re.compile(r"\s+(?:restaurants?|food|kitchen|express)$", re.I)
CUISINE_TRAILING = re.compile(
    r"\s+(?:mexican|chinese|thai|italian|indian|korean|ethiopian|japanese|vietnamese|greek|"
    r"caribbean|lebanese|pakistani|turkish|portuguese|filipino|mediterranean)(?: cuisine)?$", re.I,
)

FIELDS = (
    "city", "candidate_id", "name", "address", "latitude", "longitude", "outcome", "reason",
    "related_id", "official_record", "source_date", "source_urls", "website",
)


def branch_name(value: str) -> str:
    value = STORE_NUMBER.sub("", TRADE_SUFFIX.sub("", value.strip()))
    return text_key(value)


def name_alias(value: str) -> str:
    return branch_name(GENERIC_TRAILING.sub("", TRADE_SUFFIX.sub("", value.strip())))


def possible_alias(value: str) -> str:
    core = GENERIC_TRAILING.sub("", TRADE_SUFFIX.sub("", value.strip()))
    return branch_name(CUISINE_TRAILING.sub("", core))


def position(row: dict) -> tuple[float, float]:
    return float(row["lat"]), float(row["lng"])


def same_branch(left: dict, right: dict) -> bool:
    a, b = street_key(left["address"]), street_key(right["address"])
    if different_units(left["address"], right["address"]) or (a and b and a != b):
        return False
    left_name, right_name = branch_name(left["name"]), branch_name(right["name"])
    left_alias, right_alias = name_alias(left["name"]), name_alias(right["name"])
    distance = metres(position(left), position(right))
    if left_name == right_name and min(len(left_name), len(right_name)) >= 4:
        return distance <= (125 if a and b else 35)
    return bool(a and b and a == b and left_alias == right_alias and len(left_alias) >= 6 and distance <= 75)


def canonical_candidates(rows: list[dict]) -> dict[str, str]:
    groups = defaultdict(list)
    for row in rows:
        key = (row["city"], name_alias(row["name"]), street_key(row["address"]))
        groups[key].append(row)
    duplicate_of = {}
    for group in groups.values():
        representatives = []
        for row in sorted(group, key=lambda item: (not bool(item.get("website")), item["id"])):
            matching = [
                other for other in representatives
                if same_branch(row, other) and (
                    row.get("premise_id") and row.get("premise_id") == other.get("premise_id")
                    or unit_key(row["address"]) == unit_key(other["address"])
                )
            ]
            if len(matching) == 1:
                duplicate_of[row["id"]] = matching[0]["id"]
            else:
                representatives.append(row)
    return duplicate_of


def normalized_unit(value: str) -> str:
    # A premises comprising units 9 and 10 is distinct from unit 910.
    return " ".join(part for token in re.findall(r"\w+", value) if (part := text_key(token)))


def unit_key(address: str) -> str:
    if "," in address:
        suffix = re.sub(r"^\s*(?:unit\b|suite\b|apt\b|#)\s*", "", address.split(",", 1)[1], flags=re.I)
        return normalized_unit(suffix)
    match = UNIT.search(address)
    if match:
        return normalized_unit(address[match.start(1):])
    return ""


def different_units(left: str, right: str) -> bool:
    a, b = unit_key(left), unit_key(right)
    return bool(a and b and a != b)


def review_inputs(licences_path: Path, inspections_path: Path, directory_path: Path):
    licences = {row["Licence No."]: row for row in csv_rows(licences_path)}
    inspections = {}
    for row in csv_rows(inspections_path):
        if not row["estId"] or not row["inspectionDate"]:
            continue
        key = (row["inspectionDate"], row["inspectionStatus"] in {"Closed", "Temporarily Not Operating"})
        prev = inspections.get(row["estId"])
        if prev is None or key > prev[0]:
            inspections[row["estId"]] = (key, row)
    directory_data = json.loads(directory_path.read_text(encoding="utf-8"))
    if directory_data.get("exceededTransferLimit") or not directory_data.get("features"):
        raise ValueError("Expected a complete Mississauga restaurant directory export.")
    directory = {str(entry["attributes"]["OBJECTID"]): entry for entry in directory_data["features"]}
    return licences, {key: value[1] for key, value in inspections.items()}, directory


def inspection_matches(candidate: dict, record: dict) -> bool:
    if branch_name(candidate["name"]) != branch_name(record["estName"]):
        return False
    if street_key(candidate["address"]) != street_key(record["address"]):
        return False
    if conflicting_units(candidate["address"], record["address"]):
        return False
    try:
        return metres(position(candidate), (float(record["latitude"]), float(record["longitude"]))) <= 100
    except (TypeError, ValueError):
        return False


def directory_matches(candidate: dict, entry: dict) -> bool:
    record = entry["attributes"]
    location = entry.get("geometry") or {}
    if branch_name(candidate["name"]) != branch_name(record["BusinessName"]):
        return False
    if street_key(candidate["address"]) != street_key(record["StreetAddress"]):
        return False
    if unit_key(candidate["address"]) != normalized_unit(str(record["UnitNo"] or "")):
        return False
    try:
        return metres(position(candidate), (float(location["y"]), float(location["x"]))) <= 100
    except (KeyError, TypeError, ValueError):
        return False


def outcome_for(row, catalog_matches, possible_matches, duplicate_of, licences, inspections, directory, manual, cutoff):
    ident = row["id"]
    source_id = ident.partition(":")[2]
    name, address = row["name"], row["address"]
    toronto = row["city"] == "Toronto"
    source_urls = f"{LICENCE_URL} | {INSPECTION_URL}" if toronto else DIRECTORY_URL
    official_record = row.get("premise_id", "") if toronto else source_id
    recorded_on = row.get("checked", "")

    def decision(outcome, reason, related="", evidence_url=""):
        return {
            "outcome": outcome, "reason": reason, "related_id": related,
            "official_record": official_record, "source_date": recorded_on,
            "source_urls": f"{source_urls} | {evidence_url}" if evidence_url else source_urls,
        }

    licence = licences.get(source_id) if toronto else None
    if toronto:
        latest = inspections.get(official_record)
        if latest:
            recorded_on = latest["inspectionDate"]
        if licence and licence["Cancel Date"].strip():
            recorded_on = licence["Cancel Date"].strip()
            return decision("inactive_record", "The municipal licence was cancelled. The candidate needs fresh operating evidence.")
        if latest and latest["inspectionStatus"] in {"Closed", "Temporarily Not Operating"}:
            return decision("inactive_record", "The latest linked premises record is closed or temporarily inactive. Verify before listing.")
        if (not licence or not latest or not inspection_matches(row, latest)
                or licence["Category"] not in {EATING, TAKEOUT}
                or branch_name(name) != branch_name(licence["Operating Name"])
                or street_key(address) != street_key(licence["Licence Address Line 1"])
                or conflicting_units(address, licence["Licence Address Line 1"])):
            return decision("needs_confirmation", "The current licence and inspection no longer establish the same candidate identity.")
    else:
        entry = directory.get(source_id)
        if not entry or not directory_matches(row, entry):
            return decision("needs_confirmation", "The current directory record failed the name, unit, address, or coordinate recheck.")

    if len(catalog_matches) == 1:
        return decision("already_listed", "Branch name, street address or proximity, and unit checks match an active catalog listing.", catalog_matches[0]["id"])
    if len(catalog_matches) > 1:
        return decision("possible_catalog_match", "More than one active catalog listing passes the branch match.", " | ".join(x["id"] for x in catalog_matches))
    if target := duplicate_of.get(ident):
        return decision("duplicate_candidate", "Same municipal branch name, street address, and unit or premises ID.", target)
    if verified := manual.get(ident):
        return decision(verified["outcome"], verified["reason"], verified.get("related_id", ""), verified["source_url"])
    if NON_RESTAURANT.search(name) and not RESTAURANT_NAME.search(name):
        return decision("out_of_scope", "The municipal operating name identifies a non-restaurant business.")
    if possible_matches:
        return decision("possible_catalog_match", "A similar active catalog name is nearby, but the branch identity needs confirmation.", " | ".join(x["id"] for x in possible_matches[:3]))
    if not toronto:
        return decision("needs_confirmation", "The 2025 business directory identifies this branch. A current public operating source is still needed.")
    if recorded_on < cutoff:
        return decision("needs_confirmation", "The latest matching inspection is more than one year old.")
    if latest["inspectionStatus"] not in {"Pass", "Conditional Pass"}:
        return decision("needs_confirmation", "The latest linked inspection status does not establish current operation.")
    if (not RESTAURANT_NAME.search(name) or MIXED_VENUE.search(name)
            or NON_RESTAURANT.search(name) or "EATING/DRINKING;" not in licence["Endorsements"]
            or any(value in licence["Endorsements"] for value in ("TOBACCO", "MOTOR OIL", "AMUSEMENT"))):
        return decision("needs_confirmation", TORONTO_TYPE_UNCLEAR)
    return decision("supported_addition", "Uncancelled eating/drinking licence and a matching premises inspection within one year corroborate a restaurant-named branch.")


def review(licences_path: Path, inspections_path: Path, directory_path: Path, reviewed_on: date) -> list[dict]:
    previous = json.loads((DATA / "gta-catalog-reviewed.json").read_text(encoding="utf-8"))
    admitted = {row["id"] for row in previous["municipal_listings"]}
    coverage = json.loads((DATA / "gta-restaurant-coverage.json").read_text(encoding="utf-8"))
    pipeline = [
        {"city": city, **item} for city, current in coverage["cities"].items()
        for item in current["additions"] if item["id"] not in admitted
    ]
    pipeline_ids = {item["id"] for item in pipeline}
    if len(pipeline_ids) != len(pipeline):
        raise ValueError("The municipal candidate queue contains repeated IDs.")
    manual = json.loads(MANUAL.read_text(encoding="utf-8")) if MANUAL.exists() else {}
    if manual.keys() - pipeline_ids:
        raise ValueError("Manual evidence references a candidate outside the current queue.")
    for ident, entry in manual.items():
        source = urlsplit(entry["source_url"])
        if (entry["outcome"] not in {"supported_addition", "already_listed", "duplicate_candidate", "out_of_scope", "needs_confirmation"}
                or source.scheme != "https" or not source.hostname):
            raise ValueError(f"Invalid manual evidence for {ident}.")
    licences, inspections, directory = review_inputs(licences_path, inspections_path, directory_path)
    active = [item for item in read_catalog_rows(SNAPSHOT) if item["listed"]]
    active_ids = {item["id"] for item in active}
    for ident, entry in manual.items():
        related = entry.get("related_id")
        if ((entry["outcome"] == "already_listed" and related not in active_ids)
                or (entry["outcome"] == "duplicate_candidate" and (related not in pipeline_ids or related == ident))):
            raise ValueError(f"Invalid linked branch for {ident}.")
    by_alias = defaultdict(list)
    by_cell = defaultdict(list)
    def cell(row):
        return int(row["lat"] * 500), int(row["lng"] * 500)
    for item in active:
        by_alias[name_alias(item["name"])].append(item)
        by_cell[cell(item)].append(item)
    duplicates = canonical_candidates(pipeline)
    cutoff = (reviewed_on - timedelta(days=365)).isoformat()
    results = []
    for row in pipeline:
        alias = name_alias(row["name"])
        loose_alias = possible_alias(row["name"])
        matched = [p for p in by_alias[alias] if same_branch(row, p)]
        y, x = cell(row)
        nearby = [p for yy in range(y - 1, y + 2) for xx in range(x - 1, x + 2) for p in by_cell[yy, xx]]
        possible = sorted(
            (p for p in nearby if not conflicting_units(row["address"], p["address"])
             and metres(position(row), position(p)) <= 150
             and (alias == name_alias(p["name"]) or similar_name(alias, name_alias(p["name"]))
                  or similar_name(loose_alias, possible_alias(p["name"])))),
            key=lambda place: metres(position(row), position(place)),
        )
        decision = outcome_for(row, matched, possible, duplicates, licences, inspections, directory, manual, cutoff)
        results.append({
            "city": row["city"], "candidate_id": row["id"], "name": row["name"], "address": row["address"],
            "latitude": row["lat"], "longitude": row["lng"], **decision, "website": row.get("website", ""),
        })
    assert {row["candidate_id"] for row in results} == pipeline_ids
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("licences", "inspections", "directory", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--reviewed-on", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    rows = review(args.licences, args.inspections, args.directory, args.reviewed_on)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    for city in sorted({row["city"] for row in rows}):
        print(city, dict(sorted(Counter(row["outcome"] for row in rows if row["city"] == city).items())))


if __name__ == "__main__":
    main()
