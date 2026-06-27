from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import SyncRun
from app.schemas import SyncRunRead
from app.services.metadata_service import create_metadata_sync_run, run_metadata_sync
from app.services.sync_service import sync_account

router = APIRouter()


@router.get("/runs", response_model=list[SyncRunRead])
def list_sync_runs(db: Session = Depends(get_db)):
    return db.scalars(select(SyncRun).order_by(SyncRun.started_at.desc())).all()


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
