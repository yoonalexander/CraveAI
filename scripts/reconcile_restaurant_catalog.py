"""Cross-check the OSM seed against municipal sources without importing to a database."""
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from difflib import SequenceMatcher
from math import cos, hypot, isfinite, radians
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.prepared import prep

EATING = "EATING OR DRINKING ESTABLISHMENT"
TAKEOUT = "TAKE-OUT OR RETAIL FOOD ESTABLISHMENT"
MISSISSAUGA_RESTAURANTS = {722511, 722512, 722513, 722514}
FOOD_NAME = re.compile(
    r"\b(?:restaurant|pizzeria|pizza|burger|shawarma|ramen|pho|sushi|bistro|grill|noodles?|tacos?|"
    r"sandwiches?|diner|fish\s*(?:and|&)\s*chips)\b", re.I,
)
NON_RESTAURANT = re.compile(
    r"\b(?:medical clinic|dental clinic|pharmacy|grocery|supermarket|loblaws|"
    r"no frills|convenience store|gas station)\b", re.I,
)
POSTAL_CODE = re.compile(r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b", re.I)
UNIT = re.compile(r"(?:\b(?:unit|suite|apt)\s+|#\s*)([\w-]+)", re.I)
STREET_WORD = dict(street="st", road="rd", avenue="ave", drive="dr", boulevard="blvd",
                   crescent="cres", parkway="pkwy", pky="pkwy", court="ct", lane="ln",
                   east="e", west="w", north="n", south="s")


def text_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in text if ch.isalnum())


def street_key(value: str) -> str:
    value = POSTAL_CODE.sub("", value)
    value = re.split(r"(?i)\b(?:none|unit|suite|apt)\b|[,#]", value, maxsplit=1)[0]
    words = re.findall(r"\w+", value.lower())
    if not words or not words[0][0].isdigit():
        return ""
    return " ".join(STREET_WORD.get(word, word) for word in words)


def conflicting_units(left: str, right: str) -> bool:
    a, b = UNIT.search(left), UNIT.search(right)
    return bool(a and b and text_key(a[1]) != text_key(b[1]))


def coordinates(lat, lng) -> tuple[float, float] | None:
    try:
        lat, lng = float(lat), float(lng)
    except (ValueError, TypeError):
        return None
    if isfinite(lat) and isfinite(lng):
        return round(lat, 6), round(lng, 6)
    return None


@dataclass
class Candidate:
    id: str
    name: str
    address: str
    location: tuple[float, float] | None = None
    website: str = ""
    checked: str = ""
    premise_id: str = ""
    reason: str = ""

    def to_row(self) -> dict:
        row = {"id": self.id, "name": self.name, "address": self.address}
        if self.location:
            row.update(lat=self.location[0], lng=self.location[1])
        for key in ("website", "checked", "premise_id", "reason"):
            if value := getattr(self, key):
                row[key] = value
        return row


def csv_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        yield from csv.DictReader(file)


