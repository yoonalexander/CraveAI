"""Find existing catalog branches sharing municipal public phone evidence."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from pathlib import Path
import re

from scripts.build_restaurant_catalog import Extractor
from scripts.corroborate_municipal_candidates import excel_safe
from scripts.import_restaurant_catalog import SNAPSHOT, read_catalog_rows
from scripts.reconcile_restaurant_catalog import csv_rows, metres, street_key
from scripts.review_municipal_candidates import DATA, name_alias, review_inputs, unit_key
from scripts.stage_municipal_admissions import INITIAL, record_position

FIELDS = ("candidate_id", "name", "address", "city", "catalog_id", "catalog_name", "catalog_address",
          "distance_m", "name_matches", "street_matches", "unit_agreement", "osm_url")


def phones(value: str) -> set[str]:
    result = set()
    for part in re.split(r"[;,/]|\bext\.?\b", value or "", maxsplit=3, flags=re.I):
        digits = re.sub(r"\D", "", part)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if re.fullmatch(r"[2-9]\d{2}[2-9]\d{6}", digits) and digits not in {"4164567890", "4161234567", "9054567890"}:
            result.add(digits)
    return result


class CatalogPhones(Extractor):
    def __init__(self, active: dict):
        super().__init__()
        self.active = active

    def add(self, kind, id, tags, lat, lng):
        ident = f"osm:{kind}:{id}"
        if ident in self.active:
            branch_phones = phones(tags.get("phone", "")) | phones(tags.get("contact:phone", ""))
            if branch_phones:
                self.restaurants[ident] = {**self.active[ident], "phones": branch_phones,
                                           "unit": tags.get("addr:unit", ""), "osm_url": f"https://www.openstreetmap.org/{kind}/{id}"}


def review(args: argparse.Namespace) -> list[dict]:
    active = {r["id"]: r for r in read_catalog_rows(SNAPSHOT) if r["listed"]}
    pending = {r["candidate_id"] for r in csv_rows(args.ledger) if r["disposition"] == "pending"}
    licences, inspections, directory = review_inputs(args.licences, args.inspections, args.directory)
    extractor = CatalogPhones(active)
    extractor.apply_file(args.pbf, locations=True, idx="flex_mem")
    index = defaultdict(list)
    for place in extractor.restaurants.values():
        for number in place["phones"]:
            index[number].append(place)
    results = []
    for row in csv_rows(INITIAL):
        ident = row["candidate_id"]
        if ident not in pending:
            continue
        key = ident.partition(":")[2]
        if row["city"] == "Toronto":
            checked = inspections.get(row["official_record"], {})
            numbers = phones(checked.get("phone", "")) | phones(licences.get(key, {}).get("Business Phone", ""))
        else:
            numbers = phones(directory.get(key, {}).get("attributes", {}).get("BusinessPhone", ""))
        matches = {place["id"]: place for number in numbers if len(index[number]) == 1 for place in index[number]}
        for place in matches.values():
            distance = metres(record_position(row), (place["lat"], place["lng"]))
            if distance > 180:
                continue
            results.append({"candidate_id": ident, "name": row["name"], "address": row["address"], "city": row["city"],
                            "catalog_id": place["id"], "catalog_name": place["name"], "catalog_address": place["address"],
                            "distance_m": round(distance, 1), "name_matches": name_alias(row["name"]) == name_alias(place["name"]),
                            "street_matches": bool(place["address"] and street_key(row["address"]) == street_key(place["address"])),
                            "unit_agreement": unit_key(row["address"]) == unit_key("0 Road, " + place["unit"]),
                            "osm_url": place["osm_url"]})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pbf", "licences", "inspections", "directory", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=DATA / "gta-municipal-dispositions.csv")
    args = parser.parse_args()
    rows = review(args)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: excel_safe(v) for k, v in row.items()} for row in rows)
    print(f"{len({r['candidate_id'] for r in rows})} unique candidates with nearby shared-phone listings.")
    print(dict(Counter(r["city"] for r in rows)))


if __name__ == "__main__":
    main()
