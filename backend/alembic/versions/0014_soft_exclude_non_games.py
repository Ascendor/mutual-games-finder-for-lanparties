"""Soft-exclude verified non-game software from game lists.

Revision ID: 0014_soft_non_games
Revises: 0013_playnite_progress
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_soft_non_games"
down_revision = "0013_playnite_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("is_game", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("games", sa.Column("non_game_reason", sa.String(length=255)))
    op.create_index("ix_games_is_game", "games", ["is_game"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_games_is_game", table_name="games")
    op.drop_column("games", "non_game_reason")
    op.drop_column("games", "is_game")
