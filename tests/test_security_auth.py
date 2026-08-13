from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import get_settings
from backend.database import reset_database_cache
from backend.main import create_app
from backend.services.rate_limit import burst_limiter
from backend.services.supabase_auth import ProviderSession, SupabaseAuthClient


@pytest.fixture(autouse=True)
def security_test_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+pysqlite:///{(tmp_path / 'security.db').as_posix()}",
    )
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("DAILY_QUOTA_MULTIPLIER", "1")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service")
    monkeypatch.setenv("IDENTITY_SIGNING_SECRET", "test-identity-signing-secret")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173")
    get_settings.cache_clear()
    reset_database_cache()
    burst_limiter.reset()
    yield
    get_settings.cache_clear()
    reset_database_cache()


@pytest.fixture
def provider_session() -> ProviderSession:
    return ProviderSession(
        access_token="e30.eyJleHAiOjQxMDI0NDQ4MDB9.signature",
        refresh_token="provider-refresh-token",
        user_id=str(uuid.uuid4()),
        email="owner@example.com",
        email_verified=True,
        identities=(
            {
                "id": "password-identity",
                "provider": "email",
                "identity_data": {"email": "owner@example.com"},
            },
        ),
    )


def test_login_uses_opaque_httponly_cookie_and_blocks_csrf(
    monkeypatch, provider_session
):
    async def fake_login(self, email: str, password: str):
        return provider_session

    monkeypatch.setattr(SupabaseAuthClient, "password_login", fake_login)
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            client.cookies.set(
                "craveai_session",
                "attacker-fixed-value",
                domain="test.local",
                path="/",
            )
            login = await client.post(
                "/api/auth/login",
                json={
                    "email": "owner@example.com",
                    "password": "correct horse battery staple",
                },
            )
            session_cookie = client.cookies.get("craveai_session")
            me = await client.get("/api/auth/me")
            rejected = await client.post(
                "/api/favorites", json={"restaurant": "Safe Ramen"}
            )
            csrf = await client.get("/api/auth/csrf")
            created = await client.post(
                "/api/favorites",
                headers={"X-CSRF-Token": csrf.json()["csrf_token"]},
                json={"restaurant": "Safe Ramen", "note": "Mine"},
            )
            listed = await client.get("/api/favorites")
            return login, session_cookie, me, rejected, created, listed

    login, cookie, me, rejected, created, listed = asyncio.run(exercise())
    assert login.status_code == 200
    assert cookie and cookie != "attacker-fixed-value"
    set_cookie = login.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert provider_session.access_token not in login.text
    assert "provider-refresh-token" not in set_cookie
    assert me.json()["user"]["user_id"] == provider_session.user_id
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "csrf_validation_failed"
    assert created.status_code == 201
    assert listed.json()["favorites"][0]["restaurant"] == "Safe Ramen"


def test_feedback_rejects_caller_selected_user_and_untrusted_origin(
    monkeypatch, provider_session
):
    async def fake_login(self, email: str, password: str):
        return provider_session

    monkeypatch.setattr(SupabaseAuthClient, "password_login", fake_login)
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post(
                "/api/auth/login",
                json={
                    "email": "owner@example.com",
                    "password": "correct horse battery staple",
                },
            )
            csrf = (await client.get("/api/auth/csrf")).json()["csrf_token"]
            selected_user = await client.post(
                "/api/feedback",
                headers={"X-CSRF-Token": csrf},
                json={
                    "user_id": str(uuid.uuid4()),
                    "restaurant": "Injected",
                    "liked": True,
                },
            )
            wrong_origin = await client.post(
                "/api/feedback",
                headers={
                    "X-CSRF-Token": csrf,
                    "Origin": "https://attacker.example",
                },
                json={"restaurant": "Safe Ramen", "liked": True},
            )
            accepted = await client.post(
                "/api/feedback",
                headers={
                    "X-CSRF-Token": csrf,
                    "Origin": "http://localhost:5173",
                },
                json={"restaurant": "Safe Ramen", "liked": True},
            )
            return selected_user, wrong_origin, accepted

    selected_user, wrong_origin, accepted = asyncio.run(exercise())
    assert selected_user.status_code == 422
    assert wrong_origin.status_code == 403
    assert wrong_origin.json()["detail"]["code"] == "origin_not_allowed"
    assert accepted.status_code == 202


def test_google_callback_rejects_missing_or_reused_transaction(monkeypatch):
    called = False

    async def exchange(self, auth_code: str, code_verifier: str):
        nonlocal called
        called = True
        raise AssertionError("Provider exchange must not happen without valid state.")

    monkeypatch.setattr(SupabaseAuthClient, "exchange_pkce", exchange)
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            return await client.get(
                "/api/auth/google/callback",
                params={"code": "invalid-code", "state": "invalid-state-value"},
            )

    response = asyncio.run(exercise())
    assert response.status_code == 303
    assert "google_failed" in response.headers["location"]
    assert called is False


def test_guest_quota_cannot_be_reset_by_clearing_browser_state(monkeypatch):
    async def fake_recommendations(**kwargs):
        return {"reply": "ok", "recommendations": []}

    monkeypatch.setattr(
        "backend.routers.chat.generate_recommendations", fake_recommendations
    )
    app = create_app()

    async def exercise():
        payload = {"query": "ramen", "location": {"lat": 43.65, "lng": -79.38}}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as first:
            responses = [await first.post("/api/chat", json=payload) for _ in range(3)]
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as cleared:
            responses.append(await cleared.post("/api/chat", json=payload))
        return responses

    responses = asyncio.run(exercise())
    assert [item.status_code for item in responses] == [200, 200, 200, 429]
    assert responses[-1].json()["detail"]["code"] == "daily_chat_message_quota_exceeded"
