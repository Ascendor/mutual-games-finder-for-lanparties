from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, Callable

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Game, Ownership, Platform, PlatformGameMapping, SyncRun
from app.services.game_classification import classify_game
from app.services.import_providers import ImportedGame, _steam_metadata_from_details
from app.services.sync_service import _merge_game_metadata

STEAM_METADATA_LOCK = Lock()
STEAM_RATE_LOCK = Lock()
STEAM_METADATA_WORKERS = 4
STEAM_METADATA_COMMIT_INTERVAL = 10
STEAM_REQUEST_INTERVAL = 0.2
STEAM_LAST_REQUEST = 0.0


@dataclass
class SteamMetadataResult:
    scanned_games: int = 0
    updated_games: int = 0
    failed_games: int = 0
    errors: list[str] = field(default_factory=list)


def create_steam_metadata_run(db: Session) -> SyncRun:
    if not STEAM_METADATA_LOCK.acquire(blocking=False):
        raise RuntimeError("Ein vollstaendiger Steam-Metadatenabgleich laeuft bereits")
    try:
        run = SyncRun(
            kind="steam_metadata",
            stage="queued",
            message="Vollstaendiger Steam-Metadatenabgleich wartet auf Start",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    except Exception:
        STEAM_METADATA_LOCK.release()
        raise


def close_interrupted_steam_metadata_runs(db: Session) -> None:
    runs = db.scalars(
        select(SyncRun).where(
            SyncRun.kind == "steam_metadata",
            SyncRun.finished_at.is_(None),
        )
    ).all()
    if not runs:
        return
    now = datetime.utcnow()
    for run in runs:
        run.success = False
        run.stage = "failed"
        run.finished_at = now
        run.message = "Steam-Metadatenabgleich wurde durch einen Serverneustart abgebrochen"
    db.commit()


def _steam_games(db: Session, game_ids: set[int] | None = None) -> list[tuple[int, int, str]]:
    rows = db.execute(
        select(
            PlatformGameMapping.game_id,
            PlatformGameMapping.platform_game_id,
            Game.title,
            func.coalesce(func.max(Ownership.playtime_minutes), 0).label("playtime"),
        )
        .join(Game, Game.id == PlatformGameMapping.game_id)
        .outerjoin(Ownership, Ownership.game_id == Game.id)
        .where(PlatformGameMapping.platform == Platform.steam)
        .where(PlatformGameMapping.game_id.in_(game_ids) if game_ids is not None else True)
        .group_by(
            PlatformGameMapping.game_id,
            PlatformGameMapping.platform_game_id,
            Game.title,
        )
    ).all()
    numeric = [
        (int(game_id), int(platform_game_id), str(title), int(playtime or 0))
        for game_id, platform_game_id, title, playtime in rows
        if str(platform_game_id).isdigit()
    ]
    numeric.sort(key=lambda item: (-item[3], item[2].casefold(), item[1]))
    seen_games: set[int] = set()
    result: list[tuple[int, int, str]] = []
    for game_id, app_id, title, _playtime in numeric:
        if game_id in seen_games:
            continue
        seen_games.add(game_id)
        result.append((game_id, app_id, title))
    return result


def _fetch_steam_metadata(
    client: httpx.Client,
    app_id: int,
) -> tuple[dict[str, Any] | None, str | None]:
    response: httpx.Response | None = None
    for attempt in range(4):
        try:
            _wait_for_steam_slot()
            response = client.get(
                "https://store.steampowered.com/api/appdetails",
                params={
                    "appids": str(app_id),
                    "filters": "basic,categories,genres,release_date",
                },
            )
            if response.status_code != 429 and response.status_code < 500:
                if response.is_error:
                    return None, f"Steam Store HTTP {response.status_code}"
                payload = response.json()
                item = payload.get(str(app_id), {}) if isinstance(payload, dict) else {}
                if (
                    isinstance(item, dict)
                    and item.get("success")
                    and isinstance(item.get("data"), dict)
                ):
                    return _steam_metadata_from_details(app_id, item["data"]), None
                return None, "Steam Store lieferte keine App-Metadaten"
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 5.0 * (attempt + 1)
        except Exception as exc:
            if attempt == 3:
                return None, str(exc)
            delay = float(attempt + 1)
        time.sleep(delay)
    status = response.status_code if response is not None else "keine Antwort"
    return None, f"Steam Store HTTP {status}"


def _wait_for_steam_slot() -> None:
    global STEAM_LAST_REQUEST
    with STEAM_RATE_LOCK:
        wait = STEAM_REQUEST_INTERVAL - (time.monotonic() - STEAM_LAST_REQUEST)
        if wait > 0:
            time.sleep(wait)
        STEAM_LAST_REQUEST = time.monotonic()


def _apply_steam_metadata(game: Game, app_id: int, metadata: dict[str, Any]) -> None:
    imported = ImportedGame(
        platform_game_id=str(app_id),
        title=game.title,
        description=metadata.get("description", ""),
        cover_url=metadata.get("cover_url"),
        release_date=metadata.get("release_date"),
        genres=metadata.get("genres", []),
        is_free=metadata.get("is_free"),
        singleplayer=metadata.get("singleplayer", False),
        multiplayer=metadata.get("multiplayer", False),
        lan=metadata.get("lan", False),
        local_coop=metadata.get("local_coop", False),
        online_coop=metadata.get("online_coop", False),
        split_screen=metadata.get("split_screen", False),
        shared_screen=metadata.get("shared_screen", False),
        min_players=metadata.get("min_players", 1),
        max_players=metadata.get("max_players", 1),
        feature_metadata_known=metadata.get("feature_metadata_known", False),
        player_count_known=metadata.get("player_count_known", False),
    )
    _merge_game_metadata(game, imported)
    sources = dict(game.metadata_sources or {})
    sources["is_free"] = "steam_store"

    classification = classify_game(
        game.title,
        metadata.get("genres") or game.genres or [],
        store_type=metadata.get("store_type"),
    )
    if classification.is_game is False:
        game.is_game = False
        game.non_game_reason = classification.reason
        sources["is_game"] = "steam_store"
        sources["non_game_reason"] = "steam_store"
    elif sources.get("is_game") in {"classification", "steam_store"}:
        game.is_game = True
        game.non_game_reason = None
        sources["is_game"] = "steam_store"
        sources.pop("non_game_reason", None)
    if not game.metadata_source:
        game.metadata_source = "steam_store"
        game.metadata_external_id = str(app_id)
    game.metadata_updated_at = datetime.utcnow()
    game.metadata_sources = sources


def enrich_steam_game_metadata(
    db: Session,
    progress_callback: Callable[[int, int, int, int], None] | None = None,
    game_ids: set[int] | None = None,
    *,
    acquire_lock: bool = False,
) -> SteamMetadataResult:
    lock_acquired = False
    if acquire_lock:
        if not STEAM_METADATA_LOCK.acquire(blocking=False):
            raise RuntimeError("Ein vollstaendiger Steam-Metadatenabgleich laeuft bereits")
        lock_acquired = True
    try:
        games = _steam_games(db, game_ids)
        updated = 0
        failed = 0
        errors: list[str] = []
        if progress_callback:
            progress_callback(0, len(games), updated, failed)
        with httpx.Client(
            timeout=httpx.Timeout(20.0, connect=5.0),
            headers={"User-Agent": "Mozilla/5.0 (LAN Party Game Finder)"},
        ) as client:
            with ThreadPoolExecutor(
                max_workers=max(
                    1,
                    min(STEAM_METADATA_WORKERS, int(settings.steam_metadata_workers or 1)),
                ),
                thread_name_prefix="steam-metadata",
            ) as executor:
                futures = {
                    executor.submit(_fetch_steam_metadata, client, app_id): (
                        game_id,
                        app_id,
                        title,
                    )
                    for game_id, app_id, title in games
                }
                for current, future in enumerate(as_completed(futures), start=1):
                    game_id, app_id, title = futures[future]
                    try:
                        metadata, error = future.result()
                    except Exception as exc:
                        metadata, error = None, str(exc)
                    if metadata:
                        game = db.get(Game, game_id)
                        if game:
                            _apply_steam_metadata(game, app_id, metadata)
                            updated += 1
                    else:
                        failed += 1
                        if len(errors) < 5:
                            errors.append(f"{title} ({app_id}): {error or 'unbekannter Fehler'}")

                    if progress_callback:
                        progress_callback(current, len(games), updated, failed)
                    if current % STEAM_METADATA_COMMIT_INTERVAL == 0:
                        db.commit()
        db.commit()
        return SteamMetadataResult(
            scanned_games=len(games),
            updated_games=updated,
            failed_games=failed,
            errors=errors,
        )
    finally:
        if lock_acquired:
            STEAM_METADATA_LOCK.release()


def run_steam_metadata_sync(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(SyncRun, run_id)
        if not run:
            return

        def update_progress(current: int, total: int, updated: int, failed: int) -> None:
            progress_run = db.get(SyncRun, run_id)
            if not progress_run:
                return
            progress_run.stage = "steam_metadata"
            progress_run.progress_current = current
            progress_run.progress_total = total
            progress_run.imported_games = updated
            progress_run.message = (
                f"{current} von {total} geprueft, "
                f"{updated} aktualisiert, {failed} Fehler"
            )
            db.commit()

        result = enrich_steam_game_metadata(db, progress_callback=update_progress)
        run = db.get(SyncRun, run_id)
        if not run:
            return
        run.success = True
        run.stage = "completed"
        run.finished_at = datetime.utcnow()
        run.progress_current = result.scanned_games
        run.progress_total = result.scanned_games
        run.imported_games = result.updated_games
        run.message = (
            f"{result.updated_games} von {result.scanned_games} Steam-Spielen aktualisiert"
            + (f", {result.failed_games} Warnungen. " + " | ".join(result.errors) if result.failed_games else "")
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(SyncRun, run_id)
        if run:
            run.success = False
            run.stage = "failed"
            run.finished_at = datetime.utcnow()
            run.message = f"Vollstaendiger Steam-Metadatenabgleich fehlgeschlagen: {exc}"
            db.commit()
    finally:
        db.close()
        STEAM_METADATA_LOCK.release()
