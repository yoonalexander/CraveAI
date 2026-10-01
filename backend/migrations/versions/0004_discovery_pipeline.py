"""Source-backed regional restaurant discoveries and durable refresh leases."""
from alembic import op
import sqlalchemy as sa

revision = "0004_discovery_pipeline"
down_revision = "0003_profile_username"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("discovery_refreshes",
        sa.Column("source_id", sa.String(80), primary_key=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("error_code", sa.String(40)),
    )
    op.create_table("discovery_signals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_id", sa.String(80), nullable=False),
        sa.Column("region", sa.String(40), nullable=False),
        sa.Column("article_key", sa.String(64), nullable=False),
        sa.Column("headline_hash", sa.String(64), nullable=False),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("publisher", sa.String(200), nullable=False),
        sa.Column("publisher_group", sa.String(80)),
        sa.Column("restaurant_name", sa.String(160), nullable=False),
        sa.Column("city", sa.String(80), nullable=False),
        sa.Column("source_address", sa.String(240)),
        sa.Column("evidence", sa.String(160), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opening_date", sa.Date()),
        sa.Column("opening_evidence", sa.String(160)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("place_id", sa.String(256)),
        sa.Column("match_status", sa.String(24), nullable=False),
        sa.Column("matched_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_discovery_signals_region_expiry", "discovery_signals", ["region", "expires_at"])
    # Only the backend database role serves these tables; no direct browser writes.
    if op.get_bind().dialect.name == "postgresql":
        for table in ("discovery_refreshes", "discovery_signals"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON {table} FROM anon, authenticated")


def downgrade() -> None:
    op.drop_table("discovery_signals")
    op.drop_table("discovery_refreshes")
