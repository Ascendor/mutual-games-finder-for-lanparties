from __future__ import annotations

import json
import re
import struct
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Account, Game, Participant, Platform, SyncRun
from app.services.account_identity import is_placeholder_display_name
from app.services.import_providers import ImportedGame, _as_int, _as_list, _parse_date
from app.services.genre_utils import sanitize_genres
from app.services.metadata_service import METADATA_SYNC_LOCK, enrich_all_game_metadata
from app.services.normalization import normalize_title
from app.services.sync_service import resolve_game, upsert_ownership

PlayniteProgressCallback = Callable[[str, int, int, int], None]


@dataclass
class PlayniteImportResult:
    imported_games: int = 0
    skipped_games: int = 0
    created_accounts: int = 0
    updated_ownerships: int = 0
    platforms: list[str] | None = None
    message: str = "Playnite import completed"
    game_ids: set[int] = field(default_factory=set)


def import_playnite_export(
    db: Session,
    participant_id: int,
    raw_json: bytes | str,
    progress_callback: PlayniteProgressCallback | None = None,
) -> PlayniteImportResult:
    if progress_callback:
        progress_callback("reading", 0, 0, 0)
    entries = _extract_entries_from_upload(raw_json)
    return _import_playnite_entries(db, participant_id, entries, progress_callback)


def import_playnite_export_path(
    db: Session,
    participant_id: int,
    path: Path | str,
    progress_callback: PlayniteProgressCallback | None = None,
) -> PlayniteImportResult:
    if progress_callback:
        progress_callback("reading", 0, 0, 0)
    entries = _extract_entries_from_path(Path(path))
    return _import_playnite_entries(db, participant_id, entries, progress_callback)


def _import_playnite_entries(
    db: Session,
    participant_id: int,
    entries: list[dict[str, Any]],
    progress_callback: PlayniteProgressCallback | None = None,
) -> PlayniteImportResult:
    result = PlayniteImportResult(platforms=[])
    seen_platforms: set[str] = set()
    merged_entries: dict[tuple[str, str], ImportedGame] = {}
    merged_platforms: dict[tuple[str, str], Platform] = {}
    total_entries = len(entries)
    if progress_callback:
        progress_callback("importing", 0, total_entries, 0)

    for index, entry in enumerate(entries, start=1):
        imported, platform = _imported_game_from_playnite_entry(entry)
        if not imported:
            result.skipped_games += 1
            if progress_callback and (index % 10 == 0 or index == total_entries):
                progress_callback("importing", index, total_entries, result.imported_games)
            continue
        result.imported_games += 1
        key = _playnite_import_key(platform, imported)
        existing_import = merged_entries.get(key)
        if existing_import is None:
            merged_entries[key] = imported
            merged_platforms[key] = platform
        else:
            _merge_playnite_import(existing_import, imported)
        seen_platforms.add(platform.value)
        if progress_callback and (index % 10 == 0 or index == total_entries):
            progress_callback("importing", index, total_entries, result.imported_games)

    for key, imported in merged_entries.items():
        platform = merged_platforms[key]
        account, created = _account_for_import(db, participant_id, platform)
        if created:
            result.created_accounts += 1
        game = resolve_game(db, platform.value, imported)
        upsert_ownership(
            db,
            account,
            game,
            imported,
            playtime_priority="fallback",
            discovery_is_baseline=True,
        )
        result.updated_ownerships += 1
        result.game_ids.add(game.id)

    result.platforms = sorted(seen_platforms)
    result.message = f"{result.imported_games} Spiele aus Playnite importiert"
    db.commit()
    return result


def _playnite_import_key(platform: Platform, imported: ImportedGame) -> tuple[str, str]:
    external_id = imported.platform_game_id.strip() if imported.platform_game_id else ""
    return (platform.value, external_id or f"title:{imported.normalized_title}")


