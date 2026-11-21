import asyncio

import httpx
import pytest

from backend.services import restaurant_retrieval
from backend.services.chat_catalog import merge_catalog_candidates
from backend.services.dish_budget import BUDGET_CONSTRAINT_ID, parse_dish_budget
from backend.services.evidence_ranker import _lexical_assessments, rank_evidence_candidates
from backend.services.recommendation_models import CravingIntent, EvidenceItem, PublishedMenuPrice


@pytest.mark.parametrize(("query", "option", "amount", "channel", "expected"), [
    ("Twelve-inch pepperoni pizza under $15.", "10 inch", 1200, "published_menu", False),
    ("Twelve-inch pepperoni pizza under $15.", "12 inch", 1425, "published_menu", True),
    ("Grilled six-piece gyoza under $15", "Grilled 6 pieces", 1550, "dine_in", False),
    ("Grilled six-piece gyoza under $15", "Deep-fried 6 pieces", 1450, "dine_in", False),
    ("Grilled gyoza under $16", "Grilled 6 pieces", 1550, "dine_in", True),
    ("Grilled gyoza under $16", "Deep-fried 3 pieces", 800, "dine_in", False),
    ("Gyoza for pickup at most CAD 8", "3 pieces", 800, "pickup", True),
    ("Gyoza for delivery at most CAD 8", "3 pieces", 800, "pickup", False),
    ("Gyoza under US$10", "3 pieces", 800, "dine_in", False),
    ("Gyoza under $8.00", "3 pieces", 800, "dine_in", False),
    ("Gyoza at most $8.00", "3 pieces", 800, "dine_in", True),
])
def test_budget_requires_the_matching_price_option(query, option, amount, channel, expected):
    dish = "Pepperoni Pizza" if "pizza" in query else "Pork Gyoza"
    budget = parse_dish_budget(query)
    assert budget is not None
    assert budget.accepts(PublishedMenuPrice(option=option, amount_cents=amount, currency="CAD"), dish, channel) == expected


def test_strict_budget_cannot_borrow_price_from_another_dish():
    intent = CravingIntent(
        summary="Spicy noodle soup under $15",
        constraints=[
            {"id": "dish", "dimension": "dish_type", "value": "noodle soup", "polarity": "include", "strength": "required"},
            {"id": "spicy", "dimension": "taste", "value": "spicy", "polarity": "include", "strength": "required"},
            {"id": BUDGET_CONSTRAINT_ID, "dimension": "price", "value": "within budget", "polarity": "include", "strength": "required"},
        ],
        candidate_dishes=[], search_queries=[],
    )
    def evidence(label, amount, kind="official_menu"):
        return EvidenceItem(
            id=label, label=label, kind=kind, quality=1,
            declared_constraint_ids=[BUDGET_CONSTRAINT_ID],
            prices=[PublishedMenuPrice(amount_cents=amount, currency="CAD")] if amount else [],
        ).model_dump()

    candidates = [{"place_id": "osm:node:1", "name": "Noodle Place", "evidence": [
        evidence("Spicy noodle soup", 2000), evidence("Clear noodle soup", 900),
        evidence("Spicy rice", 1000), evidence("Spicy noodle soup from Google", 900, "provider_query"),
    ]}]
    budget = parse_dish_budget("Spicy noodle soup under $15")
    assessments = _lexical_assessments(intent, candidates)
    assert not rank_evidence_candidates(intent, candidates, assessments, budget=budget)["recommendations"]
    candidates[0]["evidence"].append(evidence("Spicy chicken noodle soup", 1400))
    assessments = _lexical_assessments(intent, candidates)
    results = rank_evidence_candidates(intent, candidates, assessments, budget=budget)["recommendations"]
    assert results[0]["matching_dishes"] == ["Spicy chicken noodle soup"]
    assert "CA$14.00" in results[0]["reason"]


def test_merge_keeps_provider_alternatives_and_only_combines_same_branch():
    local = {"place_id": "osm:node:1", "name": "Thai Kitchen", "lat": 43.65, "lng": -79.38,
             "address": "12 Main Street", "evidence": [{"id": "pending", "label": "Pad Thai"}]}
    same = dict(local, place_id="google-one", evidence=[])
    different = dict(local, place_id="google-two", address="14 Main Street", evidence=[])
    another = dict(local, place_id="google-three", name="Thai Pantry", evidence=[])
    merged = merge_catalog_candidates([same, different, another], [local])
    assert [place["place_id"] for place in merged] == ["google-one", "google-two", "google-three"]
    assert merged[0]["evidence"][0]["id"] == "google-one:e1"
    assert not merged[1]["evidence"]


def test_count_measures_each_google_http_attempt(monkeypatch):
    intent = CravingIntent(summary="noodles", constraints=[], candidate_dishes=[], search_queries=[
        {"text": "ramen", "constraint_ids": []}, {"text": "pho", "constraint_ids": []},
    ])
    urls = []
    async def dispatch(request):
        urls.append(request.url.path)
        return httpx.Response(503)

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **options: original(
        transport=httpx.MockTransport(dispatch), **options,
    ))
    monkeypatch.setattr("backend.services.places.GOOGLE_PLACES_API_KEY", "fixture")
    monkeypatch.setattr(restaurant_retrieval, "get_settings", lambda: type("Settings", (), {"GOOGLE_API_KEY": "fixture"})())
    count = restaurant_retrieval.PlacesRequestCount()
    asyncio.run(restaurant_retrieval.retrieve_candidate_restaurants(
        intent, {"lat": 43.65, "lng": -79.38}, places_count=count,
    ))
    assert count.attempts == len(urls) == 4
