from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from threading import RLock

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Game, Ownership, Participant, PlatformGameMapping
from app.schemas import RecommendationRead


CacheKey = tuple[Hashable, ...]
RELEVANT_MODELS = (Game, Ownership, Participant, PlatformGameMapping)


class RecommendationCache:
    def __init__(self, ttl_seconds: float = 3600, max_entries: int = 64) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._lock = RLock()
        self._revision = 0
        self._entries: OrderedDict[
            CacheKey,
            tuple[int, float, list[RecommendationRead]],
        ] = OrderedDict()

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def invalidate(self) -> None:
        with self._lock:
            self._revision += 1
            self._entries.clear()

    def get(
        self,
        key: CacheKey,
        factory: Callable[[], list[RecommendationRead]],
    ) -> tuple[list[RecommendationRead], int, bool]:
        while True:
            now = time.monotonic()
            with self._lock:
                revision = self._revision
                cached = self._entries.get(key)
                if cached and cached[0] == revision and cached[1] > now:
                    self._entries.move_to_end(key)
                    return cached[2], revision, True

            value = factory()
            with self._lock:
                if revision != self._revision:
                    continue
                self._entries[key] = (
                    revision,
                    time.monotonic() + self.ttl_seconds,
                    value,
                )
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    self._entries.popitem(last=False)
                return value, revision, False

    def etag(self, key: CacheKey, revision: int, limit: int | None) -> str:
        digest = hashlib.sha1(repr((key, limit)).encode("utf-8")).hexdigest()[:12]
        return f'"recommendations-{revision}-{digest}"'


recommendation_cache = RecommendationCache()


@event.listens_for(Session, "after_flush")
def _mark_recommendations_dirty(session: Session, _flush_context) -> None:
    changed = session.new.union(session.dirty).union(session.deleted)
    if any(isinstance(item, RELEVANT_MODELS) for item in changed):
        session.info["recommendations_dirty"] = True


@event.listens_for(Session, "after_commit")
def _invalidate_recommendations_after_commit(session: Session) -> None:
    if session.info.pop("recommendations_dirty", False):
        recommendation_cache.invalidate()


@event.listens_for(Session, "after_rollback")
def _clear_recommendations_dirty_marker(session: Session) -> None:
    session.info.pop("recommendations_dirty", None)


def warm_dashboard_recommendations() -> None:
    from app.services import recommendations as engine

    db = SessionLocal()
    try:
        present = tuple(sorted(engine.present_participant_ids(db)))
        all_participants = tuple(sorted(db.scalars(select(Participant.id)).all()))
        recommendation_cache.get(
            ("common", present),
            lambda: engine.find_common_games(db, list(present)),
        )
        recommendation_cache.get(
            ("popular", all_participants),
            lambda: engine.find_most_popular_games(db),
        )
        recommendation_cache.get(
            ("lan", present),
            lambda: engine.find_best_lan_games(db),
        )
        recommendation_cache.get(
            ("new", present),
            lambda: engine.find_new_for_group_games(db, list(present)),
        )
    finally:
        db.close()
