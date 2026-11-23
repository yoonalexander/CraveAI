import csv

import pytest

from scripts.review_dinesafe_history import link_current, premises_unit, same_premises
from scripts.stage_municipal_admissions import checked_duplicate, current_city_match, verified_separate_units, verified_street_number


CANDIDATE = {"name": "Test Kitchen", "address": "10 MAIN ST W, #6", "latitude": "43.7", "longitude": "-79.5"}
INSPECTION = {"estId": "current-id", "oldEstId": "123", "estName": "Test Kitchen", "address": "10 Main St W Unit-6",
              "latitude": "43.7", "longitude": "-79.5", "inspectionDate": "2026-08-01", "inspectionStatus": "Pass"}


def test_archive_requires_matching_unit_and_direction():
    assert same_premises(CANDIDATE, "Test Kitchen", "10 Main Street W, Unit-6", "43.7", "-79.5", require_unit=True)
    assert not same_premises(CANDIDATE, "Test Kitchen", "10 Main St W", "43.7", "-79.5", require_unit=True)
    assert not same_premises(CANDIDATE, "Test Kitchen", "10 Main St W, Unit-7", "43.7", "-79.5", require_unit=True)
    assert not same_premises(CANDIDATE, "Test Kitchen", "10 Main St E, Unit-6", "43.7", "-79.5", require_unit=True)


def test_inspection_placeholders_and_simple_unit_punctuation():
    assert premises_unit("38 Forest Manor Rd Unit-D None") == "d"
    assert premises_unit("3165 Markham Rd, C-1") == premises_unit("3165 Markham Rd Unit-C1 M1X 0B5")
    assert premises_unit("352 Front St W Unit-105 None") != premises_unit("352 Front St W, #105-106")


def test_store_number_matches_with_or_without_hash():
    candidate = {**CANDIDATE, "name": "Starbucks Coffee 4205"}
    address = "10 Main St W Unit-6"
    assert same_premises(candidate, "Starbucks Coffee #4205", address, "43.7", "-79.5", require_unit=True)
    assert not same_premises(candidate, "Starbucks Coffee #4206", address, "43.7", "-79.5", require_unit=True)


def test_reviewed_street_number_keeps_street_unit_and_nearby_storefront():
    row = {**CANDIDATE, "city": "Mississauga"}
    evidence = {
        "address": "16 Main Street W, Unit 6",
        "street_number_review_reason": "The plaza records and ordering page confirm the branch.",
        "url": "https://orders.example.com/store",
        "supporting_urls": ["https://plaza.example.org/store", "https://city.example.net/permits"],
        "verified_storefront": {"lat": 43.7001, "lng": -79.5},
    }
    assert verified_street_number(row, evidence)
    assert not verified_street_number(row, {**evidence, "address": "16 Main St E, Unit 6"})
    assert not verified_street_number(row, {**evidence, "address": "16 Main St W, Unit 7"})
    assert not verified_street_number(row, {**evidence, "verified_storefront": {"lat": 43.702, "lng": -79.5}})
    assert not verified_street_number(row, {**evidence, "supporting_urls": []})


def test_staging_only_accepts_the_reviewed_inspection_address():
    candidate = {**CANDIDATE, "candidate_id": "toronto-licence:test", "city": "Toronto", "official_record": "current-id"}
    licences = {"test": {"Operating Name": "Test Kitchen", "Licence Address Line 1": candidate["address"],
                         "Category": "EATING OR DRINKING ESTABLISHMENT", "Cancel Date": ""}}
    review = {"reviewed_inspection_address": "10 Main St W Unit-107",
              "unit_review_reason": "The vendor directory links stall 6 to the same premises.",
              "supporting_urls": ["https://example.org/vendor"]}

    def check(inspection, operator=None):
        return current_city_match(candidate, licences, {"current-id": inspection}, {}, "2025-11-22",
                                  "2026-11-22", operator=operator)

    disputed = {**INSPECTION, "address": review["reviewed_inspection_address"]}
    assert not check(disputed)
    assert check(disputed, review)
    assert not check(disputed, {**review, "supporting_urls": []})
    assert not check({**disputed, "address": "10 Main St W Unit-108"}, review)
    assert not check({**disputed, "inspectionStatus": "Closed"}, review)


