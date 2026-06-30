"""remove demos and other non-game Steam entries

Revision ID: 0011_steam_non_games
Revises: 0010_split_sequels
"""

from alembic import op


revision = "0011_steam_non_games"
down_revision = "0010_split_sequels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM ownerships
        WHERE platform = 'steam'
          AND game_id IN (
              SELECT game_id
              FROM platform_game_mappings
              WHERE platform = 'steam'
                AND platform_title ~* '(^|[^[:alnum:]])(demo|dedicated[[:space:]]+server|test[[:space:]]+server|sdk)([^[:alnum:]]|$)'
          )
        """
    )
    op.execute(
        """
        DELETE FROM games
        WHERE NOT EXISTS (
            SELECT 1 FROM ownerships WHERE ownerships.game_id = games.id
        )
          AND id IN (
              SELECT game_id
              FROM platform_game_mappings
              WHERE platform = 'steam'
                AND platform_title ~* '(^|[^[:alnum:]])(demo|dedicated[[:space:]]+server|test[[:space:]]+server|sdk)([^[:alnum:]]|$)'
          )
        """
    )


def downgrade() -> None:
    pass
