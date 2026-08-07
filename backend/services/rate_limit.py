from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, text

from backend.database import get_session_factory
from backend.models import AbuseEvent


class BurstLimiter:
    """Process-local burst guard layered on top of durable daily quotas."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def enforce(
        self, key: str, *, limit: int, window_seconds: int, code: str
    ) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(int(events[0] + window_seconds - now), 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={"code": code},
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)
        allowed = await asyncio.to_thread(
            _record_durable_event, key, limit, window_seconds
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": code},
                headers={"Retry-After": str(window_seconds)},
            )

    def reset(self) -> None:
        self._events.clear()


burst_limiter = BurstLimiter()


def _record_durable_event(key: str, limit: int, window_seconds: int) -> bool:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    actor_hash = hashlib.sha256(key.encode()).hexdigest()
    namespace = key.split(":", 1)[0][:40]
    with get_session_factory()() as db:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:actor))"),
                {"actor": actor_hash},
            )
        count = db.scalar(
            select(func.count())
            .select_from(AbuseEvent)
            .where(
                AbuseEvent.namespace == namespace,
                AbuseEvent.actor_hash == actor_hash,
                AbuseEvent.occurred_at > cutoff,
            )
        )
        if int(count or 0) >= limit:
            db.rollback()
            return False
        db.add(
            AbuseEvent(
                namespace=namespace,
                actor_hash=actor_hash,
                occurred_at=now,
            )
        )
        db.commit()
        return True
