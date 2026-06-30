import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from types import ModuleType
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

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
from backend.services import rag_pipeline
from backend.services.storage import init_storage
from backend.services.usage_limits import DailyQuotaExceeded, reserve_daily_quota


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
    monkeypatch.setenv("CHAT_REQUEST_TOKEN_COST", "1500")
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
    call_tracker: Dict[str, int] = {"intent": 0, "places": 0, "rank": 0}

    async def fake_build_chat_model() -> Any:
        return object()

    async def fake_parse_intent(llm: Any, user_query: str) -> Dict[str, Any]:
        call_tracker["intent"] += 1
        return {"mood": ["cozy"], "cravings": ["ramen"], "diet": []}

    async def fake_retrieve_cuisines(intent: Dict[str, Any]) -> List[str]:
        return ["ramen"]

    async def fake_fetch_places(cuisines, location):
        call_tracker["places"] += 1
        return [
            {
                "name": "Mock Ramen House",
                "rating": 4.8,
                "address": "123 Test Street",
                "reason": "Mocked match for ramen craving.",
            }
        ]

    async def fake_rank_candidates(llm: Any, user_query: str, places):
        call_tracker["rank"] += 1
        return {
            "reply": "I'd try Mock Ramen House - sounds perfect for cozy ramen vibes.",
            "recommendations": places,
        }

    monkeypatch.setattr(rag_pipeline, "_build_chat_model", lambda: None, raising=False)
    monkeypatch.setattr(rag_pipeline, "_parse_intent", fake_parse_intent, raising=False)
    monkeypatch.setattr(rag_pipeline, "_retrieve_similar_cuisines", fake_retrieve_cuisines, raising=False)
    monkeypatch.setattr(rag_pipeline, "_fetch_candidate_places", fake_fetch_places, raising=False)
    monkeypatch.setattr(rag_pipeline, "_rank_candidates", fake_rank_candidates, raising=False)

    return call_tracker


def test_chat_endpoint_returns_mocked_response(mocked_pipeline):
    app = create_app()

    async def exercise():
        async with AsyncClient(app=app, base_url="http://test") as client:
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
        "limit": 10000,
        "used": 1500,
        "remaining": 8500,
        "reset_at": body["usage"]["reset_at"],
    }
    assert response.headers["x-ratelimit-limit"] == "10000"
    assert response.headers["x-ratelimit-remaining"] == "8500"

    # Ensure the mocked RAG functions executed.
    assert mocked_pipeline["intent"] == 1
    assert mocked_pipeline["places"] == 1
    assert mocked_pipeline["rank"] == 1


def test_chat_endpoint_returns_429_before_pipeline_when_quota_exhausted(
    monkeypatch,
    mocked_pipeline,
):
    monkeypatch.setenv("DAILY_TOKEN_LIMIT", "1000")
    get_settings.cache_clear()
    app = create_app()

    async def exercise():
        async with AsyncClient(app=app, base_url="http://test") as client:
            payload = {
                "user_id": "quota-user",
                "query": "I want a cozy bowl of ramen tonight.",
                "location": {"lat": 43.6532, "lng": -79.3832},
            }
            return await client.post("/chat", json=payload)

    response = asyncio.run(exercise())
    assert response.status_code == 429
    body = response.json()

    assert body["detail"]["code"] == "daily_token_quota_exceeded"
    assert body["detail"]["usage"]["limit"] == 1000
    assert body["detail"]["usage"]["used"] == 0
    assert response.headers["x-ratelimit-limit"] == "1000"
    assert response.headers["x-ratelimit-remaining"] == "1000"
    assert "retry-after" in response.headers

    assert mocked_pipeline["intent"] == 0
    assert mocked_pipeline["places"] == 0
    assert mocked_pipeline["rank"] == 0


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


def test_chat_endpoint_uses_deterministic_fallback_identity(mocked_pipeline):
    app = create_app()

    async def exercise():
        async with AsyncClient(app=app, base_url="http://test") as client:
            payload = {
                "query": "I want a cozy bowl of ramen tonight.",
                "location": {"lat": 43.6532, "lng": -79.3832},
            }
            first = await client.post("/chat", json=payload)
            second = await client.post("/chat", json=payload)
            return first, second

    first_response, second_response = asyncio.run(exercise())
    assert first_response.status_code == 200
    assert second_response.status_code == 200

    assert first_response.json()["usage"]["used"] == 1500
    assert second_response.json()["usage"]["used"] == 3000
    assert mocked_pipeline["intent"] == 2
