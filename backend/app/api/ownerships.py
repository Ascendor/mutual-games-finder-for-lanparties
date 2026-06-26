from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Ownership
from app.schemas import OwnershipCreate, OwnershipRead

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


@router.delete("/{ownership_id}", status_code=204)
def delete_ownership(ownership_id: int, db: Session = Depends(get_db)):
    ownership = db.get(Ownership, ownership_id)
    if not ownership:
        raise HTTPException(404, "ownership not found")
    db.delete(ownership)
    db.commit()

