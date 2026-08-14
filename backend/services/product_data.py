from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.exc import IntegrityError

from backend.database import get_session_factory
from backend.models import (
    Conversation,
    ConversationMessage,
    Favorite,
    FavoriteCollection,
    FavoriteCollectionItem,
    PolicyAcceptance,
    UserConsent,
    UserPreference,
)

ALLOWED_CONSENTS = {"history", "personalization", "notifications"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _json(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


async def record_policy_acceptance(
    user_id: str, terms_version: str, privacy_version: str, age_confirmed: bool
) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        with get_session_factory()() as db:
            existing = db.scalar(
                select(PolicyAcceptance).where(
                    PolicyAcceptance.user_id == user_id,
                    PolicyAcceptance.terms_version == terms_version,
                    PolicyAcceptance.privacy_version == privacy_version,
                )
            )
            if existing is None:
                existing = PolicyAcceptance(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    terms_version=terms_version,
                    privacy_version=privacy_version,
                    age_confirmed=age_confirmed,
                    accepted_at=_now(),
                )
                db.add(existing)
            else:
                existing.age_confirmed = age_confirmed
                existing.accepted_at = _now()
            db.commit()
            return {
                "terms_version": existing.terms_version,
                "privacy_version": existing.privacy_version,
                "age_confirmed": existing.age_confirmed,
                "accepted_at": _iso(existing.accepted_at),
            }

    return await asyncio.to_thread(_write)


async def has_current_policy_acceptance(
    user_id: str, terms_version: str, privacy_version: str
) -> bool:
    def _read() -> bool:
        with get_session_factory()() as db:
            return db.scalar(
                select(PolicyAcceptance.id).where(
                    PolicyAcceptance.user_id == user_id,
                    PolicyAcceptance.terms_version == terms_version,
                    PolicyAcceptance.privacy_version == privacy_version,
                    PolicyAcceptance.age_confirmed.is_(True),
                )
            ) is not None

    return await asyncio.to_thread(_read)


def _default_preferences(user_id: str) -> UserPreference:
    return UserPreference(
        user_id=user_id,
        favorite_cuisines_json="[]",
        disliked_foods_json="[]",
        dietary_restrictions_json="[]",
        allergies_json="[]",
        default_location_json=None,
        default_radius_meters=5000,
        recommendation_preferences_json="{}",
        personalization_enabled=False,
        history_enabled=False,
        reduced_motion="system",
        notification_preferences_json="{}",
        updated_at=_now(),
    )


def _serialize_preferences(row: UserPreference) -> dict[str, Any]:
    return {
        "favorite_cuisines": _json(row.favorite_cuisines_json, []),
        "disliked_foods": _json(row.disliked_foods_json, []),
        "dietary_restrictions": _json(row.dietary_restrictions_json, []),
        "allergies": _json(row.allergies_json, []),
        "default_location": _json(row.default_location_json, None),
        "default_radius_meters": row.default_radius_meters,
        "recommendation_preferences": _json(row.recommendation_preferences_json, {}),
        "personalization_enabled": row.personalization_enabled,
        "history_enabled": row.history_enabled,
        "reduced_motion": row.reduced_motion,
        "notification_preferences": _json(row.notification_preferences_json, {}),
        "updated_at": _iso(row.updated_at),
    }


async def get_preferences(user_id: str) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        with get_session_factory()() as db:
            row = db.get(UserPreference, user_id)
            return _serialize_preferences(row or _default_preferences(user_id))

    return await asyncio.to_thread(_read)


async def update_preferences(user_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    mappings = {
        "favorite_cuisines": "favorite_cuisines_json",
        "disliked_foods": "disliked_foods_json",
        "dietary_restrictions": "dietary_restrictions_json",
        "allergies": "allergies_json",
        "default_location": "default_location_json",
        "recommendation_preferences": "recommendation_preferences_json",
        "notification_preferences": "notification_preferences_json",
    }

    def _write() -> dict[str, Any]:
        with get_session_factory()() as db:
            row = db.get(UserPreference, user_id)
            if row is None:
                row = _default_preferences(user_id)
                db.add(row)
            for key, value in changes.items():
                if key in mappings:
                    setattr(row, mappings[key], json.dumps(value, separators=(",", ":")))
                elif hasattr(row, key):
                    setattr(row, key, value)
            row.updated_at = _now()
            db.commit()
            return _serialize_preferences(row)

    return await asyncio.to_thread(_write)


async def set_consent(user_id: str, purpose: str, granted: bool) -> dict[str, Any]:
    if purpose not in ALLOWED_CONSENTS:
        raise ValueError("unsupported consent purpose")

    def _write() -> dict[str, Any]:
        with get_session_factory()() as db:
            row = db.scalar(
                select(UserConsent).where(
                    UserConsent.user_id == user_id, UserConsent.purpose == purpose
                )
            )
            if row is None:
                row = UserConsent(
                    id=str(uuid.uuid4()), user_id=user_id, purpose=purpose,
                    granted=granted, version="1", updated_at=_now(),
                )
                db.add(row)
            else:
                row.granted = granted
                row.updated_at = _now()
            prefs = db.get(UserPreference, user_id)
            if prefs is None:
                prefs = _default_preferences(user_id)
                db.add(prefs)
            if purpose == "history":
                prefs.history_enabled = granted
            elif purpose == "personalization":
                prefs.personalization_enabled = granted
            prefs.updated_at = _now()
            db.commit()
            return {"purpose": purpose, "granted": granted, "updated_at": _iso(row.updated_at)}

    return await asyncio.to_thread(_write)


async def list_consents(user_id: str) -> list[dict[str, Any]]:
    def _read() -> list[dict[str, Any]]:
        with get_session_factory()() as db:
            rows = db.scalars(select(UserConsent).where(UserConsent.user_id == user_id)).all()
            return [
                {"purpose": row.purpose, "granted": row.granted, "version": row.version, "updated_at": _iso(row.updated_at)}
                for row in rows
            ]

    return await asyncio.to_thread(_read)


async def list_policy_acceptances(user_id: str) -> list[dict[str, Any]]:
    def _read() -> list[dict[str, Any]]:
        with get_session_factory()() as db:
            rows = db.scalars(
                select(PolicyAcceptance)
                .where(PolicyAcceptance.user_id == user_id)
                .order_by(PolicyAcceptance.accepted_at.desc())
            ).all()
            return [{
                "terms_version": row.terms_version,
                "privacy_version": row.privacy_version,
                "age_confirmed": row.age_confirmed,
                "accepted_at": _iso(row.accepted_at),
            } for row in rows]

    return await asyncio.to_thread(_read)


def _ensure_default_collection(db: Any, user_id: str) -> FavoriteCollection:
    row = db.scalar(
        select(FavoriteCollection).where(
            FavoriteCollection.user_id == user_id,
            FavoriteCollection.is_default.is_(True),
        )
    )
    if row is None:
        now = _now()
        row = FavoriteCollection(
            id=str(uuid.uuid4()), user_id=user_id, name="Saved", is_default=True,
            created_at=now, updated_at=now,
        )
        db.add(row)
        db.flush()
    return row


async def create_collection(user_id: str, name: str) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        now = _now()
        with get_session_factory()() as db:
            row = FavoriteCollection(
                id=str(uuid.uuid4()), user_id=user_id, name=name, is_default=False,
                created_at=now, updated_at=now,
            )
            db.add(row)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ValueError("collection already exists") from exc
            return _collection(row, 0)

    return await asyncio.to_thread(_write)


async def list_collections(user_id: str) -> list[dict[str, Any]]:
    def _read() -> list[dict[str, Any]]:
        with get_session_factory()() as db:
            _ensure_default_collection(db, user_id)
            db.commit()
            rows = db.scalars(
                select(FavoriteCollection).where(FavoriteCollection.user_id == user_id)
                .order_by(FavoriteCollection.is_default.desc(), FavoriteCollection.created_at)
            ).all()
            return [
                _collection(
                    row,
                    len(db.scalars(select(FavoriteCollectionItem).where(FavoriteCollectionItem.collection_id == row.id)).all()),
                )
                for row in rows
            ]

    return await asyncio.to_thread(_read)


def _collection(row: FavoriteCollection, item_count: int) -> dict[str, Any]:
    return {
        "id": row.id, "name": row.name, "is_default": row.is_default,
        "item_count": item_count, "created_at": _iso(row.created_at), "updated_at": _iso(row.updated_at),
    }


async def save_place(
    user_id: str, place_id: str, collection_id: str | None, note: str | None
) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        now = _now()
        with get_session_factory()() as db:
            favorite = db.scalar(
                select(Favorite).where(Favorite.user_id == user_id, Favorite.place_id == place_id)
            )
            created = favorite is None
            if favorite is None:
                favorite = Favorite(
                    id=str(uuid.uuid4()), user_id=user_id, restaurant=None,
                    place_id=place_id, note=None, created_at=now, updated_at=now,
                )
                db.add(favorite)
                db.flush()
            collection = (
                db.scalar(select(FavoriteCollection).where(FavoriteCollection.id == collection_id, FavoriteCollection.user_id == user_id))
                if collection_id else _ensure_default_collection(db, user_id)
            )
            if collection is None:
                raise LookupError("collection not found")
            item = db.scalar(
                select(FavoriteCollectionItem).where(
                    FavoriteCollectionItem.collection_id == collection.id,
                    FavoriteCollectionItem.favorite_id == favorite.id,
                )
            )
            if item is None:
                item = FavoriteCollectionItem(
                    id=str(uuid.uuid4()), collection_id=collection.id, favorite_id=favorite.id,
                    note=note, created_at=now, updated_at=now,
                )
                db.add(item)
            elif note is not None:
                item.note = note
                item.updated_at = now
            db.commit()
            return {"id": favorite.id, "place_id": favorite.place_id, "legacy_name": None,
                    "collection_id": collection.id, "note": item.note, "created": created,
                    "created_at": _iso(favorite.created_at), "updated_at": _iso(favorite.updated_at)}

    return await asyncio.to_thread(_write)


async def list_saved_places(user_id: str, collection_id: str | None = None) -> list[dict[str, Any]]:
    def _read() -> list[dict[str, Any]]:
        with get_session_factory()() as db:
            statement = select(Favorite).where(Favorite.user_id == user_id).order_by(Favorite.created_at.desc())
            favorites = db.scalars(statement).all()
            result = []
            for favorite in favorites:
                items = db.scalars(
                    select(FavoriteCollectionItem).join(FavoriteCollection).where(
                        FavoriteCollectionItem.favorite_id == favorite.id,
                        FavoriteCollection.user_id == user_id,
                    )
                ).all()
                if collection_id and not any(item.collection_id == collection_id for item in items):
                    continue
                result.append({
                    "id": favorite.id, "place_id": favorite.place_id,
                    "legacy_name": favorite.restaurant,
                    "collections": [{"collection_id": item.collection_id, "note": item.note} for item in items],
                    "created_at": _iso(favorite.created_at), "updated_at": _iso(favorite.updated_at),
                })
            return result

    return await asyncio.to_thread(_read)


async def list_saved_places_page(
    user_id: str,
    collection_id: str | None = None,
    limit: int = 30,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Cursor-paginate owned saves while preserving the legacy list helper."""
    all_items = await list_saved_places(user_id, collection_id)
    if cursor:
        cursor_index = next((index for index, item in enumerate(all_items) if item["id"] == cursor), -1)
        if cursor_index < 0:
            return {"favorites": [], "next_cursor": None}
        all_items = all_items[cursor_index + 1:]
    items = all_items[:limit]
    next_cursor = items[-1]["id"] if len(all_items) > limit and items else None
    return {"favorites": items, "next_cursor": next_cursor}


async def update_collection_item(user_id: str, favorite_id: str, collection_id: str, note: str | None) -> bool:
    def _write() -> bool:
        with get_session_factory()() as db:
            item = db.scalar(
                select(FavoriteCollectionItem).join(FavoriteCollection).join(Favorite).where(
                    FavoriteCollectionItem.favorite_id == favorite_id,
                    FavoriteCollectionItem.collection_id == collection_id,
                    FavoriteCollection.user_id == user_id,
                    Favorite.user_id == user_id,
                )
            )
            if item is None:
                return False
            item.note = note
            item.updated_at = _now()
            db.commit()
            return True

    return await asyncio.to_thread(_write)


async def remove_collection(user_id: str, collection_id: str) -> bool:
    def _delete() -> bool:
        with get_session_factory()() as db:
            row = db.scalar(select(FavoriteCollection).where(FavoriteCollection.id == collection_id, FavoriteCollection.user_id == user_id))
            if row is None or row.is_default:
                return False
            db.delete(row)
            db.commit()
            return True

    return await asyncio.to_thread(_delete)


def title_from_prompt(prompt: str) -> str:
    normalized = " ".join(prompt.split()).strip()
    return (normalized[:57] + "...") if len(normalized) > 60 else (normalized or "New conversation")


async def create_conversation(user_id: str, title: str | None, first_prompt: str | None = None) -> dict[str, Any]:
    def _write() -> dict[str, Any]:
        now = _now()
        row = Conversation(
            id=str(uuid.uuid4()), user_id=user_id,
            title=(title or title_from_prompt(first_prompt or ""))[:60], summary="",
            created_at=now, updated_at=now,
        )
        with get_session_factory()() as db:
            db.add(row)
            db.commit()
            return _conversation(row)

    return await asyncio.to_thread(_write)


def _conversation(row: Conversation) -> dict[str, Any]:
    return {"id": row.id, "title": row.title, "summary": row.summary,
            "created_at": _iso(row.created_at), "updated_at": _iso(row.updated_at)}


async def list_conversations(user_id: str, limit: int = 30) -> list[dict[str, Any]]:
    def _read() -> list[dict[str, Any]]:
        with get_session_factory()() as db:
            rows = db.scalars(select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc()).limit(limit)).all()
            return [_conversation(row) for row in rows]

    return await asyncio.to_thread(_read)


async def list_conversations_page(
    user_id: str, limit: int = 30, cursor: str | None = None
) -> dict[str, Any]:
    def _read() -> dict[str, Any]:
        with get_session_factory()() as db:
            statement = select(Conversation).where(Conversation.user_id == user_id)
            if cursor:
                anchor = db.scalar(
                    select(Conversation).where(
                        Conversation.id == cursor, Conversation.user_id == user_id
                    )
                )
                if anchor is None:
                    return {"conversations": [], "next_cursor": None}
                statement = statement.where(
                    or_(
                        Conversation.updated_at < anchor.updated_at,
                        and_(
                            Conversation.updated_at == anchor.updated_at,
                            Conversation.id < anchor.id,
                        ),
                    )
                )
            rows = db.scalars(
                statement.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
                .limit(limit + 1)
            ).all()
            has_more = len(rows) > limit
            rows = rows[:limit]
            return {
                "conversations": [_conversation(row) for row in rows],
                "next_cursor": rows[-1].id if has_more and rows else None,
            }

    return await asyncio.to_thread(_read)


async def get_conversation(user_id: str, conversation_id: str) -> dict[str, Any] | None:
    def _read() -> dict[str, Any] | None:
        with get_session_factory()() as db:
            row = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id))
            if row is None:
                return None
            messages = db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == row.id).order_by(ConversationMessage.created_at)).all()
            return {**_conversation(row), "messages": [
                {"id": item.id, "role": item.role, "content": item.content,
                 "place_ids": _json(item.place_ids_json, []), "created_at": _iso(item.created_at)}
                for item in messages
            ]}

    return await asyncio.to_thread(_read)


async def append_message(user_id: str, conversation_id: str, role: str, content: str, place_ids: list[str]) -> bool:
    def _write() -> bool:
        with get_session_factory()() as db:
            conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id))
            if conversation is None:
                return False
            db.add(ConversationMessage(
                id=str(uuid.uuid4()), conversation_id=conversation.id, role=role,
                content=content, place_ids_json=json.dumps(place_ids[:20]), created_at=_now(),
            ))
            conversation.updated_at = _now()
            db.flush()
            rows = db.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation.id)
                .order_by(ConversationMessage.created_at)
            ).all()
            if len(rows) > 12:
                summary_lines: list[str] = []
                for item in rows[:-12]:
                    if item.role == "user":
                        normalized = " ".join(item.content.split())[:500]
                        summary_lines.append(f"User craving/context: {normalized}")
                    else:
                        references = _json(item.place_ids_json, [])[:20]
                        if references:
                            summary_lines.append(
                                "Earlier recommendation Place IDs: " + ", ".join(references)
                            )
                conversation.summary = "\n".join(summary_lines)[-4000:]
            db.commit()
            return True

    return await asyncio.to_thread(_write)


async def get_conversation_context(
    user_id: str, conversation_id: str
) -> dict[str, Any] | None:
    """Return a compact summary and bounded recent context for one owned thread."""
    def _read() -> dict[str, Any] | None:
        with get_session_factory()() as db:
            conversation = db.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            if conversation is None:
                return None
            rows = db.scalars(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation.id)
                .order_by(ConversationMessage.created_at.desc())
                .limit(12)
            ).all()
            return {
                "summary": conversation.summary[-4000:],
                "messages": [
                    {
                        "role": item.role,
                        "content": item.content[:2000],
                        "place_ids": _json(item.place_ids_json, [])[:20],
                    }
                    for item in reversed(rows)
                ],
            }

    return await asyncio.to_thread(_read)


async def rename_conversation(user_id: str, conversation_id: str, title: str) -> bool:
    def _write() -> bool:
        with get_session_factory()() as db:
            row = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id))
            if row is None:
                return False
            row.title = title[:60]
            row.updated_at = _now()
            db.commit()
            return True

    return await asyncio.to_thread(_write)


async def delete_conversation(user_id: str, conversation_id: str) -> bool:
    def _delete() -> bool:
        with get_session_factory()() as db:
            result = db.execute(delete(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id))
            db.commit()
            return bool(result.rowcount)

    return await asyncio.to_thread(_delete)


async def clear_conversations(user_id: str) -> int:
    def _delete() -> int:
        with get_session_factory()() as db:
            result = db.execute(delete(Conversation).where(Conversation.user_id == user_id))
            db.commit()
            return int(result.rowcount or 0)

    return await asyncio.to_thread(_delete)


async def export_product_data(user_id: str) -> dict[str, Any]:
    preferences, consents, acceptances, collections, favorites, conversations = await asyncio.gather(
        get_preferences(user_id), list_consents(user_id), list_policy_acceptances(user_id), list_collections(user_id),
        list_saved_places(user_id), list_conversations(user_id, 1000),
    )
    conversation_data = []
    for item in conversations:
        detail = await get_conversation(user_id, item["id"])
        if detail:
            conversation_data.append(detail)
    return {
        "preferences": preferences, "consents": consents, "policy_acceptances": acceptances, "collections": collections,
        "saved_places": favorites, "conversations": conversation_data,
    }
