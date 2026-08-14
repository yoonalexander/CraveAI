from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AppSession(Base):
    __tablename__ = "app_sessions"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("profiles.user_id", ondelete="CASCADE"), index=True
    )
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent_hash: Mapped[str | None] = mapped_column(String(64))
    ip_prefix_hash: Mapped[str | None] = mapped_column(String(64))


class AccountIdentity(Base):
    __tablename__ = "account_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_identity_id"),
        UniqueConstraint("user_id", "provider"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("profiles.user_id", ondelete="CASCADE"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_identity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthTransaction(Base):
    __tablename__ = "auth_transactions"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    transaction_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    state_hash: Mapped[str | None] = mapped_column(String(64))
    nonce_hash: Mapped[str | None] = mapped_column(String(64))
    encrypted_code_verifier: Mapped[str | None] = mapped_column(Text)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    next_path: Mapped[str] = mapped_column(String(256), nullable=False, default="/")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "place_id"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("profiles.user_id", ondelete="CASCADE"), index=True
    )
    # `restaurant` is retained only for removable legacy saves. New saves persist
    # a Place ID and hydrate provider-owned details at request time.
    restaurant: Mapped[str | None] = mapped_column(String(200))
    place_id: Mapped[str | None] = mapped_column(String(500), index=True)
    note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("user_id", "recommendation_token"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("profiles.user_id", ondelete="CASCADE"), index=True
    )
    restaurant: Mapped[str | None] = mapped_column(String(200))
    place_id: Mapped[str | None] = mapped_column(String(500))
    recommendation_token: Mapped[str | None] = mapped_column(String(512))
    rank: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[str | None] = mapped_column(String(32))
    report_reason: Mapped[str | None] = mapped_column(String(80))
    liked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PolicyAcceptance(Base):
    __tablename__ = "policy_acceptances"
    __table_args__ = (
        UniqueConstraint("user_id", "terms_version", "privacy_version"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("profiles.user_id", ondelete="CASCADE"), index=True
    )
    terms_version: Mapped[str] = mapped_column(String(32), nullable=False)
    privacy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    age_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserConsent(Base):
    __tablename__ = "user_consents"
    __table_args__ = (UniqueConstraint("user_id", "purpose"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("profiles.user_id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("profiles.user_id", ondelete="CASCADE"), primary_key=True
    )
    favorite_cuisines_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    disliked_foods_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    dietary_restrictions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    allergies_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    default_location_json: Mapped[str | None] = mapped_column(Text)
    default_radius_meters: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    recommendation_preferences_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    personalization_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    history_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reduced_motion: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    notification_preferences_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FavoriteCollection(Base):
    __tablename__ = "favorite_collections"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("profiles.user_id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FavoriteCollectionItem(Base):
    __tablename__ = "favorite_collection_items"
    __table_args__ = (UniqueConstraint("collection_id", "favorite_id"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    collection_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("favorite_collections.id", ondelete="CASCADE"), index=True
    )
    favorite_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("favorites.id", ondelete="CASCADE"), index=True
    )
    note: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("profiles.user_id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(60), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    place_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UsageLimit(Base):
    __tablename__ = "usage_limits"
    __table_args__ = (
        UniqueConstraint("namespace", "actor_key", "usage_date"),
        Index("ix_usage_limits_date_namespace", "usage_date", "namespace"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    namespace: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_key: Mapped[str] = mapped_column(String(160), nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    units_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SecurityAuditEvent(Base):
    __tablename__ = "security_audit_events"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), index=True)
    session_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    request_id: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AbuseEvent(Base):
    __tablename__ = "abuse_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    namespace: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
