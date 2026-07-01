from __future__ import annotations

from datetime import datetime
from threading import Lock

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Game, Ownership, Platform, PlatformGameMapping, SyncRun
from app.services.import_providers import ImportedGame, PROVIDERS
from app.services.genre_utils import sanitize_genres
from app.services.normalization import normalize_title

SYNC_LOCK = Lock()
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


def _player_count(value: int | None, default: int = 1) -> int:
    if value in (None, ""):
        return default
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _sequence_tokens(normalized_title: str) -> tuple[int, ...]:
    values: list[int] = []
    for token in normalized_title.split():
        if token.isdigit():
            values.append(int(token))
        elif token in ROMAN_NUMERALS:
            values.append(ROMAN_NUMERALS[token])
    return tuple(values)


def _compatible_for_fuzzy_match(existing_normalized: str, imported_normalized: str) -> bool:
    if existing_normalized == imported_normalized:
        return True
    if _sequence_tokens(existing_normalized) != _sequence_tokens(imported_normalized):
        return False
    existing_tokens = set(existing_normalized.split())
    imported_tokens = set(imported_normalized.split())
    if existing_tokens < imported_tokens or imported_tokens < existing_tokens:
        return False
    return max(
        fuzz.ratio(existing_normalized, imported_normalized),
        fuzz.token_sort_ratio(existing_normalized, imported_normalized),
    ) >= 92


def _merge_game_metadata(game: Game, imported: ImportedGame) -> None:
    game.description = game.description or imported.description
    game.cover_url = game.cover_url or imported.cover_url
    game.release_date = game.release_date or imported.release_date
    game.genres = sanitize_genres([*(game.genres or []), *(imported.genres or [])])
    if imported.is_free is not None:
        game.is_free = imported.is_free
    feature_fields = [
        "singleplayer",
        "multiplayer",
        "lan",
        "local_coop",
        "online_coop",
        "hotseat",
        "split_screen",
        "shared_screen",
    ]
    authoritative_fields = set(game.metadata_sources or {})
    if imported.feature_metadata_known:
        for field in feature_fields:
            if field not in authoritative_fields:
                setattr(game, field, bool(getattr(imported, field)))
        if "multiplayer_metadata_known" not in authoritative_fields:
            game.multiplayer_metadata_known = True
    else:
        for field in feature_fields:
            if field not in authoritative_fields:
                setattr(game, field, bool(getattr(game, field) or getattr(imported, field)))

    if imported.player_count_known:
        imported_min_players = _player_count(imported.min_players)
        imported_max_players = max(imported_min_players, _player_count(imported.max_players, imported_min_players))
        if "min_players" not in authoritative_fields:
            game.min_players = imported_min_players
        if "max_players" not in authoritative_fields:
            game.max_players = imported_max_players
        if "player_count_known" not in authoritative_fields:
            game.player_count_known = True


def _is_numeric_steam_app_id(platform: str, platform_game_id: str) -> bool:
    return str(platform) == Platform.steam and str(platform_game_id).isdigit()


def _steam_mapping_conflicts(db: Session, imported: ImportedGame) -> list[int]:
    rows = db.execute(
        select(PlatformGameMapping.game_id, PlatformGameMapping.platform_game_id).where(
            PlatformGameMapping.platform == Platform.steam,
            PlatformGameMapping.platform_game_id != imported.platform_game_id,
        )
    )
    return [game_id for game_id, platform_game_id in rows if str(platform_game_id).isdigit()]


def _find_or_create_game(
    db: Session,
    platform: str,
    imported: ImportedGame,
    exclude_game_id: int | None = None,
) -> Game:
    normalized = imported.normalized_title
    exact_query = select(Game).where(Game.normalized_title == normalized)
    if _is_numeric_steam_app_id(platform, imported.platform_game_id):
        exact_query = exact_query.where(Game.id.not_in(_steam_mapping_conflicts(db, imported)))
    if exclude_game_id is not None:
        exact_query = exact_query.where(Game.id != exclude_game_id)
    exact = db.scalar(exact_query)
    if exact:
        return exact

    candidates_query = select(Game)
    if _is_numeric_steam_app_id(platform, imported.platform_game_id):
        candidates_query = candidates_query.where(Game.id.not_in(_steam_mapping_conflicts(db, imported)))
    if exclude_game_id is not None:
        candidates_query = candidates_query.where(Game.id != exclude_game_id)
    candidates = [
        game
        for game in db.scalars(candidates_query).all()
        if _compatible_for_fuzzy_match(game.normalized_title, normalized)
    ]
    best = max(
        candidates,
        key=lambda item: max(
            fuzz.ratio(item.normalized_title, normalized),
            fuzz.token_sort_ratio(item.normalized_title, normalized),
        ),
        default=None,
    )
    if best and _compatible_for_fuzzy_match(best.normalized_title, normalized):
        return best

    game = Game(title=imported.title, normalized_title=normalized)
    db.add(game)
    db.flush()
    return game


