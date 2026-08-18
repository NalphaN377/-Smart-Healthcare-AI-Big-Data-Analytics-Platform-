#!/usr/bin/env python3
"""Measure real MySQL cold computations and Redis aggregate cache hits."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import create_app


CALLS = {
    "overview": lambda repository: repository.overview({}),
    "diseases_top": lambda repository: repository.diseases_top({}, 10),
    "diseases_cost": lambda repository: repository.diseases_cost({}, 10),
    "hospitals_top": lambda repository: repository.hospitals_top({}, 10),
    "hospitals_cost": lambda repository: repository.hospitals_cost({}, 10),
    "age_distribution": lambda repository: repository.age_distribution({}, 10),
    "age_cost": lambda repository: repository.age_cost({}, 10),
    "payment_distribution": lambda repository: repository.payment_distribution({}, 10),
    "severity_distribution": lambda repository: repository.severity_distribution({}, 10),
    "yearly_trends": lambda repository: repository.yearly_trends({}, 20),
}


def timed_call(repository, call):
    started = perf_counter()
    result = call(repository)
    duration_ms = round((perf_counter() - started) * 1000, 2)
    return result, duration_ms, repository.cache_telemetry()


def main() -> int:
    app = create_app()
    repository = app.extensions["analytics_repository"]
    if not app.extensions["redis_client"].connected:
        raise RuntimeError("Redis must be enabled and connected for cache profiling")
    output = {}
    for name, call in CALLS.items():
        first, cold_ms, cold_meta = timed_call(repository, call)
        second, hit_ms, hit_meta = timed_call(repository, call)
        if first != second:
            raise RuntimeError(f"cache changed the {name} response")
        output[name] = {
            "cold_ms": cold_ms,
            "hit_ms": hit_ms,
            "improvement_percent": round((cold_ms - hit_ms) * 100 / cold_ms, 2),
            "cold_cache_miss": cold_meta["cache_miss"],
            "hit_cache_hit": hit_meta["cache_hit"],
        }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
