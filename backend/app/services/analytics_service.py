from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AnalyticsConfiguration, Participant, UsageEvent
from app.core.config import settings


LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")
EVENT_TYPES = (
    "page_view",
    "find_players_search",
    "group_games_search",
)
_purge_lock = Lock()
_last_purge_at = 0.0


def purge_expired_usage_events(db: Session) -> int:
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        days=max(settings.analytics_retention_days, 1)
    )
    result = db.execute(delete(UsageEvent).where(UsageEvent.occurred_at < cutoff))
    db.commit()
    return int(result.rowcount or 0)


def maybe_purge_expired_usage_events(
    db: Session,
    interval_seconds: float = 3600,
) -> int:
    global _last_purge_at
    now = monotonic()
    with _purge_lock:
        if now - _last_purge_at < interval_seconds:
            return 0
        deleted = purge_expired_usage_events(db)
        _last_purge_at = now
        return deleted


def analytics_dates(
    date_from: date | None,
    date_to: date | None,
) -> tuple[date, date]:
    today = datetime.now(LOCAL_TIMEZONE).date()
    end = date_to or today
    start = date_from or (end - timedelta(days=6))
    if start > end:
        start, end = end, start
    return start, end


def events_for_period(
    db: Session,
    date_from: date,
    date_to: date,
    participant_id: int | None = None,
) -> list[UsageEvent]:
    start_local = datetime.combine(date_from, time.min, tzinfo=LOCAL_TIMEZONE)
    end_local = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=LOCAL_TIMEZONE)
    start_utc = start_local.astimezone(UTC).replace(tzinfo=None)
    end_utc = end_local.astimezone(UTC).replace(tzinfo=None)
    return events_for_window(db, start_utc, end_utc, participant_id)


def events_for_window(
    db: Session,
    start_utc: datetime | None,
    end_utc: datetime | None,
    participant_id: int | None = None,
) -> list[UsageEvent]:
    stmt = select(UsageEvent)
    if start_utc is not None:
        stmt = stmt.where(UsageEvent.occurred_at >= start_utc)
    if end_utc is not None:
        stmt = stmt.where(UsageEvent.occurred_at < end_utc)
    if participant_id is not None:
        stmt = stmt.where(UsageEvent.participant_id == participant_id)
    return db.scalars(
        stmt.order_by(UsageEvent.occurred_at.desc(), UsageEvent.id.desc())
    ).all()


def build_summary(
    db: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    period: str = "custom",
) -> dict:
    events, start, end = events_for_selection(db, period, date_from, date_to)
    counts = Counter(event.event_type for event in events)
    participant_stats: dict[int, dict] = {}

    for event in events:
        if event.participant_id is None:
            continue
        stats = participant_stats.setdefault(
            event.participant_id,
            {
                "participant_id": event.participant_id,
                "nickname": event.participant_name or f"Teilnehmer {event.participant_id}",
                "total_events": 0,
                "page_views": 0,
                "find_players_searches": 0,
                "group_games_searches": 0,
                "last_active_at": event.occurred_at,
            },
        )
        stats["total_events"] += 1
        stats["last_active_at"] = max(stats["last_active_at"], event.occurred_at)
        if event.event_type == "page_view":
            stats["page_views"] += 1
        elif event.event_type == "find_players_search":
            stats["find_players_searches"] += 1
        elif event.event_type == "group_games_search":
            stats["group_games_searches"] += 1

    return {
        "period": period,
        "date_from": start,
        "date_to": end,
        "total_events": len(events),
        "active_users": len(participant_stats),
        "page_views": counts["page_view"],
        "find_players_searches": counts["find_players_search"],
        "group_games_searches": counts["group_games_search"],
        "daily": _daily(events, start, end),
        "event_counts": _event_counts(counts),
        "top_games": _top_games(events),
        "selected_players": _selected_players(events),
        "participants": sorted(
            participant_stats.values(),
            key=lambda item: (-item["total_events"], item["nickname"].casefold()),
        ),
    }


def build_participant_detail(
    db: Session,
    participant_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    period: str = "custom",
) -> dict:
    participant = db.get(Participant, participant_id)
    events, start, end = events_for_selection(
        db,
        period,
        date_from,
        date_to,
        participant_id,
    )
    if participant is not None:
        nickname = participant.nickname
    elif events:
        nickname = events[0].participant_name or f"Teilnehmer {participant_id}"
    else:
        raise ValueError("participant not found")
    counts = Counter(event.event_type for event in events)
    return {
        "participant_id": participant_id,
        "nickname": nickname,
        "date_from": start,
        "date_to": end,
        "total_events": len(events),
        "event_counts": _event_counts(counts),
        "daily": _daily(events, start, end),
        "top_games": _top_games(events),
        "recent_events": events[:100],
    }


