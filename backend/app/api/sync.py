from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import SyncRun
from app.schemas import MetadataSyncRead, SyncRunRead
from app.services.metadata_service import enrich_all_game_metadata
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


@router.post("/metadata", response_model=MetadataSyncRead)
def metadata_all(db: Session = Depends(get_db)):
    return enrich_all_game_metadata(db)


@router.post("/metadata/repair", response_model=MetadataSyncRead)
def repair_metadata(db: Session = Depends(get_db)):
    return enrich_all_game_metadata(db)
