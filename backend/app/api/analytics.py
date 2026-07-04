import json
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import AnalyticsConfiguration, Participant, UsageEvent
from app.schemas import (
    AnalyticsConfigurationRead,
    AnalyticsConfigurationUpdate,
    AnalyticsPeriod,
    AnalyticsParticipantDetailRead,
    AnalyticsSummaryRead,
    UsageEventCreate,
    UsageEventRead,
)
from app.services.analytics_service import (
    build_participant_detail,
    build_summary,
    maybe_purge_expired_usage_events,
)


router = APIRouter()


@router.post("/events", response_model=UsageEventRead, status_code=201)
def create_event(payload: UsageEventCreate, db: Session = Depends(get_db)):
    maybe_purge_expired_usage_events(db)
    participant = db.get(Participant, payload.participant_id) if payload.participant_id else None
    if payload.participant_id and participant is None:
        raise HTTPException(404, "participant not found")
    if len(json.dumps(payload.details, ensure_ascii=False)) > 8192:
        raise HTTPException(413, "analytics event details are too large")
    event = UsageEvent(
        participant_id=participant.id if participant else None,
        participant_name=participant.nickname if participant else "",
        event_type=payload.event_type,
        details=payload.details,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/configuration", response_model=AnalyticsConfigurationRead)
def analytics_configuration(db: Session = Depends(get_db)):
    configuration = db.get(AnalyticsConfiguration, 1)
    return _configuration_response(configuration)


@router.put("/configuration", response_model=AnalyticsConfigurationRead)
def update_analytics_configuration(
    payload: AnalyticsConfigurationUpdate,
    db: Session = Depends(get_db),
):
    party_start = _as_utc_naive(payload.party_start_at)
    party_end = _as_utc_naive(payload.party_end_at) if payload.party_end_at else None
    if party_end is not None and party_end <= party_start:
        raise HTTPException(422, "party end must be after party start")
    configuration = db.get(AnalyticsConfiguration, 1)
    if configuration is None:
        configuration = AnalyticsConfiguration(id=1)
        db.add(configuration)
    configuration.party_start_at = party_start
    configuration.party_end_at = party_end
    db.commit()
    db.refresh(configuration)
    return _configuration_response(configuration)


@router.get("/summary", response_model=AnalyticsSummaryRead)
def analytics_summary(
    period: AnalyticsPeriod = Query(default="custom"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return build_summary(db, date_from, date_to, period)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get(
    "/participants/{participant_id}",
    response_model=AnalyticsParticipantDetailRead,
)
def analytics_participant(
    participant_id: int,
    period: AnalyticsPeriod = Query(default="custom"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return build_participant_detail(
            db,
            participant_id,
            date_from,
            date_to,
            period,
        )
    except ValueError as exc:
        status = 404 if str(exc) == "participant not found" else 400
        raise HTTPException(status, str(exc)) from exc


@router.delete("/participants/{participant_id}/events", status_code=204)
def delete_participant_events(
    participant_id: int,
    db: Session = Depends(get_db),
):
    participant = db.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(404, "participant not found")
    db.execute(delete(UsageEvent).where(UsageEvent.participant_id == participant_id))
    db.commit()


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _configuration_response(
    configuration: AnalyticsConfiguration | None,
) -> dict:
    if configuration is None:
        return {"party_start_at": None, "party_end_at": None}
    return {
        "party_start_at": (
            configuration.party_start_at.replace(tzinfo=UTC)
            if configuration.party_start_at
            else None
        ),
        "party_end_at": (
            configuration.party_end_at.replace(tzinfo=UTC)
            if configuration.party_end_at
            else None
        ),
    }
