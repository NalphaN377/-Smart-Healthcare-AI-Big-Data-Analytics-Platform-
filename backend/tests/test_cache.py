from __future__ import annotations

import json
from decimal import Decimal

import pytest

from backend.app import create_app
from backend.app.ai.provider import UnconfiguredProvider
from backend.app.ai.schemas import ConversationTurn
from backend.app.ai.session import RedisConversationStore
from backend.app.cache import AnalyticsCache, CachedAnalyticsRepository, RedisClient
from backend.tests.conftest import FakeAnalyticsRepository


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.fail_get = False
        self.fail_set = False

    def ping(self):
        return True

    def get(self, key):
        if self.fail_get:
            raise ConnectionError("simulated Redis outage")
        return self.values.get(key)

    def setex(self, key, ttl, value):
        if self.fail_set:
            raise ConnectionError("simulated Redis write outage")
        self.values[key] = value
        self.ttls[key] = ttl
        return True

    def expire(self, key, ttl):
        self.ttls[key] = ttl
        return True


def redis_connection(fake: FakeRedis | None = None) -> RedisClient:
    return RedisClient(
        {
            "REDIS_ENABLED": True,
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": 6379,
            "REDIS_DB": 0,
        },
        client=fake or FakeRedis(),
    )


def test_cache_key_is_consistent_for_different_parameter_order():
    first = AnalyticsCache.key_for(
        "diseases_top",
        {"filters": {"year": 2021, "age_group": "70 or Older"}, "limit": 5},
    )
    second = AnalyticsCache.key_for(
        "diseases_top",
        {"limit": 5, "filters": {"age_group": "70 or Older", "year": 2021}},
    )
    assert first == second
    assert first.startswith("medical:analytics:v1:")


def test_cache_miss_then_hit_and_ttl_without_response_change():
    fake = FakeRedis()
    cache = AnalyticsCache(redis_connection(fake), ttl=123)
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return [{"diagnosis": "A", "record_count": 2}]

    first = cache.get_or_compute("diseases_top", {"limit": 5}, compute)
    assert cache.telemetry()["cache_miss"] is True
    second = cache.get_or_compute("diseases_top", {"limit": 5}, compute)
    assert cache.telemetry()["cache_hit"] is True
    assert first == second
    assert calls == 1
    assert set(fake.ttls.values()) == {123}


def test_connected_cache_normalizes_decimal_on_miss_and_hit():
    fake = FakeRedis()
    cache = AnalyticsCache(redis_connection(fake))
    first = cache.get_or_compute("overview", {}, lambda: {"average": Decimal("1.25")})
    second = cache.get_or_compute("overview", {}, lambda: {"average": Decimal("9.99")})
    assert first == second == {"average": 1.25}


def test_cache_disabled_and_unavailable_fall_back_without_failure():
    disabled_client = RedisClient({"REDIS_ENABLED": False})
    disabled_cache = AnalyticsCache(disabled_client)
    assert disabled_cache.get_or_compute("overview", {}, lambda: {"total": 1}) == {
        "total": 1
    }
    assert disabled_cache.telemetry()["cache_disabled"] is True

    failing = FakeRedis()
    failing.fail_get = True
    unavailable_cache = AnalyticsCache(redis_connection(failing))
    assert unavailable_cache.get_or_compute("overview", {}, lambda: {"total": 2}) == {
        "total": 2
    }
    assert unavailable_cache.telemetry()["cache_error"] is True


def test_exceptional_results_are_never_cached():
    fake = FakeRedis()
    cache = AnalyticsCache(redis_connection(fake))

    with pytest.raises(RuntimeError):
        cache.get_or_compute("overview", {}, lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert fake.values == {}


def test_cached_repository_preserves_api_data_and_exposes_telemetry():
    fake = FakeRedis()
    app = create_app(
        {
            "TESTING": True,
            "ANALYTICS_REPOSITORY": FakeAnalyticsRepository(),
            "AI_PROVIDER_INSTANCE": UnconfiguredProvider(),
            "REDIS_CLIENT_INSTANCE": redis_connection(fake),
            "REDIS_CACHE_TTL": 300,
            "CORS_ORIGINS": ["http://localhost:5173"],
        }
    )
    client = app.test_client()
    first = client.get("/api/overview?year=2021").get_json()
    second = client.get("/api/overview?year=2021").get_json()
    assert first["data"] == second["data"]
    assert first["meta"]["cache_miss"] is True
    assert second["meta"]["cache_hit"] is True
    status = client.get("/api/system/cache/status").get_json()
    assert status["data"] == {
        "enabled": True,
        "connected": True,
        "backend": "redis",
        "ttl": 300,
    }
    assert "password" not in json.dumps(status).lower()


def make_turn(index: int) -> ConversationTurn:
    return ConversationTurn(
        query=f"question {index}",
        tool="get_overview",
        arguments={},
        result_summary={"total_records": index},
    )


def test_redis_session_persists_across_store_instances_and_refreshes_ttl():
    fake = FakeRedis()
    connection = redis_connection(fake)
    first_store = RedisConversationStore(connection, max_turns=3, ttl_seconds=600)
    session_id = first_store.create_session()
    first_store.append(session_id, make_turn(1))

    second_store = RedisConversationStore(connection, max_turns=3, ttl_seconds=600)
    history = second_store.history(session_id)
    assert [turn.query for turn in history] == ["question 1"]
    assert fake.ttls[f"medical:ai:session:{session_id}"] == 600


def test_redis_session_enforces_max_turns():
    fake = FakeRedis()
    store = RedisConversationStore(redis_connection(fake), max_turns=3, ttl_seconds=600)
    session_id = store.create_session()
    for index in range(5):
        store.append(session_id, make_turn(index))
    assert [turn.query for turn in store.history(session_id)] == [
        "question 2",
        "question 3",
        "question 4",
    ]


def test_redis_session_failure_falls_back_to_memory():
    fake = FakeRedis()
    connection = redis_connection(fake)
    store = RedisConversationStore(connection, max_turns=3, ttl_seconds=600)
    session_id = store.create_session()
    fake.fail_get = True
    assert store.append(session_id, make_turn(1)) == 1
    assert store.history(session_id)[0].query == "question 1"
