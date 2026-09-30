"""Provider-shaped fixtures; no live Google calls or persisted provider content."""
import asyncio

import httpx
import pytest

from backend.services import places
from backend.services.usage_limits import DailyQuotaExceeded, UsageReservation


def restaurant(index, *, lat=43.7, rating=3.6):
    return {
        "place_id": f"place-{index}", "name": f"Restaurant {index}",
        "rating": rating, "types": ["restaurant"], "price_level": index % 2 + 1,
        "geometry": {"location": {"lat": lat, "lng": -79.4}},
    }


class FixtureClient:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    async def get(self, _url, *, params):
        self.requests.append(params)
        payload = next(self.pages)
        if isinstance(payload, Exception):
            raise payload
        return httpx.Response(200, json=payload, request=httpx.Request("GET", "https://provider.test"))


@pytest.fixture(autouse=True)
def provider_settings(monkeypatch):
    monkeypatch.setattr(places, "GOOGLE_PLACES_API_KEY", "test-google")
    monkeypatch.setattr(places, "PAGE_TOKEN_DELAY_SECONDS", 0)


def discover(monkeypatch, pages, **kwargs):
    client = FixtureClient(pages)
    monkeypatch.setattr(places.httpx, "AsyncClient", lambda **_kwargs: client)
    coverage = places.DiscoveryCoverage()
    results = asyncio.run(places.get_top_rated_nearby(43.7, -79.4, coverage=coverage, **kwargs))
    return results, coverage, client.requests


def test_dense_area_grows_from_twenty_to_sixty_and_keeps_unrated_places(monkeypatch):
    raw = [restaurant(index, rating=None if index == 59 else 3.6) for index in range(60)]
    results, coverage, requests = discover(monkeypatch, [
        {"status": "OK", "results": raw[:20], "next_page_token": "page2"},
        {"status": "OK", "results": raw[20:40], "next_page_token": "page3"},
        {"status": "OK", "results": raw[40:], "next_page_token": "unexpected-page4"},
    ])
    assert len(results) == len({place["place_id"] for place in results}) == 60
    assert any(place["rating"] is None for place in results)
    assert sum(place["price_level"] == 1 for place in results) == 30
    assert coverage.provider_requests == coverage.pages_loaded == 3
    assert coverage.partial_reason is None
    assert requests[0]["radius"] == 5000
    assert requests[1] == {"key": "test-google", "pagetoken": "page2"}
    assert requests[2] == {"key": "test-google", "pagetoken": "page3"}


def test_smaller_area_loads_remaining_page_without_widening(monkeypatch):
    results, coverage, _requests = discover(monkeypatch, [
        {"status": "OK", "results": [restaurant(i) for i in range(7)], "next_page_token": "page2"},
        {"status": "OK", "results": [restaurant(i) for i in range(7, 12)]},
    ])
    assert len(results) == 12  # Previously only the seven restaurants on page one.
    assert coverage.provider_requests == coverage.pages_loaded == 2


def test_pages_deduplicate_and_apply_exact_viewport(monkeypatch):
    raw = [restaurant(i) for i in range(10)]
    results, coverage, _requests = discover(monkeypatch, [
        {"status": "OK", "results": raw, "next_page_token": "page2"},
        {"status": "OK", "results": [raw[0], restaurant(10), restaurant(11, lat=44), {"place_id": "bad"}, None]},
    ], bounds={"north": 43.75, "south": 43.65, "east": -79.34, "west": -79.46})
    assert len(results) == len({item["place_id"] for item in results}) == 11
    assert "place-11" not in {item["place_id"] for item in results}
    assert coverage.provider_requests == 2


