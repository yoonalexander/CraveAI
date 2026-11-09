import base64
import asyncio
from types import SimpleNamespace

import pytest

from backend.config import Config
from backend.services import llm


def settings(**overrides):
    values = {
        "LLM_PROVIDER": "auto",
        "OPENAI_API_KEY": "",
        "GEMINI_API_KEY": "",
        "GEMINI_BASE_URL": "",
        "MODEL_NAME": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_auto_provider_uses_whichever_key_is_configured():
    assert llm.resolve_provider(settings(OPENAI_API_KEY="openai")) == "openai"
    assert llm.resolve_provider(settings(GEMINI_API_KEY="gemini")) == "gemini"
    # Both keys present: auto stays on the historical OpenAI default.
    assert (
        llm.resolve_provider(settings(OPENAI_API_KEY="o", GEMINI_API_KEY="g"))
        == "openai"
    )


def test_explicit_provider_overrides_auto_detection():
    both = settings(LLM_PROVIDER="gemini", OPENAI_API_KEY="o", GEMINI_API_KEY="g")
    assert llm.resolve_provider(both) == "gemini"


def test_gemini_options_use_the_compatible_endpoint_without_openai_only_fields():
    gemini = settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="gemini-key")

    assert llm.is_configured(gemini) is True
    assert llm.model_name(gemini) == "gemini-3.8-flash"
    assert llm.client_options(gemini, timeout=5) == {
        "api_key": "gemini-key",
        "max_retries": 0,
        "timeout": 5,
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    }
    assert llm.completion_options(
        gemini,
        max_completion_tokens=900,
        reasoning_effort="minimal",
        verbosity="low",
    ) == {"max_tokens": 900, "reasoning_effort": "minimal"}


def test_openai_keeps_the_existing_request_shape():
    openai = settings(LLM_PROVIDER="openai", OPENAI_API_KEY="openai-key")

    assert llm.model_name(openai) == "gpt-5-nano"
    assert llm.client_options(openai, timeout=5) == {
        "api_key": "openai-key",
        "max_retries": 0,
        "timeout": 5,
    }
    assert llm.completion_options(
        openai,
        max_completion_tokens=900,
        reasoning_effort="minimal",
        verbosity="low",
    ) == {
        "max_completion_tokens": 900,
        "store": False,
        "reasoning_effort": "minimal",
        "verbosity": "low",
    }


def test_explicit_model_and_dedicated_model_overrides_win():
    gemini = settings(
        LLM_PROVIDER="gemini", GEMINI_API_KEY="g", MODEL_NAME="gemini-3.5-flash-lite"
    )
    assert llm.model_name(gemini) == "gemini-3.5-flash-lite"
    assert llm.model_name(gemini, "gemini-3.1-flash-lite") == "gemini-3.1-flash-lite"


def test_gemini_without_a_key_is_not_configured():
    assert llm.is_configured(settings(LLM_PROVIDER="gemini")) is False


def test_config_accepts_a_gemini_only_setup():
    config = Config(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="gemini-key",
        OPENAI_API_KEY="",
        DATABASE_URL="sqlite+pysqlite:///test.db",
    )
    config.validate()


def test_config_rejects_a_provider_without_its_key():
    config = Config(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="",
        OPENAI_API_KEY="openai-key",
        DATABASE_URL="sqlite+pysqlite:///test.db",
    )
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        config.validate()


def test_config_rejects_an_unknown_provider():
    config = Config(
        LLM_PROVIDER="anthropic",
        GEMINI_API_KEY="g",
        DATABASE_URL="sqlite+pysqlite:///test.db",
    )
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        config.validate()


def test_gemini_voice_transcription_sends_inline_audio(monkeypatch):
    from backend.routers import audio

    captured = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="  find noodles  ")
                    )
                ]
            )

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(audio, "AsyncOpenAI", FakeClient)
    gemini = settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="gemini-key")

    text = asyncio.run(
        audio._transcribe_with_gemini(gemini, b"audio-bytes", "audio/webm")
    )

    assert text == "  find noodles  "
    assert captured["client"]["base_url"].endswith("/openai/")
    request = captured["request"]
    assert request["model"] == "gemini-3.8-flash"
    assert request["max_tokens"] == 1500
    assert "store" not in request and "verbosity" not in request
    part = request["messages"][0]["content"][1]
    assert part["input_audio"]["format"] == "webm"
    assert part["input_audio"]["data"] == base64.b64encode(b"audio-bytes").decode()

