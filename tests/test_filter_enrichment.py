from __future__ import annotations

import asyncio

import httpx
from types import SimpleNamespace
import pytest

from backend.config import get_settings
from backend.database import reset_database_cache
from backend.services.rate_limit import burst_limiter


@pytest.fixture(autouse=True)
def settings(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{(tmp_path / 'filters.db').as_posix()}")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("IDENTITY_SIGNING_SECRET", "test-identity-signing-secret")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    get_settings.cache_clear()
    reset_database_cache()
    burst_limiter.reset()
    yield
    get_settings.cache_clear()
    reset_database_cache()


def test_filter_endpoint_reserves_each_unique_provider_call_and_rejects_oversized_or_path_ids(monkeypatch):
    from backend.main import create_app
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setenv("GUEST_DAILY_PLACES_LIMIT", "2")
    get_settings.cache_clear()
    requests = []
    def provider(request):
        requests.append(request)
        return httpx.Response(200, json={"id": request.url.path.split("/")[-1], "takeout": True})
    original_client = httpx.AsyncClient
    monkeypatch.setattr("backend.services.filter_enrichment.httpx.AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(provider), **kwargs))
    app = create_app()
    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            oversized = await client.post("/api/places/filter-data", json={"place_ids": [f"place-{i}" for i in range(11)]})
            invalid = await client.post("/api/places/filter-data", json={"place_ids": ["../other?key=foo"]})
            result = await client.post("/api/places/filter-data", json={"place_ids": ["place-1", "place-2", "place-1"]})
            exhausted = await client.post("/api/places/filter-data", json={"place_ids": ["place-3"]})
            return oversized, invalid, result, exhausted
    oversized, invalid, result, exhausted = asyncio.run(exercise())
    assert oversized.status_code == invalid.status_code == 422
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert len(result.json()["places"]) == 2
    assert exhausted.status_code == 429
    assert len(requests) == 2


def test_gpt_labels_require_known_menu_evidence_and_reject_condiments(monkeypatch):
    from backend.services.filter_enrichment import classify_menu_labels, LabelBatch

    candidates = [{"place_id": "place-1", "cuisine_labels": [], "evidence": [
        {"id": "dish", "kind": "official_menu", "label": "Vegan ramen", "detail": "Noodle soup with tofu", "source_url": "https://restaurant.example/menu"},
        {"id": "sauce", "kind": "official_menu", "label": "Gluten-free soy sauce", "source_url": "https://restaurant.example/menu"},
        {"id": "no", "kind": "official_website", "label": "We do not offer halal dishes", "source_url": "https://restaurant.example/menu"},
    ]}]

    async def parse(**kwargs):
        assert kwargs["store"] is False
        assert kwargs["reasoning_effort"] == "low"
        assert "untrusted" in kwargs["messages"][0]["content"]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=LabelBatch.model_validate({"candidates": [
            {"place_id": "place-1", "labels": [
                {"kind": "dietary", "value": "vegan", "evidence_ids": ["dish"]},
                {"kind": "dietary", "value": "gluten-free", "evidence_ids": ["sauce"]},
                {"kind": "dietary", "value": "halal", "evidence_ids": ["no"]},
                {"kind": "cuisine", "value": "Japanese", "evidence_ids": ["invented"]},
            ]},
            {"place_id": "unknown-place", "labels": []},
        ]})))])

    monkeypatch.setattr("backend.services.filter_enrichment.AsyncOpenAI", lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))))
    asyncio.run(classify_menu_labels(candidates))
    assert [label["value"] for label in candidates[0]["dietary_labels"]] == ["vegan"]
    assert candidates[0]["dietary_labels"][0]["evidence"][0]["source_url"] == "https://restaurant.example/menu"
    assert candidates[0]["cuisine_labels"] == []
    get_settings.cache_clear()