def test_nearby_listing_can_be_a_separately_inspected_unit():
    row = {**CANDIDATE, "city": "Toronto", "official_record": "current-id",
           "outcome": "possible_catalog_match", "related_id": "osm:node:1"}
    listed = {"osm:node:1": {"name": "Other Kitchen", "address": "", "lat": 43.7, "lng": -79.5}}
    operator = {"separate_inspections": {"osm:node:1": "other-id"},
                "supporting_urls": ["https://example.org/floor-plan"]}
    other = {**INSPECTION, "estName": "Other Kitchen", "address": "10 Main St W Unit-7"}

    def check(candidate, nearby_inspection):
        return verified_separate_units(candidate, operator, {"current-id": INSPECTION, "other-id": nearby_inspection},
                                       listed, "2025-11-22", "2026-11-22")

    assert check(row, other)
    assert not check(row, {**other, "address": INSPECTION["address"]})
    assert not check(row, {**other, "inspectionStatus": "Closed"})
    assert not check({**row, "related_id": "osm:node:1 | osm:node:2"}, other)


def test_current_link_checks_latest_status_and_all_claims(tmp_path):
    path = tmp_path / "current.csv"

    def link(extra_row=None):
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=INSPECTION)
            writer.writeheader()
            writer.writerow(INSPECTION)
            if extra_row:
                writer.writerow({**INSPECTION, **extra_row})
        return link_current(path, {"current-id": CANDIDATE}, "2025-11-21", "2026-11-21")

    assert link() == {"123": (CANDIDATE, "2026-08-01")}
    assert not link({"inspectionStatus": "Closed"})
    assert not link({"estId": "another-premises"})


def test_duplicate_can_use_a_separately_verified_storefront_point():
    row = {**CANDIDATE, "candidate_id": "toronto-licence:test", "related_id": "", "outcome": "needs_confirmation"}
    existing = {"osm:node:1": {"name": "Test Kitchen", "address": "", "lat": 43.7015, "lng": -79.5}}
    evidence = {
        "catalog_id": "osm:node:1", "checked_on": "2026-11-22",
        "reason": "Operator identifies this branch and the storefront map supplies a precise point.",
        "verified_branch_address": row["address"],
        "verified_storefront": {"lat": 43.7015, "lng": -79.5},
        "source_urls": ["https://example.org/operator", "https://example.net/locator",
                        "https://openstreetmap.org/node/1"],
    }
    assert checked_duplicate(row, evidence, existing, "2025-11-22", "2026-11-22") == "osm:node:1"
    for change in (
        {"verified_storefront": {"lat": 43.7, "lng": -79.5}},
        {"verified_branch_address": "10 MAIN ST W, #7"},
        {"source_urls": evidence["source_urls"][:2]},
    ):
        with pytest.raises(ValueError, match="Invalid duplicate follow-up"):
            checked_duplicate(row, {**evidence, **change}, existing, "2025-11-22", "2026-11-22")


def test_indoor_duplicate_requires_exact_inspection_and_branch_phone():
    row = {**CANDIDATE, "candidate_id": "toronto-licence:test", "related_id": "",
           "outcome": "supported_addition", "city": "Toronto", "official_record": "current-id"}
    existing = {"osm:node:1": {"name": row["name"], "address": "10 Main St W", "lat": 43.7015, "lng": -79.5}}
    evidence = {
        "catalog_id": "osm:node:1", "checked_on": "2026-11-22",
        "reason": "The directory and floor plan identify the branch in the same building.",
        "verified_branch_address": row["address"], "reviewed_inspection_address": INSPECTION["address"],
        "verified_phone": "4165550101",
        "source_urls": ["https://example.org/operator", "https://example.net/locator",
                        "https://openstreetmap.org/node/1"],
    }

    def check(inspection, details=evidence):
        return checked_duplicate(row, details, existing, "2025-11-22", "2026-11-22",
                                 inspections={"current-id": inspection})

    inspection = {**INSPECTION, "phone": "4165550101"}
    assert check(inspection) == "osm:node:1"
    for changed_inspection in ({**inspection, "phone": "4165550102"},
                               {**inspection, "inspectionStatus": "Closed"},
                               {**inspection, "address": "10 Main St W Unit-26"}):
        with pytest.raises(ValueError, match="Invalid duplicate follow-up"):
            check(changed_inspection)
    with pytest.raises(ValueError, match="Invalid duplicate follow-up"):
        check(inspection, {**evidence, "verified_branch_address": "10 MAIN ST W, #7"})