def toronto_candidates(licences: Path, inspections: Path, checked: date):
    counts = Counter()
    latest = {}
    for row in csv_rows(inspections):
        if not (row["estId"] and row["inspectionDate"] and row["estName"]):
            continue
        old = latest.get(row["estId"])
        key = (row["inspectionDate"], row["inspectionStatus"] in {"Closed", "Temporarily Not Operating"})
        if old is None or key > old[0]:
            latest[row["estId"]] = (key, row)
    cutoff = str(checked - timedelta(days=548))
    by_name_address = defaultdict(list)
    for key, row in latest.values():
        if key[0] >= cutoff:
            by_name_address[text_key(row["estName"]), street_key(row["address"])].append((key, row))
    counts["dinesafe_premises"] = len(latest)
    counts["dinesafe_recent_premises"] = sum(key[0] >= cutoff for key, _ in latest.values())

    candidates = []
    used_premises = set()
    for row in csv_rows(licences):
        if row["Category"] not in {EATING, TAKEOUT} or row["Cancel Date"].strip():
            continue
        counts["uncancelled_food_licences"] += 1
        name = row["Operating Name"].strip()
        if not name:
            counts["licences_without_public_operating_name"] += 1
            continue
        address = row["Licence Address Line 1"].strip()
        candidate = Candidate(f"toronto-licence:{row['Licence No.']}", name, address)
        matches = [
            (key, premise) for key, premise in by_name_address[text_key(name), street_key(address)]
            if street_key(address) and not conflicting_units(address, premise["address"])
        ]
        if len(matches) == 1:
            key, premise = matches[0]
            used_premises.add(premise["estId"])
            candidate.checked, candidate.premise_id = key[0], premise["estId"]
            candidate.location = coordinates(premise["latitude"], premise["longitude"])
            if key[1]:
                candidate.reason = "Check latest inspection marked closed or temporarily not operating"
        elif len(matches) > 1:
            candidate.reason = "Multiple recent DineSafe premises match the name and street"
        else:
            candidate.reason = "Confirm current premises with a recent DineSafe match or another location source"
        if row["Category"] == TAKEOUT and "EATING/DRINKING;" not in row["Endorsements"] and not FOOD_NAME.search(name):
            candidate.reason = "Confirm restaurant eligibility in the takeout or retail licence category"
        candidates.append(candidate)
    for key, row in latest.values():
        if row["estId"] in used_premises or key[0] < cutoff or not FOOD_NAME.search(row["estName"]):
            continue
        reason = ("Check latest inspection marked closed or temporarily not operating" if key[1]
                  else "Confirm restaurant eligibility and link to a current licence or restaurant source")
        candidates.append(Candidate(
            f"toronto-dinesafe:{row['estId']}", row["estName"].strip(),
            POSTAL_CODE.sub("", row["address"]).replace(" None", "").strip(),
            coordinates(row["latitude"], row["longitude"]), checked=key[0],
            premise_id=row["estId"], reason=reason,
        ))
    return candidates, counts


def mississauga_candidates(path: Path, survey: str):
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if dataset.get("exceededTransferLimit") or not dataset.get("features"):
        raise ValueError("The Mississauga input is empty or paginated.")
    candidates = []
    for entry in dataset["features"]:
        row = entry["attributes"]
        if row["NAICSCode"] not in MISSISSAUGA_RESTAURANTS:
            continue
        location = entry.get("geometry") or {}
        name, address, unit = (str(row.get(field) or "").strip() for field in
                               ("BusinessName", "StreetAddress", "UnitNo"))
        if unit:
            address += f", Unit {unit}"
        candidates.append(Candidate(
            f"mississauga-directory-2025:{row['OBJECTID']}", name, address,
            coordinates(location.get("y"), location.get("x")),
            str(row.get("WebAddress") or "").strip(), checked=survey,
        ))
    return candidates, Counter({"directory_food_service_rows": len(dataset["features"])})


def metres(left, right):
    return 111_195 * hypot(left[0] - right[0], (left[1] - right[1]) * cos(radians(left[0])))


def similar_name(left: str, right: str) -> bool:
    if min(len(left), len(right)) < 5:
        return False
    return left in right or right in left or SequenceMatcher(None, left, right).ratio() >= 0.83


