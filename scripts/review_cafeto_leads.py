"""Find unresolved Toronto branches with matching CaféTO records for follow-up."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
import json
from pathlib import Path

from scripts.corroborate_municipal_candidates import excel_safe
from scripts.reconcile_restaurant_catalog import csv_rows, metres, street_key
from scripts.review_dinesafe_history import premises_unit
from scripts.review_municipal_candidates import DATA, branch_name, review_inputs
from scripts.stage_municipal_admissions import INITIAL, current_city_match, record_position

FIELDS = ("candidate_id", "name", "address", "cafeto_record", "cafeto_address", "patio_type",
          "distance_m", "current_city_records_match", "cafeto_licence_active", "review_status")


def review(args: argparse.Namespace) -> list[dict]:
    proposals = {r["candidate_id"] for r in csv_rows(args.ledger) if r["disposition"] == "pending"}
    city_records = review_inputs(args.licences, args.inspections, args.directory)
    licences = city_records[0]
    cutoff = (args.checked_on - timedelta(days=365)).isoformat()
    day = args.checked_on.isoformat()
    by_branch = defaultdict(list)
    for row in csv_rows(args.cafeto):
        name, address = row["OPERATOR_NAME"], row["BUSINESS_ADDRESS"]
        street = street_key(address)
        if street and row["geometry"]:
            by_branch[(branch_name(name), street, premises_unit(address))].append(row)
    result = []
    for candidate in csv_rows(INITIAL):
        ident, name, address = candidate["candidate_id"], candidate["name"], candidate["address"]
        if ident not in proposals or candidate["city"] != "Toronto":
            continue
        key = (branch_name(name), street_key(address), premises_unit(address))
        for permit in by_branch[key]:
            points = json.loads(permit["geometry"])["coordinates"]
            distance = min(metres(record_position(candidate), (lat, lng)) for lng, lat in points)
            if distance > 100:
                continue
            licence = licences.get(permit["LICENCE_NUMBER"])
            result.append({
                "candidate_id": ident, "name": name, "address": address, "cafeto_record": permit["LICENCE_NUMBER"],
                "cafeto_address": permit["BUSINESS_ADDRESS"], "patio_type": permit["CATEGORY"],
                "distance_m": round(distance, 1),
                "current_city_records_match": current_city_match(candidate, *city_records, cutoff, day),
                "cafeto_licence_active": bool(licence and not licence["Cancel Date"].strip()),
                "review_status": "Check current public meal service and catalog identity",
            })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("licences", "inspections", "directory", "cafeto", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=DATA / "gta-municipal-dispositions.csv")
    parser.add_argument("--checked-on", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    records = review(args)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: excel_safe(v) for k, v in row.items()} for row in records)
    print(f"{len({r['candidate_id'] for r in records})} unique candidates across {len(records)} records")
    print(dict(Counter(r["patio_type"] for r in records)))


if __name__ == "__main__":
    main()
