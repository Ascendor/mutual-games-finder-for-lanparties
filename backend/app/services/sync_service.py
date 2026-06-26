from __future__ import annotations

import re
from datetime import datetime
from threading import Lock

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Game, Ownership, PlatformGameMapping, SyncRun
from app.services.import_providers import ImportedGame, PROVIDERS
from app.services.normalization import normalize_title

MATCH_THRESHOLD = 88
SYNC_LOCK = Lock()


def _numeric_tokens(normalized_title: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+", normalized_title))


def _compatible_for_fuzzy_match(existing_normalized: str, imported_normalized: str) -> bool:
    return _numeric_tokens(existing_normalized) == _numeric_tokens(imported_normalized)


def _merge_game_metadata(game: Game, imported: ImportedGame) -> None:
    game.description = game.description or imported.description
    game.cover_url = game.cover_url or imported.cover_url
    game.release_date = game.release_date or imported.release_date
    game.genres = sorted(set(game.genres or []) | set(imported.genres or []))
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
    if imported.feature_metadata_known:
        for field in feature_fields:
            setattr(game, field, bool(getattr(imported, field)))
        game.min_players = imported.min_players or 1
        game.max_players = imported.max_players or 1
        return
    for field in feature_fields:
        setattr(game, field, bool(getattr(game, field) or getattr(imported, field)))
    game.min_players = min(game.min_players or imported.min_players, imported.min_players or 1)
    game.max_players = max(game.max_players or imported.max_players, imported.max_players or 1)


def _find_or_create_game(db: Session, imported: ImportedGame, exclude_game_id: int | None = None) -> Game:
    normalized = imported.normalized_title
    exact_query = select(Game).where(Game.normalized_title == normalized)
    if exclude_game_id is not None:
        exact_query = exact_query.where(Game.id != exclude_game_id)
    exact = db.scalar(exact_query)
    if exact:
        return exact

    candidates_query = select(Game)
    if exclude_game_id is not None:
        candidates_query = candidates_query.where(Game.id != exclude_game_id)
    candidates = [
        game
        for game in db.scalars(candidates_query).all()
        if _compatible_for_fuzzy_match(game.normalized_title, normalized)
    ]
    best = max(candidates, key=lambda item: fuzz.token_set_ratio(item.normalized_title, normalized), default=None)
    if best and fuzz.token_set_ratio(best.normalized_title, normalized) >= MATCH_THRESHOLD:
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
        if mapped_game.normalized_title != normalized and not _compatible_for_fuzzy_match(mapped_game.normalized_title, normalized):
            mapped_game = _find_or_create_game(db, imported, exclude_game_id=mapping.game_id)
            mapping.game_id = mapped_game.id
            mapping.platform_title = imported.title
            mapping.normalized_title = normalized
            db.flush()
        _merge_game_metadata(mapped_game, imported)
        return mapped_game

    game = _find_or_create_game(db, imported)
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


def _pending_ownership(db: Session, account: Account, game: Game) -> Ownership | None:
    for item in db.new:
        if not isinstance(item, Ownership):
            continue
        if (
            item.participant_id == account.participant_id
            and item.game_id == game.id
            and item.platform == account.platform
        ):
            return item
    return None


def upsert_ownership(db: Session, account: Account, game: Game, imported: ImportedGame) -> Ownership:
    ownership = _pending_ownership(db, account, game)
    if ownership is None:
        ownership = db.scalar(
            select(Ownership).where(
                Ownership.participant_id == account.participant_id,
                Ownership.game_id == game.id,
                Ownership.platform == account.platform,
            )
        )
    if ownership is None:
        ownership = Ownership(
            participant_id=account.participant_id,
            account_id=account.id,
            game_id=game.id,
            platform=account.platform,
        )
        db.add(ownership)
    ownership.playtime_minutes = imported.playtime_minutes
    ownership.owned_since = imported.owned_since or ownership.owned_since
    ownership.last_seen = datetime.utcnow()
    return ownership


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
        for imported in imported_games:
            game = resolve_game(db, account.platform, imported)
            upsert_ownership(db, account, game, imported)
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

