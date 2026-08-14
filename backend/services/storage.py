from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from backend.database import Base, get_engine, get_session_factory
from backend.models import (
    AccountIdentity,
    AppSession,
    AuthTransaction,
    Favorite,
    Feedback,
    AbuseEvent,
    Profile,
    SecurityAuditEvent,
    UsageLimit,
)


@dataclass
class FavoriteRecord:
    id: str
    restaurant: str | None
    place_id: str | None
    note: str | None
    created_at: str


def init_storage() -> None:
    """Create tables only for local/test environments; production uses Alembic."""
    Base.metadata.create_all(get_engine())


async def purge_expired_operational_data() -> None:
    """Apply documented rolling retention to quota, security, and feedback rows."""
    def _delete() -> None:
        now = datetime.now(timezone.utc)
        with get_session_factory()() as db:
            db.execute(delete(UsageLimit).where(UsageLimit.usage_date < (now - timedelta(days=35)).date()))
            db.execute(delete(SecurityAuditEvent).where(SecurityAuditEvent.created_at < now - timedelta(days=90)))
            db.execute(delete(AbuseEvent).where(AbuseEvent.occurred_at < now - timedelta(days=30)))
            db.execute(delete(Feedback).where(Feedback.created_at < now - timedelta(days=730)))
            db.execute(
                delete(AuthTransaction).where(
                    (AuthTransaction.expires_at < now)
                    | (AuthTransaction.consumed_at < now - timedelta(days=1))
                )
            )
            db.execute(
                delete(AppSession).where(
                    (AppSession.absolute_expires_at < now)
                    | (AppSession.revoked_at < now - timedelta(days=30))
                )
            )
            db.commit()

    await asyncio.to_thread(_delete)


async def upsert_profile(user_id: str, email: str, email_verified: bool) -> None:
    def _write() -> None:
        now = datetime.now(timezone.utc)
        with get_session_factory()() as db:
            profile = db.get(Profile, user_id)
            if profile is None:
                profile = Profile(
                    user_id=user_id,
                    email=email.lower(),
                    email_verified=email_verified,
                    created_at=now,
                    updated_at=now,
                )
                db.add(profile)
            else:
                profile.email = email.lower()
                profile.email_verified = email_verified
                profile.updated_at = now
            db.commit()

    await asyncio.to_thread(_write)


async def find_profile_by_email(email: str) -> dict[str, Any] | None:
    def _read() -> dict[str, Any] | None:
        with get_session_factory()() as db:
            profile = db.scalar(
                select(Profile).where(Profile.email == email.strip().lower())
            )
            if profile is None:
                return None
            return {
                "user_id": profile.user_id,
                "email": profile.email,
                "email_verified": profile.email_verified,
            }

    return await asyncio.to_thread(_read)


async def has_account_identity(user_id: str, provider: str) -> bool:
    def _read() -> bool:
        with get_session_factory()() as db:
            return (
                db.scalar(
                    select(AccountIdentity).where(
                        AccountIdentity.user_id == user_id,
                        AccountIdentity.provider == provider,
                    )
                )
                is not None
            )

    return await asyncio.to_thread(_read)


async def sync_account_identities(
    user_id: str, identities: tuple[dict[str, Any], ...] | list[dict[str, Any]]
) -> None:
    def _write() -> None:
        now = datetime.now(timezone.utc)
        with get_session_factory()() as db:
            for item in identities:
                provider = str(item.get("provider") or "")[:32]
                identity_id = str(item.get("id") or "")[:128]
                if not provider or not identity_id:
                    continue
                existing = db.scalar(
                    select(AccountIdentity).where(
                        AccountIdentity.user_id == user_id,
                        AccountIdentity.provider == provider,
                    )
                )
                if existing:
                    existing.provider_identity_id = identity_id
                else:
                    db.add(
                        AccountIdentity(
                            id=str(uuid.uuid4()),
                            user_id=user_id,
                            provider=provider,
                            provider_identity_id=identity_id,
                            created_at=now,
                        )
                    )
            db.commit()

    await asyncio.to_thread(_write)


async def remove_account_identity(user_id: str, provider: str) -> None:
    def _delete() -> None:
        with get_session_factory()() as db:
            db.execute(
                delete(AccountIdentity).where(
                    AccountIdentity.user_id == user_id,
                    AccountIdentity.provider == provider,
                )
            )
            db.commit()

    await asyncio.to_thread(_delete)


