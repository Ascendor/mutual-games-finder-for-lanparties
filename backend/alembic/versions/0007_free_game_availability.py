"""track free game availability

Revision ID: 0007_free_games
Revises: 0006_unique_steam
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_free_games"
down_revision = "0006_unique_steam"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("is_free", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("games", "is_free")
