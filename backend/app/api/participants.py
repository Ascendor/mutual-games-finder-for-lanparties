from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Participant
from app.schemas import ParticipantCreate, ParticipantRead, ParticipantUpdate

router = APIRouter()


@router.get("", response_model=list[ParticipantRead])
def list_participants(db: Session = Depends(get_db)):
    return db.scalars(select(Participant).order_by(Participant.nickname)).all()


@router.post("", response_model=ParticipantRead, status_code=201)
def create_participant(payload: ParticipantCreate, db: Session = Depends(get_db)):
    participant = Participant(**payload.model_dump())
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


@router.get("/{participant_id}", response_model=ParticipantRead)
def get_participant(participant_id: int, db: Session = Depends(get_db)):
    participant = db.get(Participant, participant_id)
    if not participant:
        raise HTTPException(404, "participant not found")
    return participant


@router.patch("/{participant_id}", response_model=ParticipantRead)
def update_participant(participant_id: int, payload: ParticipantUpdate, db: Session = Depends(get_db)):
    participant = db.get(Participant, participant_id)
    if not participant:
        raise HTTPException(404, "participant not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(participant, key, value)
    db.commit()
    db.refresh(participant)
    return participant


@router.delete("/{participant_id}", status_code=204)
def delete_participant(participant_id: int, db: Session = Depends(get_db)):
    participant = db.get(Participant, participant_id)
    if not participant:
        raise HTTPException(404, "participant not found")
    db.delete(participant)
    db.commit()

