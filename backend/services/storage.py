from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

from backend.config import get_settings


@dataclass
class FavoriteRecord:
    restaurant: str
    note: str | None = None


def _get_db_path() -> Path:
    db_path = Path(get_settings().SQLITE_DB_PATH).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(_get_db_path(), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_storage() -> None:
    """Create required SQLite tables if they are missing."""
    connection = _get_connection()
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    restaurant TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    restaurant TEXT NOT NULL,
                    liked INTEGER NOT NULL,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_limits (
                    user_id TEXT NOT NULL,
                    usage_date TEXT NOT NULL,
                    tokens_used INTEGER NOT NULL DEFAULT 0,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, usage_date)
                )
                """
            )
    finally:
        connection.close()


async def add_favorite(user_id: str, restaurant: str, note: str | None) -> FavoriteRecord:
    """Persist a favorite entry for the given user."""

    def _insert() -> FavoriteRecord:
        connection = _get_connection()
        try:
            with connection:
                connection.execute(
                    "INSERT INTO favorites (user_id, restaurant, note) VALUES (?, ?, ?)",
                    (user_id, restaurant, note),
                )
            return FavoriteRecord(restaurant=restaurant, note=note)
        finally:
            connection.close()

    return await asyncio.to_thread(_insert)


async def get_favorites(user_id: str) -> List[FavoriteRecord]:
    """Fetch all favorites associated with a user."""

    def _query() -> List[FavoriteRecord]:
        connection = _get_connection()
        try:
            cursor = connection.execute(
                "SELECT restaurant, note FROM favorites WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            rows = cursor.fetchall()
            return [FavoriteRecord(restaurant=row["restaurant"], note=row["note"]) for row in rows]
        finally:
            connection.close()

    return await asyncio.to_thread(_query)


async def record_feedback(user_id: str, restaurant: str, liked: bool, notes: str | None) -> None:
    """Store thumbs up/down reactions for later analysis."""

    def _insert() -> None:
        connection = _get_connection()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO feedback (user_id, restaurant, liked, notes)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, restaurant, 1 if liked else 0, notes),
                )
        finally:
            connection.close()

    await asyncio.to_thread(_insert)


def serialize_favorites(records: List[FavoriteRecord]) -> List[Dict[str, Any]]:
    """Convert favorite dataclasses to JSON-compatible dictionaries."""
    return [asdict(record) for record in records]