def resolve_game(db: Session, platform: str, imported: ImportedGame) -> Game:
    normalized = imported.normalized_title
    mapping = db.scalar(
        select(PlatformGameMapping).where(
            PlatformGameMapping.platform == platform,
            PlatformGameMapping.platform_game_id == imported.platform_game_id,
        )
    )
    if mapping:
        mapped_game = mapping.game
        primary_steam_mapping_id = None
        if _is_numeric_steam_app_id(platform, imported.platform_game_id):
            numeric_mapping_ids = [
                mapping_id
                for mapping_id, platform_game_id in db.execute(
                    select(PlatformGameMapping.id, PlatformGameMapping.platform_game_id).where(
                        PlatformGameMapping.game_id == mapping.game_id,
                        PlatformGameMapping.platform == Platform.steam,
                    )
                )
                if str(platform_game_id).isdigit()
            ]
            if numeric_mapping_ids:
                primary_steam_mapping_id = min(numeric_mapping_ids)
        steam_id_collision = primary_steam_mapping_id is not None and mapping.id != primary_steam_mapping_id
        if steam_id_collision or not _compatible_for_fuzzy_match(mapped_game.normalized_title, normalized):
            mapped_game = _find_or_create_game(db, platform, imported, exclude_game_id=mapping.game_id)
            mapping.game_id = mapped_game.id
            mapping.platform_title = imported.title
            mapping.normalized_title = normalized
            db.flush()
        _merge_game_metadata(mapped_game, imported)
        return mapped_game

    game = _find_or_create_game(db, platform, imported)
    _merge_game_metadata(game, imported)
    db.add(
        PlatformGameMapping(
            game_id=game.id,
            platform=platform,
            platform_game_id=imported.platform_game_id,
            platform_title=imported.title,
            normalized_title=normalized,
        )
    )
    db.flush()
    return game


def _pending_ownership(
    db: Session,
    account: Account,
    game: Game,
    platform: Platform | str,
) -> Ownership | None:
    for item in db.new:
        if not isinstance(item, Ownership):
            continue
        if (
            item.participant_id == account.participant_id
            and item.game_id == game.id
            and item.platform == platform
        ):
            return item
    return None


def upsert_ownership(db: Session, account: Account, game: Game, imported: ImportedGame) -> Ownership:
    ownership_platform = imported.ownership_platform or account.platform
    ownership = _pending_ownership(db, account, game, ownership_platform)
    if ownership is None:
        ownership = db.scalar(
            select(Ownership).where(
                Ownership.participant_id == account.participant_id,
                Ownership.game_id == game.id,
                Ownership.platform == ownership_platform,
            )
        )
    if ownership is None:
        ownership = Ownership(
            participant_id=account.participant_id,
            account_id=account.id,
            game_id=game.id,
            platform=ownership_platform,
        )
        db.add(ownership)
    elif imported.ownership_platform is not None:
        # A direct provider supersedes a synthetic Playnite ownership while
        # retaining the participant/game/platform uniqueness contract.
        ownership.account_id = account.id
    current_playtime = ownership.playtime_minutes or 0
    if imported.playtime_minutes > 0 or current_playtime <= 0:
        ownership.playtime_minutes = imported.playtime_minutes
    ownership.owned_since = imported.owned_since or ownership.owned_since
    ownership.last_seen = datetime.utcnow()
    return ownership


def _reconcile_account_ownerships(
    db: Session,
    account: Account,
    imported_game_ids: set[int],
    platform: Platform | str | None = None,
) -> None:
    ownership_platform = platform or account.platform
    stmt = (
        select(Ownership)
        .join(Ownership.game)
        .where(
            Ownership.account_id == account.id,
            Ownership.platform == ownership_platform,
            Game.is_free == False,  # noqa: E712
        )
    )
    if imported_game_ids:
        stmt = stmt.where(Ownership.game_id.not_in(imported_game_ids))
    for ownership in db.scalars(stmt).all():
        db.delete(ownership)


def _sync_account_unlocked(db: Session, account_id: int) -> SyncRun:
    account = db.get(Account, account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")
    run = SyncRun(account_id=account.id)
    db.add(run)
    db.flush()
    try:
        provider = PROVIDERS[account.platform]
        imported_games = provider.sync_account(account)
        imported_game_ids_by_platform: dict[Platform | str, set[int]] = {}
        for imported in imported_games:
            mapping_platform = imported.mapping_platform or account.platform
            ownership_platform = imported.ownership_platform or account.platform
            game = resolve_game(db, mapping_platform, imported)
            upsert_ownership(db, account, game, imported)
            imported_game_ids_by_platform.setdefault(ownership_platform, set()).add(game.id)
        authoritative_platforms: set[Platform | str] = set(
            getattr(provider, "authoritative_ownership_platforms", set())
        )
        if getattr(provider, "authoritative_library", False):
            authoritative_platforms.add(account.platform)
        for platform in authoritative_platforms:
            _reconcile_account_ownerships(
                db,
                account,
                imported_game_ids_by_platform.get(platform, set()),
                platform,
            )
        account.last_successful_sync = datetime.utcnow()
        account.last_error = None
        run.success = True
        run.imported_games = len(imported_games)
        run.message = "sync completed"
        run.finished_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        message = str(exc)
        db.rollback()
        account = db.get(Account, account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found") from exc
        account.last_error = message
        run = SyncRun(
            account_id=account.id,
            finished_at=datetime.utcnow(),
            success=False,
            message=message,
            imported_games=0,
        )
        db.add(run)
        db.commit()
    db.refresh(run)
    return run


def sync_account(db: Session, account_id: int) -> SyncRun:
    with SYNC_LOCK:
        return _sync_account_unlocked(db, account_id)

