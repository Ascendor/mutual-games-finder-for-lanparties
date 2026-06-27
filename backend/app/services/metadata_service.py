from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import Game, Platform, PlatformGameMapping
from app.services.import_providers import _game_from_mapping, _steam_metadata_from_details
from app.services.sync_service import _merge_game_metadata

FEATURE_FIELDS = (
    "singleplayer",
    "multiplayer",
    "lan",
    "local_coop",
    "online_coop",
    "hotseat",
    "split_screen",
    "shared_screen",
    "min_players",
    "max_players",
    "feature_metadata_known",
)

@dataclass
class MetadataSyncResult:
    scanned_games: int = 0
    updated_games: int = 0
    failed_games: int = 0
    message: str = "metadata sync completed"


def _descriptive_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in FEATURE_FIELDS}


def _apply_payload(game: Game, payload: dict[str, Any], *, trusted_features: bool = False) -> bool:
    if not trusted_features:
        payload = _descriptive_payload(payload)
    imported = _game_from_mapping({"title": game.title, "platform_game_id": str(game.id), **payload})
    if not imported:
        return False
    before = _snapshot(game)
    _merge_game_metadata(game, imported)
    return _snapshot(game) != before


def _snapshot(game: Game) -> tuple[Any, ...]:
    return (
        game.description,
        game.cover_url,
        game.release_date,
        tuple(game.genres or []),
        game.singleplayer,
        game.multiplayer,
        game.lan,
        game.local_coop,
        game.online_coop,
        game.hotseat,
        game.split_screen,
        game.shared_screen,
        game.min_players,
        game.max_players,
    )


def _steam_appdetails(appid: str) -> dict[str, Any] | None:
    try:
        response = httpx.get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": appid, "filters": "basic,categories,genres,release_date"},
            headers={"User-Agent": "Mozilla/5.0 (LAN Party Game Finder)"},
            timeout=6,
        )
        response.raise_for_status()
        item = response.json().get(appid, {})
        if isinstance(item, dict) and item.get("success") and isinstance(item.get("data"), dict):
            return _steam_metadata_from_details(int(appid), item["data"])
    except Exception:
        return None
    return None


def _rawg_metadata(title: str) -> dict[str, Any] | None:
    if not settings.rawg_api_key:
        return None
    try:
        with httpx.Client(timeout=20) as client:
            search = client.get(
                "https://api.rawg.io/api/games",
                params={"key": settings.rawg_api_key, "search": title, "search_exact": "true", "page_size": 1},
            )
            search.raise_for_status()
            results = search.json().get("results") or []
            if not results:
                return None
            item = results[0]
            slug = item.get("slug") or item.get("id")
            details = client.get(f"https://api.rawg.io/api/games/{slug}", params={"key": settings.rawg_api_key})
            details.raise_for_status()
            data = details.json()
    except Exception:
        return None

    tags = {str(tag.get("name", "")).casefold() for tag in data.get("tags", []) if isinstance(tag, dict)}
    genres = [str(genre.get("name")) for genre in data.get("genres", []) if isinstance(genre, dict) and genre.get("name")]
    return {
        "description": data.get("description_raw") or data.get("description") or "",
        "cover_url": data.get("background_image"),
        "release_date": data.get("released"),
        "genres": genres,
    }


def enrich_all_game_metadata(db: Session) -> MetadataSyncResult:
    result = MetadataSyncResult()
    games = db.scalars(select(Game).options(selectinload(Game.mappings)).order_by(Game.title)).unique().all()
    result.scanned_games = len(games)
    for game in games:
        changed = False
        try:
            for mapping in game.mappings:
                if mapping.platform == Platform.steam:
                    metadata = _steam_appdetails(mapping.platform_game_id)
                    if metadata:
                        changed = _apply_payload(game, metadata, trusted_features=True) or changed
            rawg = _rawg_metadata(game.title)
            if rawg:
                changed = _apply_payload(game, rawg) or changed
            if changed:
                result.updated_games += 1
                db.flush()
        except Exception:
            result.failed_games += 1
    db.commit()
    if result.failed_games:
        result.message = f"metadata sync completed with {result.failed_games} failed games"
    return result


