from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, Callable

import httpx
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Game, Platform, SyncRun
from app.services.game_classification import classify_game
from app.services.genre_utils import sanitize_genres
from app.services.normalization import normalize_title

METADATA_SYNC_LOCK = Lock()
IGDB_TOKEN_LOCK = Lock()
IGDB_RATE_LOCK = Lock()
IGDB_TOKEN: tuple[str, float] | None = None
IGDB_LAST_REQUEST = 0.0
IGDB_REQUEST_INTERVAL = 0.26
RAWG_RATE_LOCK = Lock()
RAWG_LAST_REQUEST = 0.0
RAWG_REQUEST_INTERVAL = 0.26
LOGGER = logging.getLogger(__name__)

FEATURE_FIELDS = {
    "singleplayer",
    "multiplayer",
    "lan",
    "local_coop",
    "online_coop",
    "hotseat",
    "split_screen",
    "shared_screen",
    "campaign_coop",
    "drop_in",
    "versus",
    "min_players",
    "max_players",
    "offline_max_players",
    "online_max_players",
    "offline_coop_max_players",
    "online_coop_max_players",
    "multiplayer_metadata_known",
    "player_count_known",
}


@dataclass
class MetadataSyncResult:
    scanned_games: int = 0
    updated_games: int = 0
    failed_games: int = 0
    igdb_errors: int = 0
    rawg_errors: int = 0
    excluded_games: int = 0
    rawg_unavailable_reason: str | None = None
    message: str = "metadata sync completed"


@dataclass
class MetadataRecord:
    values: dict[str, Any] = field(default_factory=dict)
    known_fields: set[str] = field(default_factory=set)
    sources: dict[str, str] = field(default_factory=dict)
    primary_source: str | None = None
    external_id: str | None = None

    def set(self, name: str, value: Any, source: str) -> None:
        self.values[name] = value
        self.known_fields.add(name)
        self.sources[name] = source


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
        run.message = "IGDB-Verbindung wird geprüft"
        db.commit()

        def update_progress(scanned: int, updated: int, igdb_errors: int, rawg_errors: int) -> None:
            progress_run = db.get(SyncRun, run_id)
            if progress_run:
                progress_run.imported_games = updated
                progress_run.message = (
                    f"{scanned} Spiele geprüft, {updated} aktualisiert"
                    + (
                        f", Quellenfehler: IGDB {igdb_errors}, RAWG {rawg_errors}"
                        if igdb_errors or rawg_errors
                        else ""
                    )
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
            + (
                f", {result.excluded_games} Nicht-Spiele ausgeblendet"
                if result.excluded_games
                else ""
            )
            + (
                f", Quellenfehler: IGDB {result.igdb_errors}, RAWG {result.rawg_errors}"
                if result.failed_games
                else ""
            )
            + (
                f", RAWG: {result.rawg_unavailable_reason}"
                if result.rawg_unavailable_reason
                else ""
            )
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


def _igdb_access_token() -> str:
    global IGDB_TOKEN
    if not settings.igdb_client_id or not settings.igdb_client_secret:
        raise RuntimeError("IGDB_CLIENT_ID und IGDB_CLIENT_SECRET sind nicht konfiguriert")
    now = time.monotonic()
    with IGDB_TOKEN_LOCK:
        if IGDB_TOKEN and IGDB_TOKEN[1] > now + 60:
            return IGDB_TOKEN[0]
        response = httpx.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": settings.igdb_client_id,
                "client_secret": settings.igdb_client_secret,
                "grant_type": "client_credentials",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("access_token") or "")
        if not token:
            raise RuntimeError("IGDB/Twitch hat kein Access-Token geliefert")
        IGDB_TOKEN = (token, now + int(payload.get("expires_in") or 3600))
        return token


def _igdb_post(endpoint: str, query: str, token: str) -> list[dict[str, Any]]:
    global IGDB_LAST_REQUEST
    response: httpx.Response | None = None
    for attempt in range(3):
        with IGDB_RATE_LOCK:
            wait = IGDB_REQUEST_INTERVAL - (time.monotonic() - IGDB_LAST_REQUEST)
            if wait > 0:
                time.sleep(wait)
            IGDB_LAST_REQUEST = time.monotonic()
        response = httpx.post(
            f"https://api.igdb.com/v4/{endpoint}",
            headers={
                "Client-ID": settings.igdb_client_id or "",
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            content=query,
            timeout=25,
        )
        if response.status_code != 429 and response.status_code < 500:
            break
        time.sleep(1.0 * (attempt + 1))
    assert response is not None
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"IGDB {endpoint} returned an unexpected response")
    return [item for item in payload if isinstance(item, dict)]


