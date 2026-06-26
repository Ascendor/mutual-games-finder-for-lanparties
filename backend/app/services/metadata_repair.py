from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Platform, PlatformGameMapping

STEAM_FEATURE_OVERRIDES: dict[str, dict[str, bool | int]] = {
    # Older importer heuristics incorrectly tagged TFC as shared/split screen.
    "20": {
        "multiplayer": True,
        "split_screen": False,
        "shared_screen": False,
        "max_players": 32,
    }
}


def repair_legacy_steam_metadata(db: Session) -> int:
    changed = 0
    steam_mappings = db.scalars(
        select(PlatformGameMapping).where(PlatformGameMapping.platform == Platform.steam)
    ).all()
    for mapping in steam_mappings:
        game = mapping.game
        before = (
            game.multiplayer,
            game.split_screen,
            game.shared_screen,
            game.min_players,
            game.max_players,
        )
        if game.max_players == 8:
            game.max_players = 1
        override = STEAM_FEATURE_OVERRIDES.get(mapping.platform_game_id)
        if override:
            for field, value in override.items():
                setattr(game, field, value)
            game.min_players = max(1, game.min_players or 1)
        after = (
            game.multiplayer,
            game.split_screen,
            game.shared_screen,
            game.min_players,
            game.max_players,
        )
        if after != before:
            changed += 1
    if changed:
        db.commit()
    return changed

