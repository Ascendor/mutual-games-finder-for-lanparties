"""split platform mappings with different sequel numbers

Revision ID: 0010_split_sequels
Revises: 0009_playnite_ea
"""

import re

from alembic import op
import sqlalchemy as sa


revision = "0010_split_sequels"
down_revision = "0009_playnite_ea"
branch_labels = None
depends_on = None

ROMAN_NUMERALS = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
}


def _sequence_tokens(title: str) -> tuple[int, ...]:
    values: list[int] = []
    for token in re.findall(r"[a-z0-9]+", title.casefold()):
        if token.isdigit():
            values.append(int(token))
        elif token in ROMAN_NUMERALS:
            values.append(ROMAN_NUMERALS[token])
    return tuple(values)


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT mapping.id, mapping.game_id, mapping.platform,
                   mapping.platform_title, mapping.normalized_title,
                   game.normalized_title
            FROM platform_game_mappings AS mapping
            JOIN games AS game ON game.id = mapping.game_id
            ORDER BY mapping.id
            """
        )
    ).all()

    for mapping_id, old_game_id, platform, platform_title, mapping_title, game_title in rows:
        if _sequence_tokens(mapping_title) == _sequence_tokens(game_title):
            continue

        target_game_id = connection.scalar(
            sa.text(
                """
                SELECT id
                FROM games
                WHERE normalized_title = :normalized_title
                  AND id <> :old_game_id
                ORDER BY id
                LIMIT 1
                """
            ),
            {
                "normalized_title": mapping_title,
                "old_game_id": old_game_id,
            },
        )
        if target_game_id is None:
            target_game_id = connection.scalar(
                sa.text(
                    """
                    INSERT INTO games (title, normalized_title)
                    VALUES (:title, :normalized_title)
                    RETURNING id
                    """
                ),
                {
                    "title": platform_title,
                    "normalized_title": mapping_title,
                },
            )

        platform_mapping_count = connection.scalar(
            sa.text(
                """
                SELECT count(*)
                FROM platform_game_mappings
                WHERE game_id = :game_id AND platform = :platform
                """
            ),
            {"game_id": old_game_id, "platform": platform},
        )
        connection.execute(
            sa.text(
                """
                UPDATE platform_game_mappings
                SET game_id = :target_game_id
                WHERE id = :mapping_id
                """
            ),
            {
                "target_game_id": target_game_id,
                "mapping_id": mapping_id,
            },
        )

        if platform_mapping_count != 1:
            continue

        ownerships = connection.execute(
            sa.text(
                """
                SELECT id, participant_id, playtime_minutes, owned_since, last_seen
                FROM ownerships
                WHERE game_id = :old_game_id AND platform = :platform
                """
            ),
            {"old_game_id": old_game_id, "platform": platform},
        ).all()
        for ownership_id, participant_id, playtime, owned_since, last_seen in ownerships:
            existing = connection.execute(
                sa.text(
                    """
                    SELECT id, playtime_minutes, owned_since, last_seen
                    FROM ownerships
                    WHERE participant_id = :participant_id
                      AND game_id = :target_game_id
                      AND platform = :platform
                    """
                ),
                {
                    "participant_id": participant_id,
                    "target_game_id": target_game_id,
                    "platform": platform,
                },
            ).first()
            if existing is None:
                connection.execute(
                    sa.text(
                        "UPDATE ownerships SET game_id = :game_id WHERE id = :ownership_id"
                    ),
                    {"game_id": target_game_id, "ownership_id": ownership_id},
                )
                continue

            existing_id, existing_playtime, existing_owned_since, existing_last_seen = existing
            dates = [value for value in (owned_since, existing_owned_since) if value is not None]
            connection.execute(
                sa.text(
                    """
                    UPDATE ownerships
                    SET playtime_minutes = :playtime,
                        owned_since = :owned_since,
                        last_seen = :last_seen
                    WHERE id = :existing_id
                    """
                ),
                {
                    "playtime": max(playtime or 0, existing_playtime or 0),
                    "owned_since": min(dates) if dates else None,
                    "last_seen": max(last_seen, existing_last_seen),
                    "existing_id": existing_id,
                },
            )
            connection.execute(
                sa.text("DELETE FROM ownerships WHERE id = :ownership_id"),
                {"ownership_id": ownership_id},
            )


def downgrade() -> None:
    pass
