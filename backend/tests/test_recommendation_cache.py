from sqlalchemy import select

from app.models import Participant, RecommendationCacheRevision
from app.services.recommendation_cache import (
    RecommendationCache,
    recommendation_cache,
    synchronize_recommendation_cache,
)


def test_recommendation_cache_reuses_results_until_invalidated():
    cache = RecommendationCache()
    calls = 0

    def factory():
        nonlocal calls
        calls += 1
        return []

    first, first_revision, first_hit = cache.get(("popular",), factory)
    second, second_revision, second_hit = cache.get(("popular",), factory)

    assert first is second
    assert first_revision == second_revision
    assert first_hit is False
    assert second_hit is True
    assert calls == 1

    cache.invalidate()
    _, third_revision, third_hit = cache.get(("popular",), factory)
    assert third_revision > second_revision
    assert third_hit is False
    assert calls == 2


def test_recommendation_cache_is_invalidated_by_relevant_commit(db):
    revision = recommendation_cache.revision

    db.add(Participant(nickname="CacheInvalidation"))
    db.commit()

    assert recommendation_cache.revision > revision


def test_recommendation_cache_detects_revision_from_another_process(db):
    cache = RecommendationCache()
    cache.observe_database_revision(4)
    calls = 0

    def factory():
        nonlocal calls
        calls += 1
        return []

    cache.get(("common",), factory)
    cache.get(("common",), factory)
    cache.observe_database_revision(5)
    cache.get(("common",), factory)

    assert calls == 2


def test_relevant_commit_increments_shared_database_revision(db):
    db.add(RecommendationCacheRevision(id=1, revision=0))
    db.commit()
    synchronize_recommendation_cache(db)
    before = db.scalar(
        select(RecommendationCacheRevision.revision).where(
            RecommendationCacheRevision.id == 1
        )
    )

    db.add(Participant(nickname="SharedRevision"))
    db.commit()

    after = db.scalar(
        select(RecommendationCacheRevision.revision).where(
            RecommendationCacheRevision.id == 1
        )
    )
    assert after == before + 1
