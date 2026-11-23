"""Recover official Toronto venue categories by linking current and archived DineSafe IDs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timedelta
from io import TextIOWrapper
import json
from pathlib import Path
import re
from zipfile import ZipFile

from scripts.corroborate_municipal_candidates import SUPPORTED, excel_safe
from scripts.reconcile_restaurant_catalog import EATING, POSTAL_CODE, TAKEOUT, csv_rows, metres, street_key, text_key
from scripts.review_municipal_candidates import (
    MIXED_VENUE, NON_RESTAURANT, TORONTO_TYPE_UNCLEAR, branch_name, unit_key,
)

ARCHIVE_FIELDS = ("dinesafe_legacy_id", "dinesafe_archive_type", "dinesafe_archive_inspection", "dinesafe_current_inspection", "conflict_source")
ELIGIBLE_TYPES = {"Restaurant", "Food Take Out"}
TYPE_AGREEMENT = {
    "Supermarket": {"grocery_store", "supermarket"},
    "Food Store (Convenience/Variety)": {"convenience_store"},
    "Butcher Shop": {"butcher_shop"},
    "Fish Shop": {"fishmonger"},
    "Food Caterer": {"caterer", "catering"},
}
EXCLUDED = "excluded_by_consistent_type"
CONFIRMED = "corroborated_by_dinesafe_history"
CLOSED = {"Closed", "Temporarily Not Operating"}
RECHECK = {"no_exact_match", "hold_business_type", "hold_freshness"}
MIXED_NAME = re.compile(r"\b(?:fine foods|food world|gelateria|bubble tea|espresso|dessert|baskin robbins|"
                        r"gong cha|chatime|second cup|residence inn|bingo|ktv|billiards|barista|wine bar)\b", re.I)


def archive_date(value: str) -> date:
    return datetime.strptime(value, "%m/%d/%Y").date() if "/" in value else date.fromisoformat(value)


def premises_unit(address: str) -> str:
    address = re.sub(r"(?i)\s+none\s*$", "", POSTAL_CODE.sub("", address))
    unit = unit_key(re.sub(r"(?i)\b(unit|apt|suite)\s*-\s*", r"\1 ", address))
    # Removing the separator in a letter-and-number unit preserves its components.
    return re.sub(r"^([a-z]) (\d+[a-z]?)$", r"\1\2", unit)


def same_premises(candidate: dict, name: str, address: str, lat: str, lng: str, *, require_unit: bool) -> bool:
    street = street_key(candidate["address"])
    if not street or street != street_key(address):
        return False
    # The licence can omit the hash that DineSafe puts before the same store number.
    if branch_name(candidate["name"]) != branch_name(name) and text_key(candidate["name"]) != text_key(name):
        return False
    expected = premises_unit(candidate["address"])
    actual = premises_unit(address)
    if expected != actual and (require_unit or (expected and actual)):
        return False
    try:
        return metres((float(candidate["latitude"]), float(candidate["longitude"])), (float(lat), float(lng))) <= 100
    except (TypeError, ValueError):
        return False


def link_current(path: Path, candidates: dict, cutoff: str, day: str) -> dict:
    latest = {}
    legacy_ids = defaultdict(set)
    for row in csv_rows(path):
        current_id, old_id = row["estId"], row["oldEstId"]
        if current_id and old_id:
            legacy_ids[old_id].add(current_id)
        if current_id not in candidates:
            continue
        ranking = (row["inspectionDate"], row["inspectionStatus"] in CLOSED)
        if current_id not in latest or ranking > latest[current_id][0]:
            latest[current_id] = (ranking, row)
    result = {}
    for current_id, (_, row) in latest.items():
        if (row["inspectionStatus"] in {"Pass", "Conditional Pass"}
                and cutoff <= row["inspectionDate"] <= day
                and legacy_ids[row["oldEstId"]] == {current_id}
                and same_premises(candidates[current_id], row["estName"], row["address"], row["latitude"], row["longitude"], require_unit=False)):
            result[row["oldEstId"]] = (candidates[current_id], row["inspectionDate"])
    return result


def latest_archive(path: Path, linked: dict) -> dict:
    result = defaultdict(dict)
    latest_date = {}
    with ZipFile(path) as archive:
        member, = [name for name in archive.namelist() if Path(name).name == "dinesafe_hist_2023.csv"]
        with archive.open(member) as binary, TextIOWrapper(binary, encoding="utf-8-sig", errors="replace") as text:
            for row in csv.DictReader(text):
                legacy_id = row["Establishment ID"]
                if legacy_id not in linked:
                    continue
                inspected = archive_date(row["Inspection Date"])
                if inspected >= latest_date.get(legacy_id, date.min):
                    if inspected != latest_date.get(legacy_id):
                        result[legacy_id].clear()
                        latest_date[legacy_id] = inspected
                    key = (row["Establishment Type"], row["Establishment Name"], row["Establishment Address"], row["Latitude"], row["Longitude"])
                    result[legacy_id][key] = inspected
    return result


def matching_licence(candidate: dict, licence: dict) -> bool:
    unit = premises_unit(licence["Licence Address Line 1"])
    return (not licence["Cancel Date"].strip() and licence["Category"] in {EATING, TAKEOUT}
            and branch_name(licence["Operating Name"]) == branch_name(candidate["name"])
            and street_key(licence["Licence Address Line 1"]) == street_key(candidate["address"])
            and (not unit or unit == premises_unit(candidate["address"])))


def review(ledger: Path, prior: Path, current: Path, historical: Path, licences: Path,
           checked_on: date, conflicts: dict) -> list[dict]:
    municipal = {row["candidate_id"]: row for row in csv_rows(ledger)}
    rows = list(csv_rows(prior))
    candidates = defaultdict(list)
    for row in rows:
        original = municipal[row["candidate_id"]]
        if original["city"] == "Toronto" and original["reason"] == TORONTO_TYPE_UNCLEAR and row["corroboration"] in RECHECK:
            candidates[original["official_record"]].append(original)
    unique = {premise: group[0] for premise, group in candidates.items() if premise and len(group) == 1}
    linked = link_current(current, unique, (checked_on - timedelta(days=365)).isoformat(), checked_on.isoformat())
    history = latest_archive(historical, linked)
    licence_rows = {row["Licence No."]: row for row in csv_rows(licences)}
    by_id = {row["candidate_id"]: row for row in rows}
    if len(by_id) != len(rows) or conflicts.keys() - by_id.keys():
        raise ValueError("Expected unique candidate IDs and conflicts tied to the input ledger.")
    for legacy_id, (candidate, current_date) in linked.items():
        records = history.get(legacy_id, {})
        if len(records) != 1:
            continue
        (category, name, address, lat, lng), inspected = next(iter(records.items()))
        licence = licence_rows.get(candidate["candidate_id"].partition(":")[2])
        if not licence or not matching_licence(candidate, licence) or not same_premises(candidate, name, address, lat, lng, require_unit=True):
            continue
        row = by_id[candidate["candidate_id"]]
        row.update(dinesafe_legacy_id=legacy_id, dinesafe_archive_type=category,
                   dinesafe_archive_inspection=inspected.isoformat(), dinesafe_current_inspection=current_date)
        if (category in ELIGIBLE_TYPES and row["corroboration"] != "hold_business_type"
                and set(licence["Endorsements"].split(";")) - {""} == {"EATING/DRINKING"}
                and not (MIXED_VENUE.search(name) or NON_RESTAURANT.search(name) or MIXED_NAME.search(name))):
            row.update(corroboration=CONFIRMED,
                       reason="DineSafe classifies this same premises as restaurant or takeout in 2023. Its current record has a recent passing inspection and matching licence.")
        elif (row["corroboration"] == "hold_business_type"
              and row["primary_category"] in TYPE_AGREEMENT.get(category, ())):
            row.update(corroboration=EXCLUDED,
                       reason="The historical DineSafe and independent Overture classifications agree on an out-of-scope business type.")
    for ident, conflict in conflicts.items():
        by_id[ident].update(corroboration="hold_source_conflict", reason=conflict["reason"], conflict_source=conflict["url"])
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ledger", "prior", "current", "historical", "licences", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--checked-on", type=date.fromisoformat, required=True)
    parser.add_argument("--conflicts", type=Path)
    args = parser.parse_args()
    conflicts = json.loads(args.conflicts.read_text(encoding="utf-8")) if args.conflicts else {}
    rows = review(args.ledger, args.prior, args.current, args.historical, args.licences, args.checked_on, conflicts)
    fields = list(dict.fromkeys((*rows[0], *ARCHIVE_FIELDS)))
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: excel_safe(v) for k, v in row.items()} for row in rows)
    print(dict(sorted(Counter(row["corroboration"] for row in rows).items())))
    print("Supported additions:", sum(row["corroboration"] in (SUPPORTED | {CONFIRMED}) for row in rows))


if __name__ == "__main__":
    main()
