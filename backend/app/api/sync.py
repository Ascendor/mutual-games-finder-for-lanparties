from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Game, SyncRun
from app.schemas import SyncRunRead
from app.services.metadata_service import create_metadata_sync_run, run_metadata_sync
from app.services.steam_metadata_service import (
    create_steam_metadata_run,
    run_steam_metadata_sync,
)
from app.services.sync_service import sync_account

router = APIRouter()


@router.get("/runs", response_model=list[SyncRunRead])
def list_sync_runs(db: Session = Depends(get_db)):
    return db.scalars(select(SyncRun).order_by(SyncRun.started_at.desc())).all()


@router.get("/runs/{run_id}", response_model=SyncRunRead)
def get_sync_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(SyncRun, run_id)
    if not run:
        raise HTTPException(404, "sync run not found")
    return run


@router.post("/accounts/{account_id}", response_model=SyncRunRead)
def sync_single_account(account_id: int, db: Session = Depends(get_db)):
    try:
        return sync_account(db, account_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


def _start_metadata_sync(background_tasks: BackgroundTasks, db: Session) -> SyncRun:
    try:
        run = create_metadata_sync_run(db)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    background_tasks.add_task(run_metadata_sync, run.id)
    return run


@router.post("/metadata", response_model=SyncRunRead, status_code=202)
def metadata_all(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _start_metadata_sync(background_tasks, db)


@router.post("/metadata/repair", response_model=SyncRunRead, status_code=202)
def repair_metadata(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return _start_metadata_sync(background_tasks, db)


@router.post("/games/{game_id}/metadata", response_model=SyncRunRead, status_code=202)
def metadata_single_game(
    game_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    game = db.get(Game, game_id)
    if not game:
        raise HTTPException(404, "game not found")
    try:
        run = create_metadata_sync_run(
            db,
            kind="game_metadata",
            message=f"Metadaten für {game.title} warten auf Start",
            progress_total=1,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    background_tasks.add_task(run_metadata_sync, run.id, {game.id})
    return run


@router.post("/steam/metadata", response_model=SyncRunRead, status_code=202)
def metadata_all_steam_games(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        run = create_steam_metadata_run(db)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    background_tasks.add_task(run_steam_metadata_sync, run.id)
    return run
