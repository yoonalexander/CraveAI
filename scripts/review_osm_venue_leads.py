"""Find candidate leads in OSM amenity types outside the original catalog import."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from pathlib import Path

from scripts.build_restaurant_catalog import Extractor
from scripts.corroborate_municipal_candidates import excel_safe
from scripts.reconcile_restaurant_catalog import csv_rows, metres, street_key
from scripts.review_municipal_candidates import DATA, branch_name, unit_key
from scripts.stage_municipal_admissions import INITIAL, record_position

FIELDS = ("candidate_id", "name", "address", "osm_id", "osm_name", "osm_address", "amenity", "food",
          "cuisine", "distance_m", "address_evidence", "operator_url", "osm_url")


class VenueExtractor(Extractor):
    def __init__(self):
        super().__init__({"cafe", "pub", "bar", "food_court", "biergarten"})

    def add(self, kind, id, tags, lat, lng):
        super().add(kind, id, tags, lat, lng)
        row = self.restaurants[f"osm:{kind}:{id}"]
        row.update(amenity=tags["amenity"], food=tags.get("food", ""), unit=tags.get("addr:unit", ""))


def review(pbf: Path, ledger: Path) -> list[dict]:
    pending = {row["candidate_id"] for row in csv_rows(ledger) if row["disposition"] == "pending"}
    extractor = VenueExtractor()
    extractor.apply_file(pbf, locations=True, idx="flex_mem")
    by_name = defaultdict(list)
    for venue in extractor.restaurants.values():
        by_name[branch_name(venue["name"])].append(venue)
    results = []
    for row in csv_rows(INITIAL):
        ident = row["candidate_id"]
        if ident not in pending:
            continue
        for venue in by_name[branch_name(row["name"])]:
            distance = metres(record_position(row), (venue["lat"], venue["lng"]))
            street_match = bool(venue["address"] and street_key(row["address"]) == street_key(venue["address"]))
            unit = unit_key(row["address"])
            if not ((street_match and distance <= 100) or (not venue["address"] and distance <= 30)):
                continue
            _, kind, ref = venue["id"].split(":")
            results.append({"candidate_id": ident, "name": row["name"], "address": row["address"],
                            "osm_id": venue["id"], "osm_name": venue["name"], "osm_address": venue["address"],
                            "amenity": venue["amenity"], "food": venue["food"], "cuisine": venue["cuisine"],
                            "distance_m": round(distance, 1), "operator_url": venue["website"],
                            "address_evidence": "exact" if street_match and unit == venue["unit"].casefold() else "check",
                            "osm_url": f"https://www.openstreetmap.org/{kind}/{ref}"})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=DATA / "gta-municipal-dispositions.csv")
    args = parser.parse_args()
    rows = review(args.pbf, args.ledger)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: excel_safe(v) for k, v in row.items()} for row in rows)
    print(f"{len({row['candidate_id'] for row in rows})} candidate leads across {len(rows)} map matches")
    print(dict(Counter(row["amenity"] for row in rows)))


if __name__ == "__main__":
    main()
