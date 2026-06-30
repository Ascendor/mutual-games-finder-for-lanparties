"""remove orphaned unresolved GOG title tokens

Revision ID: 0012_gog_title_tokens
Revises: 0011_steam_non_games
"""

from alembic import op


revision = "0012_gog_title_tokens"
down_revision = "0011_steam_non_games"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM games
        WHERE title ~* '^product_title_[0-9]+$'
          AND NOT EXISTS (
              SELECT 1 FROM ownerships WHERE ownerships.game_id = games.id
          )
        """
    )


def downgrade() -> None:
    pass
