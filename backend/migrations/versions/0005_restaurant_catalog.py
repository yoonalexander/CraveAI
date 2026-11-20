"""Restaurant catalog from independently licensed sources."""
from alembic import op
import sqlalchemy as sa

revision = "0005_restaurant_catalog"
down_revision = "0004_discovery_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_restaurants",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("address", sa.String(300), nullable=False),
        sa.Column("cuisine", sa.String(250), nullable=False),
        sa.Column("website", sa.String(500), nullable=False),
    )
    op.create_index("ix_catalog_restaurants_lat_lng", "catalog_restaurants", ["lat", "lng"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE catalog_restaurants ENABLE ROW LEVEL SECURITY")
        op.execute("REVOKE ALL ON catalog_restaurants FROM anon, authenticated")


def downgrade() -> None:
    op.drop_table("catalog_restaurants")
