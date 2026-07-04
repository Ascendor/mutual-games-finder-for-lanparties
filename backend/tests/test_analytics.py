from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from app.api.analytics import (
    create_event,
    delete_participant_events,
    update_analytics_configuration,
)
from app.api.participants import delete_participant
from app.core.config import settings
from app.models import AnalyticsConfiguration, Participant, UsageEvent
from app.schemas import AnalyticsConfigurationUpdate, UsageEventCreate
from app.services.analytics_service import (
    build_participant_detail,
    build_summary,
    purge_expired_usage_events,
)


def test_analytics_summary_aggregates_searches_and_users(db):
    ada = Participant(nickname="Ada")
    bob = Participant(nickname="Bob")
    db.add_all([ada, bob])
    db.flush()
    occurred_at = datetime(2026, 7, 3, 18, 30)
    db.add_all(
        [
            UsageEvent(
                participant_id=ada.id,
                participant_name=ada.nickname,
                event_type="page_view",
                occurred_at=occurred_at,
                details={"path": "/"},
            ),
            UsageEvent(
                participant_id=ada.id,
                participant_name=ada.nickname,
                event_type="find_players_search",
                occurred_at=occurred_at,
                details={"game_id": 620, "game_title": "Portal 2", "result_count": 4},
            ),
            UsageEvent(
                participant_id=bob.id,
                participant_name=bob.nickname,
                event_type="find_players_search",
                occurred_at=occurred_at,
                details={"game_id": 620, "game_title": "Portal 2", "result_count": 4},
            ),
            UsageEvent(
                participant_id=ada.id,
                participant_name=ada.nickname,
                event_type="group_games_search",
                occurred_at=occurred_at,
                details={
                    "selected_players": [
                        {"id": ada.id, "nickname": "Ada"},
                        {"id": bob.id, "nickname": "Bob"},
                    ],
                    "group_size": 2,
                },
            ),
        ]
    )
    db.commit()

    summary = build_summary(db, date(2026, 7, 3), date(2026, 7, 3))

    assert summary["total_events"] == 4
    assert summary["active_users"] == 2
    assert summary["find_players_searches"] == 2
    assert summary["group_games_searches"] == 1
    assert summary["top_games"] == [
        {
            "game_id": 620,
            "title": "Portal 2",
            "searches": 2,
            "unique_users": 2,
        }
    ]
    assert summary["selected_players"][0]["participant_id"] == bob.id
    assert summary["selected_players"][0]["selections"] == 1
    assert summary["participants"][0]["nickname"] == "Ada"
    assert summary["daily"][0]["total_events"] == 4


def test_analytics_participant_detail_only_contains_selected_user(db):
    ada = Participant(nickname="Ada")
    bob = Participant(nickname="Bob")
    db.add_all([ada, bob])
    db.flush()
    occurred_at = datetime(2026, 7, 3, 18, 30)
    db.add_all(
        [
            UsageEvent(
                participant_id=ada.id,
                participant_name=ada.nickname,
                event_type="page_view",
                occurred_at=occurred_at,
                details={"path": "/dashboard"},
            ),
            UsageEvent(
                participant_id=bob.id,
                participant_name=bob.nickname,
                event_type="page_view",
                occurred_at=occurred_at,
                details={"path": "/"},
            ),
        ]
    )
    db.commit()

    detail = build_participant_detail(
        db,
        ada.id,
        date(2026, 7, 3),
        date(2026, 7, 3),
    )

    assert detail["nickname"] == "Ada"
    assert detail["total_events"] == 1
    assert detail["recent_events"][0].participant_id == ada.id


def test_create_event_stores_current_participant_name(db):
    participant = Participant(nickname="Current Name")
    db.add(participant)
    db.commit()

    event = create_event(
        UsageEventCreate(
            participant_id=participant.id,
            event_type="page_view",
            details={"path": "/dashboard"},
        ),
        db,
    )

    assert event.participant_name == "Current Name"
    assert event.details == {"path": "/dashboard"}


def test_party_period_separates_events_at_exact_start_time(db):
    participant = Participant(nickname="Ada")
    db.add(participant)
    db.flush()
    db.add(
        AnalyticsConfiguration(
            id=1,
            party_start_at=datetime(2026, 7, 3, 18, 0),
            party_end_at=datetime(2026, 7, 5, 14, 0),
        )
    )
    db.add_all(
        [
            UsageEvent(
                participant_id=participant.id,
                participant_name=participant.nickname,
                event_type="page_view",
                occurred_at=datetime(2026, 7, 3, 17, 59),
                details={"path": "/"},
            ),
            UsageEvent(
                participant_id=participant.id,
                participant_name=participant.nickname,
                event_type="find_players_search",
                occurred_at=datetime(2026, 7, 3, 18, 0),
                details={"game_title": "Portal 2"},
            ),
        ]
    )
    db.commit()

    before = build_summary(db, period="before_party")
    party = build_summary(db, period="party")

    assert before["period"] == "before_party"
    assert before["total_events"] == 1
    assert before["page_views"] == 1
    assert party["period"] == "party"
    assert party["total_events"] == 1
    assert party["find_players_searches"] == 1


def test_party_configuration_is_stored_as_utc(db):
    response = update_analytics_configuration(
        AnalyticsConfigurationUpdate(
            party_start_at=datetime.fromisoformat("2026-07-03T20:00:00+02:00"),
            party_end_at=datetime.fromisoformat("2026-07-05T16:00:00+02:00"),
        ),
        db,
    )

    configuration = db.get(AnalyticsConfiguration, 1)
    assert configuration is not None
    assert configuration.party_start_at == datetime(2026, 7, 3, 18, 0)
    assert response["party_start_at"].utcoffset().total_seconds() == 0


def test_deleting_participant_also_deletes_usage_events(db):
    participant = Participant(nickname="Delete Me")
    db.add(participant)
    db.flush()
    db.add(
        UsageEvent(
            participant_id=participant.id,
            participant_name=participant.nickname,
            event_type="page_view",
            details={"path": "/"},
        )
    )
    db.commit()

    delete_participant(participant.id, db)

    assert db.scalar(select(func.count(UsageEvent.id))) == 0


def test_participant_analytics_can_be_deleted_without_deleting_participant(db):
    participant = Participant(nickname="Keep Me")
    db.add(participant)
    db.flush()
    db.add(
        UsageEvent(
            participant_id=participant.id,
            participant_name=participant.nickname,
            event_type="page_view",
            details={"path": "/"},
        )
    )
    db.commit()

    delete_participant_events(participant.id, db)

    assert db.get(Participant, participant.id) is not None
    assert db.scalar(select(func.count(UsageEvent.id))) == 0


def test_expired_usage_events_are_purged(db, monkeypatch):
    monkeypatch.setattr(settings, "analytics_retention_days", 180)
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add_all(
        [
            UsageEvent(
                participant_name="Old",
                event_type="page_view",
                occurred_at=now - timedelta(days=181),
                details={"path": "/"},
            ),
            UsageEvent(
                participant_name="Current",
                event_type="page_view",
                occurred_at=now - timedelta(days=179),
                details={"path": "/"},
            ),
        ]
    )
    db.commit()

    assert purge_expired_usage_events(db) == 1
    assert db.scalar(select(func.count(UsageEvent.id))) == 1
