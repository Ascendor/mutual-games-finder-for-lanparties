from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import Game, Ownership, Participant
from app.schemas import GameCreate, GameOptionRead, GameOwnerRead, GameRead, GameUpdate
from app.services.normalization import normalize_title

router = APIRouter()


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
        if ownership.account.display_name:
            item["account_names"].add(ownership.account.display_name)
        elif ownership.account.account_id:
            item["account_names"].add(ownership.account.account_id)
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
