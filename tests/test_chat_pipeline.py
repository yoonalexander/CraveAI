import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from types import ModuleType
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure environment variables are set before importing application modules.
os.environ.setdefault("OPENAI_API_KEY", "test-openai")
os.environ.setdefault("GOOGLE_API_KEY", "test-google")
os.environ.setdefault("MODEL_NAME", "test-model")
os.environ.setdefault("APP_ENV", "test")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Provide lightweight stubs for LangChain modules so imports succeed without the
# real dependencies.
if "langchain_core" not in sys.modules:
    langchain_core_module = ModuleType("langchain_core")
    sys.modules["langchain_core"] = langchain_core_module

    class DummyChain:
        def __init__(self, *components):
            self.components = list(components)

        def __or__(self, other):
            self.components.append(other)
            return self

        async def ainvoke(self, *_args, **_kwargs):
            return "{}"

    class DummyStrOutputParser:
        def __call__(self, *args, **kwargs):
            return self

        def __ror__(self, other):
            return DummyChain(other, self)

        async def ainvoke(self, *_args, **_kwargs):
            return "{}"

    output_parsers_module = ModuleType("langchain_core.output_parsers")
    output_parsers_module.StrOutputParser = DummyStrOutputParser
    sys.modules["langchain_core.output_parsers"] = output_parsers_module
    langchain_core_module.output_parsers = output_parsers_module

    class DummyPromptTemplate:
        @classmethod
        def from_messages(cls, messages):
            instance = cls()
            instance.messages = messages
            return instance

        def __or__(self, other):
            return DummyChain(self, other)

    prompts_module = ModuleType("langchain_core.prompts")
    prompts_module.ChatPromptTemplate = DummyPromptTemplate
    sys.modules["langchain_core.prompts"] = prompts_module
    langchain_core_module.prompts = prompts_module

if "langchain_openai" not in sys.modules:
    langchain_openai_module = ModuleType("langchain_openai")

    class DummyChatOpenAI:
        def __init__(self, *args, **kwargs):
            pass

        async def ainvoke(self, *_args, **_kwargs):
            return "{}"

    class DummyOpenAIEmbeddings:
        def __init__(self, *args, **kwargs):
            pass

    langchain_openai_module.ChatOpenAI = DummyChatOpenAI
    langchain_openai_module.OpenAIEmbeddings = DummyOpenAIEmbeddings
    sys.modules["langchain_openai"] = langchain_openai_module

if "langchain_community" not in sys.modules:
    langchain_community_module = ModuleType("langchain_community")
    vectorstores_module = ModuleType("langchain_community.vectorstores")

    class DummyChroma:
        def __init__(self, *args, **kwargs):
            pass

        def similarity_search(self, *args, **kwargs):
            return []

    vectorstores_module.Chroma = DummyChroma
    langchain_community_module.vectorstores = vectorstores_module
    sys.modules["langchain_community"] = langchain_community_module
    sys.modules["langchain_community.vectorstores"] = vectorstores_module

from backend.config import get_settings
from backend.main import create_app
from backend.routers import places as places_router
from backend.services import places as places_service
from backend.services import rag_pipeline
from backend.services.identity import issue_identity_token, verify_identity_token
from backend.services.storage import init_storage
from backend.services.usage_limits import (
    DailyQuotaExceeded,
    PLACES_GLOBAL_USAGE_USER_ID,
    reserve_daily_quota,
)

ANONYMOUS_TOKEN_HEADER = "X-CraveAI-Anonymous-Token"
DEV_BYPASS_HEADER = "X-CraveAI-Dev-Bypass"


