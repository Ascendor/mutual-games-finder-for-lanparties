from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query, Request, Response
from sqlalchemy import String, and_, cast, func, not_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import Game, Ownership, Participant
from app.schemas import (
    GameCreate,
    GameListItemRead,
    GameOptionRead,
    GameOwnerRead,
    GamePageRead,
    GameRead,
    GameUpdate,
)
from app.services.genre_utils import sanitize_genres
from app.services.normalization import normalize_title

router = APIRouter()
GAME_FEATURE_FIELDS = {
    "singleplayer": Game.singleplayer,
    "multiplayer": Game.multiplayer,
    "lan": Game.lan,
    "local_coop": Game.local_coop,
    "online_coop": Game.online_coop,
    "versus": Game.versus,
    "hotseat": Game.hotseat,
}


def _game_page_conditions(
    search: str | None,
    genres: list[str],
    features: list[str],
    include_pure_singleplayer: bool,
    include_non_games: bool,
):
    conditions = []
    if not include_non_games:
        conditions.append(Game.is_game == True)  # noqa: E712
    if search:
        conditions.append(Game.normalized_title.contains(normalize_title(search)))
    if genres:
        conditions.append(
            or_(
                *(
                    cast(Game.genres, String).ilike(f'%"{genre}"%')
                    for genre in genres
                )
            )
        )
    for feature in features:
        if feature == "coop":
            conditions.append(
                (Game.local_coop == True)  # noqa: E712
                | (Game.online_coop == True)  # noqa: E712
                | (Game.campaign_coop == True)  # noqa: E712
            )
        elif feature == "split_screen":
            conditions.append(
                (Game.split_screen == True) | (Game.shared_screen == True)  # noqa: E712
            )
        elif feature == "free":
            conditions.append(Game.is_free == True)  # noqa: E712
        elif feature in GAME_FEATURE_FIELDS:
            conditions.append(GAME_FEATURE_FIELDS[feature] == True)  # noqa: E712
    if not include_pure_singleplayer:
        conditions.append(
            not_(
                and_(
                    Game.singleplayer == True,  # noqa: E712
                    Game.multiplayer == False,  # noqa: E712
                    Game.lan == False,  # noqa: E712
                    Game.local_coop == False,  # noqa: E712
                    Game.online_coop == False,  # noqa: E712
                    Game.campaign_coop == False,  # noqa: E712
                    Game.hotseat == False,  # noqa: E712
                    Game.split_screen == False,  # noqa: E712
                    Game.shared_screen == False,  # noqa: E712
                    Game.versus == False,  # noqa: E712
                )
            )
        )
    return conditions


@router.get("", response_model=list[GameRead])
def list_games(
    search: str | None = None,
    include_non_games: bool = False,
    db: Session = Depends(get_db),
):
    stmt = select(Game).order_by(Game.title)
    if not include_non_games:
        stmt = stmt.where(Game.is_game == True)  # noqa: E712
    if search:
        stmt = stmt.where(Game.normalized_title.contains(normalize_title(search)))
    return db.scalars(stmt).all()


