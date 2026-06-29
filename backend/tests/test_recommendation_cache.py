from app.models import Participant
from app.services.recommendation_cache import RecommendationCache, recommendation_cache


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
