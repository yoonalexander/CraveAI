"""Store reviewed menu facts and catalog source check outcomes."""
from alembic import op
import sqlalchemy as sa

revision = "0007_catalog_menu_index"
down_revision = "0006_catalog_listing_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_menu_checks",
        sa.Column("restaurant_id", sa.String(40), sa.ForeignKey("catalog_restaurants.id"), primary_key=True),
        sa.Column("checked_on", sa.Date(), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("candidates", sa.Integer(), nullable=False),
        sa.Column("documents", sa.JSON(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
    )
    op.create_table(
        "catalog_dishes",
        sa.Column("restaurant_id", sa.String(40), sa.ForeignKey("catalog_restaurants.id"), primary_key=True),
        sa.Column("slot", sa.Integer(), primary_key=True),
        sa.Column("dish_key", sa.String(160), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("family", sa.String(160), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("checked_on", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("prices", sa.JSON(), nullable=False),
        sa.CheckConstraint("slot BETWEEN 1 AND 10", name="ck_catalog_dish_slot"),
        sa.UniqueConstraint("restaurant_id", "dish_key", name="uq_catalog_dish_key"),
    )
    if op.get_bind().dialect.name == "postgresql":
        for table in ("catalog_menu_checks", "catalog_dishes"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated")


def downgrade() -> None:
    op.drop_table("catalog_dishes")
    op.drop_table("catalog_menu_checks")
