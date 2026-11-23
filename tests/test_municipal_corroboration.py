import pytest

from scripts.corroborate_municipal_candidates import decide, find_matches, operator_confirmation, overture_address
from scripts.review_municipal_candidates import TORONTO_TYPE_UNCLEAR


def candidate(**changes):
    return {
        "city": "Toronto", "candidate_id": "toronto-licence:sample", "address": "5100 DUNDAS ST W, #6",
        "latitude": "43.64", "longitude": "-79.52", "outcome": "needs_confirmation",
        "name": "Example Bistro", "reason": TORONTO_TYPE_UNCLEAR, "source_date": "2026-08-01", **changes,
    }


def place(**changes):
    return {
        "id": "sample", "name": "Example Bistro", "confidence": 0.94, "basic_category": "restaurant",
        "operating_status": "open", "category_path": ["eat_and_drink", "restaurant"],
        "sources": [{"update_time": "2026-07-02T12:00:00Z"}], "latitude": 43.6401, "longitude": -79.52,
        "addresses": [{"country": "CA", "region": "CA-ON", "locality": "Etobicoke",
                       "freeform": "6-5100 Dundas Street West, Etobicoke ON M9A 1C2"}],
        **changes,
    }


def test_address_keeps_direction_and_unit():
    parsed = overture_address("6-5100 Dundas Street West, Etobicoke ON M9A 1C2")
    assert parsed.street == "5100 dundas st w"
    assert parsed.unit == "6"
    assert overture_address("5100 Dundas St W, Unit 9 & 10").unit != overture_address("5100 Dundas St W #910").unit
    assert overture_address("1177 Central Pky W, Unit 66") == overture_address("1177 Central Parkway W, Unit 66")


@pytest.mark.parametrize(("candidate_values", "place_values", "expected"), [
    ({}, {}, "corroborated_restaurant"),
    ({"address": "5100 DUNDAS ST E, #6"}, {}, "no_exact_match"),
    ({"address": "5100 DUNDAS ST W, #9"}, {}, "hold_unit"),
    ({"outcome": "possible_catalog_match"}, {}, "hold_catalog_match"),
    ({}, {"operating_status": "closed"}, "hold_operating_status"),
    ({}, {"operating_status": None}, "corroborated_by_inspection"),
    ({"reason": "Unverified inspection"}, {"operating_status": None}, "hold_freshness"),
    ({"source_date": "2024-01-01"}, {"operating_status": None}, "hold_freshness"),
    ({"city": "Mississauga"}, {"operating_status": None, "addresses": [
        {"country": "CA", "region": "ON", "locality": "Mississauga", "freeform": "5100 Dundas St W #6"},
    ]}, "hold_freshness"),
    ({}, {"sources": [{"dataset": "Overture", "property": "/properties/confidence", "update_time": "2026-11-11"}]}, "hold_freshness"),
    ({}, {"basic_category": "grocery_store"}, "hold_business_type"),
    ({}, {"basic_category": "casual_eatery", "primary_category": "diner", "category_path": []}, "corroborated_restaurant"),
    ({}, {"basic_category": "casual_eatery", "primary_category": "bakery", "category_path": []}, "hold_business_type"),
    ({}, {"sources": []}, "hold_freshness"),
    ({"source_date": "2024-01-01"}, {}, "hold_municipal_freshness"),
    ({}, {"latitude": 43.66}, "no_exact_match"),
])
def test_evidence_does_not_clear_an_unresolved_branch_identity(candidate_values, place_values, expected):
    row = candidate(**candidate_values)
    matches = find_matches(row, [place(**place_values)])
    status, _, _ = decide(row, matches, "2025-11-21", "2026-11-21", {})
    assert status == expected


def test_cuisine_suffix_requires_a_close_name_and_street_match():
    row = candidate(name="Example Place Indian")
    assert find_matches(row, [place(name="Example Place")])
    assert not find_matches(row, [place(name="Example Place", latitude=43.6408)])
    assert not find_matches(row, [place(name="Different Place")])


@pytest.mark.parametrize(("changes", "eligible"), [
    ({}, True),
    ({"address": "5100 Dundas St W, Unit 7"}, False),
    ({"address": "5100 Dundas St E, Unit 6"}, False),
    ({"checked_on": "2025-01-01"}, False),
    ({"signal": "contact"}, False),
])
def test_operator_evidence_requires_branch_and_service_signal(changes, eligible):
    evidence = {"city": "Toronto", "name": "Example Bistro", "address": "5100 Dundas St W, Unit 6",
                "checked_on": "2026-11-21", "signal": "hours", "url": "https://example.com", **changes}
    assert operator_confirmation(candidate(), evidence, "2025-11-21", "2026-11-21") is eligible
