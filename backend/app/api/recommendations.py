from collections.abc import Callable

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Participant
from app.db.session import get_db
from app.schemas import RecommendationRead
from app.services import recommendations as engine
from app.services.recommendation_cache import (
    CacheKey,
    recommendation_cache,
    synchronize_recommendation_cache,
)

router = APIRouter()


def _limited(items: list[RecommendationRead], limit: int | None) -> list[RecommendationRead]:
    return items[:limit] if limit else items


def _cached(
    request: Request,
    response: Response,
    db: Session,
    key: CacheKey,
    factory: Callable[[], list[RecommendationRead]],
    limit: int | None = None,
):
    database_revision = synchronize_recommendation_cache(db)
    items, revision, cache_hit = recommendation_cache.get(key, factory)
    etag = recommendation_cache.etag(key, revision, database_revision, limit)
    headers = {
        "Cache-Control": "private, max-age=30",
        "ETag": etag,
        "X-Recommendation-Cache": "HIT" if cache_hit else "MISS",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return _limited(items, limit)


@router.get("/common", response_model=list[RecommendationRead])
def common_games(
    request: Request,
    response: Response,
    players: list[int] = Query(default=[]),
    minimum_coverage: int = Query(75, ge=50, le=100),
    free_games_as_owned: bool = True,
    db: Session = Depends(get_db),
):
    selected = tuple(sorted(set(players)))
    return _cached(
        request,
        response,
        db,
        ("common", selected, minimum_coverage, free_games_as_owned),
        lambda: engine.find_common_games(
            db,
            list(selected),
            minimum_coverage / 100,
            free_games_as_owned,
        ),
    )


@router.get("/coop", response_model=list[RecommendationRead])
def common_coop_games(players: list[int] = Query(default=[]), db: Session = Depends(get_db)):
    return engine.find_common_coop_games(db, players)


@router.get("/present", response_model=list[RecommendationRead])
def present_games(
    request: Request,
    response: Response,
    limit: int | None = Query(None, ge=1, le=500),
    db: Session = Depends(get_db),
):
    present = tuple(sorted(engine.present_participant_ids(db)))
    return _cached(
        request,
        response,
        db,
        ("common", present),
        lambda: engine.find_common_games(db, list(present)),
        limit,
    )


@router.get("/lan", response_model=list[RecommendationRead])
def lan_games(
    request: Request,
    response: Response,
    players: list[int] | None = Query(None),
    limit: int | None = Query(None, ge=1, le=500),
    db: Session = Depends(get_db),
):
    if players:
        selected = tuple(sorted(set(players)))
        return _cached(
            request,
            response,
            db,
            ("lan-common", selected),
            lambda: engine.find_common_lan_games(db, list(selected)),
            limit,
        )
    present = tuple(sorted(engine.present_participant_ids(db)))
    return _cached(
        request,
        response,
        db,
        ("lan", present),
        lambda: engine.find_best_lan_games(db),
        limit,
    )


@router.get("/popular", response_model=list[RecommendationRead])
def popular_games(
    request: Request,
    response: Response,
    limit: int | None = Query(None, ge=1, le=500),
    db: Session = Depends(get_db),
):
    participants = tuple(sorted(db.scalars(select(Participant.id)).all()))
    return _cached(
        request,
        response,
        db,
        ("popular", participants),
        lambda: engine.find_most_popular_games(db),
        limit,
    )


@router.get("/new", response_model=list[RecommendationRead])
def new_for_group_games(
    request: Request,
    response: Response,
    players: list[int] | None = Query(None),
    limit: int | None = Query(None, ge=1, le=500),
    db: Session = Depends(get_db),
):
    selected = tuple(sorted(set(players or engine.present_participant_ids(db))))
    return _cached(
        request,
        response,
        db,
        ("new", selected),
        lambda: engine.find_new_for_group_games(db, list(selected)),
        limit,
    )


@router.get("/group-size/{size}", response_model=list[RecommendationRead])
def group_size(size: int, db: Session = Depends(get_db)):
    return engine.find_games_for_group_size(db, size)
