from __future__ import annotations

import os
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Config:
    """Central application settings."""

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    SQLITE_DB_PATH: str = os.getenv("SQLITE_DB_PATH", "./data/craveai.db")
    CHROMA_PATH: str = os.getenv("CHROMA_PATH", "./data/chroma_db")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4-turbo")
    ENVIRONMENT: str = os.getenv("APP_ENV", "development")

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


@lru_cache()
def get_settings() -> Config:
    """Return a cached settings instance."""
    return Config()