@router.get("/page", response_model=GamePageRead)
def list_games_page(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: str | None = None,
    genres: list[str] = Query(default=[]),
    features: list[str] = Query(default=[]),
    include_pure_singleplayer: bool = False,
    include_non_games: bool = False,
    sort_by: str = Query("title"),
    sort_desc: bool = False,
    db: Session = Depends(get_db),
):
    conditions = _game_page_conditions(
        search,
        genres,
        features,
        include_pure_singleplayer,
        include_non_games,
    )
    owner_counts = (
        select(
            Ownership.game_id.label("game_id"),
            func.count(func.distinct(Ownership.participant_id)).label("owner_count"),
        )
        .group_by(Ownership.game_id)
        .subquery()
    )
    total = int(
        db.scalar(select(func.count(Game.id)).where(*conditions)) or 0
    )
    owner_count = func.coalesce(owner_counts.c.owner_count, 0)
    sort_columns = {
        "title": Game.title,
        "owner_count": owner_count,
        "metadata_updated_at": Game.metadata_updated_at,
        "max_players": Game.max_players,
    }
    sort_column = sort_columns.get(sort_by, Game.title)
    order = sort_column.desc().nullslast() if sort_desc else sort_column.asc().nullsfirst()
    stmt = (
        select(Game, owner_count.label("owner_count"))
        .outerjoin(owner_counts, owner_counts.c.game_id == Game.id)
        .where(*conditions)
        .order_by(order, Game.title.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = db.execute(stmt).all()
    genre_stmt = select(Game.genres)
    if not include_non_games:
        genre_stmt = genre_stmt.where(Game.is_game == True)  # noqa: E712
    all_genres = sanitize_genres(
        genre
        for values in db.scalars(genre_stmt)
        for genre in (values or [])
    )
    return {
        "items": [
            {
                **GameRead.model_validate(game).model_dump(),
                "owner_count": int(item_owner_count or 0),
            }
            for game, item_owner_count in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "genres": all_genres,
    }


@router.get("/options", response_model=list[GameOptionRead])
def list_game_options(
    request: Request,
    response: Response,
    search: str | None = None,
    limit: int | None = Query(None, ge=1, le=500),
    db: Session = Depends(get_db),
):
    count, latest_update = db.execute(
        select(func.count(Game.id), func.max(Game.updated_at)).where(Game.is_game == True)  # noqa: E712
    ).one()
    etag = f'"games-{count}-{latest_update.isoformat() if latest_update else "empty"}"'
    cache_headers = {
        "Cache-Control": "private, max-age=300, stale-while-revalidate=60",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cache_headers)

    stmt = select(Game.id, Game.title).where(Game.is_game == True).order_by(Game.title)  # noqa: E712
    if search:
        stmt = stmt.where(Game.normalized_title.contains(normalize_title(search)))
    if limit:
        stmt = stmt.limit(limit)
    response.headers.update(cache_headers)
    return [{"id": game_id, "title": title} for game_id, title in db.execute(stmt)]


@router.get("/{game_id}/owners", response_model=list[GameOwnerRead])
def list_game_owners(game_id: int, present_only: bool = True, db: Session = Depends(get_db)):
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(404, "game not found")
    stmt = (
        select(Ownership)
        .join(Ownership.participant)
        .where(Ownership.game_id == game_id)
        .options(selectinload(Ownership.participant), selectinload(Ownership.account))
    )
    if present_only:
        stmt = stmt.where(Participant.present == True)  # noqa: E712
    ownerships = db.scalars(stmt).all()
    by_participant: dict[int, dict] = {}
    for ownership in ownerships:
        item = by_participant.setdefault(
            ownership.participant_id,
            {
                "participant": ownership.participant,
                "platforms": set(),
                "account_names": set(),
                "total_playtime_minutes": 0,
                "last_seen": None,
            },
        )
        item["platforms"].add(ownership.platform)
        if ownership.account and ownership.account.display_name:
            item["account_names"].add(ownership.account.display_name)
        elif ownership.account and ownership.account.account_id:
            item["account_names"].add(ownership.account.account_id)
        else:
            item["account_names"].add("Manuell bestätigt")
        item["total_playtime_minutes"] += ownership.playtime_minutes or 0
        if item["last_seen"] is None or ownership.last_seen > item["last_seen"]:
            item["last_seen"] = ownership.last_seen
    return [
        {
            "participant": item["participant"],
            "platforms": sorted(item["platforms"]),
            "account_names": sorted(item["account_names"]),
            "total_playtime_minutes": item["total_playtime_minutes"],
            "last_seen": item["last_seen"],
        }
        for item in sorted(
            by_participant.values(),
            key=lambda value: (-value["total_playtime_minutes"], value["participant"].nickname.casefold()),
        )
    ]


@router.post("", response_model=GameRead, status_code=201)
def create_game(payload: GameCreate, db: Session = Depends(get_db)):
    game = Game(**payload.model_dump(), normalized_title=normalize_title(payload.title))
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


@router.get("/{game_id}", response_model=GameRead)
def get_game(game_id: int, db: Session = Depends(get_db)):
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(404, "game not found")
    return game


@router.patch("/{game_id}", response_model=GameRead)
def update_game(game_id: int, payload: GameUpdate, db: Session = Depends(get_db)):
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(404, "game not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(game, key, value)
    if "title" in data:
        game.normalized_title = normalize_title(game.title)
    db.commit()
    db.refresh(game)
    return game


@router.delete("/{game_id}", status_code=204)
def delete_game(game_id: int, db: Session = Depends(get_db)):
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(404, "game not found")
    db.delete(game)
    db.commit()
