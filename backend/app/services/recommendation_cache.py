from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from threading import RLock

from sqlalchemy import event, insert, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Account, Game, ManualOwnership, Ownership, Participant, PlatformGameMapping, RecommendationCacheRevision
from app.schemas import RecommendationRead


CacheKey = tuple[Hashable, ...]
RELEVANT_MODELS = (Account, Game, ManualOwnership, Ownership, Participant, PlatformGameMapping)


class RecommendationCache:
    def __init__(self, ttl_seconds: float = 3600, max_entries: int = 64) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._lock = RLock()
        self._revision = 0
        self._database_revision: int | None = None
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

    def observe_database_revision(self, revision: int) -> None:
        with self._lock:
            if self._database_revision is None:
                self._database_revision = revision
                return
            if self._database_revision != revision:
                self._database_revision = revision
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

    def etag(
        self,
        key: CacheKey,
        revision: int,
        database_revision: int,
        limit: int | None,
    ) -> str:
        digest = hashlib.sha1(
            repr((key, database_revision, limit)).encode("utf-8")
        ).hexdigest()[:12]
        return f'"recommendations-{revision}-{digest}"'


recommendation_cache = RecommendationCache(
    ttl_seconds=settings.recommendation_cache_entry_ttl_seconds,
    max_entries=settings.recommendation_cache_max_entries,
)


def synchronize_recommendation_cache(db: Session) -> int:
    revision = db.scalar(
        select(RecommendationCacheRevision.revision).where(
            RecommendationCacheRevision.id == 1
        )
    )
    value = int(revision or 0)
    recommendation_cache.observe_database_revision(value)
    return value


@event.listens_for(Session, "after_flush")
def _mark_recommendations_dirty(session: Session, _flush_context) -> None:
    changed = session.new.union(session.dirty).union(session.deleted)
    if any(isinstance(item, RELEVANT_MODELS) for item in changed):
        session.info["recommendations_dirty"] = True


@event.listens_for(Session, "after_commit")
def _invalidate_recommendations_after_commit(session: Session) -> None:
    if session.info.pop("recommendations_dirty", False):
        recommendation_cache.invalidate()
        bind = session.get_bind()
        with bind.begin() as connection:
            result = connection.execute(
                update(RecommendationCacheRevision)
                .where(RecommendationCacheRevision.id == 1)
                .values(revision=RecommendationCacheRevision.revision + 1)
            )
            if result.rowcount == 0:
                connection.execute(
                    insert(RecommendationCacheRevision).values(id=1, revision=1)
                )


@event.listens_for(Session, "after_rollback")
def _clear_recommendations_dirty_marker(session: Session) -> None:
    session.info.pop("recommendations_dirty", None)


def warm_dashboard_recommendations() -> None:
    from app.services import recommendations as engine

    db = SessionLocal()
    try:
        synchronize_recommendation_cache(db)
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
