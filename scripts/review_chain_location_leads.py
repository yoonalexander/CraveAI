"""Match public chain-locator extracts to unresolved municipal branches."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path

from scripts.corroborate_municipal_candidates import excel_safe, overture_address
from scripts.reconcile_restaurant_catalog import csv_rows, metres, street_key
from scripts.review_municipal_candidates import DATA, branch_name, unit_key
from scripts.stage_municipal_admissions import INITIAL, record_position

FIELDS = ("candidate_id", "name", "address", "brand", "locator_address", "unit_agreement",
          "distance_m", "operator_url", "locator_reference", "locator_check_date", "feed")


def name_keys(name: str) -> set[str]:
    key = branch_name(name)
    if key in {"timhorton", "timhortons"}:
        return {"timhortons"}
    return {key} if key else set()


def load_points(paths: list[Path]) -> dict:
    index = defaultdict(list)
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for feature in data["features"]:
            prop = feature["properties"]
            geometry = feature.get("geometry")
            if (prop.get("addr:country") != "CA" or prop.get("addr:state") != "ON"
                    or not geometry or geometry["type"] != "Point"):
                continue
            lng, lat = geometry["coordinates"]
            if not (43.45 <= lat <= 43.87 and -79.85 <= lng <= -79.10):
                continue
            text = prop.get("addr:street_address") or prop.get("addr:full") or ""
            address = overture_address(text)
            keys = name_keys(prop.get("brand") or prop.get("name") or "")
            for key in keys:
                if address.street:
                    index[key, address.street].append((prop, text, address.unit, lat, lng, path.stem))
    return index


def review(ledger: Path, feeds: list[Path]) -> list[dict]:
    pending = {r["candidate_id"] for r in csv_rows(ledger) if r["disposition"] == "pending"}
    points = load_points(feeds)
    rows = []
    for candidate in csv_rows(INITIAL):
        ident, name, address = candidate["candidate_id"], candidate["name"], candidate["address"]
        if ident not in pending:
            continue
        unit = unit_key(address)
        for key in name_keys(name):
            for prop, located, located_unit, lat, lng, feed in points[key, street_key(address)]:
                distance = metres(record_position(candidate), (lat, lng))
                if distance > 100:
                    continue
                rows.append({
                    "candidate_id": ident, "name": name, "address": address,
                    "brand": prop.get("brand"), "locator_address": located,
                    "unit_agreement": "exact" if unit == located_unit else "check",
                    "distance_m": round(distance, 1), "operator_url": prop.get("website"),
                    "locator_reference": prop.get("ref"), "locator_check_date": prop.get("check_date"),
                    "feed": feed,
                })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", type=Path, action="append", required=True)
    parser.add_argument("--ledger", type=Path, default=DATA / "gta-municipal-dispositions.csv")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = review(args.ledger, args.feed)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: excel_safe(v) for k, v in row.items()} for row in rows)
    print(f"{len({r['candidate_id'] for r in rows})} unique candidates across {len(rows)} locator matches")


if __name__ == "__main__":
    main()
