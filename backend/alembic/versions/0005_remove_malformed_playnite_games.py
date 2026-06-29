"""remove malformed Playnite game records

Revision ID: 0005_clean_playnite
Revises: 0004_postgresql_indexes
"""

from __future__ import annotations

import ast

from alembic import op
import sqlalchemy as sa


revision = "0005_clean_playnite"
down_revision = "0004_postgresql_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    malformed_ids: list[int] = []
    rows = connection.execute(
        sa.text(
            """
            SELECT DISTINCT games.id, games.title
            FROM games
            JOIN platform_game_mappings
              ON platform_game_mappings.game_id = games.id
            WHERE platform_game_mappings.platform = 'local'
              AND platform_game_mappings.platform_game_id LIKE 'playnite:%'
              AND games.title LIKE '{%'
            """
        )
    )
    for game_id, title in rows:
        try:
            parsed = ast.literal_eval(title)
        except (SyntaxError, ValueError):
            continue
        if isinstance(parsed, dict):
            malformed_ids.append(game_id)

    if malformed_ids:
        connection.execute(
            sa.text("DELETE FROM games WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": malformed_ids},
        )


def downgrade() -> None:
    pass
