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
    with op.batch_alter_table("games") as batch_op:
        batch_op.add_column(
            sa.Column("is_game", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(sa.Column("non_game_reason", sa.String(length=255)))
        batch_op.create_index("ix_games_is_game", ["is_game"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("games") as batch_op:
        batch_op.drop_index("ix_games_is_game")
        batch_op.drop_column("non_game_reason")
        batch_op.drop_column("is_game")
