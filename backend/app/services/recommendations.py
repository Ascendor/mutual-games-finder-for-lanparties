from __future__ import annotations

from statistics import median
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Game, Ownership, Participant
from app.schemas import RecommendationRead

RecommendationMode = Literal["common", "coop", "lan", "popular", "group_size", "new"]


def _score(game: Game, owner_count: int, participant_count: int, total: int, median_playtime: float, mode: RecommendationMode, group_size: int | None) -> float:
    coverage = owner_count / participant_count if participant_count else 0
    playtime = min(total, 20000) / 100
    typical_playtime = min(median_playtime, 5000) / 100
    capacity_fit = 0
    target_size = group_size or participant_count
    if target_size and game.player_count_known and game.min_players <= target_size <= game.max_players:
        capacity_fit = 300
    if mode == "common":
        return typical_playtime * 2 + playtime + capacity_fit + (150 if game.multiplayer else 0)
    if mode == "coop":
        return capacity_fit + playtime + (500 if game.online_coop else 0) + (250 if game.local_coop else 0) + (100 if game.shared_screen or game.split_screen else 0)
    if mode == "lan":
        return owner_count * 1200 + capacity_fit + playtime + (300 if game.lan else 0)
    if mode == "group_size":
        return owner_count * 1000 + capacity_fit + playtime + (150 if game.multiplayer or game.lan or game.online_coop else 0)
    if mode == "new":
        freshness = max(0, 5000 - median_playtime) / 10
        return owner_count * 1500 + freshness + capacity_fit - min(total, 20000) / 200
    return coverage * 5000 + playtime + typical_playtime


def _sort_key(item: RecommendationRead, mode: RecommendationMode) -> tuple:
    game = item.game
    if mode == "common":
        return (item.median_playtime_minutes, item.total_playtime_minutes, game.max_players, game.title.casefold())
    if mode == "coop":
        return (game.online_coop, game.local_coop, game.max_players, item.total_playtime_minutes, game.title.casefold())
    if mode == "lan":
        return (item.owner_count, game.max_players, item.total_playtime_minutes, game.title.casefold())
    if mode == "group_size":
        return (item.owner_count, item.total_playtime_minutes, game.max_players, game.title.casefold())
    if mode == "new":
        return (item.owner_count, -item.median_playtime_minutes, -item.average_playtime_minutes, game.max_players, game.title.casefold())
    return (item.owner_count, item.median_playtime_minutes, item.total_playtime_minutes, game.title.casefold())


def _recommendations_for_participants(
    db: Session,
    participant_ids: list[int],
    mode: RecommendationMode,
    require_all: bool = False,
    coop: bool = False,
    lan: bool = False,
    group_size: int | None = None,
) -> list[RecommendationRead]:
    participant_ids = sorted(set(participant_ids))
    if not participant_ids:
        return []
    query = (
        select(Game)
        .join(Ownership)
        .options(selectinload(Game.ownerships).selectinload(Ownership.participant))
        .group_by(Game.id)
    )
    if coop:
        query = query.where((Game.local_coop == True) | (Game.online_coop == True) | (Game.shared_screen == True) | (Game.split_screen == True))  # noqa: E712
    if lan:
        query = query.where(Game.lan == True)  # noqa: E712
    if group_size is not None:
        query = query.where(
            (Game.player_count_known == False)  # noqa: E712
            | ((Game.min_players <= group_size) & (Game.max_players >= group_size))
        )
        if group_size > 1:
            query = query.where(
                (Game.multiplayer == True)  # noqa: E712
                | (Game.lan == True)  # noqa: E712
                | (Game.local_coop == True)  # noqa: E712
                | (Game.online_coop == True)  # noqa: E712
            )
    query = query.where(Ownership.participant_id.in_(participant_ids))
    if require_all:
        query = query.having(func.count(func.distinct(Ownership.participant_id)) == len(participant_ids))
    games = db.scalars(query).unique().all()
    recs = []
    for game in games:
        relevant = [own for own in game.ownerships if own.participant_id in participant_ids]
        owner_ids = {own.participant_id for own in relevant}
        total = sum(own.playtime_minutes for own in relevant)
        owner_count = len(owner_ids)
        playtime_by_owner = {owner_id: 0 for owner_id in owner_ids}
        for ownership in relevant:
            playtime_by_owner[ownership.participant_id] += ownership.playtime_minutes
        median_playtime = float(median(playtime_by_owner.values())) if playtime_by_owner else 0.0
        average_playtime = total / owner_count if owner_count else 0.0
        recs.append(
            RecommendationRead(
                game=game,
                owner_count=owner_count,
                total_playtime_minutes=total,
                average_playtime_minutes=average_playtime,
                median_playtime_minutes=median_playtime,
                score=_score(game, owner_count, len(participant_ids), total, median_playtime, mode, group_size),
                platforms=sorted({own.platform for own in relevant}),
                owners=sorted({own.participant for own in relevant}, key=lambda p: p.nickname),
            )
        )
    return sorted(recs, key=lambda item: _sort_key(item, mode), reverse=True)


def present_participant_ids(db: Session) -> list[int]:
    return list(db.scalars(select(Participant.id).where(Participant.present == True)))  # noqa: E712


def find_common_games(db: Session, players: list[int]) -> list[RecommendationRead]:
    return _recommendations_for_participants(db, players, mode="common", require_all=True)


def find_common_coop_games(db: Session, players: list[int]) -> list[RecommendationRead]:
    return _recommendations_for_participants(db, players, mode="coop", require_all=True, coop=True)


def find_common_lan_games(db: Session, players: list[int]) -> list[RecommendationRead]:
    return _recommendations_for_participants(db, players, mode="lan", require_all=True, lan=True)


def find_games_for_present_players(db: Session) -> list[RecommendationRead]:
    return find_common_games(db, present_participant_ids(db))


def find_best_lan_games(db: Session) -> list[RecommendationRead]:
    present = present_participant_ids(db)
    return _recommendations_for_participants(db, present, mode="lan", require_all=False, lan=True, group_size=len(present) or None)


def find_most_popular_games(db: Session) -> list[RecommendationRead]:
    participant_ids = list(db.scalars(select(Participant.id)))
    return _recommendations_for_participants(db, participant_ids, mode="popular", require_all=False)


def find_new_for_group_games(db: Session, players: list[int] | None = None) -> list[RecommendationRead]:
    participant_ids = players or present_participant_ids(db)
    return _recommendations_for_participants(db, participant_ids, mode="new", require_all=False)


def find_games_for_group_size(db: Session, size: int) -> list[RecommendationRead]:
    return _recommendations_for_participants(db, present_participant_ids(db), mode="group_size", require_all=False, group_size=size)
