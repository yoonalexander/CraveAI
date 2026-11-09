"""Provider-neutral chat helpers.

Gemini exposes an OpenAI-compatible endpoint, so both providers are driven
through the OpenAI SDK. The free Gemini tier is enough for development; set
LLM_PROVIDER=openai (or keep an OPENAI_API_KEY) to stay on OpenAI.

OpenAI-only request fields (store, verbosity) are omitted for Gemini; Gemini
uses max_tokens as its max output token limit.
"""
from __future__ import annotations

from typing import Any, Literal, cast

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_OPENAI_MODEL = "gpt-5-nano"
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"

Provider = Literal["openai", "gemini"]
_PROVIDERS = frozenset({"openai", "gemini"})


def resolve_provider(settings: Any) -> Provider:
    """Resolve the active provider, defaulting to whichever key is present."""
    configured = str(getattr(settings, "LLM_PROVIDER", "") or "").strip().lower()
    if configured in _PROVIDERS:
        return cast(Provider, configured)
    if _has_key(settings, "GEMINI_API_KEY") and not _has_key(
        settings, "OPENAI_API_KEY"
    ):
        return "gemini"
    return "openai"


def is_configured(settings: Any) -> bool:
    """True when the active provider has an API key."""
    return bool(_api_key(settings))


def client_options(
    settings: Any, *, timeout: float | None = None, max_retries: int = 0
) -> dict[str, Any]:
    """Keyword arguments for AsyncOpenAI that select the configured provider."""
    options: dict[str, Any] = {
        "api_key": _api_key(settings),
        "max_retries": max_retries,
    }
    if timeout is not None:
        options["timeout"] = timeout
    base_url = _base_url(settings)
    if base_url:
        options["base_url"] = base_url
    return options


def model_name(settings: Any, override: str = "") -> str:
    """Use an explicit model first, then MODEL_NAME, then the provider default."""
    if override:
        return override
    configured = str(getattr(settings, "MODEL_NAME", "") or "").strip()
    if configured:
        return configured
    if resolve_provider(settings) == "gemini":
        return DEFAULT_GEMINI_MODEL
    return DEFAULT_OPENAI_MODEL


def completion_options(
    settings: Any,
    *,
    max_completion_tokens: int,
    reasoning_effort: str | None = None,
    verbosity: str | None = None,
) -> dict[str, Any]:
    """Request fields shared by both providers, omitting OpenAI-only options."""
    if resolve_provider(settings) == "gemini":
        options: dict[str, Any] = {"max_tokens": max_completion_tokens}
        if reasoning_effort:
            options["reasoning_effort"] = reasoning_effort
        return options
    options = {
        "max_completion_tokens": max_completion_tokens,
        "store": False,
    }
    if reasoning_effort:
        options["reasoning_effort"] = reasoning_effort
    if verbosity:
        options["verbosity"] = verbosity
    return options


def _api_key(settings: Any) -> str:
    name = (
        "GEMINI_API_KEY"
        if resolve_provider(settings) == "gemini"
        else "OPENAI_API_KEY"
    )
    return str(getattr(settings, name, "") or "").strip()


def _has_key(settings: Any, name: str) -> bool:
    return bool(str(getattr(settings, name, "") or "").strip())


def _base_url(settings: Any) -> str | None:
    if resolve_provider(settings) != "gemini":
        return None
    configured = str(getattr(settings, "GEMINI_BASE_URL", "") or "").strip()
    return (configured or GEMINI_BASE_URL).rstrip("/") + "/"
