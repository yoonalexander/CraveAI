from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = PROJECT_ROOT / ".env"
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
        logger.warning("Invalid integer for %s; using %s.", name, default)
        return default


def _env_int_alias(name: str, legacy_name: str, default: int) -> int:
    if os.getenv(name) is not None:
        return _env_int(name, default)
    return _env_int(legacy_name, default)


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Config:
    """Central application settings. Secrets must be supplied by the runtime."""

    OPENAI_API_KEY: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    GOOGLE_API_KEY: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    MODEL_NAME: str = field(default_factory=lambda: os.getenv("MODEL_NAME", "gpt-5-nano"))
    ENVIRONMENT: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))

    DATABASE_URL: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    AUTO_CREATE_SCHEMA: bool = field(
        default_factory=lambda: _env_bool("AUTO_CREATE_SCHEMA", False)
    )
    SUPABASE_URL: str = field(
        default_factory=lambda: os.getenv(
            "SUPABASE_URL", "https://gyrxxvxsguwugqueuaav.supabase.co"
        ).rstrip("/")
    )
    SUPABASE_ANON_KEY: str = field(
        default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", "")
    )
    SUPABASE_SERVICE_ROLE_KEY: str = field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )
    SESSION_ENCRYPTION_KEY: str = field(
        default_factory=lambda: os.getenv("SESSION_ENCRYPTION_KEY", "")
    )
    IDENTITY_SIGNING_SECRET: str = field(
        default_factory=lambda: os.getenv("IDENTITY_SIGNING_SECRET", "")
    )
    FRONTEND_ORIGIN: str = field(
        default_factory=lambda: os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").rstrip("/")
    )
    ALLOWED_ORIGINS: tuple[str, ...] = field(
        default_factory=lambda: _env_csv("ALLOWED_ORIGINS", "http://localhost:5173")
    )
    PUBLIC_API_URL: str = field(
        default_factory=lambda: os.getenv("PUBLIC_API_URL", "http://localhost:5173/api").rstrip("/")
    )
    TRUSTED_PROXY_IPS: tuple[str, ...] = field(
        default_factory=lambda: _env_csv("TRUSTED_PROXY_IPS")
    )

    CHAT_PIPELINE_TIMEOUT_SECONDS: int = field(
        default_factory=lambda: _env_int("CHAT_PIPELINE_TIMEOUT_SECONDS", 20)
    )
    CHAT_RANKING_TIMEOUT_SECONDS: int = field(
        default_factory=lambda: _env_int("CHAT_RANKING_TIMEOUT_SECONDS", 12)
    )
    GUEST_DAILY_CHAT_LIMIT: int = field(
        default_factory=lambda: _env_int_alias(
            "GUEST_DAILY_CHAT_LIMIT", "DAILY_CHAT_MESSAGE_LIMIT", 3
        )
    )
    ACCOUNT_DAILY_CHAT_LIMIT: int = field(
        default_factory=lambda: _env_int("ACCOUNT_DAILY_CHAT_LIMIT", 25)
    )
    GUEST_DAILY_PLACES_LIMIT: int = field(
        default_factory=lambda: _env_int_alias(
            "GUEST_DAILY_PLACES_LIMIT", "DAILY_PLACES_REQUEST_LIMIT", 20
        )
    )
    ACCOUNT_DAILY_PLACES_LIMIT: int = field(
        default_factory=lambda: _env_int("ACCOUNT_DAILY_PLACES_LIMIT", 100)
    )
    GLOBAL_DAILY_CHAT_LIMIT: int = field(
        default_factory=lambda: _env_int_alias(
            "GLOBAL_DAILY_CHAT_LIMIT", "GLOBAL_DAILY_TOKEN_LIMIT", 100000
        )
    )
    GLOBAL_DAILY_PLACES_LIMIT: int = field(
        default_factory=lambda: _env_int_alias(
            "GLOBAL_DAILY_PLACES_LIMIT",
            "GLOBAL_DAILY_PLACES_REQUEST_LIMIT",
            1000,
        )
    )
    FEEDBACK_DAILY_LIMIT: int = field(
        default_factory=lambda: _env_int("FEEDBACK_DAILY_LIMIT", 20)
    )
    REQUEST_BODY_LIMIT_BYTES: int = field(
        default_factory=lambda: _env_int("REQUEST_BODY_LIMIT_BYTES", 64 * 1024)
    )
    AUTH_BURST_LIMIT: int = field(
        default_factory=lambda: _env_int("AUTH_BURST_LIMIT", 10)
    )
    SESSION_IDLE_DAYS: int = field(
        default_factory=lambda: _env_int("SESSION_IDLE_DAYS", 7)
    )
    SESSION_ABSOLUTE_DAYS: int = field(
        default_factory=lambda: _env_int("SESSION_ABSOLUTE_DAYS", 30)
    )
    SESSION_ROTATE_HOURS: int = field(
        default_factory=lambda: _env_int("SESSION_ROTATE_HOURS", 24)
    )

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def session_cookie_name(self) -> str:
        return "__Host-craveai_session" if self.is_production else "craveai_session"

    @property
    def guest_cookie_name(self) -> str:
        return "__Host-craveai_guest" if self.is_production else "craveai_guest"

    def validate(self) -> None:
        if not self.OPENAI_API_KEY:
            raise RuntimeError("Missing required configuration value: OPENAI_API_KEY")
        if not self.DATABASE_URL:
            raise RuntimeError("Missing required configuration value: DATABASE_URL")
        if not self.GOOGLE_API_KEY:
            logger.warning("GOOGLE_API_KEY is not configured; Places will use fallback data.")

        if self.is_production:
            if not self.DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg://")):
                raise RuntimeError("Production DATABASE_URL must use PostgreSQL")
            if self.AUTO_CREATE_SCHEMA:
                raise RuntimeError("AUTO_CREATE_SCHEMA must be false in production")
            required = {
                "SUPABASE_ANON_KEY": self.SUPABASE_ANON_KEY,
                "SUPABASE_SERVICE_ROLE_KEY": self.SUPABASE_SERVICE_ROLE_KEY,
                "SESSION_ENCRYPTION_KEY": self.SESSION_ENCRYPTION_KEY,
                "IDENTITY_SIGNING_SECRET": self.IDENTITY_SIGNING_SECRET,
                "FRONTEND_ORIGIN": self.FRONTEND_ORIGIN,
                "PUBLIC_API_URL": self.PUBLIC_API_URL,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise RuntimeError(
                    "Missing required production configuration: " + ", ".join(missing)
                )
            if len(self.IDENTITY_SIGNING_SECRET) < 32:
                raise RuntimeError("IDENTITY_SIGNING_SECRET must contain at least 32 characters")
            try:
                decoded = base64.urlsafe_b64decode(
                    self.SESSION_ENCRYPTION_KEY.encode("ascii")
                )
            except Exception as exc:
                raise RuntimeError("SESSION_ENCRYPTION_KEY must be a Fernet key") from exc
            if len(decoded) != 32:
                raise RuntimeError("SESSION_ENCRYPTION_KEY must decode to 32 bytes")
            if "*" in self.ALLOWED_ORIGINS:
                raise RuntimeError("Wildcard CORS origins are forbidden in production")


@lru_cache()
def get_settings() -> Config:
    return Config()
