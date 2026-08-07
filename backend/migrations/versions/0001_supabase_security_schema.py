"""Supabase-backed application security schema."""

from alembic import op
import sqlalchemy as sa

revision = "0001_supabase_security"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Supabase owns identities. Keep this explicit rather than letting the app
    # create or mutate auth.users records directly.
    op.execute(
        "ALTER TABLE profiles ADD CONSTRAINT fk_profiles_auth_user "
        "FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE"
    )
    op.create_table(
        "app_sessions",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("profiles.user_id", ondelete="CASCADE")),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("user_agent_hash", sa.String(64)),
        sa.Column("ip_prefix_hash", sa.String(64)),
    )
    op.create_index("ix_app_sessions_token_hash", "app_sessions", ["token_hash"], unique=True)
    op.create_index("ix_app_sessions_user_id", "app_sessions", ["user_id"])
    op.create_table(
        "account_identities",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("profiles.user_id", ondelete="CASCADE")),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_identity_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_identity_id"),
        sa.UniqueConstraint("user_id", "provider"),
    )
    op.create_index("ix_account_identities_user_id", "account_identities", ["user_id"])
    op.create_table(
        "auth_transactions",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("transaction_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("state_hash", sa.String(64)),
        sa.Column("nonce_hash", sa.String(64)),
        sa.Column("encrypted_code_verifier", sa.Text()),
        sa.Column("encrypted_access_token", sa.Text()),
        sa.Column("user_id", sa.Uuid(as_uuid=False)),
        sa.Column("next_path", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "favorites",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("profiles.user_id", ondelete="CASCADE")),
        sa.Column("restaurant", sa.String(200), nullable=False),
        sa.Column("note", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_favorites_user_id", "favorites", ["user_id"])
    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False), sa.ForeignKey("profiles.user_id", ondelete="CASCADE")),
        sa.Column("restaurant", sa.String(200), nullable=False),
        sa.Column("liked", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])
    op.create_table(
        "usage_limits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("namespace", sa.String(32), nullable=False),
        sa.Column("actor_key", sa.String(160), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("units_used", sa.Integer(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("namespace", "actor_key", "usage_date"),
    )
    op.create_index("ix_usage_limits_date_namespace", "usage_limits", ["usage_date", "namespace"])
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False)),
        sa.Column("session_id", sa.Uuid(as_uuid=False)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_security_audit_events_event_type", "security_audit_events", ["event_type"])
    op.create_index("ix_security_audit_events_user_id", "security_audit_events", ["user_id"])
    op.create_table(
        "abuse_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("namespace", sa.String(40), nullable=False),
        sa.Column("actor_hash", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_abuse_events_namespace", "abuse_events", ["namespace"])
    op.create_index("ix_abuse_events_actor_hash", "abuse_events", ["actor_hash"])
    # The browser never accesses application tables through PostgREST. Deny
    # Supabase client roles explicitly; only the backend database role may use
    # these tables.
    for table in (
        "profiles",
        "app_sessions",
        "account_identities",
        "auth_transactions",
        "favorites",
        "feedback",
        "usage_limits",
        "security_audit_events",
        "abuse_events",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE {table} FROM anon, authenticated")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated")


def downgrade() -> None:
    for table in (
        "abuse_events",
        "security_audit_events",
        "usage_limits",
        "feedback",
        "favorites",
        "auth_transactions",
        "account_identities",
        "app_sessions",
        "profiles",
    ):
        op.drop_table(table)
