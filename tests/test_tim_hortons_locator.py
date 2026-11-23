import json

from scripts.review_tim_hortons_locator import Directory, page_evidence


def test_directory_keeps_branch_address_with_its_link():
    directory = Directory()
    directory.feed(
        '<li><a href="/en/on/mississauga/800/">Tim Hortons</a> - '
        '800 Bancroft Drive, Mississauga ON L5V 2Y6</li>'
    )
    assert directory.entries == [('/en/on/mississauga/800/', '800 Bancroft Drive, Mississauga ON L5V 2Y6')]


def test_branch_verification_requires_address_unit_coordinates_and_hours():
    row = {"city": "Mississauga", "address": "800 BANCROFT DR, Unit 2", "latitude": "43.6", "longitude": "-79.6"}
    place = {"name": "Tim Hortons",
             "address": {"addressLocality": "Mississauga", "addressRegion": "ON", "streetAddress": "800 Bancroft Drive Unit 2"},
             "geo": {"latitude": 43.6, "longitude": -79.6},
             "openingHoursSpecification": [{"opens": "06:00", "closes": "22:00"}]}

    def page(**changes):
        return '<script type="application/ld+json">' + json.dumps({**place, **changes}) + '</script>'

    assert page_evidence(page(), row) == row["address"]
    assert not page_evidence(page() + "Temporarily closed", row)
    assert not page_evidence(page(), {**row, "address": "800 BANCROFT DR, Unit 3"})
    assert not page_evidence(page(geo={"latitude": 43.7, "longitude": -79.6}), row)
    assert not page_evidence(page(openingHoursSpecification=[]), row)
