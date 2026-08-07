from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database import get_session_factory
from backend.models import UsageLimit

GLOBAL_USAGE_USER_ID = "__global__"
PLACES_GLOBAL_USAGE_USER_ID = "__global_places__"


@dataclass(frozen=True)
class UsageReservation:
    limit: int
    used: int
    remaining: int
    reset_at: str
    request_count: int


class DailyQuotaExceeded(Exception):
    def __init__(self, usage: UsageReservation):
        super().__init__("Daily quota exceeded.")
        self.usage = usage


async def reserve_daily_quota(
    user_id: str,
    token_cost: int,
    daily_limit: int,
    global_daily_limit: int | None = None,
    global_user_id: str = GLOBAL_USAGE_USER_ID,
    now: datetime | None = None,
    namespace: str = "chat",
) -> UsageReservation:
    """Atomically reserve actor and service-wide quota in one transaction."""
    token_cost = max(token_cost, 0)
    daily_limit = max(daily_limit, 0)
    timestamp = _utc(now or datetime.now(timezone.utc))
    usage_date = timestamp.date()
    reset_at = _reset_at(timestamp)
    global_limit = (
        max(global_daily_limit, 0) if global_daily_limit is not None else None
    )

    def _reserve() -> UsageReservation:
        with get_session_factory()() as db:
            actor = _locked_usage_row(db, namespace, user_id, usage_date, timestamp)
            if actor.units_used + token_cost > daily_limit:
                reservation = _reservation(actor, daily_limit, reset_at)
                db.rollback()
                raise DailyQuotaExceeded(reservation)

            global_row = None
            if global_limit is not None:
                global_row = _locked_usage_row(
                    db, namespace, global_user_id, usage_date, timestamp
                )
                if global_row.units_used + token_cost > global_limit:
                    reservation = _reservation(global_row, global_limit, reset_at)
                    db.rollback()
                    raise DailyQuotaExceeded(reservation)

            actor.units_used += token_cost
            actor.request_count += 1
            actor.updated_at = timestamp
            if global_row is not None:
                global_row.units_used += token_cost
                global_row.request_count += 1
                global_row.updated_at = timestamp
            db.commit()
            return _reservation(actor, daily_limit, reset_at)

    return await asyncio.to_thread(_reserve)


def rate_limit_headers(
    usage: UsageReservation, *, include_retry_after: bool = False
) -> dict[str, str]:
    headers = {
        "X-RateLimit-Limit": str(usage.limit),
        "X-RateLimit-Remaining": str(usage.remaining),
        "X-RateLimit-Reset": usage.reset_at,
    }
    if include_retry_after:
        reset = datetime.fromisoformat(usage.reset_at.replace("Z", "+00:00"))
        seconds = max(int((reset - datetime.now(timezone.utc)).total_seconds()), 1)
        headers["Retry-After"] = str(seconds)
    return headers


def _locked_usage_row(db, namespace, actor_key, usage_date, timestamp) -> UsageLimit:
    query = (
        select(UsageLimit)
        .where(
            UsageLimit.namespace == namespace,
            UsageLimit.actor_key == actor_key,
            UsageLimit.usage_date == usage_date,
        )
        .with_for_update()
    )
    row = db.scalar(query)
    if row is not None:
        return row
    values = {
        "namespace": namespace,
        "actor_key": actor_key,
        "usage_date": usage_date,
        "units_used": 0,
        "request_count": 0,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        statement = postgresql_insert(UsageLimit).values(**values)
    elif dialect == "sqlite":
        statement = sqlite_insert(UsageLimit).values(**values)
    else:
        row = UsageLimit(**values)
        db.add(row)
        db.flush()
        return row
    db.execute(
        statement.on_conflict_do_nothing(
            index_elements=["namespace", "actor_key", "usage_date"]
        )
    )
    return db.scalar(query)


def _reservation(row: UsageLimit, limit: int, reset_at: str) -> UsageReservation:
    return UsageReservation(
        limit=limit,
        used=row.units_used,
        remaining=max(limit - row.units_used, 0),
        reset_at=reset_at,
        request_count=row.request_count,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _reset_at(now: datetime) -> str:
    reset = datetime.combine(
        now.date() + timedelta(days=1), time.min, tzinfo=timezone.utc
    )
    return reset.isoformat().replace("+00:00", "Z")
