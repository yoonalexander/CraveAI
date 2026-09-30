"""Editable, email-independent account usernames."""

from alembic import op
import sqlalchemy as sa

revision = "0003_profile_username"
down_revision = "0002_privacy_product"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL keeps existing accounts usable without generating names from emails.
    op.add_column("profiles", sa.Column("username", sa.String(30), nullable=True))
    op.create_index("uq_profiles_username", "profiles", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_profiles_username", table_name="profiles")
    op.drop_column("profiles", "username")