async def add_favorite(user_id: str, restaurant: str, note: str | None) -> FavoriteRecord:
    def _insert() -> FavoriteRecord:
        now = datetime.now(timezone.utc)
        record = Favorite(
            id=str(uuid.uuid4()),
            user_id=user_id,
            restaurant=restaurant,
            place_id=None,
            note=note,
            created_at=now,
            updated_at=now,
        )
        with get_session_factory()() as db:
            db.add(record)
            db.commit()
        return _favorite_record(record)

    return await asyncio.to_thread(_insert)


async def get_favorites(user_id: str) -> list[FavoriteRecord]:
    def _query() -> list[FavoriteRecord]:
        with get_session_factory()() as db:
            rows = db.scalars(
                select(Favorite)
                .where(Favorite.user_id == user_id)
                .order_by(Favorite.created_at.desc())
            ).all()
            return [_favorite_record(row) for row in rows]

    return await asyncio.to_thread(_query)


async def delete_favorite(user_id: str, favorite_id: str) -> bool:
    def _delete() -> bool:
        with get_session_factory()() as db:
            result = db.execute(
                delete(Favorite).where(
                    Favorite.id == favorite_id,
                    Favorite.user_id == user_id,
                )
            )
            db.commit()
            return bool(result.rowcount)

    return await asyncio.to_thread(_delete)


async def record_feedback(
    user_id: str,
    restaurant: str | None,
    liked: bool,
    notes: str | None,
    *,
    place_id: str | None = None,
    recommendation_token: str | None = None,
    rank: int | None = None,
    score: float | None = None,
    confidence: str | None = None,
    report_reason: str | None = None,
) -> None:
    def _insert() -> None:
        with get_session_factory()() as db:
            db.add(
                Feedback(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    restaurant=restaurant,
                    place_id=place_id,
                    recommendation_token=recommendation_token,
                    rank=rank,
                    score=str(score) if score is not None else None,
                    confidence=confidence,
                    report_reason=report_reason,
                    liked=liked,
                    notes=notes,
                    created_at=datetime.now(timezone.utc),
                )
            )
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ValueError("duplicate feedback") from exc

    await asyncio.to_thread(_insert)


async def export_user_data(user_id: str) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        with get_session_factory()() as db:
            profile = db.get(Profile, user_id)
            favorites = db.scalars(
                select(Favorite).where(Favorite.user_id == user_id)
            ).all()
            feedback = db.scalars(
                select(Feedback).where(Feedback.user_id == user_id)
            ).all()
            return {
                "profile": (
                    {
                        "user_id": profile.user_id,
                        "email": profile.email,
                        "email_verified": profile.email_verified,
                        "created_at": _iso(profile.created_at),
                    }
                    if profile
                    else None
                ),
                "favorites": [
                    {
                        "id": item.id,
                        "restaurant": item.restaurant,
                        "place_id": item.place_id,
                        "note": item.note,
                        "created_at": _iso(item.created_at),
                    }
                    for item in favorites
                ],
                "feedback": [
                    {
                        "restaurant": item.restaurant,
                        "place_id": item.place_id,
                        "liked": item.liked,
                        "notes": item.notes,
                        "rank": item.rank,
                        "score": item.score,
                        "confidence": item.confidence,
                        "report_reason": item.report_reason,
                        "created_at": _iso(item.created_at),
                    }
                    for item in feedback
                ],
                "chat_history": [],
            }

    result = await asyncio.to_thread(_read)
    from backend.services.product_data import export_product_data

    result.update(await export_product_data(user_id))
    result["chat_history"] = result.pop("conversations", [])
    return result


async def audit_event(
    event_type: str,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, str | int | bool] | None = None,
) -> None:
    safe_metadata = metadata or {}

    def _insert() -> None:
        with get_session_factory()() as db:
            db.add(
                SecurityAuditEvent(
                    id=str(uuid.uuid4()),
                    event_type=event_type[:80],
                    user_id=user_id,
                    session_id=session_id,
                    request_id=request_id,
                    metadata_json=json.dumps(safe_metadata, separators=(",", ":")),
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()

    await asyncio.to_thread(_insert)


def serialize_favorites(records: list[FavoriteRecord]) -> list[dict[str, Any]]:
    return [asdict(record) for record in records]


def _favorite_record(record: Favorite) -> FavoriteRecord:
    return FavoriteRecord(
        id=record.id,
        restaurant=record.restaurant,
        place_id=record.place_id,
        note=record.note,
        created_at=_iso(record.created_at),
    )


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
