import time

from flask import Blueprint

from ..utils.responses import success_response
from .common import repository
from .params import parse_query_params


blueprint = Blueprint("trends", __name__)


@blueprint.get("/api/trends/year")
def yearly_trends():
    started = time.perf_counter()
    filters, limit = parse_query_params()
    data = repository().yearly_trends(filters, limit)
    trend_available = len(data) > 1
    return success_response(
        data,
        {
            "dimension": "discharge_year",
            "metric": "record_count_and_cost",
            "filters": filters,
            "count": len(data),
            "trend_available": trend_available,
            "note": None if trend_available else "数据仅包含一个或零个年份，无法形成有效年度趋势",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            **getattr(repository(), "cache_telemetry", lambda: {})(),
        },
    )
