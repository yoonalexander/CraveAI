"""Privacy-first product data, consent, collections, and conversations."""

from alembic import op
import sqlalchemy as sa


revision = "0002_privacy_product"
down_revision = "0001_supabase_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("favorites", "restaurant", existing_type=sa.String(200), nullable=True)
    op.add_column("favorites", sa.Column("place_id", sa.String(500)))
    op.add_column("favorites", sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_index("ix_favorites_place_id", "favorites", ["place_id"])
    op.create_unique_constraint("uq_favorites_user_place", "favorites", ["user_id", "place_id"])

    op.alter_column("feedback", "restaurant", existing_type=sa.String(200), nullable=True)
    op.add_column("feedback", sa.Column("place_id", sa.String(500)))
    op.add_column("feedback", sa.Column("recommendation_token", sa.String(512)))
    op.add_column("feedback", sa.Column("rank", sa.Integer()))
    op.add_column("feedback", sa.Column("score", sa.String(32)))
    op.add_column("feedback", sa.Column("confidence", sa.String(32)))
    op.add_column("feedback", sa.Column("report_reason", sa.String(80)))
    op.create_unique_constraint(
        "uq_feedback_user_recommendation", "feedback", ["user_id", "recommendation_token"]
    )

    op.create_table(
        "policy_acceptances",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("terms_version", sa.String(32), nullable=False),
        sa.Column("privacy_version", sa.String(32), nullable=False),
        sa.Column("age_confirmed", sa.Boolean(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "terms_version", "privacy_version"),
    )
    op.create_index("ix_policy_acceptances_user_id", "policy_acceptances", ["user_id"])

    op.create_table(
        "user_consents",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "purpose"),
    )
    op.create_index("ix_user_consents_user_id", "user_consents", ["user_id"])

    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("profiles.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("favorite_cuisines_json", sa.Text(), nullable=False),
        sa.Column("disliked_foods_json", sa.Text(), nullable=False),
        sa.Column("dietary_restrictions_json", sa.Text(), nullable=False),
        sa.Column("allergies_json", sa.Text(), nullable=False),
        sa.Column("default_location_json", sa.Text()),
        sa.Column("default_radius_meters", sa.Integer(), nullable=False),
        sa.Column("recommendation_preferences_json", sa.Text(), nullable=False),
        sa.Column("personalization_enabled", sa.Boolean(), nullable=False),
        sa.Column("history_enabled", sa.Boolean(), nullable=False),
        sa.Column("reduced_motion", sa.String(16), nullable=False),
        sa.Column("notification_preferences_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "favorite_collections",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index("ix_favorite_collections_user_id", "favorite_collections", ["user_id"])
    op.create_table(
        "favorite_collection_items",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("collection_id", sa.Uuid(as_uuid=False), sa.ForeignKey("favorite_collections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("favorite_id", sa.Uuid(as_uuid=False), sa.ForeignKey("favorites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("collection_id", "favorite_id"),
    )
    op.create_index("ix_favorite_collection_items_collection_id", "favorite_collection_items", ["collection_id"])
    op.create_index("ix_favorite_collection_items_favorite_id", "favorite_collection_items", ["favorite_id"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(60), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(as_uuid=False), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("place_ids_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversation_messages_conversation_id", "conversation_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
    op.drop_table("favorite_collection_items")
    op.drop_table("favorite_collections")
    op.drop_table("user_preferences")
    op.drop_table("user_consents")
    op.drop_table("policy_acceptances")
    op.drop_constraint("uq_feedback_user_recommendation", "feedback", type_="unique")
    for column in ("report_reason", "confidence", "score", "rank", "recommendation_token", "place_id"):
        op.drop_column("feedback", column)
    op.execute("UPDATE feedback SET restaurant = 'Legacy feedback' WHERE restaurant IS NULL")
    op.alter_column("feedback", "restaurant", existing_type=sa.String(200), nullable=False)
    op.drop_constraint("uq_favorites_user_place", "favorites", type_="unique")
    op.drop_index("ix_favorites_place_id", table_name="favorites")
    op.drop_column("favorites", "updated_at")
    op.drop_column("favorites", "place_id")
    op.execute("UPDATE favorites SET restaurant = 'Legacy saved place' WHERE restaurant IS NULL")
    op.alter_column("favorites", "restaurant", existing_type=sa.String(200), nullable=False)
