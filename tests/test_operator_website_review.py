import json

from backend.services.menu_evidence import _MenuHTMLParser
from scripts.review_operator_websites import examine, has_service


def test_exact_structured_branch_and_unit():
    row = {"city": "Toronto", "name": "Sample Table", "address": "41 KING ST W, #2"}
    restaurant = {"@type": "Restaurant", "name": "Sample Table",
                  "address": {"addressRegion": "ON", "addressLocality": "Toronto", "streetAddress": "41 King Street West Unit 2"},
                  "openingHours": "Mo-Fr 11:00-21:00"}
    page = _MenuHTMLParser()
    page.feed('<script type="application/ld+json">' + json.dumps({"@graph": [restaurant]}) + '</script>')
    assert examine(page, row, "2026-11-21") == ("structured_branch", "hours")
    assert examine(page, {**row, "address": "41 KING ST W, #3"}, "2026-11-21") == ("no_exact_evidence", "")
    page.feed("<p>Temporarily closed</p>")
    assert examine(page, row, "2026-11-21") == ("closure_text", "")


def test_expired_special_hours_do_not_verify_service():
    restaurant = {"openingHoursSpecification": [{"opens": "10:00", "closes": "15:00", "validThrough": "2026-02-01"}]}
    assert not has_service(restaurant, "2026-11-21")
