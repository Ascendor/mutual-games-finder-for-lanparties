from __future__ import annotations

import json
import re
import sqlite3
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable

from sqlalchemy import or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Account, Game, Participant, Platform, PlatformGameMapping, SyncRun
from app.services.account_identity import is_placeholder_display_name
from app.services.import_providers import ImportedGame
from app.services.metadata_service import METADATA_SYNC_LOCK, enrich_all_game_metadata
from app.services.normalization import normalize_title
from app.services.sync_service import resolve_game, upsert_ownership

GalaxyProgressCallback = Callable[[str, int, int, int], None]

TITLE_TYPES = ("title", "originalTitle", "originalSortingTitle")
ALL_RELEASE_TYPES = ("allGameReleases",)
PC_PLATFORM_PREFIXES: dict[str, Platform] = {
    "amazon": Platform.amazon,
    "battlenet": Platform.battle_net,
    "epic": Platform.epic,
    "gog": Platform.gog,
    "humble": Platform.humble,
    "origin": Platform.ea,
    "rockstar": Platform.rockstar,
    "steam": Platform.steam,
    "twitch": Platform.amazon,
    "uplay": Platform.ubisoft,
    "xboxone": Platform.xbox,
}
LOCAL_PLATFORM_PREFIXES = {"generic", "local"}
IGNORED_PLATFORM_PREFIXES = {
    "android",
    "arcade",
    "dreamcast",
    "gameboy",
    "gamecube",
    "ios",
    "n3ds",
    "n64",
    "nintendo",
    "nwii",
    "ps2",
    "ps3",
    "ps4",
    "ps5",
    "psn",
    "psp",
    "psx",
    "switch",
    "snes",
    "vita",
    "wii",
    "wiiu",
}


@dataclass
class GogGalaxyImportResult:
    imported_games: int = 0
    skipped_games: int = 0
    created_accounts: int = 0
    updated_ownerships: int = 0
    platforms: list[str] | None = None
    message: str = "GOG Galaxy import completed"
    game_ids: set[int] = field(default_factory=set)


@dataclass(frozen=True)
class GalaxyEntry:
    release_key: str
    platform: Platform
    platform_game_id: str
    title: str
    playtime_minutes: int = 0
    related_releases: tuple[tuple[Platform, str], ...] = field(default_factory=tuple)


def import_gog_galaxy_export_path(
    db: Session,
    participant_id: int,
    path: Path | str,
    progress_callback: GalaxyProgressCallback | None = None,
) -> GogGalaxyImportResult:
    if progress_callback:
        progress_callback("reading", 0, 0, 0)
    import_path = Path(path)
    extracted_path: Path | None = None
    try:
        database_path = import_path
        if zipfile.is_zipfile(import_path):
            extracted_path = _extract_galaxy_database(import_path)
            database_path = extracted_path
        entries = _read_galaxy_entries(database_path)
        return _import_galaxy_entries(db, participant_id, entries, progress_callback)
    finally:
        if extracted_path:
            _remove_sqlite_file_set(extracted_path)


def _extract_galaxy_database(path: Path) -> Path:
    with zipfile.ZipFile(path) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if not name.endswith("/") and Path(name).name.casefold() == "galaxy-2.0.db"
        ]
        if not candidates:
            raise ValueError("ZIP enthaelt keine galaxy-2.0.db.")
        selected = sorted(candidates, key=lambda value: (0 if "storage" in value.casefold() else 1, len(value)))[0]
        with archive.open(selected) as source:
            with NamedTemporaryFile(prefix="gog-galaxy-", suffix=".db", delete=False) as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
                database_path = Path(target.name)
        for sqlite_suffix in ("-wal", "-shm"):
            sidecar = _find_zip_member(archive, f"galaxy-2.0.db{sqlite_suffix}")
            if sidecar:
                with archive.open(sidecar) as source:
                    with (database_path.parent / f"{database_path.name}{sqlite_suffix}").open("wb") as target:
                        while chunk := source.read(1024 * 1024):
                            target.write(chunk)
        return database_path