def _numeric_tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+", normalize_title(value)))


def _candidate_platform_families(candidate: dict[str, Any]) -> set[str]:
    families: set[str] = set()
    for platform in candidate.get("platforms") or []:
        if not isinstance(platform, dict):
            continue
        family = _mode_platform_family({"platform": platform})
        if family:
            families.add(family)
    return families


def _select_igdb_game(
    title: str,
    candidates: list[dict[str, Any]],
    platforms: list[Platform] | None = None,
    platform_game_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    normalized = normalize_title(title)
    compatible = [
        item
        for item in candidates
        if item.get("name") and _numeric_tokens(str(item["name"])) == _numeric_tokens(title)
    ]
    expected_families = _platform_families(platforms or [])
    expected_external_ids = {
        str(identifier).strip().casefold()
        for identifier in platform_game_ids or set()
        if str(identifier).strip()
    }

    def candidate_score(item: dict[str, Any]) -> float:
        title_score = fuzz.WRatio(normalized, normalize_title(str(item["name"])))
        external_ids = {
            str(external.get("uid") or "").strip().casefold()
            for external in item.get("external_games") or []
            if isinstance(external, dict) and external.get("uid")
        }
        external_bonus = 100 if expected_external_ids & external_ids else 0
        candidate_families = _candidate_platform_families(item)
        if not expected_families or not candidate_families:
            return title_score + external_bonus
        return title_score + external_bonus + (8 if expected_families & candidate_families else -8)

    best = max(compatible, key=candidate_score, default=None)
    if not best:
        return None
    score = fuzz.WRatio(normalized, normalize_title(str(best["name"])))
    return best if score >= 86 else None


def _platform_families(platforms: list[Platform]) -> set[str]:
    families: set[str] = set()
    for platform in platforms:
        if platform == Platform.xbox:
            families.add("xbox")
        elif platform == Platform.playstation:
            families.add("playstation")
        elif platform == Platform.nintendo:
            families.add("nintendo")
        else:
            families.add("pc")
    return families


def _mode_platform_family(mode: dict[str, Any]) -> str | None:
    platform = mode.get("platform")
    name = str(platform.get("name") if isinstance(platform, dict) else "").casefold()
    if not name:
        return None
    if "xbox" in name:
        return "xbox"
    if "playstation" in name:
        return "playstation"
    if any(value in name for value in ("nintendo", "switch", "wii")):
        return "nintendo"
    if any(value in name for value in ("pc", "windows", "linux", "mac")):
        return "pc"
    return None


def _relevant_multiplayer_modes(data: dict[str, Any], platforms: list[Platform]) -> list[dict[str, Any]]:
    modes = [item for item in data.get("multiplayer_modes") or [] if isinstance(item, dict)]
    families = _platform_families(platforms)
    matching = [mode for mode in modes if _mode_platform_family(mode) in families]
    return matching or modes


def _positive_max(modes: list[dict[str, Any]], field_name: str) -> int | None:
    values = []
    for mode in modes:
        try:
            value = int(mode.get(field_name) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append(value)
    return max(values, default=None)


def _igdb_record(
    title: str,
    platforms: list[Platform],
    token: str,
    platform_game_ids: set[str] | None = None,
) -> MetadataRecord | None:
    fields = (
        "id,name,summary,first_release_date,"
        "cover.image_id,genres.name,game_modes.name,platforms.name,external_games.uid,"
        "multiplayer_modes.campaigncoop,multiplayer_modes.dropin,"
        "multiplayer_modes.lancoop,multiplayer_modes.offlinecoop,"
        "multiplayer_modes.offlinecoopmax,multiplayer_modes.offlinemax,"
        "multiplayer_modes.onlinecoop,multiplayer_modes.onlinecoopmax,"
        "multiplayer_modes.onlinemax,multiplayer_modes.splitscreen,"
        "multiplayer_modes.splitscreenonline,multiplayer_modes.platform.name"
    )
    query = f"search {json.dumps(title)}; fields {fields}; limit 10;"
    data = _select_igdb_game(
        title,
        _igdb_post("games", query, token),
        platforms,
        platform_game_ids,
    )
    if not data:
        return None

    record = MetadataRecord(primary_source="igdb", external_id=str(data["id"]))
    record.set("is_game", True, "igdb")
    record.set("non_game_reason", None, "igdb")
    if data.get("summary"):
        record.set("description", str(data["summary"]), "igdb")
    if data.get("first_release_date"):
        record.set("release_date", datetime.utcfromtimestamp(int(data["first_release_date"])).date(), "igdb")
    cover = data.get("cover")
    if isinstance(cover, dict) and cover.get("image_id"):
        record.set(
            "cover_url",
            f"https://images.igdb.com/igdb/image/upload/t_cover_big/{cover['image_id']}.jpg",
            "igdb",
        )
    genres = sorted(
        {
            str(item["name"])
            for item in data.get("genres") or []
            if isinstance(item, dict) and item.get("name")
        }
    )
    if genres:
        record.set("genres", genres, "igdb")

    game_mode_names = {
        str(item.get("name") or "").casefold()
        for item in data.get("game_modes") or []
        if isinstance(item, dict)
    }
    modes = _relevant_multiplayer_modes(data, platforms)
    has_mode_data = bool(game_mode_names or modes)
    singleplayer = any("single player" in name for name in game_mode_names)
    multiplayer = bool(modes) or any(
        marker in name
        for name in game_mode_names
        for marker in ("multiplayer", "co-operative", "split screen", "battle royale", "massively multiplayer")
    )

    if has_mode_data:
        record.set("singleplayer", singleplayer, "igdb")
        record.set("multiplayer", multiplayer, "igdb")
        record.set("multiplayer_metadata_known", True, "igdb")

    only_singleplayer = singleplayer and not multiplayer
    detailed_modes_known = bool(modes) or only_singleplayer
    if detailed_modes_known:
        local_coop = any(bool(mode.get("offlinecoop")) for mode in modes)
        online_coop = any(bool(mode.get("onlinecoop")) for mode in modes)
        split_screen = any(bool(mode.get("splitscreen") or mode.get("splitscreenonline")) for mode in modes)
        record.set("local_coop", local_coop, "igdb")
        record.set("online_coop", online_coop, "igdb")
        record.set("lan", any(bool(mode.get("lancoop")) for mode in modes), "igdb")
        record.set("split_screen", split_screen, "igdb")
        record.set("campaign_coop", any(bool(mode.get("campaigncoop")) for mode in modes), "igdb")
        record.set("drop_in", any(bool(mode.get("dropin")) for mode in modes), "igdb")
        record.set("versus", any("multiplayer" in name for name in game_mode_names), "igdb")

    offline_max = _positive_max(modes, "offlinemax")
    online_max = _positive_max(modes, "onlinemax")
    offline_coop_max = _positive_max(modes, "offlinecoopmax")
    online_coop_max = _positive_max(modes, "onlinecoopmax")
    for name, value in (
        ("offline_max_players", offline_max),
        ("online_max_players", online_max),
        ("offline_coop_max_players", offline_coop_max),
        ("online_coop_max_players", online_coop_max),
    ):
        if value is not None or only_singleplayer:
            record.set(name, value, "igdb")

    maxima = [value for value in (offline_max, online_max, offline_coop_max, online_coop_max) if value]
    if maxima:
        record.set("min_players", 1 if singleplayer else 2, "igdb")
        record.set("max_players", max(maxima), "igdb")
        record.set("player_count_known", True, "igdb")
    elif only_singleplayer:
        record.set("min_players", 1, "igdb")
        record.set("max_players", 1, "igdb")
        record.set("player_count_known", True, "igdb")
    elif has_mode_data:
        record.set("player_count_known", False, "igdb")
    return record


def _rawg_record(title: str) -> MetadataRecord | None:
    if not settings.rawg_api_key:
        return None
    with httpx.Client(timeout=20) as client:
        search = _rawg_get(
            client,
            "https://api.rawg.io/api/games",
            params={"key": settings.rawg_api_key, "search": title, "search_exact": "true", "page_size": 5},
        )
        candidates = search.json().get("results") or []
        selected = _select_igdb_game(title, candidates)
        if not selected:
            return None
        slug = selected.get("slug") or selected.get("id")
        details = _rawg_get(
            client,
            f"https://api.rawg.io/api/games/{slug}",
            params={"key": settings.rawg_api_key},
        )
        data = details.json()

    record = MetadataRecord(primary_source="rawg", external_id=str(data.get("id") or slug))
    if data.get("description_raw") or data.get("description"):
        record.set("description", data.get("description_raw") or data.get("description"), "rawg")
    if data.get("background_image"):
        record.set("cover_url", data["background_image"], "rawg")
    if data.get("released"):
        record.set("release_date", data["released"], "rawg")
    genres = sorted(
        {
            str(item["name"])
            for item in data.get("genres") or []
            if isinstance(item, dict) and item.get("name")
        }
    )
    if genres:
        record.set("genres", genres, "rawg")

    tags = {
        str(item.get("name") or "").casefold()
        for item in data.get("tags") or []
        if isinstance(item, dict)
    }
    tag_fields = {
        "singleplayer": {"singleplayer", "single-player"},
        "multiplayer": {"multiplayer"},
        "local_coop": {"local co-op", "local coop"},
        "online_coop": {"online co-op", "online coop"},
        "lan": {"lan"},
        "split_screen": {"split screen", "split-screen"},
        "hotseat": {"hotseat", "hot seat"},
        "versus": {"pvp", "player versus player"},
    }
    found_feature = False
    for field_name, aliases in tag_fields.items():
        if tags & aliases:
            record.set(field_name, True, "rawg")
            found_feature = True
    if found_feature:
        record.set("multiplayer_metadata_known", True, "rawg")
    return record


def _rawg_get(client: httpx.Client, url: str, params: dict[str, Any]) -> httpx.Response:
    global RAWG_LAST_REQUEST
    response: httpx.Response | None = None
    for attempt in range(3):
        with RAWG_RATE_LOCK:
            wait = RAWG_REQUEST_INTERVAL - (time.monotonic() - RAWG_LAST_REQUEST)
            if wait > 0:
                time.sleep(wait)
            RAWG_LAST_REQUEST = time.monotonic()
        response = client.get(url, params=params)
        if response.status_code != 429 and response.status_code < 500:
            break
        time.sleep(1.0 * (attempt + 1))
    assert response is not None
    if response.is_error:
        raise RuntimeError(f"RAWG request failed with HTTP {response.status_code}")
    return response


def _rawg_availability() -> tuple[bool, str | None]:
    if not settings.rawg_api_key:
        return False, None
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(
                "https://api.rawg.io/api/games",
                params={
                    "key": settings.rawg_api_key,
                    "search": "Portal",
                    "page_size": 1,
                },
            )
    except Exception:
        return False, "nicht erreichbar"
    if response.status_code in (401, 403):
        return False, f"nicht verfügbar (HTTP {response.status_code}; Monatskontingent oder Schlüssel prüfen)"
    if response.is_error:
        return False, f"nicht verfügbar (HTTP {response.status_code})"
    return True, None


def _needs_rawg(record: MetadataRecord | None) -> bool:
    if not record:
        return True
    important = {
        "description",
        "cover_url",
        "genres",
        "multiplayer_metadata_known",
        "player_count_known",
        "hotseat",
        "shared_screen",
    }
    return not important.issubset(record.known_fields)


def _merge_records(primary: MetadataRecord | None, fallback: MetadataRecord | None) -> MetadataRecord | None:
    if not primary:
        return fallback
    if not fallback:
        return primary
    merged = MetadataRecord(
        values=dict(fallback.values),
        known_fields=set(fallback.known_fields),
        sources=dict(fallback.sources),
        primary_source=primary.primary_source,
        external_id=primary.external_id,
    )
    for name in primary.known_fields:
        merged.set(name, primary.values.get(name), primary.sources.get(name, "igdb"))
    return merged


def _fetch_game_metadata(
    job: tuple[int, str, list[Platform], set[str], str, bool],
) -> tuple[int, MetadataRecord | None, bool, bool]:
    game_id, title, platforms, platform_game_ids, token, rawg_enabled = job
    igdb_failed = False
    rawg_failed = False
    try:
        igdb = _igdb_record(title, platforms, token, platform_game_ids)
    except Exception as exc:
        igdb = None
        igdb_failed = True
        LOGGER.warning("IGDB metadata failed for %s: %s", title, exc)
    rawg = None
    if _needs_rawg(igdb) and rawg_enabled:
        try:
            rawg = _rawg_record(title)
        except Exception as exc:
            rawg_failed = True
            LOGGER.warning("RAWG metadata failed for %s: %s", title, exc)
    return game_id, _merge_records(igdb, rawg), igdb_failed, rawg_failed


def _metadata_snapshot(game: Game) -> tuple[Any, ...]:
    return (
        game.description,
        game.cover_url,
        game.release_date,
        tuple(game.genres or []),
        game.is_game,
        game.non_game_reason,
        *(getattr(game, field) for field in sorted(FEATURE_FIELDS)),
        game.metadata_source,
        game.metadata_external_id,
        tuple(sorted((game.metadata_sources or {}).items())),
    )


def _apply_metadata_record(game: Game, record: MetadataRecord) -> bool:
    before = _metadata_snapshot(game)
    if record.values.get("multiplayer_metadata_known"):
        for unsupported_field in ("hotseat", "shared_screen"):
            if unsupported_field not in record.known_fields:
                setattr(game, unsupported_field, False)
    for name in record.known_fields:
        value = record.values.get(name)
        if name == "genres":
            value = sanitize_genres(value)
        if name == "release_date" and isinstance(value, str):
            try:
                value = datetime.fromisoformat(value).date()
            except ValueError:
                continue
        setattr(game, name, value)
    game.metadata_source = record.primary_source
    game.metadata_external_id = record.external_id
    game.metadata_sources = dict(record.sources)
    game.metadata_updated_at = datetime.utcnow()
    return _metadata_snapshot(game) != before


def _apply_content_classification(
    game: Game,
    record: MetadataRecord | None,
) -> bool:
    before = (game.is_game, game.non_game_reason, dict(game.metadata_sources or {}))
    record_genres = record.values.get("genres", []) if record else []
    classification = classify_game(
        game.title,
        [*(game.genres or []), *(record_genres or [])],
    )
    if classification.is_game is False:
        if record:
            record.set("is_game", False, "classification")
            record.set("non_game_reason", classification.reason, "classification")
        else:
            game.is_game = False
            game.non_game_reason = classification.reason
            sources = dict(game.metadata_sources or {})
            sources["is_game"] = "classification"
            sources["non_game_reason"] = "classification"
            game.metadata_sources = sources
            game.metadata_updated_at = datetime.utcnow()
    return before != (game.is_game, game.non_game_reason, dict(game.metadata_sources or {}))


def enrich_all_game_metadata(
    db: Session,
    progress_callback: Callable[[int, int, int, int], None] | None = None,
    game_ids: set[int] | None = None,
) -> MetadataSyncResult:
    token = _igdb_access_token()
    result = MetadataSyncResult()
    rawg_enabled, rawg_unavailable_reason = _rawg_availability()
    result.rawg_unavailable_reason = rawg_unavailable_reason
    if rawg_unavailable_reason:
        result.rawg_errors = 1
        result.failed_games = 1
        LOGGER.warning("RAWG metadata disabled for this run: %s", rawg_unavailable_reason)
    games_query = select(Game).options(selectinload(Game.mappings)).order_by(Game.title)
    if game_ids is not None:
        games_query = games_query.where(Game.id.in_(game_ids))
    games = db.scalars(games_query).unique().all()
    result.scanned_games = len(games)
    games_by_id = {game.id: game for game in games}
    jobs = [
        (
            game.id,
            game.title,
            sorted({mapping.platform for mapping in game.mappings}),
            {str(mapping.platform_game_id) for mapping in game.mappings},
            token,
            rawg_enabled,
        )
        for game in games
    ]
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="metadata-fetch") as executor:
        fetched = executor.map(_fetch_game_metadata, jobs)
        for scanned, (game_id, record, igdb_failed, rawg_failed) in enumerate(fetched, start=1):
            game = games_by_id[game_id]
            was_game = game.is_game
            result.igdb_errors += int(igdb_failed)
            result.rawg_errors += int(rawg_failed)
            result.failed_games += int(igdb_failed or rawg_failed)
            cleaned_genres = sanitize_genres(game.genres)
            genres_changed = cleaned_genres != (game.genres or [])
            if genres_changed:
                game.genres = cleaned_genres
            classification_changed = _apply_content_classification(game, record)
            metadata_changed = bool(record and _apply_metadata_record(game, record))
            if was_game and not game.is_game:
                result.excluded_games += 1
            if genres_changed or classification_changed or metadata_changed:
                result.updated_games += 1
                db.flush()
            if scanned % 25 == 0:
                db.commit()
                if progress_callback:
                    progress_callback(scanned, result.updated_games, result.igdb_errors, result.rawg_errors)
    db.commit()
    if progress_callback:
        progress_callback(result.scanned_games, result.updated_games, result.igdb_errors, result.rawg_errors)
    if result.failed_games:
        result.message = f"metadata sync completed with {result.failed_games} source errors"
    return result
