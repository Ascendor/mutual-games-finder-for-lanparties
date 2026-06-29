"""split colliding numeric Steam mappings

Revision ID: 0006_unique_steam
Revises: 0005_clean_playnite
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_unique_steam"
down_revision = "0005_clean_playnite"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    duplicate_game_ids = connection.scalars(
        sa.text(
            """
            SELECT game_id
            FROM platform_game_mappings
            WHERE platform = 'steam'
              AND platform_game_id ~ '^[0-9]+$'
            GROUP BY game_id
            HAVING count(*) > 1
            """
        )
    ).all()

    for game_id in duplicate_game_ids:
        game_normalized_title = connection.scalar(
            sa.text("SELECT normalized_title FROM games WHERE id = :game_id"),
            {"game_id": game_id},
        )
        mappings = connection.execute(
            sa.text(
                """
                SELECT id, platform_title, normalized_title
                FROM platform_game_mappings
                WHERE game_id = :game_id
                  AND platform = 'steam'
                  AND platform_game_id ~ '^[0-9]+$'
                ORDER BY (normalized_title = :normalized_title) DESC, id
                """
            ),
            {"game_id": game_id, "normalized_title": game_normalized_title},
        ).all()
        for mapping_id, platform_title, normalized_title in mappings[1:]:
            new_game_id = connection.scalar(
                sa.text(
                    """
                    INSERT INTO games (title, normalized_title)
                    VALUES (:title, :normalized_title)
                    RETURNING id
                    """
                ),
                {"title": platform_title, "normalized_title": normalized_title},
            )
            connection.execute(
                sa.text(
                    "UPDATE platform_game_mappings SET game_id = :game_id WHERE id = :mapping_id"
                ),
                {"game_id": new_game_id, "mapping_id": mapping_id},
            )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_one_numeric_steam_mapping_per_game
        ON platform_game_mappings (game_id)
        WHERE platform = 'steam' AND platform_game_id ~ '^[0-9]+$'
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS uq_one_numeric_steam_mapping_per_game")
