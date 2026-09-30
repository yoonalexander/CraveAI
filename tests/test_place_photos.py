from __future__ import annotations

import asyncio
import httpx
import pytest

from backend.config import get_settings
from backend.database import reset_database_cache
from backend.services.rate_limit import burst_limiter


@pytest.fixture(autouse=True)
def settings(monkeypatch, tmp_path):
    for name, value in {
        "APP_ENV": "test", "AUTO_CREATE_SCHEMA": "true",
        "DATABASE_URL": f"sqlite+pysqlite:///{(tmp_path / 'photos.db').as_posix()}",
        "IDENTITY_SIGNING_SECRET": "test-identity-signing-secret",
        "GOOGLE_API_KEY": "private-test-key",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    reset_database_cache()
    burst_limiter.reset()
    yield
    get_settings.cache_clear()
    reset_database_cache()


def install_provider(monkeypatch, provider):
    original_client = httpx.AsyncClient
    def client(**kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(provider))
        return original_client(**kwargs)
    monkeypatch.setattr("backend.services.place_photos.httpx.AsyncClient", client)


def metadata(place_id="place-1"):
    return {"id": place_id, "photos": [
        {"name": f"places/{place_id}/photos/photo-{i}", "googleMapsUri": f"https://www.google.com/maps/photo/{i}",
         "authorAttributions": [
             {"displayName": "Alice", "uri": "//maps.google.com/contrib/alice", "photoUri": "https://lh3.googleusercontent.com/avatar"},
             {"displayName": "Bob", "uri": "https://maps.google.com/contrib/bob"},
         ]} for i in range(3)
    ]}


def test_gallery_refreshes_names_and_returns_only_key_free_media_with_all_authors(monkeypatch):
    from backend.services.place_photos import fetch_place_photo
    calls = []
    def provider(request):
        calls.append(request)
        assert request.headers["x-goog-api-key"] == "private-test-key"
        assert "key" not in request.url.params
        if request.url.path.endswith("/media"):
            assert request.url.params["skipHttpRedirect"] == "true"
            assert request.url.params["maxWidthPx"] == "800"
            return httpx.Response(200, json={"photoUri": "https://lh3.googleusercontent.com/restaurant"})
        assert request.headers["x-goog-fieldmask"] == "id,photos"
        return httpx.Response(200, json=metadata())
    install_provider(monkeypatch, provider)
    reservations = []
    async def reserve(): reservations.append(1)
    async def exercise():
        first = await fetch_place_photo("place-1", 0, before_request=reserve)
        next_photo = await fetch_place_photo("place-1", 2, before_request=reserve)
        return first, next_photo
    first, next_photo = asyncio.run(exercise())
    assert first["place_id"] == "place-1"
    assert first["total"] == 3 and next_photo["index"] == 2
    assert next_photo["photo"]["source_uri"].endswith("/2")
    assert [author["name"] for author in first["photo"]["authors"]] == ["Alice", "Bob"]
    assert first["photo"]["authors"][0]["uri"].startswith("https://")
    assert "private-test-key" not in str(first) and "/photos/photo-" not in str(first)
    assert len(calls) == len(reservations) == 4


@pytest.mark.parametrize("body", [{"id": "place-1"}, metadata("another-place"), {"id": "place-1", "photos": [{"name": "places/another-place/photos/wrong"}]}])
def test_missing_or_wrong_venue_never_requests_media(monkeypatch, body):
    from backend.services.place_photos import fetch_place_photo, PhotoProviderError
    calls = []
    def provider(request):
        calls.append(request)
        return httpx.Response(200, json=body)
    install_provider(monkeypatch, provider)
    if body == {"id": "place-1"}:
        assert asyncio.run(fetch_place_photo("place-1", 0))["photo"] is None
    else:
        with pytest.raises(PhotoProviderError): asyncio.run(fetch_place_photo("place-1", 0))
    assert len(calls) == 1


@pytest.mark.parametrize("uri", ["https://places.googleapis.com/x?key=private-test-key", "https://lh3.googleusercontent.com/x?key=anything", "https://evil.example/image", "http://lh3.googleusercontent.com/image"])
def test_rejects_unsafe_media_urls(monkeypatch, uri):
    from backend.services.place_photos import fetch_place_photo, PhotoProviderError
    install_provider(monkeypatch, lambda request: httpx.Response(200, json={"photoUri": uri} if request.url.path.endswith("/media") else metadata()))
    with pytest.raises(PhotoProviderError): asyncio.run(fetch_place_photo("place-1", 0))


def test_endpoint_validates_and_enforces_quota_before_each_provider_call(monkeypatch):
    from backend.main import create_app
    monkeypatch.setenv("GUEST_DAILY_PLACES_LIMIT", "3")
    get_settings.cache_clear()
    calls = []
    def provider(request):
        calls.append(request)
        return httpx.Response(200, json={"photoUri": "https://lh3.googleusercontent.com/image"} if request.url.path.endswith("/media") else metadata())
    install_provider(monkeypatch, provider)
    app = create_app()
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            invalid = await client.post("/api/places/photo", json={"place_id": "../bad", "index": 0})
            oversized = await client.post("/api/places/photo", json={"place_id": "place-1", "index": 10})
            first = await client.post("/api/places/photo", json={"place_id": "place-1", "index": 0})
            exhausted = await client.post("/api/places/photo", json={"place_id": "place-1", "index": 1})
            return invalid, oversized, first, exhausted
    invalid, oversized, first, exhausted = asyncio.run(exercise())
    assert invalid.status_code == oversized.status_code == 422
    assert first.status_code == 200 and first.headers["cache-control"] == "no-store"
    assert exhausted.status_code == 429
    assert exhausted.headers["retry-after"]
    assert len(calls) == 3  # Second Details call allowed, second media call prevented.


@pytest.mark.parametrize("provider_status", [400, 403, 429, 500])
def test_provider_failures_are_sanitized_and_never_retry(monkeypatch, provider_status):
    from backend.main import create_app
    calls = []
    def provider(request):
        calls.append(request)
        return httpx.Response(provider_status, text="private-test-key: internal provider diagnostics")
    install_provider(monkeypatch, provider)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as client:
            return await client.post("/api/places/photo", json={"place_id": "place-1"})
    response = asyncio.run(exercise())
    assert response.status_code == 502
    assert response.json() == {"detail": {"code": "place_photo_unavailable"}}
    assert response.headers["cache-control"] == "no-store"
    assert len(calls) == 1


def test_missing_configuration_makes_no_provider_request(monkeypatch):
    from backend.main import create_app
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    get_settings.cache_clear()
    def provider(request): pytest.fail("Missing configuration must not contact Google")
    install_provider(monkeypatch, provider)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test") as client:
            return await client.post("/api/places/photo", json={"place_id": "place-1"})
    assert asyncio.run(exercise()).status_code == 503
