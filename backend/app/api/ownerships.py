from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Account, Game, ManualOwnership, Ownership, Participant, PlatformGameMapping
from app.schemas import (
    ManualOwnershipCreate,
    ManualOwnershipGameOptionRead,
    ManualOwnershipRead,
    OwnershipCreate,
    OwnershipRead,
)
from app.services.normalization import normalize_title

router = APIRouter()


@router.get("", response_model=list[OwnershipRead])
def list_ownerships(db: Session = Depends(get_db)):
    return db.scalars(select(Ownership)).all()


@router.post("", response_model=OwnershipRead, status_code=201)
def create_ownership(payload: OwnershipCreate, db: Session = Depends(get_db)):
    ownership = Ownership(**payload.model_dump(), last_seen=datetime.utcnow())
    db.add(ownership)
    db.commit()
    db.refresh(ownership)
    return ownership


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
