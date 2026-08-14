from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import get_settings
from backend.database import reset_database_cache
from backend.main import create_app
from backend.services.rate_limit import burst_limiter
from backend.services.recommendation_tokens import sign_recommendation
from backend.services.supabase_auth import ProviderSession, SupabaseAuthClient


@pytest.fixture(autouse=True)
def product_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{(tmp_path / 'product.db').as_posix()}")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service")
    monkeypatch.setenv("IDENTITY_SIGNING_SECRET", "test-identity-signing-secret")
    monkeypatch.setenv("DAILY_QUOTA_MULTIPLIER", "1")
    get_settings.cache_clear()
    reset_database_cache()
    burst_limiter.reset()
    yield
    get_settings.cache_clear()
    reset_database_cache()


@pytest.fixture
def provider() -> ProviderSession:
    return ProviderSession(
        access_token="e30.eyJleHAiOjQxMDI0NDQ4MDB9.signature",
        refresh_token="refresh",
        user_id=str(uuid.uuid4()),
        email="product@example.com",
        email_verified=True,
        identities=(),
    )


def test_legal_acceptance_preferences_collections_history_and_export(monkeypatch, provider):
    async def fake_login(self, email: str, password: str):
        return provider

    monkeypatch.setattr(SupabaseAuthClient, "password_login", fake_login)
    app = create_app()

    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/auth/login", json={"email": provider.email, "password": "correct horse battery staple"})
            before = await client.get("/api/auth/me")
            legal = (await client.get("/api/legal/current")).json()
            csrf = (await client.get("/api/auth/csrf")).json()["csrf_token"]
            headers = {"X-CSRF-Token": csrf, "Origin": "http://localhost:5173"}
            accepted = await client.post("/api/legal/accept", headers=headers, json={
                "terms_version": legal["terms"]["version"],
                "privacy_version": legal["privacy"]["version"],
                "accept_terms": True, "acknowledge_privacy": True, "age_confirmed": True,
            })
            after = await client.get("/api/auth/me")
            preferences = await client.patch("/api/account/preferences", headers=headers, json={
                "favorite_cuisines": ["Japanese"], "allergies": ["peanuts"],
                "personalization_enabled": True, "history_enabled": True,
                "notification_preferences": {"product_updates": True},
            })
            collection = await client.post("/api/favorites/collections", headers=headers, json={"name": "Date night"})
            first_save = await client.post("/api/favorites", headers=headers, json={"place_id": "google-place-1", "collection_id": collection.json()["id"], "note": "Window seat"})
            second_save = await client.post("/api/favorites", headers=headers, json={"place_id": "google-place-1", "collection_id": collection.json()["id"]})
            saved = await client.get("/api/favorites/saved")
            conversation = await client.post("/api/conversations", headers=headers, json={"first_prompt": "Cozy ramen downtown"})
            await client.post(f"/api/conversations/{conversation.json()['id']}/messages", headers=headers, json={"role": "user", "content": "Cozy ramen downtown", "place_ids": []})
            await client.post(f"/api/conversations/{conversation.json()['id']}/messages", headers=headers, json={"role": "assistant", "content": "Try the first option.", "place_ids": ["google-place-1"]})
            detail = await client.get(f"/api/conversations/{conversation.json()['id']}")
            export = await client.get("/api/account/export")
            return before, accepted, after, preferences, collection, first_save, second_save, saved, detail, export

    before, accepted, after, preferences, collection, first_save, second_save, saved, detail, export = asyncio.run(exercise())
    assert before.json()["user"]["policy_required"] is True
    assert accepted.status_code == 200
    assert after.json()["user"]["policy_required"] is False
    assert preferences.json()["history_enabled"] is True
    assert collection.status_code == 201
    assert first_save.json()["id"] == second_save.json()["id"]
    assert len(saved.json()["favorites"]) == 1
    assert saved.json()["favorites"][0]["place_id"] == "google-place-1"
    assert detail.json()["messages"][1]["place_ids"] == ["google-place-1"]
    exported = export.json()
    assert exported["saved_places"][0]["place_id"] == "google-place-1"
    assert "address" not in exported["saved_places"][0]
    assert "rating" not in exported["saved_places"][0]
    assert exported["policy_acceptances"][0]["age_confirmed"] is True
    assert {item["purpose"]: item["granted"] for item in exported["consents"]} == {
        "history": True, "notifications": True, "personalization": True,
    }


def test_dietary_evidence_endpoint_is_bounded_and_attributable(monkeypatch):
    async def fake_verify(place_ids, requirements):
        assert place_ids == ["place-1", "place-2"]
        assert requirements == ["vegan"]
        return [{
            "place_id": "place-1",
            "dietary_matches": ["vegan"],
            "evidence": [{
                "type": "official_menu", "label": "Vegan bowl",
                "source_url": "https://restaurant.example/menu",
            }],
        }]

    monkeypatch.setattr("backend.routers.places.verify_dietary_place_ids", fake_verify)
    app = create_app()

    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/places/dietary-evidence", json={
                "place_ids": ["place-1", "place-2"], "requirements": ["vegan"],
            })
            invalid = await client.post("/api/places/dietary-evidence", json={
                "place_ids": [], "requirements": ["vegan"],
            })
            return response, invalid

    response, invalid = asyncio.run(exercise())
    assert response.status_code == 200
    assert response.json()["matches"][0]["evidence"][0]["source_url"].startswith("https://")
    assert invalid.status_code == 422


def test_browser_guest_age_gate_and_signed_feedback(monkeypatch, provider):
    async def fake_recommendations(**kwargs):
        return {"reply": "A grounded answer", "recommendations": []}

    async def fake_login(self, email: str, password: str):
        return provider

    monkeypatch.setattr("backend.routers.chat.generate_recommendations", fake_recommendations)
    monkeypatch.setattr(SupabaseAuthClient, "password_login", fake_login)
    app = create_app()

    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            origin = {"Origin": "http://localhost:5173"}
            rejected = await client.post("/api/chat", headers=origin, json={"query": "ramen"})
            accepted = await client.post("/api/chat", headers=origin, json={"query": "ramen", "age_confirmed": True})
            await client.post("/api/auth/login", json={"email": provider.email, "password": "correct horse battery staple"})
            csrf = (await client.get("/api/auth/csrf")).json()["csrf_token"]
            token = sign_recommendation("place-1", 1, 0.9, "high")
            feedback = await client.post("/api/feedback", headers={**origin, "X-CSRF-Token": csrf}, json={"recommendation_token": token, "liked": True})
            duplicate = await client.post("/api/feedback", headers={**origin, "X-CSRF-Token": csrf}, json={"recommendation_token": token, "liked": False})
            return rejected, accepted, feedback, duplicate

    rejected, accepted, feedback, duplicate = asyncio.run(exercise())
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "guest_age_acknowledgment_required"
    assert accepted.status_code == 200
    assert feedback.status_code == 202
    assert duplicate.status_code == 409