def events_for_selection(
    db: Session,
    period: str,
    date_from: date | None,
    date_to: date | None,
    participant_id: int | None = None,
) -> tuple[list[UsageEvent], date, date]:
    if period == "custom":
        start, end = analytics_dates(date_from, date_to)
        return events_for_period(db, start, end, participant_id), start, end

    today = datetime.now(LOCAL_TIMEZONE).date()
    if period == "all":
        events = events_for_window(db, None, None, participant_id)
        return events, *_event_date_range(events, today, today)

    configuration = db.get(AnalyticsConfiguration, 1)
    if configuration is None or configuration.party_start_at is None:
        raise ValueError("party period is not configured")

    party_start = configuration.party_start_at
    if period == "before_party":
        events = events_for_window(db, None, party_start, participant_id)
        party_day = _local_date(party_start)
        return events, *_event_date_range(events, party_day, party_day)

    if period == "party":
        party_end = configuration.party_end_at or datetime.now(UTC).replace(tzinfo=None)
        events = events_for_window(db, party_start, party_end, participant_id)
        start_day = _local_date(party_start)
        end_day = _local_date(party_end)
        return events, start_day, end_day

    raise ValueError("unknown analytics period")


def _local_date(value: datetime) -> date:
    return value.replace(tzinfo=UTC).astimezone(LOCAL_TIMEZONE).date()


def _event_date_range(
    events: list[UsageEvent],
    fallback_start: date,
    fallback_end: date,
) -> tuple[date, date]:
    if not events:
        return fallback_start, fallback_end
    days = [_local_date(event.occurred_at) for event in events]
    return min(days), max(days)


def _daily(events: list[UsageEvent], start: date, end: date) -> list[dict]:
    by_day: dict[date, Counter] = defaultdict(Counter)
    for event in events:
        by_day[_local_date(event.occurred_at)][event.event_type] += 1
    rows = []
    current = start
    while current <= end:
        counts = by_day[current]
        rows.append(
            {
                "date": current,
                "total_events": sum(counts.values()),
                "page_views": counts["page_view"],
                "find_players_searches": counts["find_players_search"],
                "group_games_searches": counts["group_games_search"],
            }
        )
        current += timedelta(days=1)
    return rows


def _event_counts(counts: Counter) -> list[dict]:
    return [
        {"key": event_type, "count": counts[event_type]}
        for event_type in EVENT_TYPES
    ]


def _top_games(events: list[UsageEvent]) -> list[dict]:
    searches: Counter = Counter()
    users: dict[tuple[int | None, str], set[int]] = defaultdict(set)
    for event in events:
        if event.event_type != "find_players_search":
            continue
        game_id = _optional_int(event.details.get("game_id"))
        title = str(
            event.details.get("game_title")
            or event.details.get("search")
            or "Unbekannt"
        ).strip()
        key = (game_id, title)
        searches[key] += 1
        if event.participant_id is not None:
            users[key].add(event.participant_id)
    return [
        {
            "game_id": game_id,
            "title": title,
            "searches": count,
            "unique_users": len(users[(game_id, title)]),
        }
        for (game_id, title), count in sorted(
            searches.items(),
            key=lambda item: (-item[1], item[0][1].casefold()),
        )[:25]
    ]


def _selected_players(events: list[UsageEvent]) -> list[dict]:
    selections: Counter = Counter()
    searchers: dict[tuple[int | None, str], set[int]] = defaultdict(set)
    for event in events:
        if event.event_type != "group_games_search":
            continue
        for player in event.details.get("selected_players") or []:
            if not isinstance(player, dict):
                continue
            player_id = _optional_int(player.get("id"))
            if player_id == event.participant_id:
                continue
            nickname = str(player.get("nickname") or f"Teilnehmer {player_id or '?'}")
            key = (player_id, nickname)
            selections[key] += 1
            if event.participant_id is not None:
                searchers[key].add(event.participant_id)
    return [
        {
            "participant_id": participant_id,
            "nickname": nickname,
            "selections": count,
            "unique_searchers": len(searchers[(participant_id, nickname)]),
        }
        for (participant_id, nickname), count in sorted(
            selections.items(),
            key=lambda item: (-item[1], item[0][1].casefold()),
        )[:25]
    ]


def _optional_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