def test_successful_details_menu_and_model_pipeline_preserves_sources(monkeypatch):
    from backend.services.filter_enrichment import enrich_filter_places, LabelBatch
    original_client = httpx.AsyncClient
    calls = []
    def respond(request):
        calls.append(str(request.url))
        if request.url.host == "places.googleapis.com":
            return httpx.Response(200, json={"id": "place-1", "types": ["restaurant"], "websiteUri": "https://restaurant.example/menu", "takeout": True})
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text='''<html><script type="application/ld+json">{"@type":"Menu","hasMenuItem":[{"@type":"MenuItem","name":"Vegan ramen","description":"Vegan tofu noodle soup"},{"@type":"MenuItem","name":"Sushi","description":"Rice rolls with fish"}]}</script></html>''')
    monkeypatch.setattr("backend.services.filter_enrichment.httpx.AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr("backend.services.menu_evidence.socket.getaddrinfo", lambda *args: [(2, 1, 6, "", ("93.184.216.34", 443))])
    async def parse(**kwargs):
        data = __import__("json").loads(kwargs["messages"][1]["content"])
        evidence = data["candidates"][0]["evidence"]
        assert {item["label"] for item in evidence} == {"Vegan ramen", "Sushi"}
        assert all("source_url" not in item for item in evidence)
        assert set(data["candidates"][0]) == {"place_id", "google_cuisine_present", "evidence"}
        by_label = {item["label"]: item["id"] for item in evidence}
        parsed = LabelBatch.model_validate({"candidates": [{"place_id": "place-1", "labels": [
            {"kind": "cuisine", "value": "Japanese", "evidence_ids": list(by_label.values())},
            {"kind": "dietary", "value": "vegan", "evidence_ids": [by_label["Vegan ramen"]]},
        ]}]})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])
    monkeypatch.setattr("backend.services.filter_enrichment.AsyncOpenAI", lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))))
    result = asyncio.run(enrich_filter_places(["place-1"]))[0]
    assert result["cuisine_labels"][0]["value"] == "Japanese"
    assert result["dietary_labels"][0]["value"] == "vegan"
    assert result["dietary_labels"][0]["evidence"][0]["source_url"] == "https://restaurant.example/menu"
    assert result["menu_status"] == "assessed"
    assert result["takeout"] is True
    assert "evidence" not in result and "website" not in result
    assert len(calls) == 2


def test_model_failure_keeps_google_labels_and_abstains_on_diet(monkeypatch):
    from backend.services.filter_enrichment import classify_menu_labels
    candidates = [{"place_id": "place-1", "cuisine_labels": [{"value": "Japanese", "source": "google", "evidence": []}],
                   "evidence": [{"id": "dish", "kind": "official_menu", "label": "Vegan ramen", "source_url": "https://restaurant.example/menu"}]}]
    async def parse(**kwargs):
        raise TimeoutError()
    monkeypatch.setattr("backend.services.filter_enrichment.AsyncOpenAI", lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))))
    asyncio.run(classify_menu_labels(candidates))
    assert candidates[0]["dietary_labels"] == []
    assert candidates[0]["cuisine_labels"][0]["source"] == "google"
    assert candidates[0]["menu_status"] == "unavailable"


def test_details_preserve_false_and_unknown_and_use_provider_cuisine(monkeypatch):
    from backend.services.filter_enrichment import enrich_filter_places
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "place-1", "types": ["japanese_restaurant", "restaurant"],
            "takeout": False, "delivery": True,
            "accessibilityOptions": {}, "priceLevel": "PRICE_LEVEL_UNSPECIFIED",
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr("backend.services.filter_enrichment.httpx.AsyncClient", lambda **kwargs: client)
    result = asyncio.run(enrich_filter_places(["place-1"]))
    assert result[0]["takeout"] is False
    assert result[0]["delivery"] is True
    assert result[0]["reservable"] is None
    assert result[0]["wheelchair_accessible_entrance"] is None
    assert result[0]["price_level"] is None
    assert result[0]["cuisine_labels"] == [{"value": "Japanese", "source": "google", "evidence": []}]
    assert len(requests) == 1
    assert "takeout" in requests[0].headers["X-Goog-FieldMask"]
    assert "reviews" not in requests[0].headers["X-Goog-FieldMask"]
    get_settings.cache_clear()


def test_google_vegetarian_attribute_qualifies_without_model_and_other_diets_stay_unknown(monkeypatch):
    from backend.services.filter_enrichment import enrich_filter_places
    def respond(request):
        return httpx.Response(200, json={"id": "place-1", "servesVegetarianFood": True})
    original_client = httpx.AsyncClient
    monkeypatch.setattr("backend.services.filter_enrichment.httpx.AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs))
    result = asyncio.run(enrich_filter_places(["place-1"]))[0]
    assert [(item["value"], item["source"]) for item in result["dietary_labels"]] == [("vegetarian", "google")]
    assert "place-1" in result["dietary_labels"][0]["evidence"][0]["source_url"]
    assert result["menu_status"] == "no_evidence"
