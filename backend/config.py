from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import logging

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = PROJECT_ROOT / ".env"

# Load environment variables from .env if present. Values already present in the
# environment take precedence because override defaults to False.
load_dotenv(DOTENV_PATH, override=False)

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid integer for %s=%r; using %s.", name, value, default)
        return default


@dataclass(frozen=True)
class Config:
    """Central application settings."""

    OPENAI_API_KEY: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    GOOGLE_API_KEY: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    SQLITE_DB_PATH: str = field(default_factory=lambda: os.getenv("SQLITE_DB_PATH", "./data/craveai.db"))
    REDIS_URL: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))
    MODEL_NAME: str = field(default_factory=lambda: os.getenv("MODEL_NAME", "gpt-5-nano"))
    CHAT_PIPELINE_TIMEOUT_SECONDS: int = field(
        default_factory=lambda: _env_int("CHAT_PIPELINE_TIMEOUT_SECONDS", 20)
    )
    CHAT_RANKING_TIMEOUT_SECONDS: int = field(
        default_factory=lambda: _env_int("CHAT_RANKING_TIMEOUT_SECONDS", 12)
    )
    ENVIRONMENT: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    USAGE_LIMITS_ENABLED: bool = field(
        default_factory=lambda: _env_bool("USAGE_LIMITS_ENABLED", True)
    )
    DAILY_TOKEN_LIMIT: int = field(default_factory=lambda: _env_int("DAILY_TOKEN_LIMIT", 10000))
    DAILY_CHAT_MESSAGE_LIMIT: int = field(
        default_factory=lambda: _env_int("DAILY_CHAT_MESSAGE_LIMIT", 3)
    )
    CHAT_DEVELOPER_MODE: bool = field(
        default_factory=lambda: _env_bool("CHAT_DEVELOPER_MODE", False)
    )
    CHAT_DEV_BYPASS_SECRET: str = field(
        default_factory=lambda: os.getenv("CHAT_DEV_BYPASS_SECRET", "")
    )
    GLOBAL_DAILY_TOKEN_LIMIT: int = field(
        default_factory=lambda: _env_int("GLOBAL_DAILY_TOKEN_LIMIT", 100000)
    )
    PLACES_REQUEST_TOKEN_COST: int = field(
        default_factory=lambda: _env_int("PLACES_REQUEST_TOKEN_COST", 500)
    )
    IDENTITY_SIGNING_SECRET: str = field(
        default_factory=lambda: os.getenv("IDENTITY_SIGNING_SECRET", "")
    )

    def validate(self) -> None:
        """Verify that mandatory configuration values are provided."""
        if not self.OPENAI_API_KEY:
            message = "Missing required configuration value: OPENAI_API_KEY"
            logger.error(message)
            raise RuntimeError(message)

        if not self.GOOGLE_API_KEY:
            logger.warning(
                "GOOGLE_API_KEY not configured; restaurant searches will fall back to placeholder data."
            )

        if (
            self.ENVIRONMENT.lower() == "production"
            and len(self.IDENTITY_SIGNING_SECRET) < 32
        ):
            message = (
                "IDENTITY_SIGNING_SECRET must contain at least 32 characters in production"
            )
            logger.error(message)
            raise RuntimeError(message)

        if self.ENVIRONMENT.lower() == "production" and self.CHAT_DEVELOPER_MODE:
            message = "CHAT_DEVELOPER_MODE cannot be enabled in production"
            logger.error(message)
            raise RuntimeError(message)

        if (
            self.ENVIRONMENT.lower() == "production"
            and self.CHAT_DEV_BYPASS_SECRET
            and len(self.CHAT_DEV_BYPASS_SECRET) < 32
        ):
            message = "CHAT_DEV_BYPASS_SECRET must contain at least 32 characters in production"
            logger.error(message)
            raise RuntimeError(message)


@lru_cache()
def get_settings() -> Config:
    """Return a cached settings instance."""
    return Config()
