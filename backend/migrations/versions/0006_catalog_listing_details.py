"""Preserve catalog IDs across refreshes and retain known listing details."""
from alembic import op
import sqlalchemy as sa

revision = "0006_catalog_listing_details"
down_revision = "0005_restaurant_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("catalog_restaurants", sa.Column("listed", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("catalog_restaurants", sa.Column("checked_on", sa.Date()))
    op.add_column("catalog_restaurants", sa.Column("phone", sa.String(40)))
    op.add_column("catalog_restaurants", sa.Column("hours", sa.String(500)))


def downgrade() -> None:
    for column in ("hours", "phone", "checked_on", "listed"):
        op.drop_column("catalog_restaurants", column)