def _find_zip_member(archive: zipfile.ZipFile, filename: str) -> str | None:
    filename = filename.casefold()
    matches = [name for name in archive.namelist() if Path(name).name.casefold() == filename]
    return sorted(matches, key=lambda value: (0 if "storage" in value.casefold() else 1, len(value)))[0] if matches else None


def _remove_sqlite_file_set(path: Path) -> None:
    path.unlink(missing_ok=True)
    for sqlite_suffix in ("-wal", "-shm"):
        path.with_name(f"{path.name}{sqlite_suffix}").unlink(missing_ok=True)


def _read_galaxy_entries(path: Path) -> list[GalaxyEntry]:
    if not path.is_file():
        raise ValueError("GOG-Galaxy-Datenbank wurde nicht gefunden.")
    entries: list[GalaxyEntry] = []
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        _ensure_galaxy_schema(connection)
        title_type_ids = _game_piece_type_ids(connection, TITLE_TYPES)
        all_release_type_ids = _game_piece_type_ids(connection, ALL_RELEASE_TYPES)
        if not title_type_ids:
            raise ValueError("GOG-Galaxy-Datenbank enthaelt keine Titel-Metadaten.")
        owned_rows = connection.execute(
            """
            SELECT lr.userId, lr.releaseKey, COALESCE(gt.minutesInGame, 0)
            FROM LibraryReleases lr
            JOIN LicensedReleases lic ON lic.libraryId = lr.id AND lic.isOwned = 1
            LEFT JOIN GameTimes gt ON gt.userId = lr.userId AND gt.releaseKey = lr.releaseKey
            ORDER BY lr.releaseKey
            """
        ).fetchall()
        title_lookup = _title_lookup(connection, title_type_ids)
        all_release_lookup = _all_game_releases_lookup(connection, all_release_type_ids)
        for user_id, release_key, playtime in owned_rows:
            parsed = _parse_release_key(str(release_key))
            if not parsed:
                continue
            platform, platform_game_id = parsed
            title = title_lookup.get((int(user_id), str(release_key))) or title_lookup.get((0, str(release_key)))
            if not title:
                continue
            related_releases = (
                all_release_lookup.get((int(user_id), str(release_key)))
                or all_release_lookup.get((0, str(release_key)))
                or ()
            )
            entries.append(
                GalaxyEntry(
                    release_key=str(release_key),
                    platform=platform,
                    platform_game_id=platform_game_id,
                    title=title,
                    playtime_minutes=max(0, int(playtime or 0)),
                    related_releases=related_releases,
                )
            )
    return entries


def _ensure_galaxy_schema(connection: sqlite3.Connection) -> None:
    required = {"LibraryReleases", "LicensedReleases", "GameTimes", "GamePieces", "GamePieceTypes"}
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    missing = sorted(required - tables)
    if missing:
        raise ValueError(f"Keine gueltige GOG-Galaxy-Datenbank; Tabellen fehlen: {', '.join(missing)}.")


def _game_piece_type_ids(connection: sqlite3.Connection, names: tuple[str, ...]) -> dict[int, str]:
    placeholders = ",".join("?" for _ in names)
    return {
        int(row[0]): str(row[1])
        for row in connection.execute(
            f"SELECT id, type FROM GamePieceTypes WHERE type IN ({placeholders})",
            names,
        ).fetchall()
    }


def _title_lookup(connection: sqlite3.Connection, title_type_ids: dict[int, str]) -> dict[tuple[int, str], str]:
    lookup: dict[tuple[int, str], str] = {}
    priority = {"title": 0, "originalTitle": 1, "originalSortingTitle": 2}
    current_priority: dict[tuple[int, str], int] = {}
    placeholders = ",".join("?" for _ in title_type_ids)
    rows = connection.execute(
        f"""
        SELECT releaseKey, gamePieceTypeId, userId, value
        FROM GamePieces
        WHERE gamePieceTypeId IN ({placeholders})
        """,
        tuple(title_type_ids),
    ).fetchall()
    for release_key, type_id, user_id, value in rows:
        title = _title_from_piece(value)
        if not title:
            continue
        key = (int(user_id or 0), str(release_key))
        item_priority = priority.get(title_type_ids[int(type_id)], 99)
        if key not in lookup or item_priority < current_priority[key]:
            lookup[key] = title
            current_priority[key] = item_priority
    return lookup