def test_page_token_activation_retries_once_and_counts_each_request(monkeypatch):
    reservations = []

    async def reserve():
        reservations.append(1)

    results, coverage, requests = discover(monkeypatch, [
        {"status": "OK", "results": [restaurant(i) for i in range(10)], "next_page_token": "page2"},
        {"status": "INVALID_REQUEST"},
        {"status": "OK", "results": [restaurant(10)]},
    ], before_request=reserve)
    assert len(results) == 11
    assert len(reservations) == len(requests) == coverage.provider_requests == 3
    assert coverage.pages_loaded == 2
    assert requests[1] == requests[2]


@pytest.mark.parametrize("failure", [
    {"status": "INVALID_REQUEST"}, {"status": "OVER_QUERY_LIMIT"},
    httpx.ReadTimeout("test"), {"status": "OK", "results": {}},
])
def test_later_page_failures_preserve_original_results(monkeypatch, failure):
    results, coverage, _requests = discover(monkeypatch, [
        {"status": "OK", "results": [restaurant(i) for i in range(10)], "next_page_token": "page2"},
        failure, failure,
    ])
    assert len(results) == 10
    assert coverage.partial_reason == "provider"
    assert coverage.provider_requests <= 3


def test_quota_stops_before_sending_an_extra_request(monkeypatch):
    calls = 0

    async def reserve():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise DailyQuotaExceeded(UsageReservation(limit=1, used=1, remaining=0, reset_at="2026-10-01T00:00:00Z", request_count=1))

    results, coverage, requests = discover(monkeypatch, [
        {"status": "OK", "results": [restaurant(i) for i in range(10)], "next_page_token": "page2"},
    ], before_request=reserve)
    assert len(results) == 10
    assert coverage.partial_reason == "quota"
    assert coverage.provider_requests == len(requests) == 1


def test_sparse_viewport_is_measured_after_bounds_and_preserves_loaded_places(monkeypatch):
    results, coverage, requests = discover(monkeypatch, [
        {"status": "OK", "results": [restaurant(0), *[restaurant(i, lat=44) for i in range(1, 10)]]},
        {"status": "OK", "results": [restaurant(0), *[restaurant(i) for i in range(10, 16)]]},
    ], bounds={"north": 43.75, "south": 43.65, "east": -79.34, "west": -79.46})
    assert len(results) == 7
    assert coverage.provider_requests == 2
    assert [request["radius"] for request in requests] == [5000, 10000]


def test_wider_failure_preserves_the_original_sparse_page(monkeypatch):
    results, coverage, _requests = discover(monkeypatch, [
        {"status": "OK", "results": [restaurant(0)]}, httpx.ReadTimeout("test"),
    ])
    assert [place["place_id"] for place in results] == ["place-0"]
    assert coverage.partial_reason == "provider"


def test_first_page_failure_is_an_error_instead_of_fabricated_restaurants(monkeypatch):
    with pytest.raises(RuntimeError):
        discover(monkeypatch, [{"status": "REQUEST_DENIED"}])


def test_repeated_token_stops_without_duplicate_pins(monkeypatch):
    results, coverage, requests = discover(monkeypatch, [
        {"status": "OK", "results": [restaurant(i) for i in range(10)], "next_page_token": "repeated"},
        {"status": "OK", "results": [restaurant(0)], "next_page_token": "repeated"},
    ])
    assert len(results) == 10
    assert len(requests) == 2
    assert coverage.partial_reason == "provider"


def test_total_request_budget_covers_pagination_retries_and_sparse_fallback(monkeypatch):
    results, coverage, requests = discover(monkeypatch, [
        {"status": "OK", "results": [restaurant(0)], "next_page_token": "page2"},
        {"status": "INVALID_REQUEST"},
        {"status": "OK", "results": [], "next_page_token": "page3"},
        {"status": "INVALID_REQUEST"},
        {"status": "OK", "results": []},
        {"status": "OK", "results": [restaurant(1)], "next_page_token": "wider-page2"},
    ])
    assert len(results) == 2
    assert coverage.provider_requests == len(requests) == 6
    assert coverage.partial_reason == "request_limit"
