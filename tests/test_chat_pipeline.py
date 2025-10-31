import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from types import ModuleType

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


@pytest.fixture(autouse=True)
def configure_test_settings(monkeypatch):
    """Provide deterministic configuration for the test session."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("APP_ENV", "test")
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

    # Ensure the mocked RAG functions executed.
    assert mocked_pipeline["intent"] == 1
    assert mocked_pipeline["places"] == 1
    assert mocked_pipeline["rank"] == 1
