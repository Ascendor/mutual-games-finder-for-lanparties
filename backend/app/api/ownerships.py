from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, distinct, func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Account, Game, ManualOwnership, Ownership, Participant, PlatformGameMapping
from app.schemas import (
    ManualOwnershipCreate,
    ManualOwnershipGameOptionRead,
    ManualOwnershipRead,
    OwnershipCreate,
    OwnershipRead,
    PersonalGamePageRead,
    RecentAcquisitionRead,
)
from app.services.normalization import normalize_title
from app.services.genre_utils import sanitize_genres

router = APIRouter()

PERSONAL_GAME_MODE_FIELDS = {
    "singleplayer": Game.singleplayer,
    "multiplayer": Game.multiplayer,
    "lan": Game.lan,
    "local_coop": Game.local_coop,
    "online_coop": Game.online_coop,
    "campaign_coop": Game.campaign_coop,
    "versus": Game.versus,
    "hotseat": Game.hotseat,
    "shared_screen": Game.shared_screen,
}


@router.get("", response_model=list[OwnershipRead])
def list_ownerships(db: Session = Depends(get_db)):
    return db.scalars(select(Ownership)).all()


@router.post("", response_model=OwnershipRead, status_code=201)
def create_ownership(payload: OwnershipCreate, db: Session = Depends(get_db)):
    existing_first_seen = db.execute(
        select(Ownership.first_seen_at, Ownership.first_seen_is_baseline)
        .where(
            Ownership.participant_id == payload.participant_id,
            Ownership.game_id == payload.game_id,
        )
        .order_by(Ownership.first_seen_at.asc().nulls_last())
        .limit(1)
    ).first()
    ownership = Ownership(
        **payload.model_dump(),
        owned_since_source="manual" if payload.owned_since else None,
        first_seen_at=existing_first_seen[0] if existing_first_seen else datetime.utcnow(),
        first_seen_is_baseline=existing_first_seen[1] if existing_first_seen else False,
        last_seen=datetime.utcnow(),
    )
    db.add(ownership)
    db.commit()
    db.refresh(ownership)
    return ownership


