"""Validate municipal proposals and prepare an additive catalog batch."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
import json
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import create_engine, select

from backend.models import CatalogRestaurant
from backend.services import restaurant_catalog
from scripts.corroborate_municipal_candidates import SUPPORTED, excel_safe, operator_confirmation
from scripts.import_restaurant_catalog import ADMISSIONS, SNAPSHOT, TABLE, read_catalog_rows, refresh_catalog
from scripts.reconcile_restaurant_catalog import csv_rows, metres, street_key
from scripts.review_dinesafe_history import CONFIRMED, EXCLUDED, matching_licence, premises_unit, same_premises
from scripts.review_municipal_candidates import DATA, branch_name, directory_matches, review_inputs, unit_key

INITIAL = DATA / "gta-municipal-candidate-review.csv"
REVIEW = DATA / "gta-municipal-dinesafe-review.csv"
FINAL = {"already_listed", "duplicate_candidate", "inactive_record", "out_of_scope"}


def record_position(row: dict) -> tuple[float, float]:
    return float(row["latitude"]), float(row["longitude"])


def duplicate_keys(name: str, address: str) -> tuple[str, str, str]:
    return branch_name(name), street_key(address), unit_key(address)


def verified_street_number(row: dict, operator: dict) -> bool:
    point = operator.get("verified_storefront")
    old_number, _, old_street = street_key(row["address"]).partition(" ")
    new_number, _, new_street = street_key(operator["address"]).partition(" ")
    sources = [urlsplit(url) for url in [operator["url"], *operator.get("supporting_urls", [])]]
    return bool(
        row["city"] == "Mississauga" and isinstance(point, dict)
        and operator.get("street_number_review_reason", "").strip()
        and old_number != new_number and old_street and old_street == new_street
        and unit_key(row["address"]) == unit_key(operator["address"])
        and len({source.hostname for source in sources}) >= 3
        and {"lat", "lng"} <= point.keys()
        and metres(record_position(row), (float(point["lat"]), float(point["lng"]))) <= 25
    )


def checked_duplicate(row: dict, evidence: dict, listed: dict, cutoff: str, day: str,
                      *, candidates: dict | None = None, inspections: dict | None = None) -> str:
    target = evidence["catalog_id"]
    place = listed.get(target)
    urls = [urlsplit(url) for url in evidence["source_urls"]]
    confirmed_street = street_key(evidence.get("verified_branch_address", ""))
    address_verified = bool(place and confirmed_street and confirmed_street in {
        street_key(row["address"]), street_key(place["address"]),
    })
    maximum_distance = 150 if address_verified else 35
    if (not place or not cutoff <= date.fromisoformat(evidence["checked_on"]).isoformat() <= day
            or not evidence["reason"].strip() or len(urls) < 2
            or any(url.scheme != "https" or not url.hostname or url.username for url in urls)):
        raise ValueError(f"Invalid duplicate follow-up for {row['candidate_id']}.")
    pin = place["lat"], place["lng"]
    distance = metres(record_position(row), pin)
    linked = row["outcome"] == "possible_catalog_match" and target in row["related_id"].split(" | ")
    verified_point = evidence.get("verified_storefront")
    exact_storefront = (
        verified_point and row["outcome"] in {"needs_confirmation", "possible_catalog_match"}
        and confirmed_street == street_key(row["address"])
        and unit_key(evidence["verified_branch_address"]) == unit_key(row["address"])
        and branch_name(row["name"]) == branch_name(place["name"])
        and len({url.hostname.removeprefix("www.") for url in urls}) >= 3
        and distance <= 300
        and metres(pin, (verified_point["lat"], verified_point["lng"])) <= 25
    )
    municipal_target = (candidates or {}).get(target, {})
    inspection = (inspections or {}).get(row.get("official_record"))
    same_inspected_branch = (
        row.get("city") == municipal_target.get("city") == "Toronto"
        and inspection and row["official_record"] == municipal_target.get("official_record")
        and cutoff <= inspection["inspectionDate"] <= day
        and inspection["inspectionStatus"] in {"Pass", "Conditional Pass"}
        and confirmed_street == street_key(row["address"]) == street_key(place["address"])
        and bool(unit_key(place["address"]))
        and duplicate_keys(place["name"], place["address"])
        == duplicate_keys(row["name"], evidence.get("verified_branch_address", ""))
        and same_premises(municipal_target, inspection["estName"], inspection["address"],
                          inspection["latitude"], inspection["longitude"], require_unit=True)
        and distance <= 100
    )
    same_reviewed_indoor_branch = (
        row.get("city") == "Toronto" and target.startswith("osm:")
        and inspection and evidence.get("reviewed_inspection_address") == inspection["address"]
        and cutoff <= inspection["inspectionDate"] <= day
        and inspection["inspectionStatus"] in {"Pass", "Conditional Pass"}
        and confirmed_street == street_key(row["address"]) == street_key(place["address"])
        and unit_key(row["address"]) and not unit_key(place["address"])
        and unit_key(evidence["verified_branch_address"]) == unit_key(row["address"])
        and branch_name(place["name"]) == branch_name(row["name"])
        and evidence.get("verified_phone") and evidence["verified_phone"] == inspection.get("phone")
        and len({url.hostname.removeprefix("www.") for url in urls}) >= 3
        and same_premises({**row, "address": inspection["address"]}, inspection["estName"],
                          inspection["address"], inspection["latitude"], inspection["longitude"],
                          require_unit=True)
        and street_key(inspection["address"]) == confirmed_street
        and distance <= 250
    )
    if not (linked and distance <= maximum_distance or exact_storefront or same_inspected_branch
            or same_reviewed_indoor_branch):
        raise ValueError(f"Invalid duplicate follow-up for {row['candidate_id']}.")
    return target


def current_city_match(row: dict, licences: dict, inspections: dict, directory: dict,
                       cutoff: str, checked_on: str, *, operator: dict | None = None) -> bool:
    ident = row["candidate_id"].partition(":")[2]
    if row["city"] == "Mississauga":
        entry = directory.get(ident)
        if not entry:
            return False
        lat, lng = record_position(row)
        return directory_matches({**row, "lat": lat, "lng": lng}, entry)
    licence = licences.get(ident)
    inspection = inspections.get(row["official_record"])
    premise = row
    if inspection and operator:
        # Keep the licence and public stall address. Reconcile only the exact inspected address reviewed.
        reviewed_address = operator.get("reviewed_inspection_address")
        if (reviewed_address == inspection["address"] and operator.get("unit_review_reason")
                and operator.get("supporting_urls")
                and street_key(reviewed_address) == street_key(row["address"])):
            premise = {**row, "address": reviewed_address}
    return bool(licence and inspection and matching_licence(row, licence)
                and inspection["inspectionStatus"] in {"Pass", "Conditional Pass"}
                and inspection["inspectionDate"] <= checked_on
                and (operator or cutoff <= inspection["inspectionDate"])
                and same_premises(premise, inspection["estName"], inspection["address"],
                                  inspection["latitude"], inspection["longitude"], require_unit=False))


def verified_separate_units(row: dict, operator: dict, inspections: dict, listed: dict,
                            cutoff: str, day: str) -> bool:
    reviewed = operator.get("separate_inspections")
    if (row["city"] != "Toronto" or row["outcome"] != "possible_catalog_match"
            or not reviewed or set(reviewed) != set(row["related_id"].split(" | "))
            or not operator.get("supporting_urls")):
        return False
    street = street_key(row["address"])
    unit = premises_unit(row["address"])
    own = inspections.get(row["official_record"])
    if (not own or not street or not unit or not cutoff <= own["inspectionDate"] <= day
            or own["inspectionStatus"] not in {"Pass", "Conditional Pass"}
            or not same_premises(row, own["estName"], own["address"], own["latitude"], own["longitude"],
                                 require_unit=True)):
        return False
    for ident, premises_id in reviewed.items():
        place = listed.get(ident)
        other = inspections.get(premises_id)
        if not place or not other or premises_id == row["official_record"]:
            return False
        other_unit = premises_unit(other["address"])
        if (not cutoff <= other["inspectionDate"] <= day
                or other["inspectionStatus"] not in {"Pass", "Conditional Pass"}
                or not other_unit or other_unit == unit or street_key(other["address"]) != street
                or branch_name(other["estName"]) != branch_name(place["name"])
                or branch_name(other["estName"]) == branch_name(row["name"])
                or (place["address"] and street_key(place["address"]) != street)
                or metres(record_position(row), (place["lat"], place["lng"])) > 100):
            return False
    return True


def stage(args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    base = list(csv_rows(INITIAL))
    candidates = {r["candidate_id"]: r for r in base}
    review = {r["candidate_id"]: r for r in csv_rows(REVIEW)}
    if len(candidates) != len(base) or set(review) != {
        r["candidate_id"] for r in base if r["outcome"] in {"needs_confirmation", "possible_catalog_match"}
    }:
        raise ValueError("Candidate ledgers do not reconcile.")
    source = review_inputs(args.licences, args.inspections, args.directory)
    cutoff = (args.checked_on - timedelta(days=365)).isoformat()
    day = args.checked_on.isoformat()
    operator_followup = (json.loads(args.operator_followup.read_text(encoding="utf-8"))
                         if args.operator_followup else {})
    duplicate_followup = (json.loads(args.duplicate_followup.read_text(encoding="utf-8"))
                          if args.duplicate_followup else {})
    negative_followup = (json.loads(args.negative_followup.read_text(encoding="utf-8"))
                         if args.negative_followup else {})
    if (operator_followup.keys() | duplicate_followup.keys() | negative_followup.keys()) - {r["candidate_id"] for r in base}:
        raise ValueError("Follow-up includes IDs outside the review queue.")
    catalog = read_catalog_rows(SNAPSHOT)
    by_id = {r["id"]: r for r in catalog if r["listed"]}
    by_branch = defaultdict(list)
    for row in by_id.values():
        by_branch[duplicate_keys(row["name"], row["address"])].append(row)
    staged = []
    audit = []
    claims = defaultdict(list)
    for row in base:
        ident = row["candidate_id"]
        detail = review.get(ident, {})
        before = row["outcome"]
        corroboration = detail.get("corroboration", "")
        disposition = before if before in FINAL else "pending"
        reason = detail.get("reason") or row["reason"]
        linked_id = row["related_id"]
        source_urls = row["source_urls"]
        operator = operator_followup.get(ident)
        reviewed_number = bool(operator and operator.get("street_number_review_reason"))
        if reviewed_number and not verified_street_number(row, operator):
            raise ValueError(f"Invalid street number follow-up for {ident}.")
        operator_branch = {**row, "address": operator["address"]} if reviewed_number else row
        if operator and not operator_confirmation(operator_branch, operator, cutoff, day):
            raise ValueError(f"Invalid operator follow-up for {ident}.")
        public_address = operator.get("public_address") if operator else None
        if public_address and (street_key(public_address) != street_key(row["address"])
                               or not unit_key(public_address) or not operator.get("unit_review_reason")
                               or not operator.get("supporting_urls")):
            raise ValueError(f"Invalid public unit evidence for {ident}.")
        if reviewed_number:
            public_address = operator["address"]
        branch_keys = {
            duplicate_keys(name, address)
            for name in {row["name"], detail.get("overture_name", ""),
                         operator.get("public_name", "") if operator else ""} - {""}
            for address in {row["address"], public_address} - {None}
        }
        separate_units = bool(operator and verified_separate_units(row, operator, source[1], by_id, cutoff, day))
        if operator and operator.get("separate_inspections") and not separate_units:
            raise ValueError(f"Invalid separate-unit evidence for {ident}.")
        if operator:
            source_urls += " | " + operator["url"]
            for source_url in operator.get("supporting_urls", []):
                url = urlsplit(source_url)
                if url.scheme != "https" or not url.hostname or url.username is not None:
                    raise ValueError(f"Invalid supporting source for {ident}.")
                source_urls += " | " + source_url
        if detail.get("operator_checked_on"):
            source_urls += " | " + detail["operator_url"]
        if detail.get("conflict_source"):
            source_urls += " | " + detail["conflict_source"]
        if corroboration == EXCLUDED:
            disposition = "out_of_scope"
        if ident in by_id:
            disposition = "in_admission_manifest"
        if negative := negative_followup.get(ident):
            urls = [urlsplit(url) for url in negative["source_urls"]]
            if (disposition != "pending" or operator or ident in duplicate_followup
                    or negative["disposition"] not in {"inactive_record", "out_of_scope", "dropped_insufficient_evidence"}
                    or not cutoff <= date.fromisoformat(negative["checked_on"]).isoformat() <= day
                    or not negative["reason"].strip() or len(urls) < 2
                    or any(url.scheme != "https" or not url.hostname or url.username for url in urls)):
                raise ValueError(f"Invalid negative follow-up for {ident}.")
            disposition, reason = negative["disposition"], negative["reason"]
            source_urls += " | " + " | ".join(negative["source_urls"])
        if duplicate := duplicate_followup.get(ident):
            linked_id = checked_duplicate(row, duplicate, by_id, cutoff, day,
                                          candidates=candidates, inspections=source[1])
            if disposition != "pending":
                raise ValueError(f"Duplicate review conflicts with {ident} marked {disposition}.")
            disposition, reason = "already_listed", duplicate["reason"]
            source_urls += " | " + " | ".join(duplicate["source_urls"])
        if disposition == "pending":
            matches = {}
            for key in branch_keys:
                if not key[0] or not key[1]:
                    continue
                for place in by_branch[key]:
                    if metres(record_position(row), (place["lat"], place["lng"])) <= 125:
                        matches[place["id"]] = place
            if len(matches) == 1:
                disposition, linked_id = "already_listed", next(iter(matches))
                reason = "The active catalog matches the branch name, street address, unit and coordinates."
            elif len(matches) > 1:
                reason = "Several active records match this branch and require a duplicate review."
            elif (before == "supported_addition" or corroboration in SUPPORTED | {CONFIRMED}
                  or (operator and (before != "possible_catalog_match" or separate_units)
                      and corroboration != "hold_source_conflict")):
                if not current_city_match(row, *source, cutoff, day, operator=operator):
                    reason = "The current official export did not pass the branch and activity checks."
                elif corroboration == CONFIRMED and not operator:
                    reason = "Staging validated the current licence and inspection. Verify the archived category against current public service."
                else:
                    disposition = "staged_for_import"
                    website = detail.get("operator_url", "") if detail.get("operator_checked_on") else ""
                    if operator:
                        website = operator["url"]
                        reason = "The operator publishes service information for this exact branch, which also matches the city records."
                        if operator.get("unit_review_reason"):
                            reason += " " + operator["unit_review_reason"]
                        if reviewed_number:
                            reason = operator["street_number_review_reason"]
                        if separate_units:
                            linked_id = ""
                            reason += " Current inspections confirm distinct units for the nearby catalog listings."
                    if not website and row["city"] == "Mississauga" and before == "supported_addition":
                        website = source_urls.rsplit(" | ", 1)[-1]
                    listing = {"id": ident, "name": row["name"], "website": website, "checked_on": day}
                    if operator and operator.get("public_name"):
                        listing["name"] = operator["public_name"]
                    if public_address:
                        listing["address"] = public_address
                    elif operator and not unit_key(row["address"]) and unit_key(operator["address"]):
                        listing["address"] = operator["address"]
                    staged.append(listing)
                    for key in branch_keys:
                        claims[(row["city"], *key)].append(ident)
                    if row["city"] == "Toronto":
                        claims[(row["city"], row["official_record"])].append(ident)
        audit.append({
            "candidate_id": ident, "city": row["city"], "name": row["name"], "address": row["address"],
            "disposition": disposition, "reason": reason, "related_id": linked_id,
            "source_urls": source_urls, "initial_outcome": before, "corroboration": corroboration,
            "checked_on": day,
        })
    ambiguous = {ident for group in claims.values() if len(set(group)) > 1 for ident in group}
    for row in audit:
        if row["candidate_id"] in ambiguous:
            row.update(disposition="pending", reason="Another staged candidate claims the same branch or premises ID.")
    return [r for r in staged if r["id"] not in ambiguous], audit


def verify_batch(admissions_path: Path, staged: list[dict]) -> None:
    engine = create_engine("sqlite://")
    TABLE.create(engine)
    baseline = read_catalog_rows(SNAPSHOT)
    after = read_catalog_rows(SNAPSHOT, admissions_path)
    expected_ids = {row["id"] for row in after if row["listed"]}
    for rows in (baseline, after, after):
        with engine.begin() as connection:
            refresh_catalog(connection, rows)
    with engine.connect() as connection:
        assert set(connection.scalars(select(TABLE.c.id).where(TABLE.c.listed.is_(True)))) == expected_ids
        assert set(connection.scalars(select(TABLE.c.id))) == {r["id"] for r in baseline} | {r["id"] for r in after}
        wanted = {r["id"] for r in staged}
        for row in after:
            if row["id"] not in wanted:
                continue
            nearby = restaurant_catalog.catalog_area_query(row["lat"], row["lng"], 120, None)
            if nearby is None:
                raise ValueError(f"Coordinates fall outside the staged catalog for {row['id']}.")
            search = nearby.where(CatalogRestaurant.name.icontains(row["name"], autoescape=True))
            matches = connection.scalars(search.limit(restaurant_catalog.SUGGESTION_POOL_LIMIT))
            if row["id"] not in set(matches):
                raise ValueError(f"Staged catalog search failed for {row['id']}.")
    engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("licences", "inspections", "directory", "staged", "audit"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--operator-followup", type=Path, help="Reviewed operator branch evidence keyed by candidate ID")
    parser.add_argument("--duplicate-followup", type=Path, help="Reviewed duplicate evidence keyed by candidate ID")
    parser.add_argument("--negative-followup", type=Path, help="Reviewed inactive, out-of-scope, or unsupported candidates")
    parser.add_argument("--checked-on", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    staged, audit = stage(args)
    admitted = json.loads(ADMISSIONS.read_text(encoding="utf-8")) if ADMISSIONS.exists() else []
    args.staged.write_text(json.dumps(admitted + staged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verify_batch(args.staged, staged)
    with args.audit.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audit[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: excel_safe(value) for key, value in row.items()} for row in audit)
    print(dict(Counter(row["disposition"] for row in audit)))


if __name__ == "__main__":
    main()
