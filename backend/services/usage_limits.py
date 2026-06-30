from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from backend.services.storage import _get_connection


@dataclass(frozen=True)
class UsageReservation:
    """Quota state returned after a reservation attempt."""

    limit: int
    used: int
    remaining: int
    reset_at: str
    request_count: int


class DailyQuotaExceeded(Exception):
    """Raised when a user has exhausted the daily demo token quota."""

    def __init__(self, usage: UsageReservation):
        super().__init__("Daily demo token quota exceeded.")
        self.usage = usage


def resolve_usage_user_id(user_id: str | None, client_host: str | None) -> str:
    """Return the stable quota identity used for daily accounting."""
    normalized = (user_id or "").strip()
    if normalized:
        return normalized
    return f"ip:{client_host or 'unknown'}"


async def reserve_daily_quota(
    user_id: str,
    token_cost: int,
    daily_limit: int,
    now: datetime | None = None,
) -> UsageReservation:
    """Atomically reserve estimated tokens for a user's daily quota."""
    if token_cost < 0:
        token_cost = 0
    if daily_limit < 0:
        daily_limit = 0

    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc)
    usage_date = timestamp.date().isoformat()
    reset_at = _reset_at(timestamp)
    timestamp_iso = _isoformat_z(timestamp)

    def _reserve() -> UsageReservation:
        connection = _get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT tokens_used, request_count
                FROM usage_limits
                WHERE user_id = ? AND usage_date = ?
                """,
                (user_id, usage_date),
            ).fetchone()

            current_used = int(row["tokens_used"]) if row else 0
            current_count = int(row["request_count"]) if row else 0
            if current_used + token_cost > daily_limit:
                connection.rollback()
                raise DailyQuotaExceeded(
                    UsageReservation(
                        limit=daily_limit,
                        used=current_used,
                        remaining=max(daily_limit - current_used, 0),
                        reset_at=reset_at,
                        request_count=current_count,
                    )
                )

            next_used = current_used + token_cost
            next_count = current_count + 1
            if row:
                connection.execute(
                    """
                    UPDATE usage_limits
                    SET tokens_used = ?, request_count = ?, updated_at = ?
                    WHERE user_id = ? AND usage_date = ?
                    """,
                    (next_used, next_count, timestamp_iso, user_id, usage_date),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO usage_limits (
                        user_id, usage_date, tokens_used, request_count, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, usage_date, next_used, next_count, timestamp_iso, timestamp_iso),
                )
            connection.commit()
            return UsageReservation(
                limit=daily_limit,
                used=next_used,
                remaining=max(daily_limit - next_used, 0),
                reset_at=reset_at,
                request_count=next_count,
            )
        except DailyQuotaExceeded:
            raise
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    return await asyncio.to_thread(_reserve)


def rate_limit_headers(usage: UsageReservation, include_retry_after: bool = False) -> dict[str, str]:
    """Build HTTP headers that expose quota state to clients."""
    headers = {
        "X-RateLimit-Limit": str(usage.limit),
        "X-RateLimit-Remaining": str(usage.remaining),
        "X-RateLimit-Reset": usage.reset_at,
    }
    if include_retry_after:
        headers["Retry-After"] = str(_retry_after_seconds(usage.reset_at))
    return headers


def _reset_at(timestamp: datetime) -> str:
    next_day = timestamp.date() + timedelta(days=1)
    reset = datetime.combine(next_day, time.min, tzinfo=timezone.utc)
    return _isoformat_z(reset)


def _retry_after_seconds(reset_at: str) -> int:
    reset = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
    seconds = int((reset - datetime.now(timezone.utc)).total_seconds())
    return max(seconds, 0)


def _isoformat_z(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
