from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any, Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Game, Platform, PlatformGameMapping, SyncRun
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
METADATA_SYNC_LOCK = Lock()

@dataclass
class MetadataSyncResult:
    scanned_games: int = 0
    updated_games: int = 0
    failed_games: int = 0
    message: str = "metadata sync completed"


def create_metadata_sync_run(db: Session) -> SyncRun:
    if not METADATA_SYNC_LOCK.acquire(blocking=False):
        raise RuntimeError("Eine Metadatensynchronisation läuft bereits")
    try:
        run = SyncRun(kind="metadata", message="Metadatensynchronisation wartet auf Start")
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    except Exception:
        METADATA_SYNC_LOCK.release()
        raise


def close_interrupted_metadata_runs(db: Session) -> None:
    runs = db.scalars(
        select(SyncRun).where(SyncRun.kind == "metadata", SyncRun.finished_at.is_(None))
    ).all()
    if not runs:
        return
    now = datetime.utcnow()
    for run in runs:
        run.success = False
        run.finished_at = now
        run.message = "Metadatensynchronisation wurde durch einen Serverneustart abgebrochen"
    db.commit()


def run_metadata_sync(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(SyncRun, run_id)
        if not run:
            return
        run.message = "Metadaten werden geprüft"
        db.commit()

        def update_progress(scanned: int, updated: int, failed: int) -> None:
            progress_run = db.get(SyncRun, run_id)
            if progress_run:
                progress_run.imported_games = updated
                progress_run.message = (
                    f"{scanned} Spiele geprüft, {updated} aktualisiert"
                    + (f", {failed} Fehler" if failed else "")
                )
                db.commit()

        result = enrich_all_game_metadata(db, progress_callback=update_progress)
        run = db.get(SyncRun, run_id)
        if not run:
            return
        run.success = result.failed_games == 0
        run.finished_at = datetime.utcnow()
        run.imported_games = result.updated_games
        run.message = (
            f"{result.updated_games} von {result.scanned_games} Spielen aktualisiert"
            + (f", {result.failed_games} Fehler" if result.failed_games else "")
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(SyncRun, run_id)
        if run:
            run.success = False
            run.finished_at = datetime.utcnow()
            run.message = f"Metadatensynchronisation fehlgeschlagen: {exc}"
            db.commit()
    finally:
        db.close()
        METADATA_SYNC_LOCK.release()


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


def _fetch_game_metadata(job: tuple[int, str, list[tuple[Platform, str]]]) -> tuple[int, list[tuple[dict[str, Any], bool]]]:
    game_id, title, mappings = job
    payloads: list[tuple[dict[str, Any], bool]] = []
    for platform, platform_game_id in mappings:
        if platform == Platform.steam:
            metadata = _steam_appdetails(platform_game_id)
            if metadata:
                payloads.append((metadata, True))
    rawg = _rawg_metadata(title)
    if rawg:
        payloads.append((rawg, False))
    return game_id, payloads


def enrich_all_game_metadata(
    db: Session,
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> MetadataSyncResult:
    result = MetadataSyncResult()
    games = db.scalars(select(Game).options(selectinload(Game.mappings)).order_by(Game.title)).unique().all()
    result.scanned_games = len(games)
    games_by_id = {game.id: game for game in games}
    jobs = [
        (
            game.id,
            game.title,
            [(mapping.platform, mapping.platform_game_id) for mapping in game.mappings],
        )
        for game in games
    ]
    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="metadata-fetch") as executor:
        fetched = executor.map(_fetch_game_metadata, jobs)
        for scanned, (game_id, payloads) in enumerate(fetched, start=1):
            game = games_by_id[game_id]
            changed = False
            try:
                for payload, trusted_features in payloads:
                    changed = _apply_payload(game, payload, trusted_features=trusted_features) or changed
                if changed:
                    result.updated_games += 1
                    db.flush()
            except Exception:
                result.failed_games += 1
            if scanned % 25 == 0:
                db.commit()
                if progress_callback:
                    progress_callback(scanned, result.updated_games, result.failed_games)
    db.commit()
    if progress_callback:
        progress_callback(result.scanned_games, result.updated_games, result.failed_games)
    if result.failed_games:
        result.message = f"metadata sync completed with {result.failed_games} failed games"
    return result


