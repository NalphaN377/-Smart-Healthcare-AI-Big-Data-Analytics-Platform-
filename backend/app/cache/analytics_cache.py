from __future__ import annotations

import hashlib
import json
import logging
from contextvars import ContextVar
from time import perf_counter
from typing import Any, Callable

from ..utils.responses import to_json_value


logger = logging.getLogger(__name__)


class AnalyticsCache:
    KEY_PREFIX = "medical:analytics:v1"

    def __init__(self, redis_client, ttl: int = 300):
        self.redis_client = redis_client
        self.ttl = max(1, int(ttl))
        self._telemetry: ContextVar[dict[str, Any]] = ContextVar(
            "analytics_cache_telemetry",
            default=self._base_telemetry(cache_disabled=True),
        )

    @staticmethod
    def _base_telemetry(**overrides) -> dict[str, Any]:
        return {
            "cache_hit": False,
            "cache_miss": False,
            "cache_disabled": False,
            "cache_error": False,
            "query_duration_ms": 0.0,
            **overrides,
        }

    @classmethod
    def key_for(cls, operation: str, parameters: dict[str, Any]) -> str:
        canonical = json.dumps(
            {"operation": operation, "parameters": parameters},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"{cls.KEY_PREFIX}:{digest}"

    def get_or_compute(
        self,
        operation: str,
        parameters: dict[str, Any],
        compute: Callable[[], Any],
    ) -> Any:
        started = perf_counter()
        if not self.redis_client.connected:
            result = compute()
            self._set_telemetry(started, cache_disabled=True)
            return result

        key = self.key_for(operation, parameters)
        try:
            cached = self.redis_client.client.get(key)
            if cached is not None:
                result = json.loads(cached)
                self._set_telemetry(started, cache_hit=True)
                return result
        except Exception as error:
            self.redis_client.mark_unavailable(error)
            result = compute()
            self._set_telemetry(started, cache_error=True)
            return result

        result = to_json_value(compute())
        try:
            serialized = json.dumps(
                result,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            self.redis_client.client.setex(key, self.ttl, serialized)
            self._set_telemetry(started, cache_miss=True)
        except Exception as error:
            self.redis_client.mark_unavailable(error)
            self._set_telemetry(started, cache_miss=True, cache_error=True)
        return result

    def telemetry(self) -> dict[str, Any]:
        return dict(self._telemetry.get())

    def status(self) -> dict[str, Any]:
        return self.redis_client.status(self.ttl)

    def _set_telemetry(self, started: float, **flags) -> None:
        self._telemetry.set(
            self._base_telemetry(
                query_duration_ms=round((perf_counter() - started) * 1000, 2),
                **flags,
            )
        )


class CachedAnalyticsRepository:
    """Caches only aggregate repository methods; raw rows never enter Redis."""

    def __init__(self, repository, cache: AnalyticsCache):
        self.repository = repository
        self.cache = cache

    def cache_telemetry(self) -> dict[str, Any]:
        return self.cache.telemetry()

    def cache_status(self) -> dict[str, Any]:
        return self.cache.status()

    def ping(self) -> bool:
        return self.repository.ping()

    def overview(self, filters):
        return self._cached("overview", filters, None, "summary", self.repository.overview)

    def diseases_top(self, filters, limit):
        return self._cached(
            "diseases_top", filters, limit, "record_count", self.repository.diseases_top
        )

    def diseases_cost(self, filters, limit):
        return self._cached(
            "diseases_cost", filters, limit, "average_cost", self.repository.diseases_cost
        )

    def hospitals_top(self, filters, limit):
        return self._cached(
            "hospitals_top", filters, limit, "record_count", self.repository.hospitals_top
        )

    def hospitals_cost(self, filters, limit):
        return self._cached(
            "hospitals_cost", filters, limit, "average_cost", self.repository.hospitals_cost
        )

    def age_distribution(self, filters, limit):
        return self._cached(
            "age_distribution", filters, limit, "record_count", self.repository.age_distribution
        )

    def age_cost(self, filters, limit):
        return self._cached("age_cost", filters, limit, "average_cost", self.repository.age_cost)

    def payment_distribution(self, filters, limit):
        return self._cached(
            "payment_distribution",
            filters,
            limit,
            "record_count",
            self.repository.payment_distribution,
        )

    def severity_distribution(self, filters, limit):
        return self._cached(
            "severity_distribution",
            filters,
            limit,
            "record_count",
            self.repository.severity_distribution,
        )

    def yearly_trends(self, filters, limit):
        return self._cached(
            "yearly_trends",
            filters,
            limit,
            "record_count_and_cost",
            self.repository.yearly_trends,
        )

    def _cached(self, operation, filters, limit, metric, function):
        parameters = {
            "filters": filters,
            "limit": limit,
            "metric": metric,
        }
        arguments = (filters,) if limit is None else (filters, limit)
        return self.cache.get_or_compute(
            operation,
            parameters,
            lambda: function(*arguments),
        )