@pytest.fixture(autouse=True)
def configure_test_settings(monkeypatch, tmp_path):
    """Provide deterministic configuration for the test session."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "craveai-test.db"))
    monkeypatch.setenv("USAGE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("DAILY_TOKEN_LIMIT", "10000")
    monkeypatch.setenv("DAILY_CHAT_MESSAGE_LIMIT", "3")
    monkeypatch.setenv("CHAT_DEVELOPER_MODE", "false")
    monkeypatch.delenv("CHAT_DEV_BYPASS_SECRET", raising=False)
    monkeypatch.setenv("GLOBAL_DAILY_TOKEN_LIMIT", "100000")
    monkeypatch.setenv("DAILY_PLACES_REQUEST_LIMIT", "20")
    monkeypatch.setenv("GLOBAL_DAILY_PLACES_REQUEST_LIMIT", "1000")
    monkeypatch.setenv("IDENTITY_SIGNING_SECRET", "test-identity-signing-secret")
    get_settings.cache_clear()

    settings = get_settings()
    # Refresh module-level settings to keep test values in sync.
    monkeypatch.setattr(rag_pipeline, "settings", settings, raising=False)
    monkeypatch.setattr(rag_pipeline, "OPENAI_API_KEY", settings.OPENAI_API_KEY, raising=False)
    monkeypatch.setattr(rag_pipeline, "OPENAI_CHAT_MODEL", settings.MODEL_NAME, raising=False)
    monkeypatch.setattr(rag_pipeline, "GOOGLE_PLACES_API_KEY", settings.GOOGLE_API_KEY, raising=False)

    yield

    get_settings.cache_clear()


@pytest.fixture
def mocked_pipeline(monkeypatch):
    """Stub external calls used by the RAG pipeline."""
    call_tracker: Dict[str, int] = {"extract": 0, "places": 0, "rank": 0}

    def fake_extract_search_terms(user_query: str) -> List[str]:
        call_tracker["extract"] += 1
        return ["ramen"]

    async def fake_fetch_places(cuisines, location):
        call_tracker["places"] += 1
        return [
            {
                "place_id": "mock-ramen",
                "name": "Mock Ramen House",
                "rating": 4.8,
                "address": "123 Test Street",
                "reason": "Mocked match for ramen craving.",
            }
        ]

    async def fake_rank_candidates(user_query: str, places):
        call_tracker["rank"] += 1
        return {
            "reply": "I'd try Mock Ramen House - sounds perfect for cozy ramen vibes.",
            "recommendations": places,
        }

    monkeypatch.setattr(
        rag_pipeline,
        "extract_search_terms",
        fake_extract_search_terms,
        raising=False,
    )
    monkeypatch.setattr(rag_pipeline, "_fetch_candidate_places", fake_fetch_places, raising=False)
    monkeypatch.setattr(rag_pipeline, "_rank_candidates", fake_rank_candidates, raising=False)

    return call_tracker


def test_extract_search_terms_recognizes_common_cuisines():
    assert rag_pipeline.extract_search_terms("I want some pizza") == ["pizza"]
    assert rag_pipeline.extract_search_terms("Cozy ramen please") == ["ramen"]
    assert rag_pipeline.extract_search_terms("Find spicy Indian food") == ["indian"]


def test_extract_search_terms_combines_diet_and_uses_ambiguous_fallback():
    assert rag_pipeline.extract_search_terms("vegan pizza nearby") == ["vegan pizza"]
    assert rag_pipeline.extract_search_terms("Something cozy and spicy") == [
        "something cozy and spicy"
    ]


def test_chat_model_disables_retries_and_sets_deadline(monkeypatch):
    captured: Dict[str, Any] = {}

    class CapturingChatModel:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(rag_pipeline, "ChatOpenAI", CapturingChatModel)
    rag_pipeline._build_chat_model()

    assert captured["model"] == rag_pipeline.OPENAI_CHAT_MODEL
    assert captured["timeout"] == rag_pipeline.RANKING_TIMEOUT_SECONDS
    assert captured["max_retries"] == 0
    assert captured["max_completion_tokens"] == 500
    assert captured["reasoning_effort"] == "minimal"
    assert captured["verbosity"] == "low"
    assert captured["model_kwargs"] == {
        "response_format": {"type": "json_object"}
    }


def test_deterministic_fallback_sorts_by_rating_then_review_count():
    places = [
        {"place_id": "lower", "name": "Lower", "rating": 4.7, "user_ratings_total": 900},
        {"place_id": "few", "name": "Few Reviews", "rating": 4.8, "user_ratings_total": 20},
        {"place_id": "many", "name": "Many Reviews", "rating": 4.8, "user_ratings_total": 500},
    ]

    result = rag_pipeline._deterministic_response(places, reason="test")

    assert [item["name"] for item in result["recommendations"]] == [
        "Many Reviews",
        "Few Reviews",
        "Lower",
    ]


def test_pipeline_ranking_timeout_returns_fast_deterministic_fallback(monkeypatch):
    places = [
        {"place_id": "a", "name": "A", "rating": 4.5, "user_ratings_total": 100},
        {"place_id": "b", "name": "B", "rating": 4.8, "user_ratings_total": 50},
    ]

    async def fake_fetch(search_terms, location):
        return places

    async def slow_rank(user_query, candidates):
        await asyncio.sleep(0.1)
        return {"reply": "too late", "recommendations": []}

    monkeypatch.setattr(rag_pipeline, "_fetch_candidate_places", fake_fetch)
    monkeypatch.setattr(rag_pipeline, "_rank_candidates", slow_rank)
    monkeypatch.setattr(rag_pipeline, "RANKING_TIMEOUT_SECONDS", 0.01)

    started = time.perf_counter()
    result = asyncio.run(
        rag_pipeline.generate_recommendations(
            "pizza",
            {"lat": 43.6, "lng": -79.4},
        )
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
    assert [item["name"] for item in result["recommendations"]] == ["B", "A"]


def test_pipeline_malformed_ranking_falls_back_with_coordinates(monkeypatch):
    places = [
        {
            "place_id": "mapped-pizza",
            "name": "Mapped Pizza",
            "rating": 4.9,
            "user_ratings_total": 200,
            "lat": 43.61,
            "lng": -79.41,
        }
    ]

    async def fake_fetch(search_terms, location):
        return places

    async def malformed_rank(user_query, candidates):
        raise ValueError("malformed JSON")

    monkeypatch.setattr(rag_pipeline, "_fetch_candidate_places", fake_fetch)
    monkeypatch.setattr(rag_pipeline, "_rank_candidates", malformed_rank)

    result = asyncio.run(
        rag_pipeline.generate_recommendations(
            "pizza",
            {"lat": 43.6, "lng": -79.4},
        )
    )

    assert result["recommendations"][0]["lat"] == 43.61
    assert result["recommendations"][0]["lng"] == -79.41


def test_pipeline_empty_results_returns_valid_response(monkeypatch):
    async def fake_fetch(search_terms, location):
        return []

    monkeypatch.setattr(rag_pipeline, "_fetch_candidate_places", fake_fetch)

    result = asyncio.run(
        rag_pipeline.generate_recommendations(
            "pizza",
            {"lat": 43.6, "lng": -79.4},
        )
    )

    assert result["reply"]
    assert result["recommendations"] == []


def test_pipeline_total_deadline_returns_without_waiting(monkeypatch):
    async def slow_fetch(search_terms, location):
        await asyncio.sleep(0.1)
        return []

    monkeypatch.setattr(rag_pipeline, "_fetch_candidate_places", slow_fetch)
    monkeypatch.setattr(rag_pipeline, "PIPELINE_TIMEOUT_SECONDS", 0.01)

    result = asyncio.run(
        rag_pipeline.generate_recommendations(
            "pizza",
            {"lat": 43.6, "lng": -79.4},
        )
    )

    assert result["reply"]
    assert result["recommendations"] == []


def test_session_pool_skips_live_search_when_three_explicit_matches(monkeypatch):
    pool = [
        {
            "place_id": f"ramen-{index}",
            "name": f"Ramen {index}",
            "tags": ["Japanese"],
            "rating": 4.5,
        }
        for index in range(3)
    ]
    calls = {"live": 0}

    async def fail_if_live(*_args, **_kwargs):
        calls["live"] += 1
        return []

    async def echo_rank(_query, candidates):
        return {"reply": "Pool matches", "recommendations": candidates[:3]}

    monkeypatch.setattr(rag_pipeline, "_fetch_candidate_places", fail_if_live)
    monkeypatch.setattr(rag_pipeline, "_rank_candidates", echo_rank)

    result = asyncio.run(
        rag_pipeline.generate_recommendations(
            "ramen tonight",
            {"lat": 43.6, "lng": -79.4},
            pool,
        )
    )

    assert calls["live"] == 0
    assert [item["place_id"] for item in result["recommendations"]] == [
        "ramen-0",
        "ramen-1",
        "ramen-2",
    ]


def test_sparse_explicit_pool_uses_live_search_and_deduplicates(monkeypatch):
    pool = [
        {"place_id": "shared", "name": "Shared Pizza", "tags": ["Pizza"]},
        {"place_id": "pool-only", "name": "Pool Pizza", "tags": ["Pizza"]},
    ]
    captured: Dict[str, Any] = {}

    async def fake_live(*_args, **_kwargs):
        return [
            {"place_id": "shared", "name": "Duplicate Shared Pizza"},
            {"place_id": "live-only", "name": "Live Pizza"},
        ]

    async def capture_rank(_query, candidates):
        captured["ids"] = [item["place_id"] for item in candidates]
        return {"reply": "Merged", "recommendations": candidates[:3]}

    monkeypatch.setattr(rag_pipeline, "_fetch_candidate_places", fake_live)
    monkeypatch.setattr(rag_pipeline, "_rank_candidates", capture_rank)

    asyncio.run(
        rag_pipeline.generate_recommendations(
            "pizza",
            {"lat": 43.6, "lng": -79.4},
            pool,
        )
    )

    assert captured["ids"] == ["shared", "pool-only", "live-only"]


def test_ranked_recommendations_only_accept_known_place_ids():
    source = [
        {"place_id": "known", "name": "Known Place", "rating": 4.8},
    ]
    ranked = [
        {"place_id": "invented", "reason": "Not allowed"},
        {"place_id": "known", "reason": "Allowed"},
    ]

    merged = rag_pipeline._merge_ranked_recommendations(ranked, source)

    assert merged == [
        {
            "place_id": "known",
            "name": "Known Place",
            "rating": 4.8,
            "address": None,
            "reason": "Allowed",
            "lat": None,
            "lng": None,
        }
    ]


def test_chat_endpoint_returns_mocked_response(mocked_pipeline):
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            payload = {
                "query": "I want a cozy bowl of ramen tonight.",
                "location": {"lat": 43.6532, "lng": -79.3832},
            }
            return await client.post("/chat", json=payload)

    response = asyncio.run(exercise())
    assert response.status_code == 200
    body = response.json()

    assert body["reply"]
    assert isinstance(body["recommendations"], list)
    assert body["recommendations"][0]["name"] == "Mock Ramen House"
    assert body["usage"] == {
        "limit": 3,
        "used": 1,
        "remaining": 2,
        "reset_at": body["usage"]["reset_at"],
    }
    assert response.headers["x-ratelimit-limit"] == "3"
    assert response.headers["x-ratelimit-remaining"] == "2"
    assert response.headers["x-craveai-anonymous-token"]

    # Ensure the mocked RAG functions executed.
    assert mocked_pipeline["extract"] == 1
    assert mocked_pipeline["places"] == 1
    assert mocked_pipeline["rank"] == 1


def test_chat_endpoint_returns_cumulative_usage_after_each_chat(mocked_pipeline):
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            payload = {
                "query": "I want cozy Indian food tonight.",
                "location": {"lat": 43.6532, "lng": -79.3832},
            }
            first = await client.post("/chat", json=payload)
            token = first.headers[ANONYMOUS_TOKEN_HEADER]
            second = await client.post(
                "/chat",
                headers={ANONYMOUS_TOKEN_HEADER: token},
                json={**payload, "query": "Now make it spicy."},
            )
            return first, second

    first_response, second_response = asyncio.run(exercise())

    assert first_response.status_code == 200
    assert first_response.json()["usage"]["used"] == 1
    assert first_response.json()["usage"]["remaining"] == 2
    assert first_response.headers["x-ratelimit-remaining"] == "2"

    assert second_response.status_code == 200
    assert second_response.json()["usage"]["used"] == 2
    assert second_response.json()["usage"]["remaining"] == 1
    assert second_response.headers["x-ratelimit-remaining"] == "1"
    assert mocked_pipeline["extract"] == 2


def test_chat_endpoint_enforces_quota_even_if_disable_flag_is_false(
    monkeypatch,
    mocked_pipeline,
):
    monkeypatch.setenv("USAGE_LIMITS_ENABLED", "false")
    get_settings.cache_clear()
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "query": "I want cozy Indian food tonight.",
                    "location": {"lat": 43.6532, "lng": -79.3832},
                },
            )

    response = asyncio.run(exercise())

    assert response.status_code == 200
    assert response.json()["usage"]["used"] == 1
    assert response.json()["usage"]["remaining"] == 2
    assert response.headers["x-ratelimit-remaining"] == "2"
    assert mocked_pipeline["extract"] == 1


def test_cors_exposes_rate_limit_headers_for_browser_badge_fallback(mocked_pipeline):
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.post(
                "/chat",
                headers={
                    "Origin": "http://localhost:5173",
                },
                json={
                    "query": "I want cozy Indian food tonight.",
                    "location": {"lat": 43.6532, "lng": -79.3832},
                },
            )

    response = asyncio.run(exercise())

    exposed_headers = response.headers["access-control-expose-headers"].lower()
    assert "x-ratelimit-limit" in exposed_headers
    assert "x-ratelimit-remaining" in exposed_headers
    assert "x-ratelimit-reset" in exposed_headers
    assert "x-craveai-anonymous-token" in exposed_headers


def test_chat_endpoint_returns_429_before_pipeline_when_quota_exhausted(
    monkeypatch,
    mocked_pipeline,
):
    monkeypatch.setenv("DAILY_CHAT_MESSAGE_LIMIT", "0")
    get_settings.cache_clear()
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            payload = {
                "query": "I want a cozy bowl of ramen tonight.",
                "location": {"lat": 43.6532, "lng": -79.3832},
            }
            return await client.post("/chat", json=payload)

    response = asyncio.run(exercise())
    assert response.status_code == 429
    body = response.json()

    assert body["detail"]["code"] == "daily_chat_message_quota_exceeded"
    assert body["detail"]["usage"]["limit"] == 0
    assert body["detail"]["usage"]["used"] == 0
    assert response.headers["x-ratelimit-limit"] == "0"
    assert response.headers["x-ratelimit-remaining"] == "0"
    assert response.headers["x-craveai-anonymous-token"]
    assert "retry-after" in response.headers

    assert mocked_pipeline["extract"] == 0
    assert mocked_pipeline["places"] == 0
    assert mocked_pipeline["rank"] == 0


def test_chat_endpoint_allows_three_messages_then_blocks_fourth(mocked_pipeline):
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            payload = {
                "query": "I want a cozy bowl of ramen tonight.",
                "location": {"lat": 43.6532, "lng": -79.3832},
            }
            first = await client.post("/chat", json=payload)
            token = first.headers[ANONYMOUS_TOKEN_HEADER]
            headers = {ANONYMOUS_TOKEN_HEADER: token}
            second = await client.post(
                "/chat",
                headers=headers,
                json={**payload, "query": "Make it spicy."},
            )
            third = await client.post(
                "/chat",
                headers=headers,
                json={**payload, "query": "Any late-night spots?"},
            )
            fourth = await client.post(
                "/chat",
                headers=headers,
                json={**payload, "query": "One more idea?"},
            )
            return first, second, third, fourth

    first_response, second_response, third_response, fourth_response = asyncio.run(exercise())

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert third_response.status_code == 200
    assert third_response.json()["usage"]["used"] == 3
    assert third_response.json()["usage"]["remaining"] == 0

    assert fourth_response.status_code == 429
    assert fourth_response.json()["detail"]["usage"]["used"] == 3
    assert fourth_response.headers["x-ratelimit-remaining"] == "0"
    assert mocked_pipeline["extract"] == 3


def test_chat_developer_mode_allows_unlimited_messages(monkeypatch, mocked_pipeline):
    monkeypatch.setenv("CHAT_DEVELOPER_MODE", "true")
    get_settings.cache_clear()
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            payload = {
                "query": "I want a cozy bowl of ramen tonight.",
                "location": {"lat": 43.6532, "lng": -79.3832},
            }
            return [
                await client.post(
                    "/chat",
                    json={**payload, "query": f"{payload['query']} ({index})"},
                )
                for index in range(5)
            ]

    responses = asyncio.run(exercise())

    assert all(response.status_code == 200 for response in responses)
    assert all(response.json()["usage"]["unlimited"] is True for response in responses)
    assert all("x-ratelimit-limit" not in response.headers for response in responses)
    assert mocked_pipeline["extract"] == 5


def test_chat_status_reports_developer_mode_without_pipeline_call(
    monkeypatch,
    mocked_pipeline,
):
    monkeypatch.setenv("CHAT_DEVELOPER_MODE", "true")
    get_settings.cache_clear()
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.get("/chat/status")

    response = asyncio.run(exercise())

    assert response.status_code == 200
    assert response.json()["usage"]["unlimited"] is True
    assert mocked_pipeline["extract"] == 0


def test_chat_status_does_not_report_unlimited_in_standard_mode(mocked_pipeline):
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.get("/chat/status")

    response = asyncio.run(exercise())

    assert response.status_code == 200
    assert response.json() == {}
    assert mocked_pipeline["extract"] == 0


def test_chat_developer_mode_is_rejected_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CHAT_DEVELOPER_MODE", "true")
    monkeypatch.setenv("IDENTITY_SIGNING_SECRET", "x" * 32)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="CHAT_DEVELOPER_MODE cannot be enabled"):
        create_app()


def test_chat_dev_bypass_header_allows_unlimited_messages_in_production(
    monkeypatch,
    mocked_pipeline,
):
    bypass_secret = "production-test-bypass-secret-32-chars"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("IDENTITY_SIGNING_SECRET", "x" * 32)
    monkeypatch.setenv("CHAT_DEV_BYPASS_SECRET", bypass_secret)
    get_settings.cache_clear()
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            payload = {
                "query": "I want a cozy bowl of ramen tonight.",
                "location": {"lat": 43.6532, "lng": -79.3832},
            }
            return [
                await client.post(
                    "/chat",
                    headers={DEV_BYPASS_HEADER: bypass_secret},
                    json={**payload, "query": f"{payload['query']} ({index})"},
                )
                for index in range(5)
            ]

    responses = asyncio.run(exercise())

    assert all(response.status_code == 200 for response in responses)
    assert all(response.json()["usage"]["unlimited"] is True for response in responses)
    assert all("x-ratelimit-limit" not in response.headers for response in responses)
    assert mocked_pipeline["extract"] == 5


def test_chat_dev_bypass_header_with_wrong_secret_still_enforces_quota(
    monkeypatch,
    mocked_pipeline,
):
    monkeypatch.setenv("CHAT_DEV_BYPASS_SECRET", "test-bypass-secret")
    get_settings.cache_clear()
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            payload = {
                "query": "I want a cozy bowl of ramen tonight.",
                "location": {"lat": 43.6532, "lng": -79.3832},
            }
            first = await client.post(
                "/chat",
                headers={DEV_BYPASS_HEADER: "wrong-secret"},
                json=payload,
            )
            token = first.headers[ANONYMOUS_TOKEN_HEADER]
            headers = {
                ANONYMOUS_TOKEN_HEADER: token,
                DEV_BYPASS_HEADER: "wrong-secret",
            }
            second = await client.post(
                "/chat",
                headers=headers,
                json={**payload, "query": "Make it spicy."},
            )
            third = await client.post(
                "/chat",
                headers=headers,
                json={**payload, "query": "Any late-night spots?"},
            )
            fourth = await client.post(
                "/chat",
                headers=headers,
                json={**payload, "query": "One more idea?"},
            )
            return first, second, third, fourth

    first_response, second_response, third_response, fourth_response = asyncio.run(exercise())

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert third_response.status_code == 200
    assert fourth_response.status_code == 429
    assert fourth_response.json()["detail"]["usage"]["used"] == 3
    assert mocked_pipeline["extract"] == 3


def test_chat_dev_bypass_secret_must_be_strong_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("IDENTITY_SIGNING_SECRET", "x" * 32)
    monkeypatch.setenv("CHAT_DEV_BYPASS_SECRET", "too-short")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="CHAT_DEV_BYPASS_SECRET must contain"):
        create_app()


def test_chat_quota_survives_new_client_when_anonymous_token_is_reused(mocked_pipeline):
    app = create_app()

    async def exercise():
        payload = {
            "query": "I want a cozy bowl of ramen tonight.",
            "location": {"lat": 43.6532, "lng": -79.3832},
        }
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as first_client:
            first = await first_client.post("/chat", json=payload)
            token = first.headers[ANONYMOUS_TOKEN_HEADER]

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as second_client:
            headers = {ANONYMOUS_TOKEN_HEADER: token}
            second = await second_client.post(
                "/chat",
                headers=headers,
                json={**payload, "query": "Make it spicy."},
            )
            third = await second_client.post(
                "/chat",
                headers=headers,
                json={**payload, "query": "Any late-night spots?"},
            )
            fourth = await second_client.post(
                "/chat",
                headers=headers,
                json={**payload, "query": "One more idea?"},
            )
            return first, second, third, fourth

    first_response, second_response, third_response, fourth_response = asyncio.run(exercise())

    assert first_response.status_code == 200
    assert second_response.json()["usage"]["used"] == 2
    assert third_response.json()["usage"]["used"] == 3
    assert fourth_response.status_code == 429
    assert fourth_response.json()["detail"]["usage"]["used"] == 3
    assert mocked_pipeline["extract"] == 3


def test_chat_replaces_forged_anonymous_token_without_trusting_it(mocked_pipeline):
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            payload = {
                "query": "I want a cozy bowl of ramen tonight.",
                "location": {"lat": 43.6532, "lng": -79.3832},
            }
            forged = "anon:attacker.invalid-signature"
            first = await client.post(
                "/chat",
                headers={ANONYMOUS_TOKEN_HEADER: forged},
                json=payload,
            )
            issued_token = first.headers[ANONYMOUS_TOKEN_HEADER]
            second = await client.post(
                "/chat",
                headers={ANONYMOUS_TOKEN_HEADER: issued_token},
                json={**payload, "query": "Make it spicy."},
            )
            return forged, first, issued_token, second

    forged, first_response, issued_token, second_response = asyncio.run(exercise())

    assert first_response.status_code == 200
    assert first_response.json()["usage"]["used"] == 1
    assert issued_token != forged
    assert second_response.json()["usage"]["used"] == 2
    assert mocked_pipeline["extract"] == 2


def test_usage_quota_resets_on_new_utc_date():
    init_storage()

    first_day = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    next_day = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)

    first = asyncio.run(
        reserve_daily_quota(
            user_id="reset-user",
            token_cost=800,
            daily_limit=1000,
            now=first_day,
        )
    )
    assert first.used == 800
    assert first.remaining == 200

    with pytest.raises(DailyQuotaExceeded):
        asyncio.run(
            reserve_daily_quota(
                user_id="reset-user",
                token_cost=800,
                daily_limit=1000,
                now=first_day,
            )
        )

    second = asyncio.run(
        reserve_daily_quota(
            user_id="reset-user",
            token_cost=800,
            daily_limit=1000,
            now=next_day,
        )
    )
    assert second.used == 800
    assert second.remaining == 200


def test_chat_endpoint_rejects_caller_selected_quota_identity(mocked_pipeline):
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            safe_payload = {
                "query": "I want a cozy bowl of ramen tonight.",
                "location": {"lat": 43.6532, "lng": -79.3832},
            }
            first = await client.post("/chat", json=safe_payload)
            forged_payload = {**safe_payload, "user_id": "fresh-attacker-bucket"}
            second = await client.post("/chat", json=forged_payload)
            return first, second

    first_response, second_response = asyncio.run(exercise())
    assert first_response.status_code == 200
    assert second_response.status_code == 422

    assert first_response.json()["usage"]["used"] == 1
    assert mocked_pipeline["extract"] == 1


def test_chat_rejects_oversized_input_before_pipeline(mocked_pipeline):
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "query": "x" * 2001,
                    "location": {"lat": 43.6532, "lng": -79.3832},
                },
            )

    response = asyncio.run(exercise())
    assert response.status_code == 422
    assert mocked_pipeline == {"extract": 0, "places": 0, "rank": 0}


def test_chat_rejects_more_than_twenty_session_candidates(mocked_pipeline):
    app = create_app()
    candidates = [
        {
            "place_id": f"place-{index}",
            "name": f"Place {index}",
            "rating": 4.5,
            "lat": 43.65,
            "lng": -79.38,
        }
        for index in range(21)
    ]

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "query": "dinner",
                    "location": {"lat": 43.65, "lng": -79.38},
                    "candidate_places": candidates,
                },
            )

    response = asyncio.run(exercise())
    assert response.status_code == 422
    assert mocked_pipeline == {"extract": 0, "places": 0, "rank": 0}


@pytest.mark.parametrize(
    "candidate",
    [
        {"place_id": "long-name", "name": "x" * 201},
        {"place_id": "bad-location", "name": "Bad Location", "lat": 91},
        {
            "place_id": "extra-field",
            "name": "Extra Field",
            "reason": "Candidate reasons are not accepted from the browser.",
        },
    ],
)
def test_chat_rejects_invalid_session_candidate_fields(
    monkeypatch,
    mocked_pipeline,
    candidate,
):
    monkeypatch.setenv("DAILY_CHAT_MESSAGE_LIMIT", "10")
    get_settings.cache_clear()
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "query": "dinner",
                    "location": {"lat": 43.65, "lng": -79.38},
                    "candidate_places": [candidate],
                },
            )

    response = asyncio.run(exercise())
    assert response.status_code == 422
    assert mocked_pipeline == {"extract": 0, "places": 0, "rank": 0}


def test_global_quota_cannot_be_bypassed_with_multiple_actor_ids():
    init_storage()

    first = asyncio.run(
        reserve_daily_quota(
            user_id="ip:203.0.113.1",
            token_cost=600,
            daily_limit=1000,
            global_daily_limit=1000,
        )
    )
    assert first.used == 600

    with pytest.raises(DailyQuotaExceeded) as exc_info:
        asyncio.run(
            reserve_daily_quota(
                user_id="ip:203.0.113.2",
                token_cost=600,
                daily_limit=1000,
                global_daily_limit=1000,
            )
        )
    assert exc_info.value.usage.limit == 1000
    assert exc_info.value.usage.used == 600


def test_places_global_quota_is_isolated_from_chat_global_quota():
    init_storage()

    asyncio.run(
        reserve_daily_quota(
            user_id="chat:user",
            token_cost=1000,
            daily_limit=1000,
            global_daily_limit=1000,
        )
    )
    places_usage = asyncio.run(
        reserve_daily_quota(
            user_id="places:user",
            token_cost=1,
            daily_limit=20,
            global_daily_limit=1000,
            global_user_id=PLACES_GLOBAL_USAGE_USER_ID,
        )
    )

    assert places_usage.used == 1
    assert places_usage.remaining == 19


def test_places_endpoint_reserves_quota_before_provider_call(monkeypatch):
    monkeypatch.setenv("DAILY_PLACES_REQUEST_LIMIT", "1")
    monkeypatch.setenv("GLOBAL_DAILY_PLACES_REQUEST_LIMIT", "10")
    get_settings.cache_clear()
    calls = 0

    async def fake_places(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr(places_router, "get_top_rated_nearby", fake_places)
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            first = await client.get("/places/suggestions?lat=43.65&lng=-79.38")
            anonymous_token = first.headers[ANONYMOUS_TOKEN_HEADER]
            second = await client.get(
                "/places/suggestions?lat=43.65&lng=-79.38",
                headers={ANONYMOUS_TOKEN_HEADER: anonymous_token},
            )
            return first, second

    first_response, second_response = asyncio.run(exercise())
    assert first_response.status_code == 200
    assert first_response.headers["x-ratelimit-remaining"] == "0"
    assert second_response.status_code == 429
    assert second_response.json()["detail"]["code"] == "daily_places_request_quota_exceeded"
    assert calls == 1


def test_places_replaces_forged_anonymous_token(monkeypatch):
    monkeypatch.setenv("DAILY_PLACES_REQUEST_LIMIT", "2")
    get_settings.cache_clear()

    async def fake_places(*_args, **_kwargs):
        return []

    monkeypatch.setattr(places_router, "get_top_rated_nearby", fake_places)
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            first = await client.get(
                "/places/suggestions?lat=43.65&lng=-79.38",
                headers={ANONYMOUS_TOKEN_HEADER: "forged-token"},
            )
            issued_token = first.headers[ANONYMOUS_TOKEN_HEADER]
            second = await client.get(
                "/places/suggestions?lat=43.65&lng=-79.38",
                headers={ANONYMOUS_TOKEN_HEADER: issued_token},
            )
            return first, issued_token, second

    first, issued_token, second = asyncio.run(exercise())

    assert first.status_code == 200
    assert issued_token != "forged-token"
    assert first.headers["x-ratelimit-remaining"] == "1"
    assert second.status_code == 200
    assert second.headers["x-ratelimit-remaining"] == "0"


def test_top_rated_places_filter_rejects_incidental_food_venues():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "OK",
                "results": [
                    {
                        "name": "Streetsville Bowl 5 pin bowling the Canadian game",
                        "rating": 4.4,
                        "user_ratings_total": 1046,
                        "vicinity": "128 Queen Street South #9, Mississauga",
                        "types": [
                            "bowling_alley",
                            "meal_takeaway",
                            "restaurant",
                            "food",
                            "point_of_interest",
                            "establishment",
                        ],
                        "place_id": "bowling-alley",
                        "geometry": {"location": {"lat": 43.58, "lng": -79.72}},
                    },
                    {
                        "name": "Sushi In Sushi",
                        "rating": 4.5,
                        "user_ratings_total": 1149,
                        "vicinity": "2310 Battleford Road, Mississauga",
                        "types": [
                            "restaurant",
                            "meal_takeaway",
                            "food",
                            "point_of_interest",
                            "establishment",
                        ],
                        "place_id": "sushi-spot",
                        "geometry": {"location": {"lat": 43.59, "lng": -79.73}},
                    },
                ],
            }

    class FakeClient:
        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    results = asyncio.run(
        places_service._fetch_and_filter(
            FakeClient(),
            lat=43.65,
            lng=-79.38,
            radius=5000,
            min_rating=4.0,
        )
    )

    assert [place["name"] for place in results] == ["Sushi In Sushi"]
    assert "Bowling Alley" not in results[0]["tags"]


def test_suggestion_quality_balances_rating_and_review_confidence():
    high_confidence = {
        "rating": 4.7,
        "user_ratings_total": 1000,
    }
    low_confidence = {
        "rating": 4.8,
        "user_ratings_total": 5,
    }

    assert places_service._quality_sort_key(
        high_confidence
    ) > places_service._quality_sort_key(low_confidence)


def test_top_rated_suggestions_are_deduplicated_and_capped(monkeypatch):
    candidates = [
        {
            "place_id": f"place-{index}",
            "name": f"Place {index}",
            "rating": 4.5,
            "user_ratings_total": 100 + index,
        }
        for index in range(25)
    ]
    candidates.append({**candidates[0], "name": "Duplicate"})

    async def fake_fetch(*_args, **_kwargs):
        return candidates

    monkeypatch.setattr(places_service, "_fetch_and_filter", fake_fetch)

    results = asyncio.run(places_service.get_top_rated_nearby(43.65, -79.38))

    assert len(results) == 20
    assert len({item["place_id"] for item in results}) == 20


def test_restaurant_filter_rejects_closed_and_malformed_places():
    valid = {
        "place_id": "valid",
        "name": "Valid Cafe",
        "types": ["cafe"],
        "geometry": {"location": {"lat": 43.6, "lng": -79.4}},
    }

    assert places_service._is_restaurant_candidate(valid)
    assert not places_service._is_restaurant_candidate(
        {**valid, "business_status": "CLOSED_PERMANENTLY"}
    )
    assert not places_service._is_restaurant_candidate(
        {key: value for key, value in valid.items() if key != "place_id"}
    )


def test_favorites_require_signed_owner_identity():
    settings = get_settings()
    alice_token = issue_identity_token("alice", settings.IDENTITY_SIGNING_SECRET)
    headers = {"Authorization": f"Bearer {alice_token}"}
    app = create_app()

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            own_create = await client.post(
                "/favorites",
                headers=headers,
                json={"user_id": "alice", "restaurant": "Safe Ramen", "note": "Mine"},
            )
            own_read = await client.get("/favorites/alice", headers=headers)
            cross_read = await client.get("/favorites/bob", headers=headers)
            cross_write = await client.post(
                "/favorites",
                headers=headers,
                json={"user_id": "bob", "restaurant": "Injected"},
            )
            missing_token = await client.get("/favorites/alice")
            forged_token = await client.get(
                "/favorites/alice",
                headers={"Authorization": "Bearer YWxpY2U.invalid"},
            )
            return own_create, own_read, cross_read, cross_write, missing_token, forged_token

    own_create, own_read, cross_read, cross_write, missing_token, forged_token = asyncio.run(
        exercise()
    )
    assert own_create.status_code == 201
    assert own_read.status_code == 200
    assert own_read.json()["favorites"][0]["restaurant"] == "Safe Ramen"
    assert cross_read.status_code == 403
    assert cross_write.status_code == 403
    assert missing_token.status_code == 401
    assert forged_token.status_code == 401


def test_identity_tokens_expire():
    secret = get_settings().IDENTITY_SIGNING_SECRET
    token = issue_identity_token("alice", secret, ttl_seconds=60, now=100)

    assert verify_identity_token(token, secret, now=159) == "alice"
    with pytest.raises(ValueError, match="expired"):
        verify_identity_token(token, secret, now=160)