def reconcile(candidates: list[Candidate], osm_rows: list[dict], boundary) -> dict:
    by_name, by_street, by_cell = defaultdict(list), defaultdict(list), defaultdict(list)
    def cell(lat, lng):
        return int(lat * 500), int(lng * 500)

    for row in osm_rows:
        by_name[text_key(row["name"])].append(row)
        if key := street_key(row["address"]):
            by_street[key].append(row)
        by_cell[cell(row["lat"], row["lng"])].append(row)
    matches, additions, review = {}, [], []
    seen_new = {}
    for item in sorted(candidates, key=lambda candidate: candidate.id):
        name, street = text_key(item.name), street_key(item.address)
        if NON_RESTAURANT.search(item.name):
            item.reason = item.reason or "Check a retail or non-restaurant name in the source category"
        name_matches = []
        for row in by_name[name]:
            osm_street = street_key(row["address"])
            if conflicting_units(item.address, row["address"]):
                continue
            distance = metres(item.location, (row["lat"], row["lng"])) if item.location else None
            if ((street and street == osm_street and (distance is None or distance <= 125))
                    or (distance is not None and distance <= 50 and (not street or not osm_street))):
                name_matches.append(row["id"])
        if (len(name_matches) == 1 and "latest inspection marked" not in item.reason
                and not NON_RESTAURANT.search(item.name)):
            matches[item.id] = name_matches[0]
            continue
        if len(name_matches) > 1:
            item.reason = "Multiple OSM locations match the normalized restaurant name and location"
        if item.location is None:
            item.reason = item.reason or "Verify missing coordinates"
        elif not boundary.covers(Point(item.location[1], item.location[0])):
            item.reason = "Coordinates fall outside the municipal boundary"
        if not name or not street:
            item.reason = item.reason or "Verify public name and street address"
        if any(text_key(row["name"]) != name for row in by_street.get(street, ())):
            item.reason = item.reason or "Check a different OSM business name at the same street address"
        if item.location and not item.reason:
            cell_lat, cell_lng = cell(*item.location)
            nearby = (row for y in range(cell_lat - 1, cell_lat + 2)
                      for x in range(cell_lng - 1, cell_lng + 2) for row in by_cell[y, x])
            for row in nearby:
                if (not conflicting_units(item.address, row["address"])
                        and metres(item.location, (row["lat"], row["lng"])) <= 65
                        and similar_name(name, text_key(row["name"]))):
                    item.reason = f"Check similar nearby OSM restaurant {row['id']}"
                    break
        unit = UNIT.search(item.address)
        key = (name, street, text_key(unit[1]) if unit else "")
        if key in seen_new:
            item.reason = f"Check duplicate municipal location against {seen_new[key]}"
        if item.reason:
            review.append(item.to_row())
        else:
            seen_new[key] = item.id
            additions.append(item.to_row())
    duplicates = []
    for group in by_name.values():
        for i, left in enumerate(group):
            for right in group[i + 1:]:
                a, b = street_key(left["address"]), street_key(right["address"])
                if (a and b and a != b) or conflicting_units(left["address"], right["address"]):
                    continue
                if metres((left["lat"], left["lng"]), (right["lat"], right["lng"])) <= 25:
                    duplicates.append([left["id"], right["id"]])
    return {"matches": matches, "additions": additions, "review": review, "osm_duplicate_pairs": duplicates}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("osm", "boundaries", "toronto-licences", "dinesafe", "mississauga", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--checked", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    osm = json.loads(args.osm.read_text(encoding="utf-8"))
    boundaries = {name: prep(shape(value)) for name, value in
                  json.loads(args.boundaries.read_text(encoding="utf-8")).items()}
    toronto, toronto_counts = toronto_candidates(args.toronto_licences, args.dinesafe, args.checked)
    mississauga, mississauga_counts = mississauga_candidates(args.mississauga, "2025 employment survey")
    inputs = {
        "Toronto": (toronto, toronto_counts, [
            "https://open.toronto.ca/dataset/municipal-licensing-and-standards-business-licences-and-permits/",
            "https://open.toronto.ca/dataset/dinesafe/",
        ], "https://open.toronto.ca/open-data-license/"),
        "Mississauga": (mississauga, mississauga_counts, [
            "https://opendata-mississauga.hub.arcgis.com/datasets/mississauga::2025-mississauga-business-directory",
        ], "https://mississauga.maps.arcgis.com/sharing/rest/content/items/961c790805c14d8da258ec91bf4117e3/data"),
    }
    result = {"checked_on": str(args.checked), "cities": {}}
    for city, (candidates, input_counts, sources, licence) in inputs.items():
        boundary = boundaries[city]
        scoped = [r for r in osm["restaurants"] if boundary.covers(Point(r["lng"], r["lat"]))]
        if len(scoped) != osm["counts"][city]:
            raise ValueError(f"OSM boundary counts do not match the snapshot for {city}.")
        city_result = reconcile(candidates, scoped, boundary)
        counts = dict(input_counts, osm=len(scoped), compared=len(candidates),
                      **{kind: len(rows) for kind, rows in city_result.items()})
        print(city, counts)
        result["cities"][city] = {"sources": sources, "licence": licence, "counts": counts, **city_result}
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
