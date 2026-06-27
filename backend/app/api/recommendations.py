from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import RecommendationRead
from app.services import recommendations as engine

router = APIRouter()


@router.get("/common", response_model=list[RecommendationRead])
def common_games(players: list[int] = Query(default=[]), db: Session = Depends(get_db)):
    return engine.find_common_games(db, players)


@router.get("/coop", response_model=list[RecommendationRead])
def common_coop_games(players: list[int] = Query(default=[]), db: Session = Depends(get_db)):
    return engine.find_common_coop_games(db, players)


@router.get("/present", response_model=list[RecommendationRead])
def present_games(db: Session = Depends(get_db)):
    return engine.find_games_for_present_players(db)


@router.get("/lan", response_model=list[RecommendationRead])
def lan_games(players: list[int] | None = Query(None), db: Session = Depends(get_db)):
    if players:
        return engine.find_common_lan_games(db, players)
    return engine.find_best_lan_games(db)


@router.get("/popular", response_model=list[RecommendationRead])
def popular_games(db: Session = Depends(get_db)):
    return engine.find_most_popular_games(db)


@router.get("/new", response_model=list[RecommendationRead])
def new_for_group_games(players: list[int] | None = Query(None), db: Session = Depends(get_db)):
    return engine.find_new_for_group_games(db, players)


@router.get("/group-size/{size}", response_model=list[RecommendationRead])
def group_size(size: int, db: Session = Depends(get_db)):
    return engine.find_games_for_group_size(db, size)
