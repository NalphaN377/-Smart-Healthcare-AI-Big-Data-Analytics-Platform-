from __future__ import annotations

import time
from typing import Any

from flask import current_app

from ..utils.responses import success_response


def repository():
    return current_app.extensions["analytics_repository"]


def analytics_response(
    data: Any,
    started: float,
    dimension: str,
    metric: str,
    filters: dict[str, Any],
):
    count = len(data) if isinstance(data, list) else (1 if data else 0)
    cache_telemetry = getattr(repository(), "cache_telemetry", lambda: {})()
    return success_response(
        data,
        {
            "dimension": dimension,
            "metric": metric,
            "filters": filters,
            "count": count,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            **cache_telemetry,
        },
    )