def _merge_playnite_import(target: ImportedGame, incoming: ImportedGame) -> None:
    target.playtime_minutes = max(target.playtime_minutes, incoming.playtime_minutes)
    if incoming.description and not target.description:
        target.description = incoming.description
    if incoming.cover_url and not target.cover_url:
        target.cover_url = incoming.cover_url
    if incoming.release_date and target.release_date is None:
        target.release_date = incoming.release_date
    if incoming.genres:
        target.genres = sorted({*target.genres, *incoming.genres}, key=str.casefold)


def create_playnite_import_run(db: Session, participant_id: int, filename: str) -> SyncRun:
    running = db.scalar(
        select(SyncRun).where(
            SyncRun.kind == "playnite",
            SyncRun.participant_id == participant_id,
            SyncRun.finished_at.is_(None),
        )
    )
    if running:
        raise RuntimeError("Für diesen Teilnehmer läuft bereits ein Playnite-Import.")
    run = SyncRun(
        participant_id=participant_id,
        kind="playnite",
        stage="queued",
        message=f"{filename or 'Playnite-Backup'} wurde hochgeladen und wartet auf Verarbeitung.",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def close_interrupted_playnite_runs(db: Session) -> None:
    runs = db.scalars(
        select(SyncRun).where(
            SyncRun.kind == "playnite",
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
        run.message = "Playnite-Import wurde durch einen Serverneustart abgebrochen."
    db.commit()


def _update_playnite_run(run_id: int, **values: Any) -> None:
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


def run_playnite_import(run_id: int, path: Path | str) -> None:
    import_path = Path(path)
    db = SessionLocal()
    metadata_lock_acquired = False
    try:
        run = db.get(SyncRun, run_id)
        if not run or run.participant_id is None:
            return

        def update_import_progress(stage: str, current: int, total: int, imported: int) -> None:
            messages = {
                "reading": "Playnite-Backup wird gelesen und entpackt.",
                "importing": f"{current} von {total} Bibliothekseinträgen verarbeitet.",
            }
            _update_playnite_run(
                run_id,
                stage=stage,
                progress_current=current,
                progress_total=total,
                imported_games=imported,
                message=messages[stage],
            )

        result = import_playnite_export_path(
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
            _update_playnite_run(
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
            _update_playnite_run(
                run_id,
                stage="metadata",
                message=f"Metadaten für {len(metadata_ids)} Spiele werden ergänzt.",
            )

            def update_metadata_progress(
                scanned: int,
                updated: int,
                igdb_errors: int,
                rawg_errors: int,
            ) -> None:
                error_count = igdb_errors + rawg_errors
                _update_playnite_run(
                    run_id,
                    stage="metadata",
                    progress_current=scanned,
                    progress_total=len(metadata_ids),
                    message=(
                        f"Metadaten: {scanned} von {len(metadata_ids)} geprüft, "
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
            metadata_summary = f"; Metadaten konnten nicht ergänzt werden: {metadata_error}"
        elif not metadata_ids:
            metadata_summary = "; vorhandene Metadaten waren bereits vollständig"

        _update_playnite_run(
            run_id,
            stage="completed",
            progress_current=1,
            progress_total=1,
            imported_games=result.imported_games,
            success=True,
            finished_at=datetime.utcnow(),
            message=f"{result.imported_games} Spiele aus Playnite importiert{metadata_summary}.",
        )
    except Exception as exc:
        db.rollback()
        _update_playnite_run(
            run_id,
            stage="failed",
            imported_games=0,
            success=False,
            finished_at=datetime.utcnow(),
            message=f"Playnite-Import fehlgeschlagen: {exc}",
        )
    finally:
        if metadata_lock_acquired:
            METADATA_SYNC_LOCK.release()
        db.close()
        import_path.unlink(missing_ok=True)


def _extract_entries_from_upload(raw: bytes | str) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        return _extract_game_entries(json.loads(raw))
    if zipfile.is_zipfile(BytesIO(raw)):
        return _extract_entries_from_zip(raw)
    return _extract_game_entries(json.loads(raw.decode("utf-8-sig")))


def _extract_entries_from_path(path: Path) -> list[dict[str, Any]]:
    if zipfile.is_zipfile(path):
        return _extract_entries_from_zip(path)
    return _extract_game_entries(json.loads(path.read_text(encoding="utf-8-sig")))


def _extract_entries_from_zip(raw: bytes | Path) -> list[dict[str, Any]]:
    all_entries: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    source = BytesIO(raw) if isinstance(raw, bytes) else raw
    with zipfile.ZipFile(source) as archive:
        db_entries = _extract_litedb_entries_from_zip(archive)
        for entry in db_entries:
            _append_unique_playnite_entry(all_entries, seen_keys, entry)

        for name in archive.namelist():
            if not name.casefold().endswith(".json"):
                continue
            with archive.open(name) as member:
                try:
                    payload = json.loads(member.read().decode("utf-8-sig"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
            for entry in _extract_game_entries(payload):
                _append_unique_playnite_entry(all_entries, seen_keys, entry)
    return all_entries


def _append_unique_playnite_entry(
    entries: list[dict[str, Any]],
    seen_keys: set[tuple[str, str, str]],
    entry: dict[str, Any],
) -> None:
    title = _playnite_title(entry)
    if not title:
        return
    source = str(_first_deep(entry, "Source", "source", "SourceName", "sourceName", "Provider", "provider") or "")
    game_id = str(_first_deep(entry, "GameId", "gameId", "Id", "id") or "")
    key = (normalize_title(title), source.casefold(), game_id)
    if key in seen_keys:
        return
    seen_keys.add(key)
    entries.append(entry)


def _extract_litedb_entries_from_zip(archive: zipfile.ZipFile) -> list[dict[str, Any]]:
    db_files: dict[str, bytes] = {}
    required_files = {"games.db", "sources.db", "platforms.db", "genres.db"}
    for name in archive.namelist():
        lowered = name.replace("\\", "/").casefold()
        if not lowered.startswith("library/") or not lowered.endswith(".db"):
            continue
        filename = lowered.rsplit("/", 1)[-1]
        if filename not in required_files:
            continue
        with archive.open(name) as member:
            db_files[filename] = member.read()

    games_raw = db_files.get("games.db")
    if not games_raw:
        return []

    sources = _litedb_name_lookup(db_files.get("sources.db"))
    platforms = _litedb_name_lookup(db_files.get("platforms.db"))
    genres = _litedb_name_lookup(db_files.get("genres.db"))

    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for document in _read_litedb_documents(games_raw):
        if not _looks_like_game(document):
            continue
        game_key = str(_first_deep(document, "Id", "_id", "id", "GameId", "gameId") or "")
        title = _playnite_title(document)
        if not title:
            continue
        unique_key = game_key or normalize_title(title)
        if unique_key in seen_ids:
            continue
        seen_ids.add(unique_key)
        entries.append(_hydrate_litedb_game(document, sources, platforms, genres))
    return entries


def _litedb_name_lookup(raw: bytes | None) -> dict[str, str]:
    if not raw:
        return {}
    lookup: dict[str, str] = {}
    for document in _read_litedb_documents(raw):
        identifier = _first_deep(document, "Id", "_id", "id")
        name = _first_deep(document, "Name", "name")
        if identifier and name:
            lookup[str(identifier)] = str(name)
    return lookup


def _read_litedb_documents(raw: bytes) -> list[dict[str, Any]]:
    page_documents = _read_litedb_v4_pages(raw)
    return page_documents if page_documents else _scan_bson_documents(raw)


def _read_litedb_v4_pages(raw: bytes) -> list[dict[str, Any]]:
    page_size = 4096
    if len(raw) < page_size or len(raw) % page_size:
        return []

    documents: list[dict[str, Any]] = []
    page_count = len(raw) // page_size
    for page_id in range(page_count):
        page = raw[page_id * page_size : (page_id + 1) * page_size]
        stored_page_id = struct.unpack_from("<I", page, 0)[0]
        if stored_page_id != page_id or page[4] != 4:
            continue
        item_count = struct.unpack_from("<H", page, 13)[0]
        pos = 25
        for _ in range(item_count):
            if pos + 8 > page_size:
                break
            _index, extend_page_id, data_size = struct.unpack_from("<HIH", page, pos)
            pos += 8
            if pos + data_size > page_size:
                break
            bson = page[pos : pos + data_size]
            pos += data_size
            if extend_page_id != 0xFFFFFFFF:
                bson = _read_litedb_v4_extend_chain(raw, extend_page_id)
            if not bson:
                continue
            try:
                documents.append(_parse_bson_document(bson))
            except (IndexError, ValueError, struct.error, UnicodeDecodeError):
                continue
    return documents


def _read_litedb_v4_extend_chain(raw: bytes, first_page_id: int) -> bytes:
    page_size = 4096
    page_count = len(raw) // page_size
    chunks: list[bytes] = []
    visited: set[int] = set()
    page_id = first_page_id
    while page_id != 0xFFFFFFFF:
        if page_id >= page_count or page_id in visited:
            return b""
        visited.add(page_id)
        page = raw[page_id * page_size : (page_id + 1) * page_size]
        if struct.unpack_from("<I", page, 0)[0] != page_id or page[4] != 5:
            return b""
        next_page_id = struct.unpack_from("<I", page, 9)[0]
        data_size = struct.unpack_from("<H", page, 13)[0]
        if data_size > page_size - 25:
            return b""
        chunks.append(page[25 : 25 + data_size])
        page_id = next_page_id
    return b"".join(chunks)


def _hydrate_litedb_game(
    document: dict[str, Any],
    sources: dict[str, str],
    platforms: dict[str, str],
    genres: dict[str, str],
) -> dict[str, Any]:
    entry = dict(document)
    source_id = _first_deep(document, "SourceId", "sourceId")
    source_name = sources.get(str(source_id)) if source_id else None
    if source_name:
        entry["Source"] = {"Name": source_name}
        entry["SourceName"] = source_name

    platform_names = _lookup_many_names(_first_deep(document, "PlatformIds", "platformIds", "Platforms"), platforms)
    if platform_names:
        entry["Platforms"] = platform_names

    genre_names = _lookup_many_names(_first_deep(document, "GenreIds", "genreIds", "Genres"), genres)
    if genre_names:
        entry["Genres"] = genre_names
    return entry


def _lookup_many_names(value: Any, lookup: dict[str, str]) -> list[str]:
    names: list[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            item = _first_deep(item, "Id", "_id", "id", "Name", "name")
        name = lookup.get(str(item), str(item).strip())
        if name:
            names.append(name)
    return sorted(set(names))


def _scan_bson_documents(raw: bytes) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    seen_offsets: set[int] = set()
    for offset in range(0, max(0, len(raw) - 5)):
        if offset in seen_offsets:
            continue
        length = int.from_bytes(raw[offset : offset + 4], "little", signed=True)
        if length < 5 or length > 2_000_000 or offset + length > len(raw):
            continue
        if raw[offset + length - 1] != 0:
            continue
        try:
            document = _parse_bson_document(raw[offset : offset + length])
        except (IndexError, ValueError, struct.error, UnicodeDecodeError):
            continue
        if document:
            documents.append(document)
            seen_offsets.add(offset)
    return documents


def _parse_bson_document(raw: bytes) -> dict[str, Any]:
    length = struct.unpack_from("<i", raw, 0)[0]
    if length != len(raw) or raw[-1] != 0:
        raise ValueError("invalid bson document")
    pos = 4
    document: dict[str, Any] = {}
    while pos < length - 1:
        element_type = raw[pos]
        pos += 1
        if pos >= length:
            raise ValueError("invalid bson element")
        key_end = raw.index(0, pos)
        key = raw[pos:key_end].decode("utf-8")
        pos = key_end + 1
        value, pos = _parse_bson_value(raw, pos, element_type)
        document[key] = value
    if pos != length - 1:
        raise ValueError("invalid bson document boundary")
    return document


def _parse_bson_value(raw: bytes, pos: int, element_type: int) -> tuple[Any, int]:
    if element_type == 0x01:
        _ensure_bson_bytes(raw, pos, 8)
        return struct.unpack_from("<d", raw, pos)[0], pos + 8
    if element_type == 0x02:
        _ensure_bson_bytes(raw, pos, 4)
        size = struct.unpack_from("<i", raw, pos)[0]
        start = pos + 4
        _ensure_bson_bytes(raw, start, size)
        return raw[start : start + size - 1].decode("utf-8"), start + size
    if element_type in (0x03, 0x04):
        _ensure_bson_bytes(raw, pos, 4)
        size = struct.unpack_from("<i", raw, pos)[0]
        _ensure_bson_bytes(raw, pos, size)
        nested = _parse_bson_document(raw[pos : pos + size])
        if element_type == 0x04:
            keys = sorted(nested, key=lambda item: (0, int(item)) if item.isdigit() else (1, item))
            return [nested[key] for key in keys], pos + size
        return nested, pos + size
    if element_type == 0x05:
        _ensure_bson_bytes(raw, pos, 5)
        size = struct.unpack_from("<i", raw, pos)[0]
        subtype = raw[pos + 4]
        start = pos + 5
        _ensure_bson_bytes(raw, start, size)
        data = raw[start : start + size]
        if size == 16 and subtype in (0x03, 0x04):
            return str(uuid.UUID(bytes=data)), start + size
        return data.hex(), start + size
    if element_type == 0x07:
        _ensure_bson_bytes(raw, pos, 12)
        return raw[pos : pos + 12].hex(), pos + 12
    if element_type == 0x08:
        _ensure_bson_bytes(raw, pos, 1)
        return bool(raw[pos]), pos + 1
    if element_type == 0x09:
        _ensure_bson_bytes(raw, pos, 8)
        return struct.unpack_from("<q", raw, pos)[0], pos + 8
    if element_type == 0x0A:
        return None, pos
    if element_type == 0x10:
        _ensure_bson_bytes(raw, pos, 4)
        return struct.unpack_from("<i", raw, pos)[0], pos + 4
    if element_type == 0x12:
        _ensure_bson_bytes(raw, pos, 8)
        return struct.unpack_from("<q", raw, pos)[0], pos + 8
    raise ValueError(f"unsupported bson element type {element_type}")


def _ensure_bson_bytes(raw: bytes, pos: int, size: int) -> None:
    if pos < 0 or size < 0 or pos + size > len(raw):
        raise ValueError("truncated bson value")


def _extract_game_entries(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        if isinstance(payload, list):
            candidates: list[dict[str, Any]] = []
            for item in payload:
                candidates.extend(_extract_game_entries(item))
            return candidates
        return []

    for key in ("Games", "games", "Library", "library", "Items", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            entries: list[dict[str, Any]] = []
            for item in value:
                entries.extend(_extract_game_entries(item))
            if entries:
                return entries

    candidates: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if _looks_like_game(value):
                candidates.append(value)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    return candidates


def _looks_like_game(value: Any) -> bool:
    if not isinstance(value, dict) or not _playnite_title(value):
        return False
    game_keys = {
        "Added",
        "added",
        "CompletionStatus",
        "completionStatus",
        "GameId",
        "gameId",
        "Genre",
        "genre",
        "Genres",
        "genres",
        "Hidden",
        "hidden",
        "InstallDirectory",
        "installDirectory",
        "IsInstalled",
        "isInstalled",
        "Platform",
        "platform",
        "Platforms",
        "platforms",
        "Playtime",
        "playtime",
        "PlaytimeMinutes",
        "playtimeMinutes",
        "PluginId",
        "pluginId",
        "Provider",
        "provider",
        "ReleaseDate",
        "releaseDate",
        "Source",
        "source",
        "SourceId",
        "sourceId",
        "SourceName",
        "sourceName",
    }
    return any(key in value for key in game_keys)


def _imported_game_from_playnite_entry(entry: dict[str, Any]) -> tuple[ImportedGame | None, Platform]:
    title = _playnite_title(entry)
    if not title:
        return None, Platform.local

    platform = _detect_platform(entry)
    platform_game_id = _detect_platform_game_id(entry, platform, title)
    playtime_minutes = _playtime_minutes(entry)
    release_date = _parse_date(_first_deep(entry, "ReleaseDate", "releaseDate", "Released", "released"))
    genres = _names_from_collection(_first_deep(entry, "Genres", "genres", "Genre", "genre"))
    cover_url = _first_deep(entry, "CoverImage", "coverImage", "Cover", "cover", "Icon", "icon")

    return (
        ImportedGame(
            platform_game_id=platform_game_id,
            title=title,
            playtime_minutes=playtime_minutes,
            cover_url=str(cover_url) if cover_url else None,
            release_date=release_date,
            genres=genres,
            feature_metadata_known=False,
        ),
        platform,
    )


def _account_for_import(db: Session, participant_id: int, platform: Platform) -> tuple[Account, bool]:
    participant = db.get(Participant, participant_id)
    participant_label = participant.nickname if participant else str(participant_id)
    existing = db.scalar(
        select(Account)
        .where(Account.participant_id == participant_id, Account.platform == platform)
        .order_by(Account.id)
    )
    if existing:
        if existing.account_id.startswith("playnite:") and is_placeholder_display_name(existing):
            existing.display_name = f"{participant_label} (Playnite)"
        existing.last_successful_sync = datetime.utcnow()
        existing.last_error = None
        return existing, False

    account = Account(
        participant_id=participant_id,
        platform=platform,
        account_id=f"playnite:{participant_id}:{platform.value}",
        display_name=f"{participant_label} (Playnite)",
        last_successful_sync=datetime.utcnow(),
        last_error=None,
    )
    db.add(account)
    db.flush()
    return account, True


def _detect_platform(entry: dict[str, Any]) -> Platform:
    text = " ".join(
        str(value)
        for value in (
            _first_deep(entry, "Source", "source", "SourceName", "sourceName", "PluginId", "pluginId", "Provider", "provider"),
            _first_deep(entry, "Platform", "platform", "Platforms", "platforms"),
        )
        if value
    ).casefold()
    if "steam" in text:
        return Platform.steam
    if "epic" in text:
        return Platform.epic
    if "gog" in text:
        return Platform.gog
    if "ubisoft" in text or "uplay" in text:
        return Platform.ubisoft
    if "origin" in text or re.search(r"\bea\b", text):
        return Platform.ea
    if "xbox" in text or "microsoft" in text:
        return Platform.xbox
    if "amazon" in text or "prime gaming" in text:
        return Platform.amazon
    if "battle.net" in text or "battlenet" in text or "blizzard" in text:
        return Platform.battle_net
    if "bethesda" in text:
        return Platform.bethesda
    if "game jolt" in text or "gamejolt" in text:
        return Platform.gamejolt
    if "humble" in text and re.search(r"\bkeys?\b", text):
        return Platform.humble_key
    if "humble" in text:
        return Platform.humble
    if "oculus" in text or "meta quest" in text or "meta pcvr" in text:
        return Platform.meta
    if "itch" in text or "itch.io" in text:
        return Platform.itch
    if "legacy games" in text or "legacygames" in text:
        return Platform.legacy
    if "nintendo" in text:
        return Platform.nintendo
    if "playstation" in text or "psn" in text:
        return Platform.playstation
    if "riot" in text:
        return Platform.riot
    if "rockstar" in text:
        return Platform.rockstar
    return Platform.local


def _detect_platform_game_id(entry: dict[str, Any], platform: Platform, title: str) -> str:
    key_candidates = {
        Platform.steam: ("SteamAppId", "steamAppId", "SteamId", "steamId", "AppId", "appId"),
        Platform.epic: ("EpicId", "epicId", "Namespace", "namespace", "AppName", "appName"),
        Platform.gog: ("GogId", "gogId", "GogGameId", "gogGameId", "ProductId", "productId"),
        Platform.ubisoft: ("UbisoftId", "ubisoftId", "UplayId", "uplayId", "ProductId", "productId"),
        Platform.ea: ("EaId", "eaId", "OriginId", "originId", "ProductId", "productId"),
        Platform.xbox: ("XboxTitleId", "xboxTitleId", "TitleId", "titleId", "ProductId", "productId"),
        Platform.amazon: ("AmazonId", "amazonId", "ProductId", "productId", "GameId", "gameId"),
        Platform.battle_net: ("BattleNetId", "battleNetId", "BattlenetId", "battlenetId", "ProductId", "productId"),
        Platform.bethesda: ("BethesdaId", "bethesdaId", "ProductId", "productId"),
        Platform.gamejolt: ("GameJoltId", "gameJoltId", "GameId", "gameId"),
        Platform.humble: ("HumbleId", "humbleId", "MachineName", "machineName", "ProductId", "productId"),
        Platform.humble_key: ("HumbleKeyId", "humbleKeyId", "KeyIndex", "keyIndex", "GameId", "gameId", "ProductId", "productId"),
        Platform.meta: ("OculusId", "oculusId", "MetaId", "metaId", "AppId", "appId", "ProductId", "productId"),
        Platform.itch: ("ItchId", "itchId", "ItchioId", "itchioId", "Url", "url"),
        Platform.legacy: ("LegacyId", "legacyId", "ProductId", "productId"),
        Platform.nintendo: ("NintendoId", "nintendoId", "TitleId", "titleId", "ProductId", "productId"),
        Platform.playstation: ("PlaystationId", "playstationId", "PsnId", "psnId", "TitleId", "titleId"),
        Platform.riot: ("RiotId", "riotId", "ProductId", "productId"),
        Platform.rockstar: ("RockstarId", "rockstarId", "ProductId", "productId"),
        Platform.local: (),
    }
    for key in key_candidates[platform]:
        value = _first_deep(entry, key)
        if value:
            return str(value)

    game_id = _first_deep(entry, "GameId", "gameId", "Id", "id")
    if game_id and (platform == Platform.local or _looks_external_id(game_id)):
        return str(game_id)
    return f"playnite:{normalize_title(title)}"


def _looks_external_id(value: Any) -> bool:
    text = str(value).strip()
    return bool(text and not re.fullmatch(r"[0-9a-fA-F-]{32,36}", text))


def _playtime_minutes(entry: dict[str, Any]) -> int:
    seconds = _first_deep(entry, "Playtime", "playtime", "PlaytimeSeconds", "playtimeSeconds")
    if seconds not in (None, ""):
        duration = _duration_minutes(seconds)
        if duration is not None:
            return duration
        numeric_seconds = _as_int(seconds)
        if numeric_seconds > 10_000_000:
            return max(0, numeric_seconds // 600_000_000)
        return max(0, numeric_seconds // 60)
    minutes = _first_deep(entry, "PlaytimeMinutes", "playtimeMinutes", "MinutesPlayed", "minutesPlayed")
    if minutes not in (None, ""):
        return max(0, _as_int(minutes))
    hours = _first_deep(entry, "PlaytimeHours", "playtimeHours")
    if hours not in (None, ""):
        return max(0, _as_int(float(hours) * 60))
    return 0


def _duration_minutes(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.isdigit():
        return None
    match = re.fullmatch(r"(?:(\d+)\.)?(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?", text)
    if not match:
        return None
    days = _as_int(match.group(1), 0)
    hours = _as_int(match.group(2), 0)
    minutes = _as_int(match.group(3), 0)
    seconds = _as_int(match.group(4), 0)
    return max(0, days * 24 * 60 + hours * 60 + minutes + seconds // 60)


def _names_from_collection(value: Any) -> list[str]:
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, dict):
                name = _first_deep(item, "Name", "name")
                if name:
                    names.append(str(name))
            elif str(item).strip():
                names.append(str(item).strip())
        return sanitize_genres(names)
    return sanitize_genres(_as_list(value))


def _first_deep(data: Any, *keys: str) -> Any:
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    for value in data.values():
        if isinstance(value, dict):
            found = _first_deep(value, *keys)
            if found not in (None, ""):
                return found
    return None


def _first_shallow(data: Any, *keys: str) -> Any:
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _playnite_title(entry: dict[str, Any]) -> str | None:
    value = _first_shallow(entry, "Name", "name", "Title", "title")
    if not isinstance(value, str):
        return None
    title = value.strip()
    if not title or len(title) > 255:
        return None
    return title
