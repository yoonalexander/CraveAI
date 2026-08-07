from __future__ import annotations

import os

# Module-level FastAPI app creation happens during collection. Keep collection
# isolated from production services; individual tests receive a fresh database.
os.environ.setdefault("OPENAI_API_KEY", "test-openai")
os.environ.setdefault("GOOGLE_API_KEY", "test-google")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./data/pytest-collection.db")
os.environ.setdefault("AUTO_CREATE_SCHEMA", "true")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("IDENTITY_SIGNING_SECRET", "test-identity-signing-secret")