@router.get("/recent-acquisitions", response_model=list[RecentAcquisitionRead])
def recent_acquisitions(
    days: Annotated[int, Query(ge=1, le=3650)] = 90,
    limit: Annotated[int, Query(ge=1, le=250)] = 100,
    db: Session = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    library_dates = (
        select(
            Ownership.participant_id.label("participant_id"),
            Ownership.game_id.label("game_id"),
            func.min(
                case(
                    (
                        Ownership.owned_since_source.is_not(None),
                        Ownership.owned_since,
                    ),
                    else_=None,
                )
            ).label("owned_since"),
            func.min(
                case(
                    (
                        Ownership.first_seen_is_baseline == False,  # noqa: E712
                        Ownership.first_seen_at,
                    ),
                    else_=None,
                )
            ).label("first_seen_at"),
        )
        .join(Game, Game.id == Ownership.game_id)
        .where(
            Game.is_game == True,  # noqa: E712
        )
        .group_by(Ownership.participant_id, Ownership.game_id)
        .subquery()
    )
    occurred_at = func.coalesce(library_dates.c.owned_since, library_dates.c.first_seen_at)

    rows = db.execute(
        select(
            Participant,
            Game,
            occurred_at.label("occurred_at"),
            library_dates.c.owned_since,
        )
        .join(library_dates, library_dates.c.participant_id == Participant.id)
        .join(Game, Game.id == library_dates.c.game_id)
        .where(occurred_at >= cutoff)
        .order_by(occurred_at.desc(), func.lower(Participant.nickname), func.lower(Game.title))
        .limit(limit)
    ).all()
    pairs = [(participant.id, game.id) for participant, game, _occurred_at, _owned_since in rows]
    platforms_by_pair: dict[tuple[int, int], set] = {pair: set() for pair in pairs}
    if pairs:
        ownership_filters = [
            and_(Ownership.participant_id == participant_id, Ownership.game_id == game_id)
            for participant_id, game_id in pairs
        ]
        for participant_id, game_id, platform in db.execute(
            select(Ownership.participant_id, Ownership.game_id, Ownership.platform)
            .where(or_(*ownership_filters))
            .order_by(Ownership.platform)
        ):
            platforms_by_pair[(participant_id, game_id)].add(platform)

    return [
        {
            "participant": participant,
            "game": game,
            "occurred_at": occurred_at_value,
            "date_kind": "acquired" if owned_since is not None else "first_seen",
            "platforms": sorted(platforms_by_pair.get((participant.id, game.id), set()), key=str),
        }
        for participant, game, occurred_at_value, owned_since in rows
    ]


@router.get("/participants/{participant_id}/games", response_model=PersonalGamePageRead)
def participant_games(
    participant_id: int,
    search: str = "",
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 50,
    sort_by: str = "title",
    sort_desc: bool = False,
    db: Session = Depends(get_db),
    platforms: Annotated[list[str] | None, Query()] = None,
    genres: Annotated[list[str] | None, Query()] = None,
    modes: Annotated[list[str] | None, Query()] = None,
    player_count: Annotated[int | None, Query(ge=1, le=128)] = None,
):
    if not db.get(Participant, participant_id):
        raise HTTPException(404, "participant not found")

    selected_platforms = [platform for platform in platforms or [] if platform.strip()]
    ownership_filters = [Ownership.participant_id == participant_id]
    if selected_platforms:
        ownership_filters.append(Ownership.platform.in_(selected_platforms))

    matching_game_ids = (
        select(Ownership.game_id)
        .where(*ownership_filters)
        .group_by(Ownership.game_id)
        .subquery()
    )
    ownership_totals = (
        select(
            Ownership.game_id.label("game_id"),
            func.coalesce(func.sum(Ownership.playtime_minutes), 0).label("total_playtime_minutes"),
            func.min(Ownership.platform).label("first_platform"),
        )
        .where(Ownership.participant_id == participant_id)
        .where(Ownership.game_id.in_(select(matching_game_ids.c.game_id)))
        .group_by(Ownership.game_id)
        .subquery()
    )
    filters = [Game.is_game == True]  # noqa: E712
    normalized_search = normalize_title(search)
    if normalized_search:
        filters.append(Game.normalized_title.contains(normalized_search))
    selected_genres = [genre for genre in genres or [] if genre.strip()]
    if selected_genres:
        filters.append(
            or_(
                *(
                    Game.genres.contains([genre])
                    for genre in selected_genres
                )
            )
        )
    for mode in [mode for mode in modes or [] if mode.strip()]:
        if mode == "coop":
            filters.append(
                (Game.local_coop == True)  # noqa: E712
                | (Game.online_coop == True)  # noqa: E712
                | (Game.campaign_coop == True)  # noqa: E712
            )
        elif mode == "split_screen":
            filters.append(
                (Game.split_screen == True) | (Game.shared_screen == True)  # noqa: E712
            )
        elif mode == "free":
            filters.append(Game.is_free == True)  # noqa: E712
        elif mode in PERSONAL_GAME_MODE_FIELDS:
            filters.append(PERSONAL_GAME_MODE_FIELDS[mode] == True)  # noqa: E712
    if player_count is not None:
        filters.extend(
            [
                Game.player_count_known == True,  # noqa: E712
                Game.min_players <= player_count,
                Game.max_players >= player_count,
            ]
        )

    available_platforms = db.scalars(
        select(Ownership.platform)
        .join(Game, Game.id == Ownership.game_id)
        .where(
            Ownership.participant_id == participant_id,
            Game.is_game == True,  # noqa: E712
        )
        .distinct()
    ).all()
    available_platforms = sorted(available_platforms, key=lambda platform: str(platform).lower())
    available_genres = sanitize_genres(
        genre
        for values in db.scalars(
            select(Game.genres)
            .join(Ownership, Ownership.game_id == Game.id)
            .where(
                Ownership.participant_id == participant_id,
                Game.is_game == True,  # noqa: E712
            )
        )
        for genre in (values or [])
    )

    total = db.scalar(
        select(func.count())
        .select_from(Game)
        .join(ownership_totals, ownership_totals.c.game_id == Game.id)
        .where(*filters)
    ) or 0

    order_expression = {
        "title": func.lower(Game.title),
        "platform": func.lower(ownership_totals.c.first_platform),
        "playtime_minutes": ownership_totals.c.total_playtime_minutes,
    }.get(sort_by, func.lower(Game.title))
    if sort_desc:
        order_expression = order_expression.desc()

    rows = db.execute(
        select(Game, ownership_totals.c.total_playtime_minutes)
        .join(ownership_totals, ownership_totals.c.game_id == Game.id)
        .where(*filters)
        .order_by(order_expression, func.lower(Game.title), Game.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    games = [game for game, _total_playtime in rows]
    game_ids = [game.id for game in games]

    ownerships_by_game: dict[int, list[dict]] = {game_id: [] for game_id in game_ids}
    if game_ids:
        for ownership, account in db.execute(
            select(Ownership, Account)
            .outerjoin(Account, Account.id == Ownership.account_id)
            .where(
                Ownership.participant_id == participant_id,
                Ownership.game_id.in_(game_ids),
            )
            .order_by(Ownership.platform, Ownership.id)
        ):
            ownerships_by_game[ownership.game_id].append(
                {
                    "platform": ownership.platform,
                    "playtime_minutes": ownership.playtime_minutes,
                    "account_id": account.account_id if account else None,
                    "account_display_name": account.display_name if account else None,
                }
            )

    return {
        "items": [
            {
                "game": game,
                "platforms": ownerships_by_game.get(game.id, []),
                "total_playtime_minutes": int(total_playtime or 0),
            }
            for game, total_playtime in rows
        ],
        "total": int(total),
        "page": page,
        "per_page": per_page,
        "platforms": available_platforms,
        "genres": available_genres,
    }


@router.get("/manual/options", response_model=list[ManualOwnershipGameOptionRead])
def manual_ownership_options(
    participant_id: int,
    search: str = "",
    limit: int = 25,
    db: Session = Depends(get_db),
):
    if not db.get(Participant, participant_id):
        raise HTTPException(404, "participant not found")
    if not search.strip():
        return []

    games = db.scalars(
        select(Game)
        .where(
            Game.is_game == True,  # noqa: E712
            Game.normalized_title.contains(normalize_title(search)),
        )
        .order_by(func.lower(Game.title), Game.id)
        .limit(min(max(limit, 1), 50))
    ).all()
    game_ids = [game.id for game in games]
    if not game_ids:
        return []

    owner_counts = {
        game_id: owner_count
        for game_id, owner_count in db.execute(
            select(Ownership.game_id, func.count(distinct(Ownership.participant_id)))
            .where(Ownership.game_id.in_(game_ids))
            .group_by(Ownership.game_id)
        ).all()
    }
    owned_game_ids = set(
        db.scalars(
            select(Ownership.game_id).where(
                Ownership.participant_id == participant_id,
                Ownership.game_id.in_(game_ids),
            )
        )
    )
    platforms_by_game: dict[int, set] = {game_id: set() for game_id in game_ids}
    for game_id, platform in db.execute(
        select(PlatformGameMapping.game_id, PlatformGameMapping.platform).where(
            PlatformGameMapping.game_id.in_(game_ids)
        )
    ):
        platforms_by_game[game_id].add(platform)

    manual_by_game: dict[int, list[dict]] = {game_id: [] for game_id in game_ids}
    for confirmation in db.scalars(
        select(ManualOwnership).where(
            ManualOwnership.participant_id == participant_id,
            ManualOwnership.game_id.in_(game_ids),
        )
    ):
        manual_by_game[confirmation.game_id].append(
            {"id": confirmation.id, "platform": confirmation.platform}
        )

    return [
        {
            "id": game.id,
            "title": game.title,
            "release_date": game.release_date,
            "owner_count": int(owner_counts.get(game.id, 0)),
            "platforms": sorted(platforms_by_game[game.id], key=str),
            "owned": game.id in owned_game_ids,
            "manual_confirmations": manual_by_game[game.id],
        }
        for game in games
    ]


@router.post("/manual", response_model=ManualOwnershipRead, status_code=201)
def create_manual_ownership(payload: ManualOwnershipCreate, db: Session = Depends(get_db)):
    participant = db.get(Participant, payload.participant_id)
    if not participant:
        raise HTTPException(404, "participant not found")
    game = db.get(Game, payload.game_id)
    if not game or not game.is_game:
        raise HTTPException(404, "game not found")

    confirmation = db.scalar(
        select(ManualOwnership).where(
            ManualOwnership.participant_id == payload.participant_id,
            ManualOwnership.game_id == payload.game_id,
            ManualOwnership.platform == payload.platform,
        )
    )
    if confirmation is None:
        confirmation = ManualOwnership(**payload.model_dump())
        db.add(confirmation)

    ownership = db.scalar(
        select(Ownership).where(
            Ownership.participant_id == payload.participant_id,
            Ownership.game_id == payload.game_id,
            Ownership.platform == payload.platform,
        )
    )
    if ownership is None:
        existing_first_seen = db.execute(
            select(Ownership.first_seen_at, Ownership.first_seen_is_baseline)
            .where(
                Ownership.participant_id == payload.participant_id,
                Ownership.game_id == payload.game_id,
            )
            .order_by(Ownership.first_seen_at.asc().nulls_last())
            .limit(1)
        ).first()
        accounts = db.scalars(
            select(Account).where(
                Account.participant_id == payload.participant_id,
                Account.platform == payload.platform,
            )
        ).all()
        account = min(
            accounts,
            key=lambda item: item.account_id.startswith("playnite:"),
            default=None,
        )
        db.add(
            Ownership(
                participant_id=payload.participant_id,
                account_id=account.id if account else None,
                game_id=payload.game_id,
                platform=payload.platform,
                first_seen_at=existing_first_seen[0] if existing_first_seen else datetime.utcnow(),
                first_seen_is_baseline=existing_first_seen[1] if existing_first_seen else False,
                last_seen=datetime.utcnow(),
            )
        )

    db.commit()
    db.refresh(confirmation)
    return confirmation


@router.delete("/manual/{manual_ownership_id}", status_code=204)
def delete_manual_ownership(manual_ownership_id: int, db: Session = Depends(get_db)):
    confirmation = db.get(ManualOwnership, manual_ownership_id)
    if not confirmation:
        raise HTTPException(404, "manual ownership not found")

    ownership = db.scalar(
        select(Ownership).where(
            Ownership.participant_id == confirmation.participant_id,
            Ownership.game_id == confirmation.game_id,
            Ownership.platform == confirmation.platform,
        )
    )
    db.delete(confirmation)
    if ownership is not None and ownership.account_id is None:
        db.delete(ownership)
    db.commit()


@router.delete("/{ownership_id}", status_code=204)
def delete_ownership(ownership_id: int, db: Session = Depends(get_db)):
    ownership = db.get(Ownership, ownership_id)
    if not ownership:
        raise HTTPException(404, "ownership not found")
    db.delete(ownership)
    db.commit()