def _all_game_releases_lookup(
    connection: sqlite3.Connection,
    all_release_type_ids: dict[int, str],
) -> dict[tuple[int, str], tuple[tuple[Platform, str], ...]]:
    if not all_release_type_ids:
        return {}
    lookup: dict[tuple[int, str], tuple[tuple[Platform, str], ...]] = {}
    placeholders = ",".join("?" for _ in all_release_type_ids)
    rows = connection.execute(
        f"""
        SELECT releaseKey, userId, value
        FROM GamePieces
        WHERE gamePieceTypeId IN ({placeholders})
        """,
        tuple(all_release_type_ids),
    ).fetchall()
    for release_key, user_id, value in rows:
        releases = _release_mappings_from_piece(value)
        if releases:
            lookup[(int(user_id or 0), str(release_key))] = releases
    return lookup


def _release_mappings_from_piece(value: Any) -> tuple[tuple[Platform, str], ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return ()
    raw_releases = parsed.get("releases") if isinstance(parsed, dict) else parsed
    if not isinstance(raw_releases, list):
        return ()
    mappings: list[tuple[Platform, str]] = []
    seen: set[tuple[Platform, str]] = set()
    for release_key in raw_releases:
        parsed_release = _parse_release_key(str(release_key))
        if not parsed_release:
            continue
        platform, platform_game_id = parsed_release
        if platform == Platform.local:
            continue
        key = (platform, platform_game_id)
        if key in seen:
            continue
        mappings.append(key)
        seen.add(key)
    return tuple(mappings)


def _title_from_piece(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    text = str(value).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text if _valid_title(text) else ""
    if isinstance(parsed, dict):
        title = parsed.get("title") or parsed.get("name")
        return str(title).strip() if _valid_title(title) else ""
    if isinstance(parsed, str):
        return parsed.strip() if _valid_title(parsed) else ""
    return ""


def _valid_title(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not value.strip().startswith("{")


def _parse_release_key(release_key: str) -> tuple[Platform, str] | None:
    if "_" not in release_key:
        return None
    prefix, external_id = release_key.split("_", 1)
    prefix = prefix.casefold()
    external_id = external_id.strip()
    if not external_id:
        return None
    if prefix in IGNORED_PLATFORM_PREFIXES:
        return None
    if prefix in LOCAL_PLATFORM_PREFIXES:
        return Platform.local, external_id
    platform = PC_PLATFORM_PREFIXES.get(prefix)
    if not platform:
        return None
    return platform, external_id


def _import_galaxy_entries(
    db: Session,
    participant_id: int,
    entries: list[GalaxyEntry],
    progress_callback: GalaxyProgressCallback | None = None,
) -> GogGalaxyImportResult:
    result = GogGalaxyImportResult(platforms=[])
    seen_platforms: set[str] = set()
    total_entries = len(entries)
    if progress_callback:
        progress_callback("importing", 0, total_entries, 0)

    for index, entry in enumerate(entries, start=1):
        imported = ImportedGame(
            platform_game_id=entry.platform_game_id,
            title=entry.title,
            playtime_minutes=entry.playtime_minutes,
            feature_metadata_known=False,
        )
        account, created = _account_for_import(db, participant_id, entry.platform)
        if created:
            result.created_accounts += 1
        game = resolve_game(db, entry.platform.value, imported)
        upsert_ownership(
            db,
            account,
            game,
            imported,
            playtime_priority="fallback",
            discovery_is_baseline=True,
        )
        _add_galaxy_related_mappings(db, game, entry.title, entry.related_releases)
        result.imported_games += 1
        result.updated_ownerships += 1
        result.game_ids.add(game.id)
        seen_platforms.add(entry.platform.value)
        if progress_callback and (index % 10 == 0 or index == total_entries):
            progress_callback("importing", index, total_entries, result.imported_games)

    result.platforms = sorted(seen_platforms)
    result.message = f"{result.imported_games} Spiele aus GOG Galaxy importiert"
    db.commit()
    return result


def _add_galaxy_related_mappings(
    db: Session,
    game: Game,
    title: str,
    related_releases: tuple[tuple[Platform, str], ...],
) -> None:
    if not related_releases:
        return
    existing_numeric_steam_ids = {
        str(platform_game_id)
        for platform_game_id in db.scalars(
            select(PlatformGameMapping.platform_game_id).where(
                PlatformGameMapping.game_id == game.id,
                PlatformGameMapping.platform == Platform.steam,
            )
        )
        if str(platform_game_id).isdigit()
    }
    related_numeric_steam_ids = {
        platform_game_id
        for platform, platform_game_id in related_releases
        if platform == Platform.steam and platform_game_id.isdigit()
    }
    ambiguous_new_steam_mapping = len(related_numeric_steam_ids) > 1 and not existing_numeric_steam_ids

    for platform, platform_game_id in related_releases:
        if platform == Platform.steam and platform_game_id.isdigit():
            if ambiguous_new_steam_mapping:
                continue
            if existing_numeric_steam_ids and platform_game_id not in existing_numeric_steam_ids:
                continue
        existing = db.scalar(
            select(PlatformGameMapping).where(
                PlatformGameMapping.platform == platform,
                PlatformGameMapping.platform_game_id == platform_game_id,
            )
        )
        if existing:
            continue
        db.add(
            PlatformGameMapping(
                game_id=game.id,
                platform=platform,
                platform_game_id=platform_game_id,
                platform_title=title,
                normalized_title=normalize_title(title),
            )
        )
        if platform == Platform.steam and platform_game_id.isdigit():
            existing_numeric_steam_ids.add(platform_game_id)
    db.flush()


def _account_for_import(db: Session, participant_id: int, platform: Platform) -> tuple[Account, bool]:
    participant = db.get(Participant, participant_id)
    participant_label = participant.nickname if participant else str(participant_id)
    existing = db.scalar(
        select(Account)
        .where(Account.participant_id == participant_id, Account.platform == platform)
        .order_by(Account.id)
    )
    if existing:
        if existing.account_id.startswith("gog-galaxy:") and is_placeholder_display_name(existing):
            existing.display_name = f"{participant_label} (GOG Galaxy)"
        existing.last_successful_sync = datetime.utcnow()
        existing.last_error = None
        return existing, False

    account = Account(
        participant_id=participant_id,
        platform=platform,
        account_id=f"gog-galaxy:{participant_id}:{platform.value}",
        display_name=f"{participant_label} (GOG Galaxy)",
        last_successful_sync=datetime.utcnow(),
        last_error=None,
    )
    db.add(account)
    db.flush()
    return account, True


def create_gog_galaxy_import_run(db: Session, participant_id: int, filename: str) -> SyncRun:
    running = db.scalar(
        select(SyncRun).where(
            SyncRun.kind == "gog_galaxy",
            SyncRun.participant_id == participant_id,
            SyncRun.finished_at.is_(None),
        )
    )
    if running:
        raise RuntimeError("Fuer diesen Teilnehmer laeuft bereits ein GOG-Galaxy-Import.")
    run = SyncRun(
        participant_id=participant_id,
        kind="gog_galaxy",
        stage="queued",
        message=f"{filename or 'GOG-Galaxy-Datenbank'} wurde hochgeladen und wartet auf Verarbeitung.",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def close_interrupted_gog_galaxy_runs(db: Session) -> None:
    runs = db.scalars(
        select(SyncRun).where(
            SyncRun.kind == "gog_galaxy",
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
        run.message = "GOG-Galaxy-Import wurde durch einen Serverneustart abgebrochen."
    db.commit()


def _update_gog_galaxy_run(run_id: int, **values: Any) -> None:
    progress_db = SessionLocal()
    try:
        run = progress_db.get(SyncRun, run_id)
        if not run:
            return
        for key, value in values.items():
            setattr(run, key, value)
        progress_db.commit()
    except OperationalError:
        progress_db.rollback()
    finally:
        progress_db.close()


def run_gog_galaxy_import(run_id: int, path: Path | str) -> None:
    import_path = Path(path)
    db = SessionLocal()
    metadata_lock_acquired = False
    try:
        run = db.get(SyncRun, run_id)
        if not run or run.participant_id is None:
            return

        def update_import_progress(stage: str, current: int, total: int, imported: int) -> None:
            messages = {
                "reading": "GOG-Galaxy-Datenbank wird gelesen.",
                "importing": f"{current} von {total} Bibliothekseintraegen verarbeitet.",
            }
            _update_gog_galaxy_run(
                run_id,
                stage=stage,
                progress_current=current,
                progress_total=total,
                imported_games=imported,
                message=messages[stage],
            )

        result = import_gog_galaxy_export_path(
            db,
            run.participant_id,
            import_path,
            progress_callback=update_import_progress,
        )
        metadata_ids = set(
            db.scalars(
                select(Game.id).where(
                    Game.id.in_(result.game_ids),
                    or_(
                        Game.metadata_updated_at.is_(None),
                        Game.multiplayer_metadata_known.is_(False),
                        Game.player_count_known.is_(False),
                    ),
                )
            ).all()
        )

        metadata_result = None
        metadata_error: str | None = None
        if metadata_ids:
            _update_gog_galaxy_run(
                run_id,
                stage="metadata_waiting",
                progress_current=0,
                progress_total=len(metadata_ids),
                imported_games=result.imported_games,
                message=(
                    f"{result.imported_games} Spiele importiert. "
                    "Metadaten-Anreicherung wartet auf einen freien Slot."
                ),
            )
            METADATA_SYNC_LOCK.acquire()
            metadata_lock_acquired = True
            _update_gog_galaxy_run(
                run_id,
                stage="metadata",
                message=f"Metadaten fuer {len(metadata_ids)} Spiele werden ergaenzt.",
            )

            def update_metadata_progress(
                scanned: int,
                updated: int,
                igdb_errors: int,
                rawg_errors: int,
            ) -> None:
                error_count = igdb_errors + rawg_errors
                _update_gog_galaxy_run(
                    run_id,
                    stage="metadata",
                    progress_current=scanned,
                    progress_total=len(metadata_ids),
                    message=(
                        f"Metadaten: {scanned} von {len(metadata_ids)} geprueft, "
                        f"{updated} aktualisiert"
                        + (f", {error_count} Quellenfehler" if error_count else "")
                    ),
                )

            try:
                metadata_result = enrich_all_game_metadata(
                    db,
                    progress_callback=update_metadata_progress,
                    game_ids=metadata_ids,
                )
            except Exception as exc:
                db.rollback()
                metadata_error = str(exc)

        metadata_summary = ""
        if metadata_result:
            metadata_summary = (
                f"; Metadaten: {metadata_result.updated_games} aktualisiert"
                + (
                    f", {metadata_result.failed_games} mit Quellenfehlern"
                    if metadata_result.failed_games
                    else ""
                )
            )
        elif metadata_error:
            metadata_summary = f"; Metadaten konnten nicht ergaenzt werden: {metadata_error}"
        elif not metadata_ids:
            metadata_summary = "; vorhandene Metadaten waren bereits vollstaendig"

        _update_gog_galaxy_run(
            run_id,
            stage="completed",
            progress_current=1,
            progress_total=1,
            imported_games=result.imported_games,
            success=True,
            finished_at=datetime.utcnow(),
            message=f"{result.imported_games} Spiele aus GOG Galaxy importiert{metadata_summary}.",
        )
    except Exception as exc:
        db.rollback()
        _update_gog_galaxy_run(
            run_id,
            stage="failed",
            success=False,
            finished_at=datetime.utcnow(),
            message=f"GOG-Galaxy-Import fehlgeschlagen: {exc}",
        )
    finally:
        if metadata_lock_acquired:
            METADATA_SYNC_LOCK.release()
        db.close()
        import_path.unlink(missing_ok=True)
